"""Client error intake, admin monitoring feed and manual backup controls."""
from __future__ import annotations

import asyncio
import re
import threading
import time
from collections import deque
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.observability import (
    alert_manager,
    count_recent_errors,
    get_recent_alerts,
    get_recent_errors,
    log_event,
    log_exception,
    sanitize_text,
)
from app.security.deps import admin_user
from app.services.backups import (
    BackupBusy,
    BackupError,
    backup_status,
    create_backup,
    run_restore_verification,
)

router = APIRouter(tags=["monitoring"])
settings = get_settings()

_client_hits: dict[str, deque[float]] = {}
_client_lock = threading.Lock()
_CLIENT_LIMIT = 30
_CLIENT_WINDOW = 60.0


class ClientErrorIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    stack: str | None = Field(default=None, max_length=4000)
    source: str | None = Field(default=None, max_length=64)
    url: str | None = Field(default=None, max_length=500)
    component_stack: str | None = Field(default=None, max_length=4000)


def _client_rate_ok(key: str) -> bool:
    now = time.monotonic()
    with _client_lock:
        bucket = _client_hits.setdefault(key, deque())
        while bucket and now - bucket[0] > _CLIENT_WINDOW:
            bucket.popleft()
        if len(bucket) >= _CLIENT_LIMIT:
            return False
        bucket.append(now)
        return True


def _safe_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        return (parsed.path or "/")[:300]
    except ValueError:
        return None


@router.post("/api/client-errors", status_code=204)
async def client_error(body: ClientErrorIn, request: Request) -> Response:
    client = request.client.host if request.client else "unknown"
    if not _client_rate_ok(client):
        raise HTTPException(429, "Too many error reports.")

    source = body.source if body.source and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", body.source) else "frontend"
    log_event(
        "error",
        "frontend",
        f"frontend error: {sanitize_text(body.message)[:200]}",
        alert=False,
        module="frontend",
        source=source,
        path=_safe_url(body.url),
        stack=sanitize_text(body.stack) if body.stack else None,
        component_stack=sanitize_text(body.component_stack) if body.component_stack else None,
    )
    return Response(status_code=204)


@router.get("/api/admin/monitoring")
async def monitoring(admin=Depends(admin_user)):
    return {
        "backup": backup_status(),
        "recent_errors": get_recent_errors(limit=10),
        "recent_alerts": get_recent_alerts(limit=10),
        "failed_analyses_24h": count_recent_errors(category="analysis", since_minutes=1440),
        "critical_errors_24h": count_recent_errors(since_minutes=1440),
        "alert_delivery_configured": alert_manager.configured,
        "monitoring_enabled": bool(settings.MONITORING_ENABLED),
        "backup_enabled": bool(settings.BACKUP_ENABLED),
    }


@router.post("/api/admin/backups/run")
async def run_backup(admin=Depends(admin_user)):
    try:
        record = await asyncio.to_thread(create_backup, "manual")
        verification = None
        if settings.BACKUP_VERIFY_AFTER_RUN:
            verification = await asyncio.to_thread(run_restore_verification, record["id"])
        return {
            "backup": record,
            "restore_verification": {
                "status": verification.get("status") if verification else "skipped",
                "id": verification.get("id") if verification else None,
            },
        }
    except BackupBusy:
        log_event(
            "warning",
            "backup",
            "manual backup rejected because another job is running",
            alert=False,
            module="backups",
        )
        raise HTTPException(409, "A backup is already running.")
    except BackupError as exc:
        log_event(
            "warning",
            "backup",
            "manual backup rejected",
            alert=False,
            module="backups",
            reason=sanitize_text(exc),
        )
        raise HTTPException(409, "The backup configuration is invalid.")
    except Exception as exc:
        log_exception(exc, "backup", "manual backup failed", module="backups")
        raise HTTPException(503, "Backup could not be completed. Please check the server logs.")


@router.post("/api/admin/backups/verify")
async def verify_backup(admin=Depends(admin_user)):
    try:
        result = await asyncio.to_thread(run_restore_verification)
        return {
            "id": result.get("id"),
            "status": result.get("status"),
            "backup_id": result.get("backup_id"),
            "finished_at": result.get("finished_at"),
            "reason": result.get("reason"),
            "error": result.get("error"),
        }
    except Exception as exc:
        log_exception(exc, "restore", "manual restore verification failed", module="backups")
        raise HTTPException(503, "Restore verification could not be completed.")


@router.post("/api/admin/monitoring/test-alert")
async def test_alert(admin=Depends(admin_user)):
    queued = alert_manager.notify(
        "critical",
        "monitoring",
        "test alert from the PixelForensics admin dashboard",
        {"module": "admin", "test": True},
    )
    return {
        "queued": queued,
        "delivery_configured": alert_manager.configured,
        "note": (
            "Alert delivery is configured; check the administrator channel."
            if alert_manager.configured
            else "No webhook or SMTP destination is configured. The alert was recorded in the dashboard only."
        ),
    }