"""
Unit-Tests für alle API-Endpunkte der Feuerwehr Alarmierungs-App.
Verwendet FastAPI TestClient mit einer SQLite-In-Memory-Datenbank.

Ausführen:
    pip install fastapi httpx sqlalchemy jinja2 python-multipart
    python -m pytest tests/test_api.py -v
    # oder:
    python -m unittest tests/test_api -v
"""

import sys
import os
import unittest

# Sicherstellen, dass das app-Verzeichnis im Pfad liegt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Patch DATABASE_URL vor dem Import von main
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Jetzt main importieren – nach dem Setzen der Env-Variable
from app.main import (
    app, Base, get_db,
    Fahrzeug, FahrzeugGruppe, Territorium,
    Alarmierungstyp, Alarmierungsstichwort,
    Alarmierungsplan, AktivAlarm, AlarmierungsplanFahrzeug,
)

# ─── Test-Datenbank ───────────────────────────────────────────────────────────

from sqlalchemy import event as sa_event

TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(bind=TEST_ENGINE)

# SQLite: FK-Constraints aktivieren (sonst werden CASCADE-Deletes ignoriert)
@sa_event.listens_for(TEST_ENGINE, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# ─── Basis-Testklasse ─────────────────────────────────────────────────────────

class BaseTestCase(unittest.TestCase):
    """Erstellt vor jedem Test ein frisches Schema und einen TestClient."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=TEST_ENGINE)
        cls.client = TestClient(app, raise_server_exceptions=True)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=TEST_ENGINE)

    def setUp(self):
        """Leert alle Tabellen vor jedem einzelnen Test."""
        db = TestSessionLocal()
        try:
            # Reihenfolge beachten: FK-Constraints (auch in SQLite mit PRAGMA foreign_keys=ON)
            db.query(AktivAlarm).delete()
            db.query(AlarmierungsplanFahrzeug).delete()
            db.query(Alarmierungsplan).delete()
            db.query(Alarmierungsstichwort).delete()
            db.query(Alarmierungstyp).delete()
            # Ersatzfahrzeug-Verknüpfungen via raw SQL löschen (M:N self-ref)
            db.execute(__import__("sqlalchemy").text("DELETE FROM fahrzeug_ersatz"))
            db.query(Fahrzeug).delete()
            db.query(FahrzeugGruppe).delete()
            db.query(Territorium).delete()
            db.commit()
        finally:
            db.close()

    # ── Hilfsmethoden ─────────────────────────────────────────────────────────

    def _create_gruppe(self, name="Gruppe 1"):
        r = self.client.post("/admin/gruppe", data={"name": name})
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        g = db.query(FahrzeugGruppe).filter_by(name=name).first()
        db.close()
        return g

    def _create_territorium(self, name="Süd"):
        r = self.client.post("/admin/territorium", data={"name": name})
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        t = db.query(Territorium).filter_by(name=name).first()
        db.close()
        return t

    def _create_alarmierungstyp(self, name="BRAND", stichworte=""):
        # Backend expects stichwort_text as list; split newline-separated string
        stichwort_list = [s.strip() for s in stichworte.split("\n") if s.strip()]
        r = self.client.post("/admin/alarmierungstyp",
                             data={"name": name, "beschreibung": "", "stichwort_text": stichwort_list})
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        at = db.query(Alarmierungstyp).filter_by(name=name).first()
        db.close()
        return at

    def _create_fahrzeug(self, name="HLF 1", typ="HLF", gruppe_id=None):
        data = {"name": name, "typ": typ, "kennzeichen": "", "funkkennung": ""}
        if gruppe_id:
            data["gruppe_id"] = gruppe_id
        r = self.client.post("/admin/fahrzeug", data=data)
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        f = db.query(Fahrzeug).filter_by(name=name).first()
        db.close()
        return f

    def _create_alarmierungsplan(self, at_id, territorium_id, fahrzeug_ids=None,
                                  stichwort_id=None, ist_standard=False):
        data = {
            "alarmierungstyp_id": at_id,
            "territorium_id": territorium_id,
            "ist_standard": str(ist_standard).lower(),
        }
        if stichwort_id:
            data["stichwort_id"] = stichwort_id
        if fahrzeug_ids:
            data["fahrzeug_eintraege"] = [f"{fid}:alarmiert" for fid in fahrzeug_ids]
        r = self.client.post("/admin/alarmierungsplan", data=data)
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        ep = db.query(Alarmierungsplan).filter_by(
            alarmierungstyp_id=at_id, territorium_id=territorium_id
        ).first()
        db.close()
        return ep

    def _start_alarm(self, alarmierungstyp_id, alarmierungsplan_id):
        return self.client.post("/api/alarm/starten", json={
            "alarmierungstyp_id": alarmierungstyp_id,
            "alarmierungsplan_id": alarmierungsplan_id,
        })


# ─── Fahrzeuge ────────────────────────────────────────────────────────────────

class TestFahrzeugeAPI(BaseTestCase):

    def test_fahrzeug_anlegen(self):
        r = self.client.post("/admin/fahrzeug", data={
            "name": "HLF 20", "typ": "HLF", "kennzeichen": "KU-FL 1", "funkkennung": "Florian 1"
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        db = TestSessionLocal()
        f = db.query(Fahrzeug).filter_by(name="HLF 20").first()
        db.close()
        self.assertIsNotNone(f)
        self.assertEqual(f.kennzeichen, "KU-FL 1")
        self.assertEqual(f.status, "einsatzbereit")

    def test_fahrzeug_anlegen_ohne_optionale_felder(self):
        r = self.client.post("/admin/fahrzeug", data={"name": "TLF", "typ": "TLF"})
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        f = db.query(Fahrzeug).filter_by(name="TLF").first()
        db.close()
        self.assertIsNone(f.kennzeichen)
        self.assertIsNone(f.funkkennung)

    def test_fahrzeug_bearbeiten(self):
        f = self._create_fahrzeug("Alt")
        r = self.client.put(f"/admin/fahrzeug/{f.id}", data={
            "name": "Neu", "typ": "RW", "kennzeichen": "", "funkkennung": ""
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        db = TestSessionLocal()
        f_updated = db.get(Fahrzeug, f.id)
        db.close()
        self.assertEqual(f_updated.name, "Neu")
        self.assertEqual(f_updated.typ, "RW")

    def test_fahrzeug_bearbeiten_nicht_gefunden(self):
        r = self.client.put("/admin/fahrzeug/9999", data={
            "name": "X", "typ": "Y", "kennzeichen": "", "funkkennung": ""
        })
        self.assertEqual(r.status_code, 404)

    def test_fahrzeug_loeschen(self):
        f = self._create_fahrzeug()
        r = self.client.delete(f"/admin/fahrzeug/{f.id}")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        db = TestSessionLocal()
        self.assertIsNone(db.get(Fahrzeug, f.id))
        db.close()

    def test_fahrzeug_loeschen_nicht_vorhanden_gibt_ok(self):
        r = self.client.delete("/admin/fahrzeug/9999")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_fahrzeug_mit_gruppe(self):
        g = self._create_gruppe()
        r = self.client.post("/admin/fahrzeug", data={
            "name": "MTF", "typ": "MTF", "gruppe_id": g.id
        })
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        f = db.query(Fahrzeug).filter_by(name="MTF").first()
        db.close()
        self.assertEqual(f.gruppe_id, g.id)


# ─── Fahrzeuggruppen ──────────────────────────────────────────────────────────

class TestGruppenAPI(BaseTestCase):

    def test_gruppe_anlegen(self):
        r = self.client.post("/admin/gruppe", data={"name": "Löschgruppe"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        db = TestSessionLocal()
        self.assertIsNotNone(db.query(FahrzeugGruppe).filter_by(name="Löschgruppe").first())
        db.close()

    def test_gruppe_bearbeiten(self):
        g = self._create_gruppe("Alt")
        r = self.client.put(f"/admin/gruppe/{g.id}", data={"name": "Neu"})
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        self.assertEqual(db.get(FahrzeugGruppe, g.id).name, "Neu")
        db.close()

    def test_gruppe_bearbeiten_nicht_gefunden(self):
        r = self.client.put("/admin/gruppe/9999", data={"name": "X"})
        self.assertEqual(r.status_code, 404)

    def test_gruppe_loeschen(self):
        g = self._create_gruppe()
        r = self.client.delete(f"/admin/gruppe/{g.id}")
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        self.assertIsNone(db.get(FahrzeugGruppe, g.id))
        db.close()

    def test_gruppe_loeschen_nicht_vorhanden_gibt_ok(self):
        r = self.client.delete("/admin/gruppe/9999")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_gruppe_move_up(self):
        g1 = self._create_gruppe("Gruppe A")
        g2 = self._create_gruppe("Gruppe B")
        # Setzt Position explizit
        db = TestSessionLocal()
        db.get(FahrzeugGruppe, g1.id).position = 0
        db.get(FahrzeugGruppe, g2.id).position = 1
        db.commit()
        db.close()
        r = self.client.post(f"/api/gruppe/{g2.id}/move", params={"direction": "up"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_gruppe_move_nicht_gefunden(self):
        r = self.client.post("/api/gruppe/9999/move", params={"direction": "up"})
        self.assertEqual(r.status_code, 404)


# ─── Territorien ──────────────────────────────────────────────────────────────

class TestTerritorienAPI(BaseTestCase):

    def test_territorium_anlegen(self):
        r = self.client.post("/admin/territorium", data={"name": "Nord", "beschreibung": "Nördlicher Bereich"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        db = TestSessionLocal()
        t = db.query(Territorium).filter_by(name="Nord").first()
        db.close()
        self.assertIsNotNone(t)
        self.assertEqual(t.beschreibung, "Nördlicher Bereich")

    def test_territorium_bearbeiten(self):
        t = self._create_territorium("Alt")
        r = self.client.put(f"/admin/territorium/{t.id}", data={"name": "Neu", "beschreibung": ""})
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        self.assertEqual(db.get(Territorium, t.id).name, "Neu")
        db.close()

    def test_territorium_bearbeiten_nicht_gefunden(self):
        r = self.client.put("/admin/territorium/9999", data={"name": "X"})
        self.assertEqual(r.status_code, 404)

    def test_territorium_loeschen(self):
        t = self._create_territorium()
        r = self.client.delete(f"/admin/territorium/{t.id}")
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        self.assertIsNone(db.get(Territorium, t.id))
        db.close()

    def test_territorium_loeschen_nicht_vorhanden_gibt_ok(self):
        r = self.client.delete("/admin/territorium/9999")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])


# ─── Alarmierungstypen ────────────────────────────────────────────────────────

class TestAlarmierungstypenAPI(BaseTestCase):

    def test_alarmierungstyp_anlegen(self):
        r = self.client.post("/admin/alarmierungstyp", data={
            "name": "BRAND", "beschreibung": "Brandeinsatz", "stichworte": "B1\nB2\nB3"
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        db = TestSessionLocal()
        at = db.query(Alarmierungstyp).filter_by(name="BRAND").first()
        db.close()
        self.assertIsNotNone(at)

    def test_alarmierungstyp_anlegen_erstellt_stichworte(self):
        at = self._create_alarmierungstyp("THL", stichworte="THL 1\nTHL 2")
        db = TestSessionLocal()
        stichworte = db.query(Alarmierungsstichwort).filter_by(alarmierungstyp_id=at.id).all()
        db.close()
        self.assertEqual(len(stichworte), 2)
        texte = {s.text for s in stichworte}
        self.assertEqual(texte, {"THL 1", "THL 2"})

    def test_alarmierungstyp_bearbeiten(self):
        at = self._create_alarmierungstyp("Alt")
        r = self.client.put(f"/admin/alarmierungstyp/{at.id}", data={
            "name": "Neu", "beschreibung": "Aktualisiert", "stichworte": "S1"
        })
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        at_updated = db.get(Alarmierungstyp, at.id)
        stichworte = db.query(Alarmierungsstichwort).filter_by(alarmierungstyp_id=at.id).all()
        db.close()
        self.assertEqual(at_updated.name, "Neu")
        self.assertEqual(len(stichworte), 1)
        self.assertEqual(stichworte[0].text, "S1")

    def test_alarmierungstyp_bearbeiten_ersetzt_stichworte(self):
        at = self._create_alarmierungstyp("X", stichworte="Alt1\nAlt2")
        self.client.put(f"/admin/alarmierungstyp/{at.id}", data={
            "name": "X", "beschreibung": "", "stichworte": "Neu1"
        })
        db = TestSessionLocal()
        stichworte = db.query(Alarmierungsstichwort).filter_by(alarmierungstyp_id=at.id).all()
        db.close()
        self.assertEqual(len(stichworte), 1)
        self.assertEqual(stichworte[0].text, "Neu1")

    def test_alarmierungstyp_bearbeiten_nicht_gefunden(self):
        r = self.client.put("/admin/alarmierungstyp/9999", data={"name": "X", "stichworte": ""})
        self.assertEqual(r.status_code, 404)

    def test_alarmierungstyp_loeschen(self):
        at = self._create_alarmierungstyp()
        r = self.client.delete(f"/admin/alarmierungstyp/{at.id}")
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        self.assertIsNone(db.get(Alarmierungstyp, at.id))
        db.close()

    def test_alarmierungstyp_loeschen_nicht_vorhanden_gibt_ok(self):
        r = self.client.delete("/admin/alarmierungstyp/9999")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_stichworte_api(self):
        at = self._create_alarmierungstyp("BRAND", stichworte="B1\nB2")
        r = self.client.get(f"/api/alarmierungstyp/{at.id}/stichworte")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data), 2)
        texte = {s["text"] for s in data}
        self.assertEqual(texte, {"B1", "B2"})

    def test_stichworte_api_leer(self):
        at = self._create_alarmierungstyp("LEER")
        r = self.client.get(f"/api/alarmierungstyp/{at.id}/stichworte")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])


# ─── Alarmierungspläne ────────────────────────────────────────────────────────

class TestAlarmierungsplaeneAPI(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.at = self._create_alarmierungstyp("BRAND")
        self.t = self._create_territorium("Süd")
        self.f1 = self._create_fahrzeug("HLF 1")
        self.f2 = self._create_fahrzeug("HLF 2")

    def test_alarmierungsplan_anlegen(self):
        r = self.client.post("/admin/alarmierungsplan", data={
            "alarmierungstyp_id": self.at.id,
            "territorium_id": self.t.id,
            "fahrzeug_eintraege": [f"{self.f1.id}:alarmiert"],
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        db = TestSessionLocal()
        ep = db.query(Alarmierungsplan).filter_by(
            alarmierungstyp_id=self.at.id, territorium_id=self.t.id
        ).first()
        db.close()
        self.assertIsNotNone(ep)

    def test_alarmierungsplan_doppelt_abgelehnt(self):
        self._create_alarmierungsplan(self.at.id, self.t.id)
        r = self.client.post("/admin/alarmierungsplan", data={
            "alarmierungstyp_id": self.at.id,
            "territorium_id": self.t.id,
        })
        self.assertEqual(r.status_code, 400)

    def test_alarmierungsplan_standard_setzt_anderen_zurueck(self):
        ep1 = self._create_alarmierungsplan(self.at.id, self.t.id, ist_standard=True)
        t2 = self._create_territorium("Nord")
        r = self.client.post("/admin/alarmierungsplan", data={
            "alarmierungstyp_id": self.at.id,
            "territorium_id": t2.id,
            "ist_standard": "true",
        })
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        ep1_updated = db.get(Alarmierungsplan, ep1.id)
        db.close()
        self.assertFalse(ep1_updated.ist_standard)

    def test_alarmierungsplan_bearbeiten(self):
        ep = self._create_alarmierungsplan(self.at.id, self.t.id)
        t2 = self._create_territorium("Nord")
        r = self.client.put(f"/admin/alarmierungsplan/{ep.id}", data={
            "alarmierungstyp_id": self.at.id,
            "territorium_id": t2.id,
            "fahrzeug_eintraege": [f"{self.f2.id}:alarmiert"],
        })
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        ep_updated = db.get(Alarmierungsplan, ep.id)
        db.close()
        self.assertEqual(ep_updated.territorium_id, t2.id)

    def test_alarmierungsplan_bearbeiten_nicht_gefunden(self):
        r = self.client.put("/admin/alarmierungsplan/9999", data={
            "alarmierungstyp_id": self.at.id,
            "territorium_id": self.t.id,
        })
        self.assertEqual(r.status_code, 404)

    def test_alarmierungsplan_loeschen(self):
        ep = self._create_alarmierungsplan(self.at.id, self.t.id)
        r = self.client.delete(f"/admin/alarmierungsplan/{ep.id}")
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        self.assertIsNone(db.get(Alarmierungsplan, ep.id))
        db.close()

    def test_alarmierungsplan_loeschen_nicht_vorhanden_gibt_ok(self):
        r = self.client.delete("/admin/alarmierungsplan/9999")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_einsatzplaene_api(self):
        ep = self._create_alarmierungsplan(self.at.id, self.t.id, fahrzeug_ids=[self.f1.id])
        r = self.client.get(f"/api/alarmierungstyp/{self.at.id}/einsatzplaene")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], ep.id)
        self.assertIn("fahrzeuge", data[0])
        self.assertIn("warnungen", data[0])
        self.assertEqual(data[0]["territorium"]["id"], self.t.id)

    def test_einsatzplaene_api_leer(self):
        r = self.client.get(f"/api/alarmierungstyp/{self.at.id}/einsatzplaene")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_einsatzplaene_effektive_fahrzeuge_mit_ersatz(self):
        """Nicht einsatzbereites Fahrzeug wird durch Ersatz in der Vorschau ersetzt."""
        db = TestSessionLocal()
        f1 = db.get(Fahrzeug, self.f1.id)
        f2 = db.get(Fahrzeug, self.f2.id)
        f1.status = "nicht_einsatzbereit"
        f1.ersatzfahrzeuge = [f2]
        db.commit()
        db.close()

        ep = self._create_alarmierungsplan(self.at.id, self.t.id, fahrzeug_ids=[self.f1.id])
        r = self.client.get(f"/api/alarmierungstyp/{self.at.id}/einsatzplaene")
        data = r.json()
        fahrzeuge = data[0]["fahrzeuge"]
        # Ersatzfahrzeug soll in Liste erscheinen
        namen = [f["name"] for f in fahrzeuge]
        self.assertIn(self.f2.name, namen)
        self.assertNotIn(self.f1.name, namen)

    def test_einsatzplaene_warnung_wenn_kein_ersatz(self):
        """Warnung erscheint, wenn Fahrzeug nicht einsatzbereit und kein Ersatz."""
        db = TestSessionLocal()
        f1 = db.get(Fahrzeug, self.f1.id)
        f1.status = "nicht_einsatzbereit"
        db.commit()
        db.close()

        self._create_alarmierungsplan(self.at.id, self.t.id, fahrzeug_ids=[self.f1.id])
        r = self.client.get(f"/api/alarmierungstyp/{self.at.id}/einsatzplaene")
        warnungen = r.json()[0]["warnungen"]
        self.assertEqual(len(warnungen), 1)
        self.assertIn(self.f1.name, warnungen[0]["fahrzeug"])


# ─── Alarm starten / beenden ──────────────────────────────────────────────────

class TestAlarmAPI(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.at = self._create_alarmierungstyp("BRAND")
        self.t = self._create_territorium("Süd")
        self.f1 = self._create_fahrzeug("HLF 1")
        self.f2 = self._create_fahrzeug("HLF 2")
        self.ep = self._create_alarmierungsplan(
            self.at.id, self.t.id, fahrzeug_ids=[self.f1.id]
        )

    def test_alarm_starten(self):
        r = self._start_alarm(self.at.id, self.ep.id)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["alarmierungstyp_id"], self.at.id)

    def test_alarm_starten_setzt_fahrzeug_auf_alarmiert(self):
        self._start_alarm(self.at.id, self.ep.id)
        db = TestSessionLocal()
        f = db.get(Fahrzeug, self.f1.id)
        db.close()
        self.assertEqual(f.status, "alarmiert")

    def test_alarm_starten_doppelt_abgelehnt(self):
        self._start_alarm(self.at.id, self.ep.id)
        r = self._start_alarm(self.at.id, self.ep.id)
        self.assertEqual(r.status_code, 409)

    def test_alarm_starten_falscher_plan_abgelehnt(self):
        r = self._start_alarm(self.at.id, 9999)
        self.assertEqual(r.status_code, 404)

    def test_alarm_starten_falsche_typzuordnung_abgelehnt(self):
        at2 = self._create_alarmierungstyp("THL")
        r = self._start_alarm(at2.id, self.ep.id)
        self.assertEqual(r.status_code, 404)

    def test_alarm_starten_mit_ersatzfahrzeug(self):
        """Nicht einsatzbereites Fahrzeug wird durch Ersatz alarmiert."""
        db = TestSessionLocal()
        f1 = db.get(Fahrzeug, self.f1.id)
        f2 = db.get(Fahrzeug, self.f2.id)
        f1.status = "nicht_einsatzbereit"
        f1.ersatzfahrzeuge = [f2]
        db.commit()
        db.close()

        r = self._start_alarm(self.at.id, self.ep.id)
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        f2_updated = db.get(Fahrzeug, self.f2.id)
        db.close()
        self.assertEqual(f2_updated.status, "alarmiert")

    def test_alarm_starten_warnung_wenn_kein_ersatz(self):
        """Warnung zurückgegeben wenn kein Ersatz verfügbar."""
        db = TestSessionLocal()
        db.get(Fahrzeug, self.f1.id).status = "nicht_einsatzbereit"
        db.commit()
        db.close()

        r = self._start_alarm(self.at.id, self.ep.id)
        self.assertEqual(r.status_code, 200)
        warnungen = r.json()["warnungen"]
        self.assertEqual(len(warnungen), 1)
        self.assertIn(self.f1.name, warnungen[0]["fahrzeug"])

    def test_alarm_starten_warnungen_in_db_gespeichert(self):
        """Warnungen werden im AktivAlarm als JSON gespeichert."""
        db = TestSessionLocal()
        db.get(Fahrzeug, self.f1.id).status = "nicht_einsatzbereit"
        db.commit()
        db.close()

        self._start_alarm(self.at.id, self.ep.id)
        db = TestSessionLocal()
        alarm = db.query(AktivAlarm).filter_by(aktiv=True).first()
        db.close()
        self.assertIsNotNone(alarm.warnungen_json)
        warnungen = __import__("json").loads(alarm.warnungen_json)
        self.assertEqual(len(warnungen), 1)

    def test_alarm_starten_speichert_territorium_und_stichwort(self):
        self._start_alarm(self.at.id, self.ep.id)
        db = TestSessionLocal()
        alarm = db.query(AktivAlarm).filter_by(aktiv=True).first()
        db.close()
        self.assertEqual(alarm.territorium_id, self.t.id)

    def test_alarm_beenden(self):
        self._start_alarm(self.at.id, self.ep.id)
        r = self.client.post("/api/alarm/beenden")
        # Erwartet Redirect auf /
        self.assertIn(r.status_code, [200, 302, 303])
        db = TestSessionLocal()
        alarm = db.query(AktivAlarm).filter_by(aktiv=True).first()
        f = db.get(Fahrzeug, self.f1.id)
        db.close()
        self.assertIsNone(alarm)
        self.assertEqual(f.status, "einsatzbereit")

    def test_alarm_beenden_setzt_alle_fahrzeuge_zurueck(self):
        db = TestSessionLocal()
        db.get(Fahrzeug, self.f2.id).status = "bereitschaft"
        db.commit()
        db.close()
        self._start_alarm(self.at.id, self.ep.id)
        self.client.post("/api/alarm/beenden")
        db = TestSessionLocal()
        f1 = db.get(Fahrzeug, self.f1.id)
        f2 = db.get(Fahrzeug, self.f2.id)
        db.close()
        self.assertEqual(f1.status, "einsatzbereit")
        self.assertEqual(f2.status, "einsatzbereit")


# ─── Fahrzeug Status-Toggle ───────────────────────────────────────────────────

class TestFahrzeugStatusToggle(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.f = self._create_fahrzeug()

    def test_toggle_ohne_alarm_wechselt_zwischen_einsatzbereit_und_nicht(self):
        r = self.client.post("/api/fahrzeug/status-toggle",
                             json={"fahrzeug_id": self.f.id})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "nicht_einsatzbereit")
        # Nochmal: zurück auf einsatzbereit
        r = self.client.post("/api/fahrzeug/status-toggle",
                             json={"fahrzeug_id": self.f.id})
        self.assertEqual(r.json()["status"], "einsatzbereit")

    def test_toggle_mit_alarm_durchlaeuft_vollen_zyklus(self):
        at = self._create_alarmierungstyp()
        t = self._create_territorium()
        ep = self._create_alarmierungsplan(at.id, t.id)
        self._start_alarm(at.id, ep.id)

        stati = []
        for _ in range(4):
            r = self.client.post("/api/fahrzeug/status-toggle",
                                 json={"fahrzeug_id": self.f.id})
            stati.append(r.json()["status"])

        self.assertIn("alarmiert", stati)
        self.assertIn("bereitschaft", stati)
        self.assertIn("nicht_einsatzbereit", stati)
        self.assertEqual(stati[-1], "einsatzbereit")

    def test_toggle_nicht_gefunden(self):
        r = self.client.post("/api/fahrzeug/status-toggle",
                             json={"fahrzeug_id": 9999})
        self.assertEqual(r.status_code, 404)


# ─── Fahrzeug Reihenfolge ─────────────────────────────────────────────────────

class TestReihenfolgeAPI(BaseTestCase):

    def test_reihenfolge_speichern(self):
        f1 = self._create_fahrzeug("F1")
        f2 = self._create_fahrzeug("F2")
        r = self.client.post("/api/fahrzeug/reihenfolge", json=[
            {"id": f1.id, "position": 5},
            {"id": f2.id, "position": 3},
        ])
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        db = TestSessionLocal()
        self.assertEqual(db.get(Fahrzeug, f1.id).position, 5)
        self.assertEqual(db.get(Fahrzeug, f2.id).position, 3)
        db.close()

    def test_reihenfolge_unbekannte_id_wird_ignoriert(self):
        f = self._create_fahrzeug()
        r = self.client.post("/api/fahrzeug/reihenfolge", json=[
            {"id": f.id, "position": 2},
            {"id": 9999, "position": 7},
        ])
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        self.assertEqual(db.get(Fahrzeug, f.id).position, 2)
        db.close()


# ─── Einsatz-API ─────────────────────────────────────────────────────────────

class TestEinsatzAPI(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.at = self._create_alarmierungstyp("BRAND")
        self.t = self._create_territorium("Süd")
        self.f = self._create_fahrzeug("HLF 1")
        self.ep = self._create_alarmierungsplan(self.at.id, self.t.id, fahrzeug_ids=[self.f.id])

    def test_einsatz_api_ohne_alarm(self):
        r = self.client.get("/api/einsatz")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["alarm"])

    def test_einsatz_api_mit_alarm(self):
        self._start_alarm(self.at.id, self.ep.id)
        r = self.client.get("/api/einsatz")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsNotNone(data["alarm"])
        self.assertEqual(data["alarm"]["alarmierungstyp"], self.at.name)
        self.assertEqual(data["alarm"]["territorium"], self.t.name)
        self.assertGreaterEqual(data["gesamt"], 1)

    def test_einsatz_api_enthält_warnungen(self):
        db = TestSessionLocal()
        db.get(Fahrzeug, self.f.id).status = "nicht_einsatzbereit"
        db.commit()
        db.close()

        self._start_alarm(self.at.id, self.ep.id)
        r = self.client.get("/api/einsatz")
        data = r.json()
        self.assertIn("warnungen", data)
        self.assertIsInstance(data["warnungen"], list)
        self.assertGreater(len(data["warnungen"]), 0)

    def test_einsatz_api_gruppen_struktur(self):
        g = self._create_gruppe("Löschgruppe")
        db = TestSessionLocal()
        db.get(Fahrzeug, self.f.id).gruppe_id = g.id
        db.commit()
        db.close()

        self._start_alarm(self.at.id, self.ep.id)
        r = self.client.get("/api/einsatz")
        data = r.json()
        gruppen_namen = [gr["gruppe"] for gr in data["gruppen"]]
        self.assertIn("Löschgruppe", gruppen_namen)


# ─── Ersatzfahrzeug-Logik (Einheitentests der Hilfsfunktionen) ────────────────

class TestErsatzfahrzeugLogik(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.at = self._create_alarmierungstyp("BRAND")
        self.t = self._create_territorium("Süd")

    def test_ersatz_wird_nicht_doppelt_eingesetzt(self):
        """Zwei nicht-verfügbare Fahrzeuge mit demselben Ersatz: nur eines bekommt Ersatz."""
        f1 = self._create_fahrzeug("F1")
        f2 = self._create_fahrzeug("F2")
        ersatz = self._create_fahrzeug("Ersatz")

        db = TestSessionLocal()
        f1_db = db.get(Fahrzeug, f1.id)
        f2_db = db.get(Fahrzeug, f2.id)
        e_db = db.get(Fahrzeug, ersatz.id)
        f1_db.status = "nicht_einsatzbereit"
        f2_db.status = "nicht_einsatzbereit"
        f1_db.ersatzfahrzeuge = [e_db]
        f2_db.ersatzfahrzeuge = [e_db]
        db.commit()
        db.close()

        ep = self._create_alarmierungsplan(self.at.id, self.t.id,
                                           fahrzeug_ids=[f1.id, f2.id])
        r = self._start_alarm(self.at.id, ep.id)
        self.assertEqual(r.status_code, 200)
        warnungen = r.json()["warnungen"]
        # Einer bleibt ohne Ersatz
        self.assertEqual(len(warnungen), 1)

        db = TestSessionLocal()
        e_updated = db.get(Fahrzeug, ersatz.id)
        db.close()
        self.assertEqual(e_updated.status, "alarmiert")

    def test_fahrzeuge_im_plan_nicht_als_ersatz_genutzt(self):
        """Fahrzeug das selbst im Plan ist, darf nicht als Ersatz dienen."""
        f1 = self._create_fahrzeug("F1")
        f2 = self._create_fahrzeug("F2")

        db = TestSessionLocal()
        f1_db = db.get(Fahrzeug, f1.id)
        f2_db = db.get(Fahrzeug, f2.id)
        f1_db.status = "nicht_einsatzbereit"
        f1_db.ersatzfahrzeuge = [f2_db]  # F2 ist Ersatz für F1, aber auch im Plan
        db.commit()
        db.close()

        ep = self._create_alarmierungsplan(self.at.id, self.t.id,
                                           fahrzeug_ids=[f1.id, f2.id])
        r = self._start_alarm(self.at.id, ep.id)
        warnungen = r.json()["warnungen"]
        # F2 darf nicht als Ersatz für F1 verwendet werden
        self.assertEqual(len(warnungen), 1)
        self.assertIn(f1.name, warnungen[0]["fahrzeug"])

    def test_sammelwarnung_mehrere_nicht_verfuegbare(self):
        """Mehrere nicht verfügbare Fahrzeuge werden in einer Warnung zusammengefasst."""
        f1 = self._create_fahrzeug("F1")
        f2 = self._create_fahrzeug("F2")
        f3 = self._create_fahrzeug("F3")

        db = TestSessionLocal()
        db.get(Fahrzeug, f1.id).status = "nicht_einsatzbereit"
        db.get(Fahrzeug, f2.id).status = "nicht_einsatzbereit"
        db.get(Fahrzeug, f3.id).status = "nicht_einsatzbereit"
        db.commit()
        db.close()

        ep = self._create_alarmierungsplan(self.at.id, self.t.id,
                                           fahrzeug_ids=[f1.id, f2.id, f3.id])
        r = self._start_alarm(self.at.id, ep.id)
        warnungen = r.json()["warnungen"]
        self.assertEqual(len(warnungen), 1)
        # Alle drei Namen in der Warnung
        warnung_text = warnungen[0]["fahrzeug"]
        self.assertIn(f1.name, warnung_text)
        self.assertIn(f2.name, warnung_text)
        self.assertIn(f3.name, warnung_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ─── Neue Tests: ziel_status / Bereitschaft ───────────────────────────────────

class TestZielStatus(BaseTestCase):
    """Prüft, dass der ziel_status pro Fahrzeug korrekt gesetzt wird."""

    def setUp(self):
        super().setUp()
        self.at = self._create_alarmierungstyp("BRAND")
        self.t  = self._create_territorium("Mitte")
        self.f1 = self._create_fahrzeug("TLF 1")
        self.f2 = self._create_fahrzeug("HLF 2")

    def test_plan_mit_bereitschaft_setzt_fahrzeug_auf_bereitschaft(self):
        """Fahrzeug mit ziel_status=bereitschaft bekommt nach Alarm Status bereitschaft."""
        r = self.client.post("/admin/alarmierungsplan", data={
            "alarmierungstyp_id": self.at.id,
            "territorium_id": self.t.id,
            "fahrzeug_eintraege": [f"{self.f1.id}:bereitschaft"],
        })
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        ep = db.query(Alarmierungsplan).filter_by(
            alarmierungstyp_id=self.at.id, territorium_id=self.t.id
        ).first()
        db.close()

        self._start_alarm(self.at.id, ep.id)
        db = TestSessionLocal()
        f = db.get(Fahrzeug, self.f1.id)
        db.close()
        self.assertEqual(f.status, "bereitschaft")

    def test_plan_gemischter_ziel_status(self):
        """Ein Fahrzeug alarmiert, ein anderes in Bereitschaft."""
        r = self.client.post("/admin/alarmierungsplan", data={
            "alarmierungstyp_id": self.at.id,
            "territorium_id": self.t.id,
            "fahrzeug_eintraege": [
                f"{self.f1.id}:alarmiert",
                f"{self.f2.id}:bereitschaft",
            ],
        })
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        ep = db.query(Alarmierungsplan).filter_by(
            alarmierungstyp_id=self.at.id, territorium_id=self.t.id
        ).first()
        db.close()

        self._start_alarm(self.at.id, ep.id)
        db = TestSessionLocal()
        self.assertEqual(db.get(Fahrzeug, self.f1.id).status, "alarmiert")
        self.assertEqual(db.get(Fahrzeug, self.f2.id).status, "bereitschaft")
        db.close()

    def test_ziel_status_in_einsatzplaene_api(self):
        """Die /api/.../einsatzplaene Antwort enthält ziel_status je Fahrzeug."""
        r = self.client.post("/admin/alarmierungsplan", data={
            "alarmierungstyp_id": self.at.id,
            "territorium_id": self.t.id,
            "fahrzeug_eintraege": [
                f"{self.f1.id}:alarmiert",
                f"{self.f2.id}:bereitschaft",
            ],
        })
        self.assertEqual(r.status_code, 200)
        r2 = self.client.get(f"/api/alarmierungstyp/{self.at.id}/einsatzplaene")
        self.assertEqual(r2.status_code, 200)
        fzg = r2.json()[0]["fahrzeuge"]
        stati = {f["name"]: f["ziel_status"] for f in fzg}
        self.assertEqual(stati["TLF 1"], "alarmiert")
        self.assertEqual(stati["HLF 2"], "bereitschaft")

    def test_ersatz_erbt_ziel_status_des_originals(self):
        """Ersatzfahrzeug übernimmt den ziel_status des ausgefallenen Fahrzeugs."""
        ersatz = self._create_fahrzeug("ELW 1")
        # f1 als nicht einsatzbereit markieren
        db = TestSessionLocal()
        f1 = db.get(Fahrzeug, self.f1.id)
        f1.status = "nicht_einsatzbereit"
        f1.ersatzfahrzeuge = [db.get(Fahrzeug, ersatz.id)]
        db.commit()
        db.close()

        r = self.client.post("/admin/alarmierungsplan", data={
            "alarmierungstyp_id": self.at.id,
            "territorium_id": self.t.id,
            "fahrzeug_eintraege": [f"{self.f1.id}:bereitschaft"],
        })
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        ep = db.query(Alarmierungsplan).filter_by(
            alarmierungstyp_id=self.at.id, territorium_id=self.t.id
        ).first()
        db.close()

        self._start_alarm(self.at.id, ep.id)
        db = TestSessionLocal()
        self.assertEqual(db.get(Fahrzeug, ersatz.id).status, "bereitschaft")
        db.close()


# ─── Neue Tests: Stichwort-Referenzschutz ────────────────────────────────────

class TestStichwortReferenzschutz(BaseTestCase):
    """Prüft, dass referenzierte Stichworte beim Bearbeiten nicht gelöscht werden."""

    def setUp(self):
        super().setUp()
        self.at = self._create_alarmierungstyp("BRAND", stichworte="B1\nB2")
        self.t  = self._create_territorium("Mitte")
        db = TestSessionLocal()
        stichworte = db.query(Alarmierungsstichwort).filter_by(
            alarmierungstyp_id=self.at.id
        ).all()
        self.sw_b1 = next(s for s in stichworte if s.text == "B1")
        self.sw_b2 = next(s for s in stichworte if s.text == "B2")
        db.close()

    def test_referenziertes_stichwort_bleibt_erhalten(self):
        """Stichwort B1 ist in einem Plan → darf nicht gelöscht werden."""
        self.client.post("/admin/alarmierungsplan", data={
            "alarmierungstyp_id": self.at.id,
            "stichwort_id": self.sw_b1.id,
            "territorium_id": self.t.id,
        })
        # Bearbeiten: B1 aus der Liste entfernen, nur B2 behalten
        r = self.client.put(f"/admin/alarmierungstyp/{self.at.id}", data={
            "name": "BRAND",
            "stichworte": f"{self.sw_b2.id}:B2",
        })
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        verbleibend = [s.text for s in db.query(Alarmierungsstichwort).filter_by(
            alarmierungstyp_id=self.at.id
        ).all()]
        db.close()
        self.assertIn("B1", verbleibend, "Referenziertes Stichwort muss erhalten bleiben")
        self.assertIn("B2", verbleibend)

    def test_nicht_referenziertes_stichwort_wird_geloescht(self):
        """Stichwort B2 ist nicht referenziert → wird beim Bearbeiten entfernt."""
        # Nur B1 in Plan verwenden
        self.client.post("/admin/alarmierungsplan", data={
            "alarmierungstyp_id": self.at.id,
            "stichwort_id": self.sw_b1.id,
            "territorium_id": self.t.id,
        })
        # Bearbeiten: nur B1 behalten, B2 entfernen
        r = self.client.put(f"/admin/alarmierungstyp/{self.at.id}", data={
            "name": "BRAND",
            "stichworte": f"{self.sw_b1.id}:B1",
        })
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        verbleibend = [s.text for s in db.query(Alarmierungsstichwort).filter_by(
            alarmierungstyp_id=self.at.id
        ).all()]
        db.close()
        self.assertNotIn("B2", verbleibend, "Nicht referenziertes Stichwort muss gelöscht werden")

    def test_stichwort_umbenennen(self):
        """Umbenennen eines Stichwortes per id:text Format."""
        r = self.client.put(f"/admin/alarmierungstyp/{self.at.id}", data={
            "name": "BRAND",
            "stichworte": f"{self.sw_b1.id}:B1-NEU\n{self.sw_b2.id}:B2",
        })
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        sw = db.get(Alarmierungsstichwort, self.sw_b1.id)
        db.close()
        self.assertEqual(sw.text, "B1-NEU")


# ─── Neue Tests: Datenverwaltung ─────────────────────────────────────────────

class TestDatenverwaltung(BaseTestCase):
    """Prüft Export, Import und Reset der Datenverwaltung."""

    def setUp(self):
        super().setUp()
        self.g  = self._create_gruppe("Gruppe A")
        self.t  = self._create_territorium("Mitte")
        self.at = self._create_alarmierungstyp("BRAND", stichworte="B1")
        self.f1 = self._create_fahrzeug("TLF 1", gruppe_id=self.g.id)

    def test_export_gibt_json_zurueck(self):
        r = self.client.get("/admin/datenverwaltung/export")
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/json", r.headers.get("content-type", ""))
        data = r.json()
        self.assertEqual(data["version"], 1)
        self.assertIn("fahrzeuge", data)
        self.assertIn("gruppen", data)
        self.assertIn("territorien", data)
        self.assertIn("alarmierungstypen", data)
        self.assertIn("alarmierungsplaene", data)

    def test_export_enthaelt_stammdaten(self):
        r = self.client.get("/admin/datenverwaltung/export")
        data = r.json()
        namen_fzg = [f["name"] for f in data["fahrzeuge"]]
        self.assertIn("TLF 1", namen_fzg)
        namen_at = [a["name"] for a in data["alarmierungstypen"]]
        self.assertIn("BRAND", namen_at)
        namen_ter = [t["name"] for t in data["territorien"]]
        self.assertIn("Mitte", namen_ter)

    def test_export_enthaelt_stichworte(self):
        r = self.client.get("/admin/datenverwaltung/export")
        data = r.json()
        at = next(a for a in data["alarmierungstypen"] if a["name"] == "BRAND")
        self.assertEqual(len(at["stichworte"]), 1)
        self.assertEqual(at["stichworte"][0]["text"], "B1")

    def test_export_enthaelt_ziel_status(self):
        """Exportierte Alarmierungspläne enthalten fahrzeug_eintraege mit ziel_status."""
        self.client.post("/admin/alarmierungsplan", data={
            "alarmierungstyp_id": self.at.id,
            "territorium_id": self.t.id,
            "fahrzeug_eintraege": [f"{self.f1.id}:bereitschaft"],
        })
        r = self.client.get("/admin/datenverwaltung/export")
        data = r.json()
        self.assertEqual(len(data["alarmierungsplaene"]), 1)
        eintraege = data["alarmierungsplaene"][0]["fahrzeug_eintraege"]
        self.assertTrue(any("bereitschaft" in e for e in eintraege))

    def test_import_legt_neue_eintraege_an(self):
        """Import einer gültigen JSON-Datei legt fehlende Einträge an."""
        import json, io
        payload = {
            "version": 1,
            "gruppen": [{"id": 99, "name": "Import-Gruppe", "position": 0}],
            "territorien": [{"id": 99, "name": "Import-Territorium"}],
            "fahrzeuge": [
                {"id": 99, "name": "Import-Fahrzeug", "typ": "LF",
                 "status": "einsatzbereit", "position": 0,
                 "gruppe_id": 99, "ersatz_ids": []}
            ],
            "alarmierungstypen": [
                {"id": 99, "name": "Import-AT",
                 "stichworte": [{"id": 99, "text": "IMP1"}]}
            ],
            "alarmierungsplaene": [],
        }
        file_bytes = json.dumps(payload).encode()
        r = self.client.post(
            "/admin/datenverwaltung/import",
            files={"file": ("import.json", io.BytesIO(file_bytes), "application/json")},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        db = TestSessionLocal()
        self.assertIsNotNone(db.query(FahrzeugGruppe).filter_by(name="Import-Gruppe").first())
        self.assertIsNotNone(db.query(Fahrzeug).filter_by(name="Import-Fahrzeug").first())
        self.assertIsNotNone(db.query(Alarmierungstyp).filter_by(name="Import-AT").first())
        db.close()

    def test_import_dupliziert_keine_bestehenden_eintraege(self):
        """Import überspringt Einträge, die bereits vorhanden sind (Name-Dedup)."""
        import json, io
        payload = {
            "version": 1,
            "gruppen": [],
            "territorien": [{"id": 1, "name": "Mitte"}],  # bereits vorhanden
            "fahrzeuge": [],
            "alarmierungstypen": [],
            "alarmierungsplaene": [],
        }
        file_bytes = json.dumps(payload).encode()
        self.client.post(
            "/admin/datenverwaltung/import",
            files={"file": ("import.json", io.BytesIO(file_bytes), "application/json")},
        )
        db = TestSessionLocal()
        count = db.query(Territorium).filter_by(name="Mitte").count()
        db.close()
        self.assertEqual(count, 1, "Kein doppelter Eintrag nach Import")

    def test_import_ungueltige_datei_gibt_400(self):
        import io
        r = self.client.post(
            "/admin/datenverwaltung/import",
            files={"file": ("bad.json", io.BytesIO(b"kein json"), "application/json")},
        )
        self.assertEqual(r.status_code, 400)

    def test_import_falsches_format_gibt_400(self):
        import json, io
        r = self.client.post(
            "/admin/datenverwaltung/import",
            files={"file": ("bad.json", io.BytesIO(json.dumps({"version": 99}).encode()), "application/json")},
        )
        self.assertEqual(r.status_code, 400)

    def test_reset_loescht_alle_daten(self):
        """Reset entfernt alle Datensätze aus allen Tabellen."""
        r = self.client.post("/admin/datenverwaltung/reset")
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        self.assertEqual(db.query(Fahrzeug).count(), 0)
        self.assertEqual(db.query(FahrzeugGruppe).count(), 0)
        self.assertEqual(db.query(Territorium).count(), 0)
        self.assertEqual(db.query(Alarmierungstyp).count(), 0)
        self.assertEqual(db.query(Alarmierungsstichwort).count(), 0)
        self.assertEqual(db.query(Alarmierungsplan).count(), 0)
        db.close()


# ─── Neue Tests: fehlende Lücken ─────────────────────────────────────────────

class TestFehlendeLuecken(BaseTestCase):
    """Sammelt noch nicht abgedeckte Edge Cases."""

    def setUp(self):
        super().setUp()
        self.at = self._create_alarmierungstyp("THL")
        self.t  = self._create_territorium("Süd")
        self.f1 = self._create_fahrzeug("RW 1")
        self.f2 = self._create_fahrzeug("GW-L 1")

    # ── Gruppe move_down ──────────────────────────────────────────────────────

    def test_gruppe_move_down(self):
        g1 = self._create_gruppe("Alpha")
        g2 = self._create_gruppe("Beta")
        db = TestSessionLocal()
        db.get(FahrzeugGruppe, g1.id).position = 0
        db.get(FahrzeugGruppe, g2.id).position = 1
        db.commit()
        db.close()
        r = self.client.post(f"/api/gruppe/{g1.id}/move", params={"direction": "down"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        db = TestSessionLocal()
        self.assertGreater(
            db.get(FahrzeugGruppe, g1.id).position,
            db.get(FahrzeugGruppe, g2.id).position,
        )
        db.close()

    # ── Alarm beenden setzt bereitschaft → einsatzbereit ─────────────────────

    def test_alarm_beenden_setzt_bereitschaft_zurueck(self):
        """Auch Fahrzeuge im Status bereitschaft werden nach Alarm-Ende zurückgesetzt."""
        ep = self._create_alarmierungsplan(
            self.at.id, self.t.id,
            fahrzeug_ids=[self.f1.id, self.f2.id],
        )
        self._start_alarm(self.at.id, ep.id)
        # f2 manuell auf bereitschaft setzen
        db = TestSessionLocal()
        db.get(Fahrzeug, self.f2.id).status = "bereitschaft"
        db.commit()
        db.close()
        self.client.post("/api/alarm/beenden")
        db = TestSessionLocal()
        self.assertEqual(db.get(Fahrzeug, self.f1.id).status, "einsatzbereit")
        self.assertEqual(db.get(Fahrzeug, self.f2.id).status, "einsatzbereit")
        db.close()

    # ── Fahrzeug-Löschung entfernt Eintrag aus Plan ───────────────────────────

    def test_fahrzeug_loeschen_entfernt_aus_plan(self):
        """Wird ein Fahrzeug gelöscht, verschwindet es aus dem Alarmierungsplan (CASCADE)."""
        ep = self._create_alarmierungsplan(
            self.at.id, self.t.id,
            fahrzeug_ids=[self.f1.id],
        )
        r = self.client.delete(f"/admin/fahrzeug/{self.f1.id}")
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        pf_count = db.query(AlarmierungsplanFahrzeug).filter_by(
            alarmierungsplan_id=ep.id,
            fahrzeug_id=self.f1.id,
        ).count()
        db.close()
        self.assertEqual(pf_count, 0)

    # ── Alarmierungsplan ohne Fahrzeuge anlegen ───────────────────────────────

    def test_alarmierungsplan_ohne_fahrzeuge_anlegen(self):
        """Ein Plan ohne Fahrzeuge ist zulässig."""
        r = self.client.post("/admin/alarmierungsplan", data={
            "alarmierungstyp_id": self.at.id,
            "territorium_id": self.t.id,
        })
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        ep = db.query(Alarmierungsplan).filter_by(
            alarmierungstyp_id=self.at.id, territorium_id=self.t.id,
        ).first()
        self.assertIsNotNone(ep)
        self.assertEqual(len(ep.plan_fahrzeuge), 0)
        db.close()

    # ── Export: Content-Disposition Header ───────────────────────────────────

    def test_export_content_disposition_header(self):
        """Export-Response enthält einen Content-Disposition attachment Header."""
        r = self.client.get("/admin/datenverwaltung/export")
        self.assertEqual(r.status_code, 200)
        cd = r.headers.get("content-disposition", "")
        self.assertIn("attachment", cd)
        self.assertIn(".json", cd)

    # ── Import: Plan mit Fahrzeugen und ziel_status ───────────────────────────

    def test_import_plan_mit_fahrzeugen_und_ziel_status(self):
        """Import legt Plan mit Fahrzeug-Zuordnung inkl. ziel_status korrekt an."""
        import json, io
        payload = {
            "version": 1,
            "gruppen": [],
            "territorien": [{"id": 1, "name": "Süd"}],
            "fahrzeuge": [
                {"id": 1, "name": "RW 1", "typ": "RW",
                 "status": "einsatzbereit", "position": 0,
                 "gruppe_id": None, "ersatz_ids": []},
            ],
            "alarmierungstypen": [
                {"id": 1, "name": "THL", "stichworte": []},
            ],
            "alarmierungsplaene": [
                {
                    "id": 1,
                    "alarmierungstyp_id": 1,
                    "stichwort_id": None,
                    "territorium_id": 1,
                    "ist_standard": False,
                    "fahrzeug_eintraege": ["1:bereitschaft"],
                }
            ],
        }
        # Reset first so IDs are clean
        self.client.post("/admin/datenverwaltung/reset")
        r = self.client.post(
            "/admin/datenverwaltung/import",
            files={"file": ("import.json", io.BytesIO(json.dumps(payload).encode()), "application/json")},
        )
        self.assertEqual(r.status_code, 200)
        db = TestSessionLocal()
        ep = db.query(Alarmierungsplan).first()
        self.assertIsNotNone(ep)
        self.assertEqual(len(ep.plan_fahrzeuge), 1)
        self.assertEqual(ep.plan_fahrzeuge[0].ziel_status, "bereitschaft")
        db.close()