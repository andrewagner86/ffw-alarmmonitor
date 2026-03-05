# 🔥 Feuerwehr Alarmierungs-App

Webbasierte Alarmierungssoftware für Feuerwehren zur Verwaltung und Alarmierung von Fahrzeugen auf Basis von Alarmierungstypen und Alarmierungsplänen.

[![Test, Build & Publish](https://github.com/andrewagner86/ffw-alarmmonitor/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/andrewagner86/ffw-alarmmonitor/actions/workflows/docker-publish.yml)
[![Docker Hub](https://img.shields.io/docker/v/andrewagner86/ffw-alarmmonitor?label=Docker%20Hub)](https://hub.docker.com/r/andrewagner86/ffw-alarmmonitor)

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
- **Drag & Drop** Reihenfolge der Fahrzeuge anpassen (Button „⠿ Reihenfolge") — nur innerhalb der Fahrzeuggruppe
- Warnhinweise bei nicht verfügbaren Fahrzeugen ohne verfügbares Ersatzfahrzeug
- **Konfigurierbare Darstellung** der Fahrzeuggruppen (siehe Einstellungen)

#### Alarmauslösung mit Alarmierungsplänen
- **Kein Alarmierungsplan hinterlegt** → Alarm wird direkt ausgelöst
- **Genau ein Plan vorhanden** → Fahrzeuge des Plans werden sofort alarmiert
- **Mehrere Pläne vorhanden** → Modaler Auswahldialog erscheint:
  - Territorium-Auswahl (wenn mehrere Territorien in den Plänen hinterlegt)
  - Stichwort-Auswahl (wenn mehrere Stichworte in den Plänen hinterlegt)
  - Vorbelegt mit dem als Standard markierten Plan
  - Fahrzeugvorschau zeigt die tatsächlich alarmierten Fahrzeuge (inkl. Ersatz)
  - Farbkodierung: 🟢 grün = Alarmiert, 🟡 gelb = Bereitschaft
  - Warnungen für nicht verfügbare Fahrzeuge werden sofort angezeigt
  - **Automatische Alarmierung nach 10 Sekunden** — Countdown auf dem Alarmieren-Button; bei Auswahländerung startet der Countdown neu

### Einsatzübersicht (`/einsatz`)
- Separate Live-Ansicht für den aktiven Einsatz (z. B. auf Anzeigebildschirm)
- Zeigt Alarmierungstyp, Stichwort, Territorium und Alarmierungszeit
- Zeigt nur Fahrzeuge mit Status **Alarmiert** oder **Bereitschaft**
- Gruppierung nach Fahrzeuggruppen
- Warnhinweise für nicht verfügbare Fahrzeuge
- Aktualisiert sich automatisch via **Server-Sent Events** (kein Polling)
- **Konfigurierbare Darstellung** der Fahrzeuggruppen (siehe Einstellungen)

### Echtzeit-Updates (Server-Sent Events)
- Alarmübersicht und Einsatzübersicht werden sofort aktualisiert wenn sich der Alarmstatus oder ein Fahrzeugstatus ändert
- Keep-Alive alle 25 Sekunden, automatische Wiederverbindung nach Verbindungsabbruch
- Lokale DOM-Änderungen (eigener Client) werden nicht doppelt neu geladen

### Ersatzfahrzeuge
- Jedem Fahrzeug können ein oder mehrere Ersatzfahrzeuge zugeordnet werden
- Ist ein Fahrzeug beim Alarmauslösen **nicht einsatzbereit**, wird automatisch das erste verfügbare Ersatzfahrzeug alarmiert
- Fahrzeuge, die selbst Teil der Alarmierung sind, werden nicht als Ersatz berücksichtigt
- Jedes Ersatzfahrzeug kann nur einmal vergeben werden (kein Doppeleinsatz)
- Sind keine Ersatzfahrzeuge verfügbar, erscheint eine Sammelwarnung mit allen betroffenen Fahrzeugen

### Admin-Bereich (`/admin`)

Startet direkt auf der **Alarmierungspläne**-Übersicht. Fehlermeldungen aus dem Backend werden direkt im Formular angezeigt.

**Alarmierungspläne** (`/admin/alarmierungsplan`)
- Kombination aus Alarmierungstyp, optionalem Stichwort und Territorium
- Fahrzeuge dem Plan zuordnen mit visuellem Tag-Picker (klicken zum Durchschalten)
- Pro Fahrzeug kann der Zielstatus festgelegt werden: 🟢 **Alarmiert** oder 🟡 **Bereitschaft**
- Einen Plan als Standard markieren (automatisch vorausgewählt im Dialog)
- Jede Kombination (Alarmierungstyp + Stichwort + Territorium) ist eindeutig

**Fahrzeuge** (`/admin/fahrzeug`)
- Name, Kennzeichen (optional), Funkkennung (optional), Typ
- Fahrzeuggruppe zuweisen
- Ersatzfahrzeuge aus dem Fahrzeugbestand auswählen (alphabetisch sortiert)

**Fahrzeuggruppen** (`/admin/gruppe`)
- Gruppen anlegen, umbenennen, löschen
- Reihenfolge der Gruppen mit ▲/▼-Buttons anpassen

**Territorien** (`/admin/territorium`)
- Territorien anlegen, umbenennen, löschen
- Wird ein Territorium gelöscht, werden alle zugehörigen Alarmierungspläne automatisch mitgelöscht

**Alarmierungstypen** (`/admin/alarmierungstyp`)
- Name und Beschreibung
- Alarmierungsstichworte pro Typ (eines pro Zeile)
- Umbenennen von Stichworten wird unterstützt — referenzierte Stichworte (in Alarmierungsplänen verwendet) werden beim Bearbeiten nicht gelöscht

**Datenverwaltung** (`/admin/datenverwaltung`)
- **Export**: Alle Stammdaten als JSON-Datei herunterladen
- **Import**: Zuvor exportierte JSON-Datei einlesen; bestehende Daten bleiben erhalten, nur neue Einträge werden hinzugefügt
- **Zurücksetzen**: Alle erfassten Daten nach doppelter Sicherheitsabfrage löschen

**Einstellungen** (`/admin/einstellungen`)
- Darstellung der Fahrzeuggruppen separat für Alarmübersicht und Einsatzübersicht konfigurierbar
- **Fahrzeuggruppendarstellung**: `↕ Vertikal` (Gruppen übereinander) oder `↔ Horizontal` (Gruppen nebeneinander)
- **Unterteilungen** (1–5): Bei vertikaler Darstellung die Anzahl der Spalten, bei horizontaler Darstellung die Anzahl der Zeilen
- Einstellungen für Alarmübersicht und Einsatzübersicht sind unabhängig voneinander

---

## Darstellungsmodi

### Vertikal (Standard)
Fahrzeuggruppen werden in Spalten untereinander angeordnet. Die Anzahl der Spalten wird über **Unterteilungen** gesteuert. Gruppen werden spaltenweise verteilt.

Beispiel: 6 Gruppen, 2 Unterteilungen → je 3 Gruppen pro Spalte nebeneinander.

### Horizontal
Fahrzeuggruppen werden in Zeilen nebeneinander angeordnet. Die Anzahl der Zeilen wird über **Unterteilungen** gesteuert.

Beispiel: 6 Gruppen, 2 Unterteilungen → 2 Zeilen mit je 3 Gruppen nebeneinander.

In beiden Modi sind nebeneinander liegende Gruppen-Header immer gleich hoch; übereinanderliegende Gruppen haben stets dieselbe Breite. Fahrzeugkarten innerhalb einer Gruppe sind ebenfalls einheitlich hoch — auch wenn Kennzeichen oder Funkkennung fehlen.

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
  stichwort_id            → alarmierungsstichworte (RESTRICT, nullable)
  territorium_id          → territorien (CASCADE)
  ist_standard
  UNIQUE (alarmierungstyp_id, stichwort_id, territorium_id)

alarmierungsplan_fahrzeuge   ← M:N Alarmierungsplan ↔ Fahrzeug
  alarmierungsplan_id, fahrzeug_id, ziel_status (alarmiert | bereitschaft)

aktiv_alarme
  id, alarmierungstyp_id, stichwort_id, territorium_id
  warnungen_json, erstellt_am, aktiv

einstellungen
  schluessel (PK), wert
  Schlüssel: einsatz_darstellung, einsatz_unterteilungen,
             alarm_darstellung,   alarm_unterteilungen
```

---

## REST API

Alle Ressourcen werden über einheitliche Singular-URLs verwaltet.

| Methode | URL | Beschreibung |
|---|---|---|
| `GET` | `/` | Alarmübersicht |
| `GET` | `/alarm/{typ_id}` | Alarmübersicht mit aktivem Alarm |
| `GET` | `/einsatz` | Live-Einsatzübersicht |
| `GET` | `/api/einsatz` | Einsatzdaten als JSON |
| `GET` | `/api/einsatz/stream` | Server-Sent Events Stream |
| `GET` | `/api/alarmierungstyp/{id}/einsatzplaene` | Alarmierungspläne mit Fahrzeugvorschau |
| `GET` | `/api/alarmierungstyp/{id}/stichworte` | Stichworte eines Alarmierungstyps |
| `POST` | `/api/alarm/starten` | Alarm auslösen (JSON-Body) |
| `POST` | `/api/alarm/beenden` | Aktiven Alarm beenden |
| `POST` | `/api/fahrzeug/status-toggle` | Fahrzeugstatus wechseln (JSON-Body) |
| `POST` | `/api/fahrzeug/reihenfolge` | Reihenfolge speichern (JSON-Body) |
| `POST` | `/api/gruppe/{id}/move` | Gruppenreihenfolge anpassen |
| `GET` | `/admin` | → Weiterleitung auf `/admin/alarmierungsplan` |
| `GET` | `/admin/fahrzeug` | Admin-Ansicht Fahrzeuge |
| `POST` | `/admin/fahrzeug` | Fahrzeug anlegen |
| `PUT` | `/admin/fahrzeug/{id}` | Fahrzeug bearbeiten |
| `DELETE` | `/admin/fahrzeug/{id}` | Fahrzeug löschen |
| `GET` | `/admin/gruppe` | Admin-Ansicht Gruppen |
| `POST` | `/admin/gruppe` | Gruppe anlegen |
| `PUT` | `/admin/gruppe/{id}` | Gruppe bearbeiten |
| `DELETE` | `/admin/gruppe/{id}` | Gruppe löschen |
| `GET` | `/admin/territorium` | Admin-Ansicht Territorien |
| `POST` | `/admin/territorium` | Territorium anlegen |
| `PUT` | `/admin/territorium/{id}` | Territorium bearbeiten |
| `DELETE` | `/admin/territorium/{id}` | Territorium löschen |
| `GET` | `/admin/alarmierungsplan` | Admin-Ansicht Alarmierungspläne |
| `POST` | `/admin/alarmierungsplan` | Alarmierungsplan anlegen |
| `PUT` | `/admin/alarmierungsplan/{id}` | Alarmierungsplan bearbeiten |
| `DELETE` | `/admin/alarmierungsplan/{id}` | Alarmierungsplan löschen |
| `GET` | `/admin/alarmierungstyp` | Admin-Ansicht Alarmierungstypen |
| `POST` | `/admin/alarmierungstyp` | Alarmierungstyp anlegen |
| `PUT` | `/admin/alarmierungstyp/{id}` | Alarmierungstyp bearbeiten |
| `DELETE` | `/admin/alarmierungstyp/{id}` | Alarmierungstyp löschen |
| `GET` | `/admin/datenverwaltung` | Datenverwaltung |
| `GET` | `/admin/datenverwaltung/export` | Datenexport als JSON-Datei |
| `POST` | `/admin/datenverwaltung/import` | Datenimport aus JSON-Datei |
| `POST` | `/admin/datenverwaltung/reset` | Alle Daten löschen |
| `GET` | `/admin/einstellungen` | Einstellungen-Ansicht |
| `POST` | `/admin/einstellungen` | Einstellungen speichern |

Alle schreibenden Endpunkte geben `{"ok": true}` zurück. Fehler werden als HTTP-Statuscodes mit `{"detail": "..."}` signalisiert.

---

## Technologie

| Komponente | Version |
|---|---|
| Python | 3.12 |
| FastAPI | 0.115 |
| SQLAlchemy | 2.0 |
| Jinja2 | 3.1 |
| PostgreSQL | 16 |
| Uvicorn | 0.30 |
| aiofiles | 23.2 |
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

Alternativ kann die Datenbank über den Admin-Bereich unter **Datenverwaltung → Datenbank zurücksetzen** geleert werden.

---

## CI/CD

Der GitHub Actions Workflow `.github/workflows/docker-publish.yml` führt bei jedem Push auf `main` und bei Pull Requests automatisch Folgendes aus:

1. **Tests** — alle Unit-Tests werden mit pytest ausgeführt, Coverage-Report wird als Artefakt gespeichert
2. **Docker Build & Push** — Image wird gebaut und auf Docker Hub veröffentlicht (nur bei Push auf `main` oder bei versionierten Tags, nicht bei PRs)

### Tagging-Strategie

| Auslöser | Docker-Tags |
|---|---|
| Push auf `main` | `latest`, `sha-<commit>` |
| Git-Tag `v1.2.3` | `1.2.3`, `1.2`, `1`, `sha-<commit>` |
| Pull Request | kein Push, nur Test |

### Secrets einrichten

Im GitHub-Repository unter **Settings → Secrets and variables → Actions** müssen folgende Secrets hinterlegt werden:

| Secret | Inhalt |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub Benutzername |
| `DOCKERHUB_TOKEN` | Docker Hub Access Token (nicht das Passwort) |

---

## Tests

Unit-Tests für alle API-Endpunkte befinden sich in `tests/test_api.py`. Sie verwenden `unittest` mit FastAPIs `TestClient` und einer SQLite-In-Memory-Datenbank — es wird keine laufende PostgreSQL-Instanz benötigt.

### Abhängigkeiten installieren

```bash
pip install fastapi httpx sqlalchemy jinja2 python-multipart aiofiles pytest pytest-cov
```

### Tests ausführen

```bash
# Mit pytest (empfohlen):
python -m pytest tests/test_api.py -v

# Mit Coverage:
python -m pytest tests/test_api.py -v --cov=app --cov-report=term-missing

# Mit unittest:
python -m unittest tests.test_api -v
```

### Testabdeckung

89 Tests in 15 Testklassen:

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
| `TestEinsatzAPI` | Einsatzdaten-API, Gruppenstruktur, Warnungen, Einstellungsfelder |
| `TestErsatzfahrzeugLogik` | Kein Doppeleinsatz, Plan-Ausschluss, Sammelwarnung |
| `TestZielStatus` | Bereitschaft-Status, gemischter Zielstatus, Ersatz erbt Status |
| `TestStichwortReferenzschutz` | Referenzierte Stichworte bleiben erhalten, Umbenennung |
| `TestDatenverwaltung` | Export, Import, Reset, Zielstatus im Export |
| `TestFehlendeLuecken` | Gruppe move down, Bereitschaft-Reset, Plan-Fahrzeug-Kaskade |
| `TestEinstellungen` | Standardwerte, Speichern, Lesen, Validierung |

---

## Projektstruktur

```
ffw-alarmmonitor/
├── .github/
│   └── workflows/
│       └── docker-publish.yml  # CI/CD: Test → Build → Push
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
├── tests/
│   └── test_api.py             # Unit-Tests (89 Tests, SQLite in-memory)
└── app/
    ├── main.py                 # FastAPI-App, Routen, Datenbankmodelle
    ├── static/
    │   └── favicon.svg         # App-Icon
    └── templates/
        ├── index.html          # Alarmübersicht
        ├── einsatz.html        # Live-Einsatzübersicht
        └── admin.html          # Admin-Bereich
```