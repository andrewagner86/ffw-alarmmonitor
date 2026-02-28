from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Table, ForeignKey, inspect, text
from sqlalchemy.orm import DeclarativeBase, relationship, Session, sessionmaker
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
import os

# Status-Zyklen abhängig vom Alarm-Status
ZYKLUS_MIT_ALARM    = ["einsatzbereit", "alarmiert", "bereitschaft", "nicht_einsatzbereit"]
ZYKLUS_OHNE_ALARM   = ["einsatzbereit", "nicht_einsatzbereit"]

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://feuerwehr:feuerwehr123@localhost:5432/feuerwehr")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

fahrzeug_schlagwort = Table(
    "fahrzeug_schlagwort", Base.metadata,
    Column("fahrzeug_id", Integer, ForeignKey("fahrzeuge.id", ondelete="CASCADE"), primary_key=True),
    Column("schlagwort_id", Integer, ForeignKey("schlagworte.id", ondelete="CASCADE"), primary_key=True),
)

fahrzeug_ersatz = Table(
    "fahrzeug_ersatz", Base.metadata,
    Column("fahrzeug_id",  Integer, ForeignKey("fahrzeuge.id", ondelete="CASCADE"), primary_key=True),
    Column("ersatz_id",    Integer, ForeignKey("fahrzeuge.id", ondelete="CASCADE"), primary_key=True),
)

class FahrzeugGruppe(Base):
    __tablename__ = "fahrzeug_gruppen"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    position = Column(Integer, default=0, nullable=False)
    fahrzeuge = relationship("Fahrzeug", back_populates="gruppe")

class Fahrzeug(Base):
    __tablename__ = "fahrzeuge"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    kennzeichen = Column(String(20), nullable=True)
    funkkennung = Column(String(50), nullable=True)
    typ = Column(String(50), nullable=False)
    # Neues Status-Feld ersetzt einsatzfaehig
    status = Column(String(30), default="einsatzbereit", nullable=False)
    position = Column(Integer, default=0, nullable=False)
    gruppe_id = Column(Integer, ForeignKey("fahrzeug_gruppen.id", ondelete="SET NULL"), nullable=True)
    gruppe = relationship("FahrzeugGruppe", back_populates="fahrzeuge")
    schlagworte = relationship("Schlagwort", secondary=fahrzeug_schlagwort, back_populates="fahrzeuge")
    ersatzfahrzeuge = relationship(
        "Fahrzeug", secondary=fahrzeug_ersatz,
        primaryjoin="Fahrzeug.id == fahrzeug_ersatz.c.fahrzeug_id",
        secondaryjoin="Fahrzeug.id == fahrzeug_ersatz.c.ersatz_id",
    )

class Schlagwort(Base):
    __tablename__ = "schlagworte"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    beschreibung = Column(String(255))
    fahrzeuge = relationship("Fahrzeug", secondary=fahrzeug_schlagwort, back_populates="schlagworte")

class AktivAlarm(Base):
    __tablename__ = "aktiv_alarme"
    id = Column(Integer, primary_key=True)
    schlagwort_id = Column(Integer, ForeignKey("schlagworte.id", ondelete="SET NULL"), nullable=True)
    schlagwort = relationship("Schlagwort")
    erstellt_am = Column(DateTime, default=datetime.utcnow)
    aktiv = Column(Boolean, default=True, nullable=False)

Base.metadata.create_all(bind=engine)

def migrate():
    inspector = inspect(engine)
    with engine.connect() as conn:
        existing = [c["name"] for c in inspector.get_columns("fahrzeuge")]
        if "funkkennung" not in existing:
            conn.execute(text("ALTER TABLE fahrzeuge ADD COLUMN funkkennung VARCHAR(50)"))
        if "gruppe_id" not in existing:
            conn.execute(text("ALTER TABLE fahrzeuge ADD COLUMN gruppe_id INTEGER REFERENCES fahrzeug_gruppen(id) ON DELETE SET NULL"))
        if "position" not in existing:
            conn.execute(text("ALTER TABLE fahrzeuge ADD COLUMN position INTEGER NOT NULL DEFAULT 0"))
        if "status" not in existing:
            # Migriere einsatzfaehig → status
            conn.execute(text("ALTER TABLE fahrzeuge ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'einsatzbereit'"))
            if "einsatzfaehig" in existing:
                conn.execute(text("UPDATE fahrzeuge SET status = 'nicht_einsatzbereit' WHERE einsatzfaehig = false"))
        existing_g = [c["name"] for c in inspector.get_columns("fahrzeug_gruppen")]
        if "position" not in existing_g:
            conn.execute(text("ALTER TABLE fahrzeug_gruppen ADD COLUMN position INTEGER NOT NULL DEFAULT 0"))
        # Sicherstellen dass kennzeichen nullable ist
        try:
            conn.execute(text("ALTER TABLE fahrzeuge ALTER COLUMN kennzeichen DROP NOT NULL"))
        except Exception:
            pass
        conn.commit()

migrate()

app = FastAPI(title="Feuerwehr")
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def fahrzeuge_sortiert(db: Session):
    return db.query(Fahrzeug).order_by(Fahrzeug.gruppe_id.nullslast(), Fahrzeug.position, Fahrzeug.name).all()

def gruppen_sortiert(db: Session):
    return db.query(FahrzeugGruppe).order_by(FahrzeugGruppe.position, FahrzeugGruppe.name).all()

def aktiver_alarm(db: Session) -> Optional[AktivAlarm]:
    return db.query(AktivAlarm).filter(AktivAlarm.aktiv == True).order_by(AktivAlarm.id.desc()).first()

# ─── Hauptansicht ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    alarm = aktiver_alarm(db)
    # Aktiven Alarm wiederherstellen → direkt zur Alarmansicht weiterleiten
    if alarm and alarm.schlagwort_id:
        return RedirectResponse(f"/alarm/{alarm.schlagwort_id}", status_code=302)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "schlagworte": db.query(Schlagwort).order_by(Schlagwort.name).all(),
        "alle_fahrzeuge": fahrzeuge_sortiert(db),
        "gruppen": gruppen_sortiert(db),
        "aktiver_alarm": alarm,
        "schlagwort_fahrzeug_ids": set(),
        "warnungen": [],
    })

@app.get("/alarm/{schlagwort_id}", response_class=HTMLResponse)
def alarm_view(schlagwort_id: int, request: Request, db: Session = Depends(get_db)):
    schlagwort = db.get(Schlagwort, schlagwort_id)
    if not schlagwort:
        raise HTTPException(status_code=404)

    alarm = aktiver_alarm(db)
    if alarm and alarm.schlagwort_id != schlagwort_id:
        # Anderer Alarm bereits aktiv → abweisen
        return RedirectResponse(f"/alarm/{alarm.schlagwort_id}", status_code=302)

    warnungen = []

    if not alarm:
        alarm = AktivAlarm(schlagwort_id=schlagwort_id, aktiv=True)
        db.add(alarm)

        for f in schlagwort.fahrzeuge:
            if f.status == "einsatzbereit":
                f.status = "alarmiert"
            elif f.status == "nicht_einsatzbereit":
                # Ersatzfahrzeug suchen
                ersatz_gefunden = False
                for ersatz in f.ersatzfahrzeuge:
                    if ersatz.status == "einsatzbereit":
                        ersatz.status = "alarmiert"
                        ersatz_gefunden = True
                        break
                if not ersatz_gefunden:
                    if f.ersatzfahrzeuge:
                        warnungen.append({
                            "fahrzeug": f.name,
                            "grund": "Fahrzeug und alle Ersatzfahrzeuge nicht einsatzbereit",
                        })
                    else:
                        warnungen.append({
                            "fahrzeug": f.name,
                            "grund": "Fahrzeug nicht einsatzbereit, keine Ersatzfahrzeuge hinterlegt",
                        })

        db.commit()
        db.refresh(alarm)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "schlagworte": db.query(Schlagwort).order_by(Schlagwort.name).all(),
        "alle_fahrzeuge": fahrzeuge_sortiert(db),
        "gruppen": gruppen_sortiert(db),
        "aktives_schlagwort": schlagwort,
        "aktiver_alarm": alarm,
        "schlagwort_fahrzeug_ids": {f.id for f in schlagwort.fahrzeuge},
        "warnungen": warnungen,
    })

def _alarm_beenden_intern(db: Session):
    """Aktiven Alarm beenden und alle alarmiert/bereitschaft zurücksetzen."""
    alarm = aktiver_alarm(db)
    if alarm:
        alarm.aktiv = False
    # Alle Fahrzeuge mit grün/gelb → zurück auf einsatzbereit
    db.query(Fahrzeug).filter(
        Fahrzeug.status.in_(["alarmiert", "bereitschaft"])
    ).update({"status": "einsatzbereit"}, synchronize_session=False)
    db.commit()

# ─── Einsatzübersicht ─────────────────────────────────────────────────────────

@app.get("/einsatz", response_class=HTMLResponse)
def einsatz(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("einsatz.html", {"request": request})

@app.get("/api/einsatz", response_class=JSONResponse)
def einsatz_api(db: Session = Depends(get_db)):
    alarm = aktiver_alarm(db)
    if not alarm:
        return {"alarm": None}

    gruppen = gruppen_sortiert(db)
    alle_fzg = fahrzeuge_sortiert(db)
    # Nur alarmiert + bereitschaft anzeigen
    einsatz_fzg = [f for f in alle_fzg if f.status in ("alarmiert", "bereitschaft")]

    gruppen_data = []
    for gruppe in gruppen:
        fzg = [f for f in einsatz_fzg if f.gruppe_id == gruppe.id]
        if fzg:
            gruppen_data.append({"gruppe": gruppe.name, "fahrzeuge": [_fzg_dict(f) for f in fzg]})

    ohne = [f for f in einsatz_fzg if f.gruppe_id is None]
    if ohne:
        gruppen_data.append({"gruppe": None, "fahrzeuge": [_fzg_dict(f) for f in ohne]})

    return {
        "alarm": {
            "schlagwort": alarm.schlagwort.name if alarm.schlagwort else None,
            "beschreibung": alarm.schlagwort.beschreibung if alarm.schlagwort else None,
            "erstellt_am": alarm.erstellt_am.strftime("%H:%M Uhr") if alarm.erstellt_am else None,
        },
        "gruppen": gruppen_data,
        "gesamt": len(einsatz_fzg),
    }

def _fzg_dict(f: Fahrzeug) -> dict:
    return {
        "id": f.id, "name": f.name,
        "kennzeichen": f.kennzeichen, "funkkennung": f.funkkennung,
        "status": f.status,
    }

# ─── API: Fahrzeug-Status wechseln ────────────────────────────────────────────

class StatusPayload(BaseModel):
    fahrzeug_id: int

@app.post("/api/fahrzeug/status-toggle")
def fahrzeug_status_toggle(payload: StatusPayload, db: Session = Depends(get_db)):
    fzg = db.get(Fahrzeug, payload.fahrzeug_id)
    if not fzg:
        raise HTTPException(status_code=404)
    alarm = aktiver_alarm(db)
    zyklus = ZYKLUS_MIT_ALARM if alarm else ZYKLUS_OHNE_ALARM
    # Falls aktueller Status nicht im Zyklus ist (z.B. alarmiert ohne Alarm) → einsatzbereit
    idx = zyklus.index(fzg.status) if fzg.status in zyklus else 0
    fzg.status = zyklus[(idx + 1) % len(zyklus)]
    db.commit()
    return {"status": fzg.status}

@app.post("/api/alarm/beenden")
def alarm_beenden(db: Session = Depends(get_db)):
    _alarm_beenden_intern(db)
    return RedirectResponse("/", status_code=303)

# ─── API: Reihenfolge ─────────────────────────────────────────────────────────

class ReihenfolgeItem(BaseModel):
    id: int
    position: int

@app.post("/api/fahrzeug/reihenfolge")
def reihenfolge_speichern(items: list[ReihenfolgeItem], db: Session = Depends(get_db)):
    for item in items:
        f = db.get(Fahrzeug, item.id)
        if f:
            f.position = item.position
    db.commit()
    return JSONResponse({"ok": True})

@app.post("/api/gruppe/{gid}/move")
def gruppe_move(gid: int, direction: str = "up", db: Session = Depends(get_db)):
    gruppen = db.query(FahrzeugGruppe).order_by(FahrzeugGruppe.position, FahrzeugGruppe.name).all()
    for i, g in enumerate(gruppen):
        g.position = i
    db.flush()
    idx = next((i for i, g in enumerate(gruppen) if g.id == gid), None)
    if idx is None:
        raise HTTPException(status_code=404)
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap_idx < len(gruppen):
        gruppen[idx].position, gruppen[swap_idx].position = gruppen[swap_idx].position, gruppen[idx].position
    db.commit()
    return JSONResponse({"ok": True})

# ─── Admin: Fahrzeuge ─────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "fahrzeuge": fahrzeuge_sortiert(db),
        "schlagworte": db.query(Schlagwort).order_by(Schlagwort.name).all(),
        "gruppen": gruppen_sortiert(db),
        "tab": "fahrzeuge"
    })

@app.post("/admin/fahrzeug/neu")
def fahrzeug_neu(
    name: str = Form(...), kennzeichen: str = Form(""), funkkennung: str = Form(""),
    typ: str = Form(...), gruppe_id: Optional[int] = Form(None),
    ersatz_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db)
):
    existing = db.query(Fahrzeug).filter(Fahrzeug.gruppe_id == gruppe_id).count()
    f = Fahrzeug(name=name, kennzeichen=kennzeichen or None, funkkennung=funkkennung or None,
                 typ=typ, status="einsatzbereit", gruppe_id=gruppe_id, position=existing)
    f.ersatzfahrzeuge = db.query(Fahrzeug).filter(Fahrzeug.id.in_(ersatz_ids)).all()
    db.add(f)
    db.commit()
    return RedirectResponse("/admin", status_code=303)

@app.post("/admin/fahrzeug/{fid}/bearbeiten")
def fahrzeug_bearbeiten(
    fid: int, name: str = Form(...), kennzeichen: str = Form(""), funkkennung: str = Form(""),
    typ: str = Form(...), gruppe_id: Optional[int] = Form(None),
    ersatz_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db)
):
    f = db.get(Fahrzeug, fid)
    if not f:
        raise HTTPException(status_code=404)
    f.name = name
    f.kennzeichen = kennzeichen or None
    f.funkkennung = funkkennung or None
    f.typ = typ
    f.gruppe_id = gruppe_id
    f.ersatzfahrzeuge = db.query(Fahrzeug).filter(Fahrzeug.id.in_(ersatz_ids)).all()
    db.commit()
    return RedirectResponse("/admin", status_code=303)

@app.post("/admin/fahrzeug/{fid}/loeschen")
def fahrzeug_loeschen(fid: int, db: Session = Depends(get_db)):
    f = db.get(Fahrzeug, fid)
    if f:
        db.delete(f)
        db.commit()
    return RedirectResponse("/admin", status_code=303)

# ─── Admin: Gruppen ───────────────────────────────────────────────────────────

@app.get("/admin/gruppen", response_class=HTMLResponse)
def admin_gruppen(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "fahrzeuge": fahrzeuge_sortiert(db),
        "schlagworte": db.query(Schlagwort).order_by(Schlagwort.name).all(),
        "gruppen": gruppen_sortiert(db),
        "tab": "gruppen"
    })

@app.post("/admin/gruppe/neu")
def gruppe_neu(name: str = Form(...), db: Session = Depends(get_db)):
    db.add(FahrzeugGruppe(name=name))
    db.commit()
    return RedirectResponse("/admin/gruppen", status_code=303)

@app.post("/admin/gruppe/{gid}/bearbeiten")
def gruppe_bearbeiten(gid: int, name: str = Form(...), db: Session = Depends(get_db)):
    g = db.get(FahrzeugGruppe, gid)
    if not g:
        raise HTTPException(status_code=404)
    g.name = name
    db.commit()
    return RedirectResponse("/admin/gruppen", status_code=303)

@app.post("/admin/gruppe/{gid}/loeschen")
def gruppe_loeschen(gid: int, db: Session = Depends(get_db)):
    g = db.get(FahrzeugGruppe, gid)
    if g:
        db.delete(g)
        db.commit()
    return RedirectResponse("/admin/gruppen", status_code=303)

# ─── Admin: Schlagworte ───────────────────────────────────────────────────────

@app.get("/admin/schlagworte", response_class=HTMLResponse)
def admin_schlagworte(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "fahrzeuge": fahrzeuge_sortiert(db),
        "schlagworte": db.query(Schlagwort).order_by(Schlagwort.name).all(),
        "gruppen": gruppen_sortiert(db),
        "tab": "schlagworte"
    })

@app.post("/admin/schlagwort/neu")
def schlagwort_neu(
    name: str = Form(...), beschreibung: str = Form(""),
    fahrzeug_ids: list[int] = Form(default=[]), db: Session = Depends(get_db)
):
    s = Schlagwort(name=name, beschreibung=beschreibung)
    s.fahrzeuge = db.query(Fahrzeug).filter(Fahrzeug.id.in_(fahrzeug_ids)).all()
    db.add(s)
    db.commit()
    return RedirectResponse("/admin/schlagworte", status_code=303)

@app.post("/admin/schlagwort/{sid}/bearbeiten")
def schlagwort_bearbeiten(
    sid: int, name: str = Form(...), beschreibung: str = Form(""),
    fahrzeug_ids: list[int] = Form(default=[]), db: Session = Depends(get_db)
):
    s = db.get(Schlagwort, sid)
    if not s:
        raise HTTPException(status_code=404)
    s.name = name
    s.beschreibung = beschreibung
    s.fahrzeuge = db.query(Fahrzeug).filter(Fahrzeug.id.in_(fahrzeug_ids)).all()
    db.commit()
    return RedirectResponse("/admin/schlagworte", status_code=303)

@app.post("/admin/schlagwort/{sid}/loeschen")
def schlagwort_loeschen(sid: int, db: Session = Depends(get_db)):
    s = db.get(Schlagwort, sid)
    if s:
        db.delete(s)
        db.commit()
    return RedirectResponse("/admin/schlagworte", status_code=303)