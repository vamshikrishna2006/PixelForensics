"""End-to-end authorization / IDOR tests against the real FastAPI app."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from helpers import analyze, make_jpeg

settings = get_settings()


def _db_path() -> Path:
    return Path(settings.DATABASE_URL.replace("sqlite:///", "", 1))


def _storage_path(analysis_id: str) -> str:
    connection = sqlite3.connect(_db_path())
    try:
        row = connection.execute(
            "select storage_path from analyses where id = ?", (analysis_id,)
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return str(row[0])


def test_customer_can_view_own_dashboard_and_history(client: TestClient, customer: dict):
    report = analyze(client, customer["headers"], seed=11)
    analysis_id = report["analysis"]["id"]

    me = client.get("/api/auth/me", headers=customer["headers"])
    assert me.status_code == 200
    assert me.json()["role"] == "CUSTOMER"

    history = client.get("/api/analysis/history", headers=customer["headers"])
    assert history.status_code == 200
    assert analysis_id in {item["id"] for item in history.json()}


def test_customer_can_download_own_reports(client: TestClient, customer: dict):
    report = analyze(client, customer["headers"], seed=12)
    analysis_id = report["analysis"]["id"]

    json_report = client.get(f"/api/report/{analysis_id}/json", headers=customer["headers"])
    assert json_report.status_code == 200
    assert json_report.headers["content-type"].startswith("application/json")
    assert "attachment" in json_report.headers.get("content-disposition", "")

    pdf_report = client.get(f"/api/report/{analysis_id}/pdf", headers=customer["headers"])
    assert pdf_report.status_code == 200
    assert pdf_report.headers["content-type"] == "application/pdf"
    assert pdf_report.content.startswith(b"%PDF")

    signature = client.get(f"/api/report/{analysis_id}/signature", headers=customer["headers"])
    assert signature.status_code == 200
    assert signature.json()["signature_id"].startswith("PF-")


def test_customer_cannot_access_another_customers_analysis(
    client: TestClient, customer: dict, other_customer: dict
):
    victim = analyze(client, other_customer["headers"], seed=21)
    analysis_id = victim["analysis"]["id"]

    assert client.get(f"/api/analysis/{analysis_id}", headers=customer["headers"]).status_code == 404
    assert client.get(f"/api/report/{analysis_id}/json", headers=customer["headers"]).status_code == 404
    assert client.get(f"/api/report/{analysis_id}/pdf", headers=customer["headers"]).status_code == 404
    assert client.get(f"/api/report/{analysis_id}/signature", headers=customer["headers"]).status_code == 404
    assert client.delete(f"/api/analysis/{analysis_id}", headers=customer["headers"]).status_code == 404

    # The victim's record must still exist and remain readable by its owner.
    assert client.get(f"/api/analysis/{analysis_id}", headers=other_customer["headers"]).status_code == 200


def test_customer_cannot_access_another_customers_uploaded_image(
    client: TestClient, customer: dict, other_customer: dict
):
    victim = analyze(client, other_customer["headers"], seed=22)
    analysis_id = victim["analysis"]["id"]
    relative = _storage_path(analysis_id)

    stored = Path(settings.LOCAL_STORAGE_PATH) / relative
    assert stored.is_file()
    assert relative.startswith(other_customer["user"]["id"])

    # The backend exposes no static storage route. These requests must not
    # return the victim's image bytes.
    for path in (f"/storage/{relative}", f"/api/storage/{relative}", f"/api/analysis/{analysis_id}/image"):
        response = client.get(path, headers=customer["headers"])
        assert response.status_code == 404
        assert b"\xff\xd8\xff" not in response.content


def test_customer_cannot_reach_admin_endpoints(client: TestClient, customer: dict):
    for path in (
        "/api/admin/statistics",
        "/api/admin/users",
        "/api/admin/system-health",
        "/api/admin/monitoring",
    ):
        response = client.get(path, headers=customer["headers"])
        assert response.status_code == 403


def test_unauthenticated_and_invalid_tokens_are_rejected(client: TestClient):
    assert client.get("/api/analysis/history").status_code == 401
    assert client.get("/api/admin/statistics").status_code == 401
    assert client.get("/api/admin/monitoring").status_code == 401
    assert client.get("/api/report/not-a-real-id/json").status_code == 401
    assert client.get(
        "/api/analysis/history", headers={"Authorization": "Bearer not-a-real-token"}
    ).status_code == 401


def test_admin_can_access_admin_endpoints(client: TestClient, admin: dict):
    assert admin["user"]["role"] == "ADMIN"
    for path in (
        "/api/admin/statistics",
        "/api/admin/users",
        "/api/admin/system-health",
        "/api/admin/monitoring",
    ):
        response = client.get(path, headers=admin["headers"])
        assert response.status_code == 200, response.text

    monitoring = client.get("/api/admin/monitoring", headers=admin["headers"]).json()
    assert "backup" in monitoring
    assert "recent_errors" in monitoring
    assert "recent_alerts" in monitoring
    assert "alert_delivery_configured" in monitoring


def test_registration_cannot_self_promote(client: TestClient):
    import uuid

    suffix = uuid.uuid4().hex[:10]
    response = client.post(
        "/api/auth/register",
        json={
            "username": f"escalate_{suffix}",
            "email": f"escalate_{suffix}@example.com",
            "password": "StrongPass1!",
            "confirm_password": "StrongPass1!",
            "role": "ADMIN",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["role"] == "CUSTOMER"

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/api/admin/statistics", headers=headers).status_code == 403


def test_error_responses_do_not_leak_internals(client: TestClient, customer: dict):
    response = client.post(
        "/api/analyze",
        headers=customer["headers"],
        files={"file": ("broken.jpg", b"not-an-image", "image/jpeg")},
    )
    assert response.status_code == 400
    text = response.text.lower()
    for forbidden in ("traceback", "sqlalchemy", "sqlite", "postgres", "secret", "/users/"):
        assert forbidden not in text

    missing = client.get("/api/analysis/does-not-exist", headers=customer["headers"])
    assert missing.status_code == 404
    assert "not found" in missing.json()["detail"].lower()


def test_frontend_errors_are_recorded_for_admin(client: TestClient, admin: dict):
    response = client.post(
        "/api/client-errors",
        json={
            "message": "boom in a component",
            "stack": "Error: boom",
            "source": "react-boundary",
            "url": "/dashboard?token=should-not-be-logged",
        },
    )
    assert response.status_code == 204

    monitoring = client.get("/api/admin/monitoring", headers=admin["headers"])
    assert monitoring.status_code == 200
    errors = monitoring.json()["recent_errors"]
    assert any(
        error.get("category") == "frontend" and "boom" in (error.get("message") or "")
        for error in errors
    )


def test_pipeline_failure_returns_generic_message(client: TestClient, customer: dict, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("internal database password must not leak")

    monkeypatch.setattr("app.api.analysis.run_full_analysis", boom)
    response = client.post(
        "/api/analyze",
        headers=customer["headers"],
        files={"file": ("sample.jpg", make_jpeg(31), "image/jpeg")},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Image analysis could not be completed. Please try again later."
    body = response.text.lower()
    for forbidden in ("runtimeerror", "password", "traceback", "sqlalchemy"):
        assert forbidden not in body


def test_unhandled_error_returns_generic_message_with_request_id(client: TestClient, customer: dict, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("private path /etc/passwd must not leak")

    monkeypatch.setattr("app.api.analysis.report_basename", boom)
    response = client.post(
        "/api/analyze",
        headers=customer["headers"],
        files={"file": ("sample.jpg", make_jpeg(32), "image/jpeg")},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Something went wrong. Please try again."
    assert response.json().get("request_id")
    body = response.text.lower()
    for forbidden in ("runtimeerror", "private path", "/etc/passwd", "traceback"):
        assert forbidden not in body
