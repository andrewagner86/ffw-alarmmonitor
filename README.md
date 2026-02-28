# 🔥 Feuerwehr Fahrzeugauswahl

Web-Anwendung zur Fahrzeugauswahl bei Alarmierungen der Feuerwehr.

## Technologie-Stack

- **Backend**: Python / FastAPI
- **Datenbank**: PostgreSQL 16
- **Frontend**: Jinja2 Templates + Vanilla JS
- **Container**: Docker + Docker Compose

## Schnellstart

### Voraussetzungen
- Docker & Docker Compose installiert

### Starten

```bash
docker compose up --build
```

Die Anwendung ist danach erreichbar unter:

| URL | Beschreibung |
|-----|--------------|
| http://localhost:8000 | Alarmansicht (Einsatzkräfte) |
| http://localhost:8000/admin | Fahrzeuge verwalten |
| http://localhost:8000/admin/schlagworte | Schlagworte verwalten |

### Stoppen

```bash
docker compose down
```

Daten bleiben in einem Docker Volume erhalten.  
Zum vollständigen Löschen inkl. Daten:

```bash
docker compose down -v
```

---

## Konfiguration

### Umgebungsvariablen

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `DATABASE_URL` | `postgresql://...` | PostgreSQL-Verbindungsstring |

---

## Nutzung

### 1. Admin: Fahrzeuge anlegen
- Unter `/admin` Fahrzeuge mit Name, Kennzeichen, Typ anlegen
- Status "Einsatzfähig" per Toggle setzen

### 2. Admin: Schlagworte anlegen
- Unter `/admin/schlagworte` Alarmierungsschlagworte erstellen
- Fahrzeuge dem Schlagwort zuordnen

### 3. Alarmierung
- Unter `/` das Schlagwort auswählen
- Die zugeordneten Fahrzeuge werden angezeigt
- **Nicht einsatzfähige Fahrzeuge** sind sichtbar aber ausgegraut markiert

---

## Datenbankschema

```
fahrzeuge
├── id (PK)
├── name
├── kennzeichen
├── typ
└── einsatzfaehig (bool)

schlagworte
├── id (PK)
├── name
└── beschreibung

fahrzeug_schlagwort  (M:N)
├── fahrzeug_id (FK)
└── schlagwort_id (FK)
```
