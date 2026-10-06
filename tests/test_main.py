from fastapi.testclient import TestClient

from app.main import create_app


def test_health_check_initializes_local_database(tmp_path):
    database_path = tmp_path / "data" / "test.sqlite3"
    application = create_app(database_path)

    with TestClient(application) as client:
        response = client.get("/health")
        docs_response = client.get("/docs")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "storage": "sqlite"}
    assert docs_response.status_code == 404
    assert database_path.is_file()
