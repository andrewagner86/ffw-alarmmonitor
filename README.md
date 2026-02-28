# 🔥 FFW Alarmmonitor

Web-Anwendung zur Alarmierung und Fahrzeugverwaltung für Freiwillige Feuerwehren. Ermöglicht die Auswahl von Alarmstichworten, automatische Fahrzeugzuordnung, Live-Einsatzübersicht und Verwaltung aller Stammdaten.

## Technologie-Stack

- **Backend**: Python 3.12 / FastAPI
- **Datenbank**: PostgreSQL 16
- **Frontend**: Jinja2 Templates + Vanilla JS
- **Container**: Docker + Docker Compose

---

## Schnellstart

### Voraussetzungen

- Docker & Docker Compose installiert

### Starten

```bash
docker compose up --build
```

### Stoppen

```bash
docker compose down          # Daten bleiben erhalten
docker compose down -v       # Daten vollständig löschen
```

---

## Seiten & URLs

| URL | Beschreibung |
|-----|--------------|
| `http://localhost:8000` | Alarmierungsansicht |
| `http://localhost:8000/einsatz` | Live-Einsatzübersicht |
| `http://localhost:8000/admin` | Fahrzeuge verwalten |
| `http://localhost:8000/admin/gruppen` | Fahrzeuggruppen verwalten |
| `http://localhost:8000/admin/schlagworte` | Alarmschlagworte verwalten |

---

## Funktionsübersicht

### Alarmierungsansicht (`/`)

- Linke Sidebar mit allen Alarmstichworten
- Klick auf ein Stichwort löst Alarm aus:
  - Alle dem Stichwort zugeordneten, einsatzbereiten Fahrzeuge werden automatisch auf **Alarmiert** gesetzt
  - Nicht einsatzbereite Fahrzeuge werden ignoriert — sofern ein einsatzbereites **Ersatzfahrzeug** hinterlegt ist, wird dieses stattdessen alarmiert
  - Ist kein Ersatz verfügbar, erscheint ein Warnhinweis
- Alle Fahrzeuge bleiben sichtbar mit farbiger Statusanzeige
- **Status per Klick wechseln** (zyklisch):
  - Bei aktivem Alarm: Einsatzbereit → Alarmiert → Bereitschaft → Nicht einsatzbereit → …
  - Ohne Alarm: Einsatzbereit ↔ Nicht einsatzbereit
- Reihenfolge der Fahrzeuge per Drag & Drop anpassbar (Schalter „⠿ Reihenfolge")
- Ist ein Alarm aktiv, können keine weiteren Alarme ausgelöst werden — der laufende Alarm muss zuerst beendet werden
- „Alarm beenden" setzt alle alarmierten/in Bereitschaft befindlichen Fahrzeuge zurück auf Einsatzbereit

#### Fahrzeugstatus

| Farbe | Status | Bedeutung |
|-------|--------|-----------|
| Grau | Einsatzbereit | Fahrzeug verfügbar |
| Grün | Alarmiert | Fahrzeug im Einsatz |
| Gelb | Bereitschaft | Fahrzeug in Bereitschaft |
| Rot | Nicht einsatzbereit | Fahrzeug nicht verfügbar |

### Live-Einsatzübersicht (`/einsatz`)

- Zeigt alle Fahrzeuge mit Status **Alarmiert** oder **Bereitschaft**
- Gruppiert nach Fahrzeuggruppe
- Aktualisiert sich automatisch alle **5 Sekunden**
- Geeignet für separate Monitore im Feuerwehrhaus

### Admin: Fahrzeuge (`/admin`)

- Fahrzeuge anlegen und bearbeiten mit:
  - Name, Kennzeichen (optional), Funkkennung (optional), Typ
  - Fahrzeuggruppe
  - Ersatzfahrzeuge (bei Ausfall des Primärfahrzeugs)
- Übersicht aller Fahrzeuge mit Gruppe und zugeordneten Ersatzfahrzeugen

### Admin: Fahrzeuggruppen (`/admin/gruppen`)

- Gruppen anlegen und benennen
- Reihenfolge der Gruppen per ▲/▼-Schaltflächen festlegen
- Gruppen steuern die Darstellungsreihenfolge auf der Alarmierungs- und Einsatzansicht

### Admin: Alarmschlagworte (`/admin/schlagworte`)

- Schlagworte mit Name und optionaler Beschreibung anlegen
- Fahrzeuge dem Schlagwort zuordnen

---

## Datenbankschema

```
fahrzeug_gruppen
├── id (PK)
├── name
└── position

fahrzeuge
├── id (PK)
├── name
├── kennzeichen (optional)
├── funkkennung (optional)
├── typ
├── status  (einsatzbereit | alarmiert | bereitschaft | nicht_einsatzbereit)
├── position
└── gruppe_id (FK → fahrzeug_gruppen)

schlagworte
├── id (PK)
├── name
└── beschreibung

aktiv_alarme
├── id (PK)
├── schlagwort_id (FK → schlagworte)
├── erstellt_am
└── aktiv (bool)

fahrzeug_schlagwort  (M:N)
├── fahrzeug_id (FK)
└── schlagwort_id (FK)

fahrzeug_ersatz  (M:N self-referencing)
├── fahrzeug_id (FK → fahrzeuge)
└── ersatz_id   (FK → fahrzeuge)
```

---

## Konfiguration

| Variable | Standard | Beschreibung |
|----------|----------|--------------| 
| `DATABASE_URL` | `postgresql://feuerwehr:feuerwehr123@db:5432/feuerwehr` | PostgreSQL-Verbindungsstring |

---

## Empfohlene Ersteinrichtung

1. Anwendung starten: `docker compose up --build`
2. **Fahrzeuggruppen** anlegen unter `/admin/gruppen` (z. B. Löschzug, Hilfeleistung)
3. **Fahrzeuge** anlegen unter `/admin` — Gruppe und ggf. Ersatzfahrzeuge zuweisen
4. **Alarmschlagworte** anlegen unter `/admin/schlagworte` — Fahrzeuge zuordnen
5. Alarmierungsansicht unter `http://localhost:8000` aufrufen