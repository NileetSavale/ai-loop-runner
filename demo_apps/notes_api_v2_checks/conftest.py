import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTES_DB", str(tmp_path / "notes.db"))
    monkeypatch.setenv("NOTES_FILES", str(tmp_path / "files"))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def login(client):
    def _login(username, password="correct horse"):
        client.post("/register", json={"username": username, "password": password})
        token = client.post("/login", json={"username": username, "password": password}).json()["token"]
        return {"Authorization": f"Bearer {token}"}
    return _login
