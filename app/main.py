from fastapi import FastAPI, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Table, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, relationship, Session, sessionmaker
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
import os
import json

ZYKLUS_MIT_ALARM  = ["einsatzbereit", "alarmiert", "bereitschaft", "nicht_einsatzbereit"]
ZYKLUS_OHNE_ALARM = ["einsatzbereit", "nicht_einsatzbereit"]

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://feuerwehr:feuerwehr123@localhost:5432/feuerwehr")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


# ─── Assoziationstabellen ─────────────────────────────────────────────────────

class AlarmierungsplanFahrzeug(Base):
    __tablename__ = "alarmierungsplan_fahrzeuge"
    alarmierungsplan_id = Column(Integer, ForeignKey("einsatzplaene.id", ondelete="CASCADE"), primary_key=True)
    fahrzeug_id         = Column(Integer, ForeignKey("fahrzeuge.id",     ondelete="CASCADE"), primary_key=True)
    ziel_status         = Column(String(30), default="alarmiert", nullable=False)
    fahrzeug            = relationship("Fahrzeug", lazy="joined")

fahrzeug_ersatz = Table(
    "fahrzeug_ersatz", Base.metadata,
    Column("fahrzeug_id", Integer, ForeignKey("fahrzeuge.id", ondelete="CASCADE"), primary_key=True),
    Column("ersatz_id",   Integer, ForeignKey("fahrzeuge.id", ondelete="CASCADE"), primary_key=True),
)


# ─── Modelle ──────────────────────────────────────────────────────────────────

class FahrzeugGruppe(Base):
    __tablename__ = "fahrzeug_gruppen"
    id       = Column(Integer, primary_key=True)
    name     = Column(String(100), nullable=False, unique=True)
    position = Column(Integer, default=0, nullable=False)
    fahrzeuge = relationship("Fahrzeug", back_populates="gruppe")


class Territorium(Base):
    __tablename__ = "territorien"
    id           = Column(Integer, primary_key=True)
    name         = Column(String(100), nullable=False, unique=True)
    beschreibung = Column(String(255), nullable=True)


class Fahrzeug(Base):
    __tablename__ = "fahrzeuge"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(100), nullable=False)
    kennzeichen = Column(String(20),  nullable=True)
    funkkennung = Column(String(50),  nullable=True)
    typ         = Column(String(50),  nullable=False)
    status      = Column(String(30),  default="einsatzbereit", nullable=False)
    position    = Column(Integer,     default=0, nullable=False)
    gruppe_id   = Column(Integer, ForeignKey("fahrzeug_gruppen.id", ondelete="SET NULL"), nullable=True)
    gruppe             = relationship("FahrzeugGruppe", back_populates="fahrzeuge")
    ersatzfahrzeuge    = relationship(
        "Fahrzeug", secondary=fahrzeug_ersatz,
        primaryjoin="Fahrzeug.id == fahrzeug_ersatz.c.fahrzeug_id",
        secondaryjoin="Fahrzeug.id == fahrzeug_ersatz.c.ersatz_id",
    )


class Alarmierungstyp(Base):
    __tablename__ = "alarmierungstypen"
    id           = Column(Integer, primary_key=True)
    name         = Column(String(100), nullable=False, unique=True)
    beschreibung = Column(String(255), nullable=True)
    alarmierungsstichworte = relationship("Alarmierungsstichwort", back_populates="alarmierungstyp", cascade="all, delete-orphan")


class Alarmierungsstichwort(Base):
    __tablename__ = "alarmierungsstichworte"
    id                 = Column(Integer, primary_key=True)
    text               = Column(String(200), nullable=False)
    alarmierungstyp_id = Column(Integer, ForeignKey("alarmierungstypen.id", ondelete="CASCADE"), nullable=False)
    alarmierungstyp    = relationship("Alarmierungstyp", back_populates="alarmierungsstichworte")


class Alarmierungsplan(Base):
    __tablename__ = "einsatzplaene"
    id                    = Column(Integer, primary_key=True)
    alarmierungstyp_id    = Column(Integer, ForeignKey("alarmierungstypen.id", ondelete="CASCADE"), nullable=False)
    stichwort_id          = Column(Integer, ForeignKey("alarmierungsstichworte.id", ondelete="RESTRICT"), nullable=True)
    territorium_id        = Column(Integer, ForeignKey("territorien.id", ondelete="CASCADE"), nullable=False)
    ist_standard          = Column(Boolean, default=False, nullable=False)
    __table_args__        = (UniqueConstraint("alarmierungstyp_id", "stichwort_id", "territorium_id", name="uq_alarmierungsplan"),)
    alarmierungstyp       = relationship("Alarmierungstyp")
    stichwort             = relationship("Alarmierungsstichwort")
    territorium           = relationship("Territorium")
    plan_fahrzeuge        = relationship("AlarmierungsplanFahrzeug", cascade="all, delete-orphan")


class AktivAlarm(Base):
    __tablename__ = "aktiv_alarme"
    id                 = Column(Integer, primary_key=True)
    alarmierungstyp_id = Column(Integer, ForeignKey("alarmierungstypen.id", ondelete="SET NULL"), nullable=True)
    stichwort_id       = Column(Integer, ForeignKey("alarmierungsstichworte.id", ondelete="SET NULL"), nullable=True)
    territorium_id     = Column(Integer, ForeignKey("territorien.id", ondelete="SET NULL"), nullable=True)
    alarmierungstyp    = relationship("Alarmierungstyp")
    stichwort          = relationship("Alarmierungsstichwort")
    territorium        = relationship("Territorium")
    warnungen_json     = Column(String, nullable=True)
    erstellt_am        = Column(DateTime, default=datetime.utcnow)
    aktiv              = Column(Boolean, default=True, nullable=False)


# ─── Datenbank initialisieren ─────────────────────────────────────────────────

Base.metadata.create_all(bind=engine)

# Bestehende DBs: ziel_status-Spalte nachrüsten falls noch nicht vorhanden
try:
    with engine.connect() as conn:
        conn.execute(__import__("sqlalchemy").text(
            "ALTER TABLE alarmierungsplan_fahrzeuge ADD COLUMN ziel_status VARCHAR(30) NOT NULL DEFAULT 'alarmiert'"
        ))
        conn.commit()
except Exception:
    pass  # Spalte existiert bereits

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="FFW Alarmmonitor")
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


def admin_context(db: Session, tab: str) -> dict:
    return {
        "fahrzeuge":         fahrzeuge_sortiert(db),
        "alarmierungstypen": db.query(Alarmierungstyp).order_by(Alarmierungstyp.name).all(),
        "gruppen":           gruppen_sortiert(db),
        "territorien":       db.query(Territorium).order_by(Territorium.name).all(),
        "einsatzplaene":     db.query(Alarmierungsplan).order_by(Alarmierungsplan.alarmierungstyp_id, Alarmierungsplan.id).all(),
        "tab":               tab,
    }


# ─── Hauptansicht ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    alarm = aktiver_alarm(db)
    if alarm and alarm.alarmierungstyp_id:
        return RedirectResponse(f"/alarm/{alarm.alarmierungstyp_id}", status_code=302)
    return templates.TemplateResponse("index.html", {
        "request":                      request,
        "alarmierungstypen":            db.query(Alarmierungstyp).order_by(Alarmierungstyp.name).all(),
        "alle_fahrzeuge":               fahrzeuge_sortiert(db),
        "gruppen":                      gruppen_sortiert(db),
        "aktiver_alarm":                alarm,
        "warnungen":                    [],
    })


@app.get("/alarm/{alarmierungstyp_id}", response_class=HTMLResponse)
def alarm_view(alarmierungstyp_id: int, request: Request, db: Session = Depends(get_db)):
    alarmierungstyp = db.get(Alarmierungstyp, alarmierungstyp_id)
    if not alarmierungstyp:
        raise HTTPException(status_code=404)

    alarm = aktiver_alarm(db)
    if alarm and alarm.alarmierungstyp_id != alarmierungstyp_id:
        return RedirectResponse(f"/alarm/{alarm.alarmierungstyp_id}", status_code=302)

    return templates.TemplateResponse("index.html", {
        "request":                 request,
        "alarmierungstypen":       db.query(Alarmierungstyp).order_by(Alarmierungstyp.name).all(),
        "alle_fahrzeuge":          fahrzeuge_sortiert(db),
        "gruppen":                 gruppen_sortiert(db),
        "aktiver_alarmierungstyp": alarmierungstyp,
        "aktiver_alarm":           alarm,
        "warnungen":               json.loads(alarm.warnungen_json) if alarm and alarm.warnungen_json else [],
    })


@app.get("/api/alarmierungstyp/{atid}/einsatzplaene", response_class=JSONResponse)
def get_einsatzplaene(atid: int, db: Session = Depends(get_db)):
    plaene = db.query(Alarmierungsplan).filter(
        Alarmierungsplan.alarmierungstyp_id == atid
    ).order_by(Alarmierungsplan.id).all()
    return [
        {
            "id": ep.id,
            "ist_standard": ep.ist_standard,
            "territorium": {"id": ep.territorium.id, "name": ep.territorium.name} if ep.territorium else None,
            "stichwort": {"id": ep.stichwort.id, "text": ep.stichwort.text} if ep.stichwort else None,
            "fahrzeuge": _effektive_fahrzeuge(ep.plan_fahrzeuge),
            "warnungen": _warnungen_vorschau(ep.plan_fahrzeuge),
        }
        for ep in plaene
    ]


class AlarmStartenPayload(BaseModel):
    alarmierungstyp_id: int
    alarmierungsplan_id: int

def _effektive_fahrzeuge(plan_fahrzeuge) -> list:
    """Gibt die tatsächlich zu alarmierenden Fahrzeuge zurück (Ersatz bei nicht_einsatzbereit)."""
    alarm_ids = {pf.fahrzeug.id for pf in plan_fahrzeuge}
    verwendete_ersatz_ids: set = set()
    result = []
    for pf in plan_fahrzeuge:
        f = pf.fahrzeug
        ziel = pf.ziel_status
        if f.status == "einsatzbereit":
            result.append({"id": f.id, "name": f.name, "ziel_status": ziel, "ersatz_fuer": None})
        else:
            ersatz = next(
                (e for e in f.ersatzfahrzeuge
                 if e.status == "einsatzbereit"
                 and e.id not in alarm_ids
                 and e.id not in verwendete_ersatz_ids),
                None
            )
            if ersatz:
                verwendete_ersatz_ids.add(ersatz.id)
                result.append({"id": ersatz.id, "name": ersatz.name, "ziel_status": ziel, "ersatz_fuer": f.name})
    return result


def _warnungen_vorschau(plan_fahrzeuge) -> list:
    """Simuliert Alarmierung ohne DB-Änderungen. Gibt voraussichtliche Warnungen zurück."""
    alarm_ids = {pf.fahrzeug.id for pf in plan_fahrzeuge}
    verwendete_ersatz_ids: set = set()
    warnungen = []
    nicht_verfuegbar = []
    for pf in plan_fahrzeuge:
        f = pf.fahrzeug
        if f.status != "einsatzbereit":
            ersatz = next(
                (e for e in f.ersatzfahrzeuge
                 if e.status == "einsatzbereit"
                 and e.id not in alarm_ids
                 and e.id not in verwendete_ersatz_ids),
                None
            )
            if ersatz:
                verwendete_ersatz_ids.add(ersatz.id)
            else:
                nicht_verfuegbar.append(f.name)
    if nicht_verfuegbar:
        warnungen.append({
            "fahrzeug": ", ".join(nicht_verfuegbar),
            "grund": "Nicht einsatzbereit – kein Ersatzfahrzeug verfügbar",
        })
    return warnungen


def _fahrzeuge_alarmieren(plan_fahrzeuge) -> list:
    """Alarmiert Fahrzeuge, nutzt Ersatz bei nicht_einsatzbereit. Gibt Warnungen zurück."""
    alarm_ids = {pf.fahrzeug.id for pf in plan_fahrzeuge}
    verwendete_ersatz_ids: set = set()
    warnungen = []
    nicht_verfuegbar = []
    for pf in plan_fahrzeuge:
        f = pf.fahrzeug
        ziel = pf.ziel_status
        if f.status == "einsatzbereit":
            f.status = ziel
        else:
            ersatz = next(
                (e for e in f.ersatzfahrzeuge
                 if e.status == "einsatzbereit"
                 and e.id not in alarm_ids
                 and e.id not in verwendete_ersatz_ids),
                None
            )
            if ersatz:
                verwendete_ersatz_ids.add(ersatz.id)
                ersatz.status = ziel
            else:
                nicht_verfuegbar.append(f.name)
    if nicht_verfuegbar:
        warnungen.append({
            "fahrzeug": ", ".join(nicht_verfuegbar),
            "grund": "Nicht einsatzbereit – kein Ersatzfahrzeug verfügbar",
        })
    return warnungen


@app.post("/api/alarm/starten")
def alarm_starten(payload: AlarmStartenPayload, db: Session = Depends(get_db)):
    alarm = aktiver_alarm(db)
    if alarm:
        raise HTTPException(status_code=409, detail="Alarm bereits aktiv")

    ep = db.get(Alarmierungsplan, payload.alarmierungsplan_id)
    if not ep or ep.alarmierungstyp_id != payload.alarmierungstyp_id:
        raise HTTPException(status_code=404)

    warnungen = _fahrzeuge_alarmieren(ep.plan_fahrzeuge)

    alarm = AktivAlarm(
        alarmierungstyp_id=payload.alarmierungstyp_id,
        stichwort_id=ep.stichwort_id,
        territorium_id=ep.territorium_id,
        warnungen_json=json.dumps(warnungen, ensure_ascii=False) if warnungen else None,
        aktiv=True,
    )
    db.add(alarm)
    db.commit()
    return {"ok": True, "alarmierungstyp_id": payload.alarmierungstyp_id, "warnungen": warnungen}


def _alarm_beenden_intern(db: Session):
    alarm = aktiver_alarm(db)
    if alarm:
        alarm.aktiv = False
    db.query(Fahrzeug).filter(
        Fahrzeug.status.in_(["alarmiert", "bereitschaft"])
    ).update({"status": "einsatzbereit"}, synchronize_session=False)
    db.commit()


# ─── Einsatzübersicht ─────────────────────────────────────────────────────────

@app.get("/einsatz", response_class=HTMLResponse)
def einsatz(request: Request):
    return templates.TemplateResponse("einsatz.html", {"request": request})


@app.get("/api/einsatz", response_class=JSONResponse)
def einsatz_api(db: Session = Depends(get_db)):
    alarm = aktiver_alarm(db)
    if not alarm:
        return {"alarm": None}

    alle_fzg    = fahrzeuge_sortiert(db)
    einsatz_fzg = [f for f in alle_fzg if f.status in ("alarmiert", "bereitschaft")]

    gruppen_data = []
    for gruppe in gruppen_sortiert(db):
        fzg = [f for f in einsatz_fzg if f.gruppe_id == gruppe.id]
        if fzg:
            gruppen_data.append({"gruppe": gruppe.name, "fahrzeuge": [_fzg_dict(f) for f in fzg]})

    ohne = [f for f in einsatz_fzg if f.gruppe_id is None]
    if ohne:
        gruppen_data.append({"gruppe": None, "fahrzeuge": [_fzg_dict(f) for f in ohne]})

    return {
        "alarm": {
            "alarmierungstyp": alarm.alarmierungstyp.name        if alarm.alarmierungstyp else None,
            "beschreibung":    alarm.alarmierungstyp.beschreibung if alarm.alarmierungstyp else None,
            "stichwort":       alarm.stichwort.text               if alarm.stichwort       else None,
            "territorium":     alarm.territorium.name             if alarm.territorium     else None,
            "erstellt_am":     alarm.erstellt_am.strftime("%H:%M Uhr") if alarm.erstellt_am else None,
        },
        "gruppen": gruppen_data,
        "gesamt":  len(einsatz_fzg),
        "warnungen": json.loads(alarm.warnungen_json) if alarm.warnungen_json else [],
    }


def _fzg_dict(f: Fahrzeug) -> dict:
    return {"id": f.id, "name": f.name, "kennzeichen": f.kennzeichen, "funkkennung": f.funkkennung, "status": f.status}


# ─── API: Fahrzeug-Status ─────────────────────────────────────────────────────

class StatusPayload(BaseModel):
    fahrzeug_id: int

@app.post("/api/fahrzeug/status-toggle")
def fahrzeug_status_toggle(payload: StatusPayload, db: Session = Depends(get_db)):
    fzg = db.get(Fahrzeug, payload.fahrzeug_id)
    if not fzg:
        raise HTTPException(status_code=404)
    zyklus = ZYKLUS_MIT_ALARM if aktiver_alarm(db) else ZYKLUS_OHNE_ALARM
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
    swap = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap < len(gruppen):
        gruppen[idx].position, gruppen[swap].position = gruppen[swap].position, gruppen[idx].position
    db.commit()
    return JSONResponse({"ok": True})


# ─── Admin: Fahrzeuge ─────────────────────────────────────────────────────────

# ─── Admin: Datenverwaltung ───────────────────────────────────────────────────

@app.get("/admin/datenverwaltung", response_class=HTMLResponse)
def admin_datenverwaltung(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("admin.html", {"request": request, **admin_context(db, "datenverwaltung")})


@app.get("/admin/datenverwaltung/export")
def datenverwaltung_export(db: Session = Depends(get_db)):
    gruppen = db.query(FahrzeugGruppe).order_by(FahrzeugGruppe.position, FahrzeugGruppe.name).all()
    territorien = db.query(Territorium).order_by(Territorium.name).all()
    fahrzeuge = fahrzeuge_sortiert(db)
    alarmierungstypen = db.query(Alarmierungstyp).order_by(Alarmierungstyp.name).all()
    plaene = db.query(Alarmierungsplan).all()

    data = {
        "version": 1,
        "gruppen": [{"id": g.id, "name": g.name, "position": g.position} for g in gruppen],
        "territorien": [{"id": t.id, "name": t.name, "beschreibung": t.beschreibung} for t in territorien],
        "fahrzeuge": [
            {
                "id": f.id, "name": f.name, "kennzeichen": f.kennzeichen,
                "funkkennung": f.funkkennung, "typ": f.typ, "status": f.status,
                "position": f.position, "gruppe_id": f.gruppe_id,
                "ersatz_ids": [e.id for e in f.ersatzfahrzeuge],
            }
            for f in fahrzeuge
        ],
        "alarmierungstypen": [
            {
                "id": at.id, "name": at.name, "beschreibung": at.beschreibung,
                "stichworte": [{"id": s.id, "text": s.text} for s in at.alarmierungsstichworte],
            }
            for at in alarmierungstypen
        ],
        "alarmierungsplaene": [
            {
                "id": ep.id,
                "alarmierungstyp_id": ep.alarmierungstyp_id,
                "stichwort_id": ep.stichwort_id,
                "territorium_id": ep.territorium_id,
                "ist_standard": ep.ist_standard,
                "fahrzeug_eintraege": [f"{pf.fahrzeug_id}:{pf.ziel_status}" for pf in ep.plan_fahrzeuge],
            }
            for ep in plaene
        ],
    }
    content = json.dumps(data, ensure_ascii=False, indent=2)
    filename = datetime.utcnow().strftime("ffw-export-%Y%m%d-%H%M%S.json")
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/admin/datenverwaltung/import")
async def datenverwaltung_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        raw = await file.read()
        data = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige JSON-Datei")

    if data.get("version") != 1:
        raise HTTPException(status_code=400, detail="Unbekanntes Exportformat")

    stats = {"gruppen": 0, "territorien": 0, "fahrzeuge": 0, "alarmierungstypen": 0, "plaene": 0}

    # Gruppen – anhand Name deduplizieren, ID-Mapping merken
    gruppen_map: dict[int, int] = {}  # alte ID → neue ID
    for g in data.get("gruppen", []):
        existing = db.query(FahrzeugGruppe).filter_by(name=g["name"]).first()
        if existing:
            gruppen_map[g["id"]] = existing.id
        else:
            neu = FahrzeugGruppe(name=g["name"], position=g.get("position", 0))
            db.add(neu); db.flush()
            gruppen_map[g["id"]] = neu.id
            stats["gruppen"] += 1

    # Territorien
    territorien_map: dict[int, int] = {}
    for t in data.get("territorien", []):
        existing = db.query(Territorium).filter_by(name=t["name"]).first()
        if existing:
            territorien_map[t["id"]] = existing.id
        else:
            neu = Territorium(name=t["name"], beschreibung=t.get("beschreibung"))
            db.add(neu); db.flush()
            territorien_map[t["id"]] = neu.id
            stats["territorien"] += 1

    # Fahrzeuge – anhand Name + Typ deduplizieren
    fahrzeuge_map: dict[int, int] = {}
    fahrzeuge_roh = data.get("fahrzeuge", [])
    for f in fahrzeuge_roh:
        existing = db.query(Fahrzeug).filter_by(name=f["name"], typ=f["typ"]).first()
        if existing:
            fahrzeuge_map[f["id"]] = existing.id
        else:
            neu = Fahrzeug(
                name=f["name"], kennzeichen=f.get("kennzeichen"),
                funkkennung=f.get("funkkennung"), typ=f["typ"],
                status="einsatzbereit", position=f.get("position", 0),
                gruppe_id=gruppen_map.get(f.get("gruppe_id")) if f.get("gruppe_id") else None,
            )
            db.add(neu); db.flush()
            fahrzeuge_map[f["id"]] = neu.id
            stats["fahrzeuge"] += 1

    # Ersatzfahrzeug-Verknüpfungen setzen
    for f in fahrzeuge_roh:
        fzg = db.get(Fahrzeug, fahrzeuge_map[f["id"]])
        fzg.ersatzfahrzeuge = [
            db.get(Fahrzeug, fahrzeuge_map[eid])
            for eid in f.get("ersatz_ids", [])
            if eid in fahrzeuge_map and fahrzeuge_map[eid]
        ]

    # Alarmierungstypen + Stichworte
    at_map: dict[int, int] = {}
    sw_map: dict[int, int] = {}
    for at in data.get("alarmierungstypen", []):
        existing = db.query(Alarmierungstyp).filter_by(name=at["name"]).first()
        if existing:
            at_map[at["id"]] = existing.id
            for sw in at.get("stichworte", []):
                ex_sw = db.query(Alarmierungsstichwort).filter_by(
                    text=sw["text"], alarmierungstyp_id=existing.id
                ).first()
                sw_map[sw["id"]] = ex_sw.id if ex_sw else sw["id"]
        else:
            neu_at = Alarmierungstyp(name=at["name"], beschreibung=at.get("beschreibung"))
            db.add(neu_at); db.flush()
            at_map[at["id"]] = neu_at.id
            stats["alarmierungstypen"] += 1
            for sw in at.get("stichworte", []):
                neu_sw = Alarmierungsstichwort(text=sw["text"], alarmierungstyp_id=neu_at.id)
                db.add(neu_sw); db.flush()
                sw_map[sw["id"]] = neu_sw.id

    # Alarmierungspläne
    for ep in data.get("alarmierungsplaene", []):
        at_id  = at_map.get(ep["alarmierungstyp_id"])
        ter_id = territorien_map.get(ep["territorium_id"])
        sw_id  = sw_map.get(ep.get("stichwort_id")) if ep.get("stichwort_id") else None
        if not at_id or not ter_id:
            continue
        existing = db.query(Alarmierungsplan).filter_by(
            alarmierungstyp_id=at_id, stichwort_id=sw_id, territorium_id=ter_id
        ).first()
        if not existing:
            neu_ep = Alarmierungsplan(
                alarmierungstyp_id=at_id, stichwort_id=sw_id,
                territorium_id=ter_id, ist_standard=ep.get("ist_standard", False),
            )
            db.add(neu_ep); db.flush()
            # Support both old format (fahrzeug_ids) and new format (fahrzeug_eintraege)
            eintraege = ep.get("fahrzeug_eintraege") or [
                str(fid) for fid in ep.get("fahrzeug_ids", [])
            ]
            mapped = []
            for eintrag in eintraege:
                teile = str(eintrag).split(":", 1)
                orig_fid = int(teile[0])
                ziel = teile[1] if len(teile) > 1 else "alarmiert"
                new_fid = fahrzeuge_map.get(orig_fid)
                if new_fid:
                    mapped.append(f"{new_fid}:{ziel}")
            _set_plan_fahrzeuge(neu_ep, mapped, db)
            stats["plaene"] += 1

    db.commit()
    msg = (
        f"Import abgeschlossen: "
        f"{stats['gruppen']} Gruppen, {stats['territorien']} Territorien, "
        f"{stats['fahrzeuge']} Fahrzeuge, {stats['alarmierungstypen']} Alarmierungstypen, "
        f"{stats['plaene']} Alarmierungspläne neu angelegt."
    )
    return {"ok": True, "message": msg}


@app.post("/admin/datenverwaltung/reset")
def datenverwaltung_reset(db: Session = Depends(get_db)):
    db.query(AktivAlarm).delete()
    db.query(Alarmierungsplan).delete()
    db.query(Alarmierungsstichwort).delete()
    db.query(Alarmierungstyp).delete()
    db.query(Fahrzeug).delete()
    db.query(FahrzeugGruppe).delete()
    db.query(Territorium).delete()
    db.commit()
    return {"ok": True}



@app.get("/admin", response_class=HTMLResponse)
def admin():
    return RedirectResponse("/admin/alarmierungsplan", status_code=302)


@app.get("/admin/fahrzeug", response_class=HTMLResponse)
def admin_fahrzeuge(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("admin.html", {"request": request, **admin_context(db, "fahrzeuge")})


@app.post("/admin/fahrzeug")
def fahrzeug_neu(
    name: str = Form(...), kennzeichen: str = Form(""), funkkennung: str = Form(""),
    typ: str = Form(...), gruppe_id: Optional[int] = Form(None),
    ersatz_ids: list[int] = Form(default=[]), db: Session = Depends(get_db)
):
    pos = db.query(Fahrzeug).filter(Fahrzeug.gruppe_id == gruppe_id).count()
    f = Fahrzeug(name=name, kennzeichen=kennzeichen or None, funkkennung=funkkennung or None,
                 typ=typ, status="einsatzbereit", gruppe_id=gruppe_id, position=pos)
    f.ersatzfahrzeuge = db.query(Fahrzeug).filter(Fahrzeug.id.in_(ersatz_ids)).all()
    db.add(f)
    db.commit()
    return {"ok": True}


@app.put("/admin/fahrzeug/{fid}")
def fahrzeug_bearbeiten(
    fid: int, name: str = Form(...), kennzeichen: str = Form(""), funkkennung: str = Form(""),
    typ: str = Form(...), gruppe_id: Optional[int] = Form(None),
    ersatz_ids: list[int] = Form(default=[]), db: Session = Depends(get_db)
):
    f = db.get(Fahrzeug, fid)
    if not f:
        raise HTTPException(status_code=404)
    f.name        = name
    f.kennzeichen = kennzeichen or None
    f.funkkennung = funkkennung or None
    f.typ         = typ
    f.gruppe_id   = gruppe_id
    f.ersatzfahrzeuge = db.query(Fahrzeug).filter(Fahrzeug.id.in_(ersatz_ids)).all()
    db.commit()
    return {"ok": True}


@app.delete("/admin/fahrzeug/{fid}")
def fahrzeug_loeschen(fid: int, db: Session = Depends(get_db)):
    f = db.get(Fahrzeug, fid)
    if f:
        db.delete(f)
        db.commit()
    return {"ok": True}


# ─── Admin: Fahrzeuggruppen ───────────────────────────────────────────────────

@app.get("/admin/gruppe", response_class=HTMLResponse)
def admin_gruppen(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("admin.html", {"request": request, **admin_context(db, "gruppen")})


@app.post("/admin/gruppe")
def gruppe_neu(name: str = Form(...), db: Session = Depends(get_db)):
    db.add(FahrzeugGruppe(name=name))
    db.commit()
    return {"ok": True}


@app.put("/admin/gruppe/{gid}")
def gruppe_bearbeiten(gid: int, name: str = Form(...), db: Session = Depends(get_db)):
    g = db.get(FahrzeugGruppe, gid)
    if not g:
        raise HTTPException(status_code=404)
    g.name = name
    db.commit()
    return {"ok": True}


@app.delete("/admin/gruppe/{gid}")
def gruppe_loeschen(gid: int, db: Session = Depends(get_db)):
    g = db.get(FahrzeugGruppe, gid)
    if g:
        db.delete(g)
        db.commit()
    return {"ok": True}


# ─── Admin: Territorien ───────────────────────────────────────────────────────

@app.get("/admin/territorium", response_class=HTMLResponse)
def admin_territorien(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("admin.html", {"request": request, **admin_context(db, "territorien")})


@app.post("/admin/territorium")
def territorium_neu(name: str = Form(...), beschreibung: str = Form(""), db: Session = Depends(get_db)):
    db.add(Territorium(name=name, beschreibung=beschreibung or None))
    db.commit()
    return {"ok": True}


@app.put("/admin/territorium/{tid}")
def territorium_bearbeiten(tid: int, name: str = Form(...), beschreibung: str = Form(""), db: Session = Depends(get_db)):
    t = db.get(Territorium, tid)
    if not t:
        raise HTTPException(status_code=404)
    t.name         = name
    t.beschreibung = beschreibung or None
    db.commit()
    return {"ok": True}


@app.delete("/admin/territorium/{tid}")
def territorium_loeschen(tid: int, db: Session = Depends(get_db)):
    t = db.get(Territorium, tid)
    if t:
        db.delete(t)
        db.commit()
    return {"ok": True}


# ─── Admin: Alarmierungsplan ───────────────────────────────────────────────────────

@app.get("/admin/alarmierungsplan", response_class=HTMLResponse)
def admin_alarmierungsplan(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("admin.html", {"request": request, **admin_context(db, "alarmierungsplaene")})



def _set_plan_fahrzeuge(ep, fahrzeug_eintraege: list[str], db):
    """Setzt plan_fahrzeuge aus codierten Strings 'id:status' oder 'id'."""
    ep.plan_fahrzeuge.clear()
    for eintrag in fahrzeug_eintraege:
        teile = eintrag.split(":", 1)
        fid   = int(teile[0])
        ziel  = teile[1] if len(teile) > 1 and teile[1] in ("alarmiert", "bereitschaft") else "alarmiert"
        f     = db.get(Fahrzeug, fid)
        if f:
            ep.plan_fahrzeuge.append(AlarmierungsplanFahrzeug(
                fahrzeug_id=fid, ziel_status=ziel
            ))


@app.post("/admin/alarmierungsplan")
def alarmierungsplan_neu(
    alarmierungstyp_id: int = Form(...),
    stichwort_id: Optional[str] = Form(None),
    territorium_id: int = Form(...),
    ist_standard: bool = Form(False),
    fahrzeug_eintraege: list[str] = Form(default=[]),
    db: Session = Depends(get_db)
):
    sw_id = int(stichwort_id) if stichwort_id and stichwort_id.strip() else None
    existing = db.query(Alarmierungsplan).filter(
        Alarmierungsplan.alarmierungstyp_id == alarmierungstyp_id,
        Alarmierungsplan.stichwort_id == sw_id,
        Alarmierungsplan.territorium_id == territorium_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ein Alarmierungsplan mit dieser Kombination existiert bereits")
    if ist_standard:
        db.query(Alarmierungsplan).filter(
            Alarmierungsplan.alarmierungstyp_id == alarmierungstyp_id,
            Alarmierungsplan.ist_standard == True
        ).update({"ist_standard": False})
    ep = Alarmierungsplan(
        alarmierungstyp_id=alarmierungstyp_id,
        stichwort_id=sw_id,
        territorium_id=territorium_id,
        ist_standard=ist_standard,
    )
    db.add(ep)
    db.flush()
    _set_plan_fahrzeuge(ep, fahrzeug_eintraege, db)
    db.commit()
    return {"ok": True}


@app.put("/admin/alarmierungsplan/{epid}")
def alarmierungsplan_bearbeiten(
    epid: int,
    alarmierungstyp_id: int = Form(...),
    stichwort_id: Optional[str] = Form(None),
    territorium_id: int = Form(...),
    ist_standard: bool = Form(False),
    fahrzeug_eintraege: list[str] = Form(default=[]),
    db: Session = Depends(get_db)
):
    ep = db.get(Alarmierungsplan, epid)
    if not ep:
        raise HTTPException(status_code=404)
    sw_id = int(stichwort_id) if stichwort_id and stichwort_id.strip() else None
    existing = db.query(Alarmierungsplan).filter(
        Alarmierungsplan.alarmierungstyp_id == alarmierungstyp_id,
        Alarmierungsplan.stichwort_id == sw_id,
        Alarmierungsplan.territorium_id == territorium_id,
        Alarmierungsplan.id != epid,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ein Alarmierungsplan mit dieser Kombination existiert bereits")
    if ist_standard:
        db.query(Alarmierungsplan).filter(
            Alarmierungsplan.alarmierungstyp_id == alarmierungstyp_id,
            Alarmierungsplan.ist_standard == True,
            Alarmierungsplan.id != epid
        ).update({"ist_standard": False})
    ep.alarmierungstyp_id = alarmierungstyp_id
    ep.stichwort_id       = sw_id
    ep.territorium_id     = territorium_id
    ep.ist_standard       = ist_standard
    _set_plan_fahrzeuge(ep, fahrzeug_eintraege, db)
    db.commit()
    return {"ok": True}


@app.delete("/admin/alarmierungsplan/{epid}")
def alarmierungsplan_loeschen(epid: int, db: Session = Depends(get_db)):
    ep = db.get(Alarmierungsplan, epid)
    if ep:
        db.delete(ep)
        db.commit()
    return {"ok": True}


@app.get("/api/alarmierungstyp/{atid}/stichworte", response_class=JSONResponse)
def get_stichworte(atid: int, db: Session = Depends(get_db)):
    stichworte = db.query(Alarmierungsstichwort).filter(
        Alarmierungsstichwort.alarmierungstyp_id == atid
    ).order_by(Alarmierungsstichwort.text).all()
    return [{"id": s.id, "text": s.text} for s in stichworte]


# ─── Admin: Alarmierungstypen ─────────────────────────────────────────────────

@app.get("/admin/alarmierungstyp", response_class=HTMLResponse)
def admin_alarmierungstypen(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("admin.html", {"request": request, **admin_context(db, "alarmierungstypen")})


@app.post("/admin/alarmierungstyp")
def alarmierungstyp_neu(
    name: str = Form(...), beschreibung: str = Form(""),
    stichwort_text: list[str] = Form(default=[]),
    db: Session = Depends(get_db)
):
    at = Alarmierungstyp(name=name, beschreibung=beschreibung or None)
    db.add(at)
    db.flush()
    for text in [t.strip() for t in stichwort_text if t.strip()]:
        db.add(Alarmierungsstichwort(text=text, alarmierungstyp_id=at.id))
    db.commit()
    return {"ok": True}


@app.put("/admin/alarmierungstyp/{atid}")
def alarmierungstyp_bearbeiten(
    atid: int, name: str = Form(...), beschreibung: str = Form(""),
    stichworte: str = Form(""),
    db: Session = Depends(get_db)
):
    at = db.get(Alarmierungstyp, atid)
    if not at:
        raise HTTPException(status_code=404)
    at.name         = name
    at.beschreibung = beschreibung or None
    eingehend = []
    for zeile in [z.strip() for z in stichworte.split("\n") if z.strip()]:
        if ":" in zeile:
            prefix, _, text = zeile.partition(":")
            if prefix.strip().isdigit():
                eingehend.append((int(prefix.strip()), text.strip()))
                continue
        eingehend.append((None, zeile))
    eingehende_ids = {sid for sid, _ in eingehend if sid}
    bestehende = db.query(Alarmierungsstichwort).filter(
        Alarmierungsstichwort.alarmierungstyp_id == atid
    ).all()
    for s in bestehende:
        if s.id not in eingehende_ids:
            in_verwendung = db.query(Alarmierungsplan).filter(
                Alarmierungsplan.stichwort_id == s.id
            ).first()
            if not in_verwendung:
                db.delete(s)
    for sid, text in eingehend:
        if sid:
            s = db.get(Alarmierungsstichwort, sid)
            if s:
                s.text = text
        else:
            db.add(Alarmierungsstichwort(text=text, alarmierungstyp_id=atid))
    db.commit()
    return {"ok": True}


@app.delete("/admin/alarmierungstyp/{atid}")
def alarmierungstyp_loeschen(atid: int, db: Session = Depends(get_db)):
    at = db.get(Alarmierungstyp, atid)
    if at:
        db.delete(at)
        db.commit()
    return {"ok": True}