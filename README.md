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

The prototype supports local accounts, Apple Health XML/ZIP import, encrypted
record storage, and descriptive summaries by metric and time period. It also
has an optional, encrypted self-report journal for activity, sleep, tobacco
use/second-hand exposure, alcohol, and a limited fruit-and-vegetable measure.
A local evidence guide links to public-health summaries of population-level
associations for those behavior domains. The guide does not score a person's
risk, infer causation, or generate personalized health advice. Accounts are
device-local and records are encrypted with a key derived from each account's
password. Passwords are not stored. Exact duplicate wearable and journal
entries are ignored and reported as duplicates.

This is not production-ready: it does not yet provide session management,
role-based access, recovery for forgotten passwords, or a security-reviewed
multi-user shared-device workflow. Losing an account password makes that
account's encrypted records unrecoverable. Do not use this prototype to store
clinical records or rely on its output for care decisions.

## Run locally

Requires Python 3.10 or newer.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The app listens on the local machine at <http://127.0.0.1:8000>. Keep the
`127.0.0.1` bind address: it prevents access from other machines on the
network. Open <http://127.0.0.1:8000> to create a local account, import an
Apple Health export, and view summaries. The app does not call external APIs or
load external page assets.

The supported input is Apple Health's `export.xml` or the original export ZIP
containing exactly one `export.xml`. Uploads are limited to 100 MiB and expanded
XML to 500 MiB; each import is limited to 250,000 numeric quantity records.
Non-quantity records (including category and workout records) are skipped.
Accepted values retain their type, unit, value, and timezone-normalized start
and end timestamps; unrelated source/device metadata is discarded.

The summaries group each metric by day, ISO week (Monday start), or month and
report count, average, minimum, and maximum, optionally constrained to a date
range. They describe imported data only and do not produce predictions or
medical advice.

Optional behavioral entries are manually reported for a selected date. They
are not populated from external services. Activity and sleep entries can be
compared with wearable summaries, but the app currently does not calculate a
combined personal health impact. The evidence guide is bundled with the app;
its source links are not fetched unless the user opens a link.

Use **Refresh my insights** to connect available signals to a WHO-style
determinant framework. Activity self-reports and selected activity measurements
are listed under behavioral/lifestyle factors. Health measurements such as
heart rate are shown separately as health indicators, not mislabeled as
determinants. Social/economic conditions, physical environment, health services,
and personal characteristics are marked “not collected” because this prototype
does not yet gather them. The map links behavioral domains to general,
population-level evidence; it does not infer an individual health impact or
causal relationship. It also summarizes the user's own recorded averages and,
when there are at least five matching dates, can show an exploratory
self-reported activity/step-count correlation. This is an observational
within-person comparison, not evidence that one measure caused another. The
framework description is informed by the
[WHO social determinants of health](https://www.who.int/health-topics/social-determinants-of-health)
overview.

By default, SQLite is created at `data/det_health.sqlite3`. Health record
payloads are encrypted before being written to SQLite using Fernet with a
per-account key derived by scrypt from the account password and a random salt.
The database stores a keyed fingerprint for exact duplicate detection; metric
types, units, values, and timestamps remain inside the encrypted payload. Set
`DET_HEALTH_DB` to choose another local database file, for example:

```sh
DET_HEALTH_DB=/path/to/local/det-health.sqlite3 uvicorn app.main:app --host 127.0.0.1
```

## Project structure

```text
.
├── app/
│   ├── apple_health.py   # Bounded, streaming Apple export parser
│   ├── database.py       # SQLite initialization
│   ├── determinants.py   # Signal-to-domain and health-indicator mappings
│   ├── evidence.py       # Locally bundled, source-linked evidence notes
│   ├── main.py           # Local UI, import, journal, and analysis endpoints
│   └── security.py       # Password KDF and record encryption helpers
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

1. Add additional import formats and richer quality checks.
2. Harden authentication, session handling, account recovery, and shared-device
   role-based access for patient, clinician, and administrator roles.
3. Add an audit log of who accessed what.
4. Add opt-in device-to-device synchronization with conflict handling.
