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

alarmierungsplaene
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

## Routen-Übersicht

| Route | Beschreibung |
|---|---|
| `GET /` | Alarmübersicht (leitet bei aktivem Alarm weiter) |
| `GET /alarm/{id}` | Alarmansicht für Alarmierungstyp |
| `GET /einsatz` | Live-Einsatzübersicht |
| `GET /api/einsatz` | JSON-API für Einsatzübersicht |
| `GET /api/alarmierungstyp/{id}/einsatzplaene` | Alarmierungspläne mit Fahrzeugvorschau und Warnungen |
| `GET /api/alarmierungstyp/{id}/stichworte` | Stichworte eines Alarmierungstyps |
| `POST /api/alarm/starten` | Alarm auslösen (mit Ersatzfahrzeug-Logik) |
| `POST /api/alarm/beenden` | Aktiven Alarm beenden |
| `POST /api/fahrzeug/status-toggle` | Fahrzeugstatus wechseln |
| `POST /api/fahrzeug/reihenfolge` | Reihenfolge speichern |
| `POST /api/gruppe/{id}/move` | Gruppenreihenfolge anpassen |
| `GET /admin` | → Weiterleitung auf `/admin/alarmierungsplaene` |
| `GET /admin/alarmierungsplaene` | Admin: Alarmierungspläne |
| `GET /admin/fahrzeuge` | Admin: Fahrzeuge |
| `GET /admin/gruppen` | Admin: Fahrzeuggruppen |
| `GET /admin/territorien` | Admin: Territorien |
| `GET /admin/alarmierungstypen` | Admin: Alarmierungstypen |

---

## Projektstruktur

```
feuerwehr-app/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
└── app/
    ├── main.py
    └── templates/
        ├── index.html    # Alarmübersicht
        ├── einsatz.html  # Live-Einsatzübersicht
        └── admin.html    # Admin-Bereich
```