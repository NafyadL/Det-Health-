# Det(Health)

A local-first prototype for keeping and exploring personal wearable data on the
device where it is used. It is motivated by shared-device clinical settings
where reliable internet, cloud services, and dedicated IT support may not be
available.

## Design principles

- **Offline by design:** data will enter through local file imports, not wearable
  cloud APIs or external services.
- **Private by default:** the target is encryption at rest with keys derived
  from each user's password.
- **Shared-device aware:** the roadmap includes multiple users, role-based
  access, and an audit trail.
- **Descriptive, not diagnostic:** the app will show trends, averages, and
  changes over time. It will not predict health outcomes or give medical advice.

## Current status

This repository is an early application scaffold. It has a FastAPI app, a local
SQLite database bootstrap, and a database readiness endpoint. The database
currently stores only a schema-version marker; health records, authentication,
encryption, imports, and role-based access are **not implemented yet**. Do not
use this prototype to store real health data.

## Run locally

Requires Python 3.10 or newer.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The app listens on the local machine at <http://127.0.0.1:8000>. Check
<http://127.0.0.1:8000/health> to confirm the app can read its SQLite schema
metadata. The OpenAPI schema is available locally at
<http://127.0.0.1:8000/openapi.json>; hosted Swagger/ReDoc pages are disabled
to avoid loading documentation assets from a CDN.

By default, SQLite is created at `data/det_health.sqlite3`. Set
`DET_HEALTH_DB` to choose another local database file, for example:

```sh
DET_HEALTH_DB=/path/to/local/det-health.sqlite3 uvicorn app.main:app --host 127.0.0.1
```

## Project structure

```text
.
├── app/
│   ├── database.py       # SQLite initialization and readiness check
│   └── main.py           # FastAPI app and /health endpoint
├── tests/
│   └── test_main.py      # Local app smoke test
├── main.py               # Optional `uvicorn main:app` entry point
├── requirements.txt
└── requirements-dev.txt
```

Run the tests with:

```sh
pytest
```

## Roadmap

1. Import one wearable export format from a local file (initial candidate:
   Apple Health XML or a Fitbit CSV export).
2. Add password-derived encryption before health records are written to SQLite.
3. Add per-device users and authentication, then role-based visibility for
   patient, clinician, and administrator roles.
4. Present descriptive trends over time without diagnostic claims.
5. Add an audit log and, later, opt-in device-to-device sync with conflict
   handling.

Encryption and authentication are prerequisites to persisting real health
records; until then, this project is a development scaffold, not a clinical
tool.
