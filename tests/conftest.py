"""Shared test configuration.

Environment is set *before* importing the application so the global async
engine points at an isolated temporary SQLite database.  Production data is
never touched.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

TEST_ROOT = Path(tempfile.mkdtemp(prefix="pixelforensics-tests-"))
DB_PATH = TEST_ROOT / "test.db"
STORAGE_PATH = TEST_ROOT / "storage"
BACKUP_PATH = TEST_ROOT / "backups"
LOG_PATH = TEST_ROOT / "logs" / "app.jsonl"

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["LOCAL_STORAGE_PATH"] = str(STORAGE_PATH)
os.environ["BACKUP_DIR"] = str(BACKUP_PATH)
os.environ["BACKUP_ENABLED"] = "false"
os.environ["BACKUP_VERIFY_AFTER_RUN"] = "false"
os.environ["MONITORING_ENABLED"] = "false"
os.environ["LOG_FILE"] = str(LOG_PATH)
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["AUTH_MODE"] = "local"
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-with-at-least-32-characters"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_root():
    yield
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


def _register(client: TestClient, prefix: str = "customer") -> dict:
    suffix = uuid.uuid4().hex[:10]
    username = f"{prefix}_{suffix}"
    email = f"{username}@example.com"
    password = "StrongPass1!"
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "username": username,
        "email": email,
        "password": password,
        "token": body["access_token"],
        "user": body["user"],
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }


@pytest.fixture
def customer(client):
    return _register(client, "customer")


@pytest.fixture
def other_customer(client):
    return _register(client, "other")


@pytest.fixture
def admin(client):
    response = client.post(
        "/api/auth/login",
        json={"identifier": "admin@pixelforensics.com", "password": "Admin@12345"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "user": response.json()["user"]}
