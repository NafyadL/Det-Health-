import io
import sqlite3
import zipfile

from fastapi.testclient import TestClient

from app.main import create_app

USERNAME = "patient.one"
PASSWORD = "correct horse battery"


def _export_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
  <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch"
    unit="count/min" value="60" startDate="2025-01-01 08:00:00 -0500"
    endDate="2025-01-01 08:00:01 -0500" />
  <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch"
    unit="count/min" value="80" startDate="2025-01-01 09:00:00 -0500"
    endDate="2025-01-01 09:00:01 -0500" />
  <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch"
    unit="count/min" value="72" startDate="2025-01-02 08:00:00 -0500"
    endDate="2025-01-02 08:00:01 -0500" />
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="asleep"
    startDate="2025-01-01 22:00:00 -0500" endDate="2025-01-02 06:00:00 -0500" />
</HealthData>"""


def _create_account(client: TestClient) -> None:
    response = client.post(
        "/users", json={"username": USERNAME, "password": PASSWORD}
    )
    assert response.status_code == 201


def _import(client: TestClient, content: bytes, filename: str = "export.xml"):
    return client.post(
        "/imports/apple-health",
        data={"username": USERNAME, "password": PASSWORD},
        files={"file": (filename, content, "application/xml")},
    )


def test_health_check_initializes_local_database(tmp_path):
    database_path = tmp_path / "data" / "test.sqlite3"
    application = create_app(database_path)

    with TestClient(application) as client:
        response = client.get("/health")
        home_response = client.get("/")
        docs_response = client.get("/docs")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "storage": "sqlite"}
    assert "Import Apple Health export" in home_response.text
    assert "What your records show" in home_response.text
    assert "domain-grid" in home_response.text
    assert "not proof of a health effect" not in home_response.text
    assert docs_response.status_code == 404
    assert database_path.is_file()
    with sqlite3.connect(database_path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
    assert schema_version == "3"


def test_existing_scaffold_database_is_migrated(tmp_path):
    database_path = tmp_path / "det_health.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO app_metadata (key, value) VALUES ('schema_version', '1')"
        )

    with TestClient(create_app(database_path)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    with sqlite3.connect(database_path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert schema_version == "3"
    assert {"users", "health_records", "import_batches", "behavior_entries"} <= tables


def test_behavioral_entries_are_encrypted_private_and_deduplicated(tmp_path):
    database_path = tmp_path / "det_health.sqlite3"
    entry = {
        "username": USERNAME,
        "password": PASSWORD,
        "category": "sleep",
        "reported_on": "2025-01-01",
        "values": {"duration_hours": 7.5},
    }
    with TestClient(create_app(database_path)) as client:
        _create_account(client)
        saved = client.post("/behaviors/entry", json=entry)
        duplicate = client.post("/behaviors/entry", json=entry)
        entries = client.post(
            "/behaviors", json={"username": USERNAME, "password": PASSWORD}
        )
        other_account = client.post(
            "/users", json={"username": "another.user", "password": PASSWORD}
        )
        other_entries = client.post(
            "/behaviors",
            json={"username": "another.user", "password": PASSWORD},
        )

    assert saved.status_code == 200
    assert saved.json() == {"status": "saved", "duplicate": False}
    assert duplicate.json() == {"status": "already_saved", "duplicate": True}
    assert entries.json()["entries"] == [
        {
            "category": "sleep",
            "reported_on": "2025-01-01",
            "values": {"duration_hours": 7.5},
        }
    ]
    assert other_account.status_code == 201
    assert other_entries.json() == {"entries": []}
    with sqlite3.connect(database_path) as connection:
        encrypted_payload = connection.execute(
            "SELECT encrypted_payload FROM behavior_entries LIMIT 1"
        ).fetchone()[0]
    assert b"sleep" not in encrypted_payload
    assert b"7.5" not in encrypted_payload


def test_behavioral_entry_validation_and_local_evidence_catalog(tmp_path):
    with TestClient(create_app(tmp_path / "det_health.sqlite3")) as client:
        _create_account(client)
        invalid = client.post(
            "/behaviors/entry",
            json={
                "username": USERNAME,
                "password": PASSWORD,
                "category": "sleep",
                "reported_on": "2025-01-01",
                "values": {"duration_hours": 30},
            },
        )
        evidence = client.get("/evidence")

    assert invalid.status_code == 422
    assert {
        item["category"] for item in evidence.json()["evidence"]
    } == {"activity", "sleep", "tobacco", "alcohol", "nutrition"}
    assert evidence.json()["interpretation"].startswith("Population-level")


def test_determinant_map_connects_behavior_data_and_separates_health_indicators(
    tmp_path,
):
    database_path = tmp_path / "det_health.sqlite3"
    export_with_activity = _export_xml().replace(
        b"</HealthData>",
        b"""
  <Record type="HKQuantityTypeIdentifierStepCount" unit="count"
    value="6500" startDate="2025-01-03 08:00:00 -0500"
    endDate="2025-01-03 23:00:00 -0500" />
  <Record type="HKQuantityTypeIdentifierStepCount" unit="count"
    value="7000" startDate="2025-01-04 08:00:00 -0500"
    endDate="2025-01-04 23:00:00 -0500" />
  <Record type="HKQuantityTypeIdentifierStepCount" unit="count"
    value="7500" startDate="2025-01-05 08:00:00 -0500"
    endDate="2025-01-05 23:00:00 -0500" />
  <Record type="HKQuantityTypeIdentifierStepCount" unit="count"
    value="8000" startDate="2025-01-06 08:00:00 -0500"
    endDate="2025-01-06 23:00:00 -0500" />
  <Record type="HKQuantityTypeIdentifierStepCount" unit="count"
    value="8500" startDate="2025-01-07 08:00:00 -0500"
    endDate="2025-01-07 23:00:00 -0500" />
</HealthData>""",
    )
    with TestClient(create_app(database_path)) as client:
        _create_account(client)
        imported = _import(client, export_with_activity)
        activity_entries = [
            client.post(
                "/behaviors/entry",
                json={
                    "username": USERNAME,
                    "password": PASSWORD,
                    "category": "activity",
                    "reported_on": f"2025-01-0{day}",
                    "values": {"moderate_minutes": day * 10},
                },
            )
            for day in range(3, 8)
        ]
        journal_entry = client.post(
            "/behaviors/entry",
            json={
                "username": USERNAME,
                "password": PASSWORD,
                "category": "sleep",
                "reported_on": "2025-01-03",
                "values": {"duration_hours": 7.25},
            },
        )
        determinant_map = client.post(
            "/determinants",
            json={"username": USERNAME, "password": PASSWORD},
        )

    result = determinant_map.json()
    domains = {item["id"]: item for item in result["domains"]}
    behavioral_signals = {item["label"]: item for item in domains["behavioral"]["signals"]}

    assert imported.status_code == 200
    assert all(entry.json()["status"] == "saved" for entry in activity_entries)
    assert journal_entry.json()["status"] == "saved"
    assert domains["behavioral"]["status"] == "data_available"
    assert "Step count" in behavioral_signals
    assert "Self-reported sleep duration" in behavioral_signals
    assert behavioral_signals["Step count"]["source"] == "Apple Health import"
    assert behavioral_signals["Self-reported sleep duration"]["source"] == "Self-report"
    assert "31% higher" in behavioral_signals["Step count"]["insight"]
    assert any(
        "31% higher" in insight["text"]
        for insight in domains["behavioral"]["insights"]
    )
    assert any(
        "average was 7.25" in insight["text"]
        for insight in domains["behavioral"]["insights"]
    )
    assert any(
        "Pearson correlation of 1.00" in insight["text"]
        for insight in domains["behavioral"]["insights"]
    )
    assert domains["social_economic"]["status"] == "not_collected"
    assert domains["physical_environment"]["status"] == "not_collected"
    assert domains["health_services"]["status"] == "not_collected"
    assert domains["personal_characteristics"]["status"] == "not_collected"
    assert any(
        indicator["metric_type"] == "HKQuantityTypeIdentifierHeartRate"
        for indicator in result["health_indicators"]
    )
    assert any(
        evidence["category"] == "sleep"
        for evidence in domains["behavioral"]["evidence"]
    )
    assert "does not estimate individual risk" in result["interpretation"]


def test_xml_import_deduplicates_and_returns_descriptive_trends(tmp_path):
    database_path = tmp_path / "det_health.sqlite3"
    with TestClient(create_app(database_path)) as client:
        _create_account(client)

        first_import = _import(client, _export_xml())
        duplicate_import = _import(client, _export_xml())
        metrics = client.post(
            "/metrics", json={"username": USERNAME, "password": PASSWORD}
        )
        trends = client.post(
            "/trends",
            json={
                "username": USERNAME,
                "password": PASSWORD,
                "metric_type": "HKQuantityTypeIdentifierHeartRate",
                "bucket": "day",
            },
        )

    assert first_import.status_code == 200
    assert first_import.json() == {"imported": 3, "duplicates": 0, "skipped": 1}
    assert duplicate_import.json() == {
        "imported": 0,
        "duplicates": 3,
        "skipped": 1,
    }
    assert metrics.json()["metrics"] == [
        {
            "type": "HKQuantityTypeIdentifierHeartRate",
            "units": ["count/min"],
            "count": 3,
            "first_seen": "2025-01-01T13:00:00+00:00",
            "last_seen": "2025-01-02T13:00:00+00:00",
        }
    ]
    assert trends.json()["trends"] == [
        {
            "period": "2025-01-01",
            "unit": "count/min",
            "count": 2,
            "average": 70.0,
            "minimum": 60.0,
            "maximum": 80.0,
        },
        {
            "period": "2025-01-02",
            "unit": "count/min",
            "count": 1,
            "average": 72.0,
            "minimum": 72.0,
            "maximum": 72.0,
        },
    ]

    with sqlite3.connect(database_path) as connection:
        encrypted_payload = connection.execute(
            "SELECT encrypted_payload FROM health_records LIMIT 1"
        ).fetchone()[0]
    assert b"HKQuantityTypeIdentifierHeartRate" not in encrypted_payload
    assert b"60.0" not in encrypted_payload


def test_zip_import_and_user_isolation(tmp_path):
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("apple_health_export/export.xml", _export_xml())

    with TestClient(create_app(tmp_path / "det_health.sqlite3")) as client:
        _create_account(client)
        imported = _import(client, archive_bytes.getvalue(), "export.zip")
        second_account = client.post(
            "/users", json={"username": "another.user", "password": PASSWORD}
        )
        empty_metrics = client.post(
            "/metrics",
            json={"username": "another.user", "password": PASSWORD},
        )

    assert imported.status_code == 200
    assert imported.json()["imported"] == 3
    assert second_account.status_code == 201
    assert empty_metrics.json() == {"metrics": []}


def test_invalid_credentials_and_unsafe_xml_are_rejected(tmp_path):
    with TestClient(create_app(tmp_path / "det_health.sqlite3")) as client:
        _create_account(client)
        unauthorized = client.post(
            "/metrics", json={"username": USERNAME, "password": "wrong password"}
        )
        unsafe_xml = _import(
            client,
            b'<!DOCTYPE x [<!ENTITY entity "expanded">]><HealthData>&entity;</HealthData>',
        )

    assert unauthorized.status_code == 401
    assert unsafe_xml.status_code == 400


def test_malformed_import_rolls_back_records_and_reversed_date_range_is_rejected(
    tmp_path,
):
    malformed_xml = (
        _export_xml()
        .replace(b"</HealthData>", b"</HealthData")
    )
    with TestClient(create_app(tmp_path / "det_health.sqlite3")) as client:
        _create_account(client)
        failed_import = _import(client, malformed_xml)
        metrics = client.post(
            "/metrics", json={"username": USERNAME, "password": PASSWORD}
        )
        reversed_range = client.post(
            "/trends",
            json={
                "username": USERNAME,
                "password": PASSWORD,
                "metric_type": "HKQuantityTypeIdentifierHeartRate",
                "start_date": "2025-01-02",
                "end_date": "2025-01-01",
            },
        )

    assert failed_import.status_code == 400
    assert metrics.json() == {"metrics": []}
    assert reversed_range.status_code == 422
