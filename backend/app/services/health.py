"""Readiness probes and periodic database/storage availability monitoring."""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.observability import log_event, log_exception

settings = get_settings()


async def check_database() -> dict[str, Any]:
    started = time.perf_counter()
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:
        return {
            "status": "down",
            "latency_ms": None,
            "error_type": type(exc).__name__,
        }


def check_storage() -> dict[str, Any]:
    path = Path(settings.LOCAL_STORAGE_PATH).expanduser().resolve()
    exists = path.is_dir()
    writable = os.access(path if exists else path.parent, os.W_OK)
    return {
        "status": "healthy" if exists and writable else "down",
        "exists": exists,
        "writable": writable,
    }


async def readiness() -> dict[str, Any]:
    database = await check_database()
    storage = check_storage()
    ready = database["status"] == "healthy" and storage["status"] == "healthy"
    return {
        "status": "ready" if ready else "unavailable",
        "database": database["status"],
        "storage": storage["status"],
    }


async def monitoring_loop() -> None:
    """Alert on database/storage transitions while the process is running.

    This cannot detect a fully stopped process; an external uptime monitor
    should poll ``/api/ready`` for that case.
    """
    interval = max(60, int(settings.MONITOR_INTERVAL_SECONDS))
    previous: dict[str, str] = {}
    while True:
        try:
            database = await check_database()
            storage = check_storage()
            current = {"database": database["status"], "storage": storage["status"]}
            for component, state in current.items():
                if state != "healthy" and previous.get(component) != "down":
                    log_event(
                        "error",
                        component if component == "database" else "storage",
                        f"{component} availability check failed",
                        module="monitoring",
                        component=component,
                        state=state,
                        recovered=False,
                    )
                elif state == "healthy" and previous.get(component) == "down":
                    log_event(
                        "info",
                        component if component == "database" else "storage",
                        f"{component} availability restored",
                        alert=False,
                        module="monitoring",
                        component=component,
                        recovered=True,
                    )
            previous = current
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_exception(
                exc,
                "monitoring",
                "monitoring loop failed",
                module="monitoring",
            )
        await asyncio.sleep(interval)