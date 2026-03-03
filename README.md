# 🔥 FFW Alarmmonitor

Webbasierte Alarmierungssoftware für Feuerwehren zur Verwaltung und Alarmierung von Fahrzeugen auf Basis von Alarmierungstypen und Alarmierungsplänen.

---

## Features

### Alarmübersicht (`/`)
- Übersicht aller Fahrzeuge, gruppiert nach Fahrzeuggruppen
- **4 Fahrzeugstatus** — per Klick auf die Karte wechselbar:
  - ⬜ **Einsatzbereit** (grau)
  - 🟢 **Alarmiert** (grün) — nur bei aktivem Alarm verfügbar
  - 🟡 **Bereitschaft** (gelb) — nur bei aktivem Alarm verfügbar
  - 🔴 **Nicht einsatzbereit** (rot)
- Alarmierungstyp aus der Seitenleiste auswählen → Alarm wird ausgelöst
- Ist ein Alarm aktiv, sind andere Alarmierungstypen gesperrt
- Drag & Drop Reihenfolge der Fahrzeuge anpassen (Button „⠿ Reihenfolge")
- Warnhinweise bei nicht verfügbaren Fahrzeugen ohne verfügbares Ersatzfahrzeug

#### Alarmauslösung mit Alarmierungsplänen
- **Kein Alarmierungsplan hinterlegt** → Alarm wird direkt ausgelöst
- **Genau ein Plan vorhanden** → Fahrzeuge des Plans werden sofort alarmiert
- **Mehrere Pläne vorhanden** → Modaler Auswahldialog erscheint:
  - Territorium-Auswahl (wenn mehrere Territorien in den Plänen hinterlegt)
  - Stichwort-Auswahl (wenn mehrere Stichworte in den Plänen hinterlegt)
  - Vorbelegt mit dem als Standard markierten Plan
  - Fahrzeugvorschau zeigt die tatsächlich alarmierten Fahrzeuge (inkl. Ersatz)
  - Warnungen für nicht verfügbare Fahrzeuge werden sofort angezeigt
  - **Automatische Alarmierung nach 10 Sekunden** — Countdown auf dem Alarmieren-Button; bei Auswahländerung startet der Countdown neu

### Einsatzübersicht (`/einsatz`)
- Separate Live-Ansicht für den aktiven Einsatz (z. B. auf Anzeigebildschirm)
- Zeigt Alarmierungstyp, Stichwort, Territorium und Alarmierungszeit
- Zeigt nur Fahrzeuge mit Status **Alarmiert** oder **Bereitschaft**
- Gruppierung nach Fahrzeuggruppen
- Warnhinweise für nicht verfügbare Fahrzeuge
- Aktualisiert sich automatisch **alle 5 Sekunden**

### Ersatzfahrzeuge
- Jedem Fahrzeug können ein oder mehrere Ersatzfahrzeuge zugeordnet werden
- Ist ein Fahrzeug beim Alarmauslösen **nicht einsatzbereit**, wird automatisch das erste verfügbare Ersatzfahrzeug alarmiert
- Fahrzeuge, die selbst Teil der Alarmierung sind, werden nicht als Ersatz berücksichtigt
- Jedes Ersatzfahrzeug kann nur einmal vergeben werden (kein Doppeleinsatz)
- Sind keine Ersatzfahrzeuge verfügbar, erscheint eine Sammelwarnung mit allen betroffenen Fahrzeugen

### Admin-Bereich (`/admin`)

Startet direkt auf der **Alarmierungspläne**-Übersicht.

**Alarmierungspläne** (`/admin/alarmierungsplaene`)
- Kombination aus Alarmierungstyp, optionalem Stichwort und Territorium
- Fahrzeuge dem Plan zuordnen (Mehrfachauswahl)
- Einen Plan als Standard markieren (automatisch vorausgewählt im Dialog)
- Jede Kombination (Alarmierungstyp + Stichwort + Territorium) ist eindeutig

**Fahrzeuge** (`/admin/fahrzeuge`)
- Name, Kennzeichen (optional), Funkkennung (optional), Typ
- Fahrzeuggruppe zuweisen
- Ersatzfahrzeuge aus dem Fahrzeugbestand auswählen

**Fahrzeuggruppen** (`/admin/gruppen`)
- Gruppen anlegen, umbenennen, löschen
- Reihenfolge der Gruppen mit ▲/▼-Buttons anpassen

**Territorien** (`/admin/territorien`)
- Territorien anlegen, umbenennen, löschen
- Wird ein Territorium gelöscht, werden alle zugehörigen Alarmierungspläne automatisch mitgelöscht

**Alarmierungstypen** (`/admin/alarmierungstypen`)
- Name und Beschreibung
- Alarmierungsstichworte pro Typ (eines pro Zeile)

---

## Datenmodell

```
fahrzeug_gruppen
  id, name (unique), position

territorien
  id, name (unique), beschreibung

fahrzeuge
  id, name, kennzeichen, funkkennung, typ
  status: einsatzbereit | alarmiert | bereitschaft | nicht_einsatzbereit
  position, gruppe_id → fahrzeug_gruppen

fahrzeug_ersatz              ← M:N self-referencing (Fahrzeug ↔ Ersatzfahrzeug)

alarmierungstypen
  id, name (unique), beschreibung

alarmierungsstichworte
  id, text, alarmierungstyp_id → alarmierungstypen (CASCADE)

einsatzplaene
  id, alarmierungstyp_id → alarmierungstypen (CASCADE)
  stichwort_id → alarmierungsstichworte (RESTRICT, nullable)
  territorium_id → territorien (CASCADE)
  ist_standard
  UNIQUE (alarmierungstyp_id, stichwort_id, territorium_id)

alarmierungsplan_fahrzeuge   ← M:N Alarmierungsplan ↔ Fahrzeug

aktiv_alarme
  id, alarmierungstyp_id, stichwort_id, territorium_id
  warnungen_json, erstellt_am, aktiv
```

---

## REST API

Die API ist vollständig REST-konform. Ressourcen werden über einheitliche Collection-URLs verwaltet:

| Methode | URL | Beschreibung |
|---|---|---|
| `GET` | `/` | Alarmübersicht |
| `GET` | `/alarm/{id}` | Alarmansicht für Alarmierungstyp |
| `GET` | `/einsatz` | Live-Einsatzübersicht |
| `GET` | `/api/einsatz` | Einsatzdaten als JSON |
| `GET` | `/api/alarmierungstyp/{id}/einsatzplaene` | Alarmierungspläne mit Fahrzeugvorschau |
| `GET` | `/api/alarmierungstyp/{id}/stichworte` | Stichworte eines Alarmierungstyps |
| `POST` | `/api/alarm/starten` | Alarm auslösen (JSON-Body) |
| `POST` | `/api/alarm/beenden` | Aktiven Alarm beenden |
| `POST` | `/api/fahrzeug/status-toggle` | Fahrzeugstatus wechseln (JSON-Body) |
| `POST` | `/api/fahrzeug/reihenfolge` | Reihenfolge speichern (JSON-Body) |
| `POST` | `/api/gruppe/{id}/move` | Gruppenreihenfolge anpassen |
| `GET` | `/admin` | → Weiterleitung auf `/admin/alarmierungsplaene` |
| `GET` | `/admin/fahrzeuge` | Admin-Ansicht Fahrzeuge |
| `POST` | `/admin/fahrzeuge` | Fahrzeug anlegen |
| `PUT` | `/admin/fahrzeug/{id}` | Fahrzeug bearbeiten |
| `DELETE` | `/admin/fahrzeug/{id}` | Fahrzeug löschen |
| `GET` | `/admin/gruppen` | Admin-Ansicht Gruppen |
| `POST` | `/admin/gruppen` | Gruppe anlegen |
| `PUT` | `/admin/gruppe/{id}` | Gruppe bearbeiten |
| `DELETE` | `/admin/gruppe/{id}` | Gruppe löschen |
| `GET` | `/admin/territorien` | Admin-Ansicht Territorien |
| `POST` | `/admin/territorien` | Territorium anlegen |
| `PUT` | `/admin/territorium/{id}` | Territorium bearbeiten |
| `DELETE` | `/admin/territorium/{id}` | Territorium löschen |
| `GET` | `/admin/alarmierungsplaene` | Admin-Ansicht Alarmierungspläne |
| `POST` | `/admin/alarmierungsplaene` | Alarmierungsplan anlegen |
| `PUT` | `/admin/alarmierungsplan/{id}` | Alarmierungsplan bearbeiten |
| `DELETE` | `/admin/alarmierungsplan/{id}` | Alarmierungsplan löschen |
| `GET` | `/admin/alarmierungstypen` | Admin-Ansicht Alarmierungstypen |
| `POST` | `/admin/alarmierungstypen` | Alarmierungstyp anlegen |
| `PUT` | `/admin/alarmierungstyp/{id}` | Alarmierungstyp bearbeiten |
| `DELETE` | `/admin/alarmierungstyp/{id}` | Alarmierungstyp löschen |

Alle schreibenden Endpunkte geben `{"ok": true}` zurück. Fehler werden als HTTP-Statuscodes signalisiert (404 bei nicht gefundener Ressource, 400/409 bei Konflikten).

---

## Technologie

| Komponente | Version |
|---|---|
| Python | 3.11 |
| FastAPI | 0.115 |
| SQLAlchemy | 2.0 |
| Jinja2 | 3.1 |
| PostgreSQL | 16 |
| Uvicorn | 0.30 |
| SortableJS (CDN) | 1.15.2 |

---

## Installation & Start

### Voraussetzungen
- [Docker](https://docs.docker.com/get-docker/) und Docker Compose

### Start

```bash
docker compose up -d --build
```

Die App ist danach unter **http://localhost:8000** erreichbar.

### Stopp

```bash
docker compose down
```

Daten bleiben im Docker-Volume `postgres_data` erhalten.

### Daten zurücksetzen

```bash
docker compose down -v && docker compose up -d --build
```

---

## Tests

Unit-Tests für alle API-Endpunkte befinden sich in `tests/test_api.py`. Sie verwenden `unittest` mit FastAPIs `TestClient` und einer SQLite-In-Memory-Datenbank — es wird keine laufende PostgreSQL-Instanz benötigt.

### Abhängigkeiten installieren

```bash
pip install fastapi httpx sqlalchemy jinja2 python-multipart
```

### Tests ausführen

```bash
# Mit pytest (empfohlen):
python -m pytest tests/test_api.py -v

# Mit unittest:
python -m unittest tests.test_api -v
```

### Testabdeckung

62 Tests in 10 Testklassen:

| Testklasse | Beschreibung |
|---|---|
| `TestFahrzeugeAPI` | CRUD Fahrzeuge, Gruppenzuweisung |
| `TestGruppenAPI` | CRUD Gruppen, Reihenfolge verschieben |
| `TestTerritorienAPI` | CRUD Territorien |
| `TestAlarmierungstypenAPI` | CRUD Alarmierungstypen, Stichwort-API |
| `TestAlarmierungsplaeneAPI` | CRUD Pläne, Duplikat-Prüfung, Standard-Reset, Fahrzeugvorschau |
| `TestAlarmAPI` | Alarm starten/beenden, Fahrzeugstatus, Warnungen, Persistenz |
| `TestFahrzeugStatusToggle` | Statuszyklus mit und ohne aktiven Alarm |
| `TestReihenfolgeAPI` | Fahrzeug-Reihenfolge speichern |
| `TestEinsatzAPI` | Einsatzdaten-API, Gruppenstruktur, Warnungen |
| `TestErsatzfahrzeugLogik` | Kein Doppeleinsatz, Plan-Ausschluss, Sammelwarnung |

---

## Projektstruktur

```
feuerwehr-app/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
├── tests/
│   └── test_api.py       # Unit-Tests (62 Tests)
└── app/
    ├── main.py
    └── templates/
        ├── index.html    # Alarmübersicht
        ├── einsatz.html  # Live-Einsatzübersicht
        └── admin.html    # Admin-Bereich
```