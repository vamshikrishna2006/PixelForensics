"""Structured logging, request correlation, alert delivery and admin error feeds.

Design goals
------------
* One JSON object per log line, so logs are machine-readable and easy to redact.
* Every request gets a correlation ID (``X-Request-ID``), included in error
  responses and log records.
* Secrets, passwords, tokens and connection strings are stripped before a
  record is written or returned to the admin dashboard.
* Alerts are optional: without ``ALERT_WEBHOOK_URL`` or SMTP settings they are
  recorded in the admin dashboard only.  This module never pretends an alert
  was delivered.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import smtplib
import threading
import time
import traceback
import uuid
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from email.message import EmailMessage
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

settings = get_settings()

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)

LOGGER_NAME = "pixelforensics"
logger = logging.getLogger(LOGGER_NAME)

_SEVERITY_ORDER = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}
_SENSITIVE_KEY = re.compile(
    r"(password|passwd|pwd|token|secret|authorization|api[_-]?key|"
    r"service[_-]?role|jwt|cookie|session|credential)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/\-=]+", re.IGNORECASE)
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_PG_URL_RE = re.compile(
    r"(postgres(?:ql)?(?:\+asyncpg)?://)([^:\s/]+):([^@\s]+)@",
    re.IGNORECASE,
)
_API_KEY_RE = re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9]{16,}\b")
_MAX_TEXT = 4000


def sanitize_text(value: Any) -> str:
    """Remove likely credentials and cap the length of free text."""
    text = "" if value is None else str(value)
    text = _BEARER_RE.sub("Bearer [redacted]", text)
    text = _JWT_RE.sub("[redacted-jwt]", text)
    text = _PG_URL_RE.sub(r"\1\2:***@", text)
    text = _API_KEY_RE.sub("[redacted-key]", text)
    text = re.sub(
        r"(?i)(SUPABASE_SERVICE_ROLE_KEY|SUPABASE_ANON_KEY|SUPABASE_JWT_SECRET|"
        r"SECRET_KEY|DATABASE_URL|ALERT_EMAIL_SMTP_PASSWORD)\s*=\s*[^\s,;]+",
        r"\1=[redacted]",
        text,
    )
    return text[:_MAX_TEXT]


def sanitize(value: Any, depth: int = 0) -> Any:
    """Recursively redact dictionaries/lists before logging."""
    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if _SENSITIVE_KEY.search(name):
                out[name] = "[redacted]"
            else:
                out[name] = sanitize(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [sanitize(item, depth + 1) for item in value][:50]
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return sanitize_text(value)


class JsonFormatter(logging.Formatter):
    """One-line JSON records with stable keys."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "severity": getattr(record, "severity", record.levelname.lower()),
            "category": getattr(record, "category", "application"),
            "service": "pixelforensics-backend",
            "module": getattr(record, "module_name", record.name),
            "request_id": getattr(record, "request_id", request_id_ctx.get()),
            "message": sanitize_text(record.getMessage()),
            "recovered": bool(getattr(record, "recovered", False)),
        }
        fields = getattr(record, "fields", None)
        if fields:
            payload["details"] = sanitize(fields)
        if record.exc_info:
            payload["exception"] = sanitize_text(
                "".join(traceback.format_exception(*record.exc_info))
            )
        return json.dumps(payload, ensure_ascii=False, default=str)


_configured = False


def setup_logging() -> None:
    """Configure JSON console + rotating-file logging exactly once."""
    global _configured
    if _configured:
        return
    _configured = True

    level = getattr(logging, (settings.LOG_LEVEL or "INFO").upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    formatter = JsonFormatter()
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        log_path = Path(settings.LOG_FILE).expanduser().resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max(100_000, int(settings.LOG_MAX_BYTES)),
            backupCount=max(1, int(settings.LOG_BACKUP_COUNT)),
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # Console logging still works if the log directory is not writable.
        logger.warning("log file unavailable; using console logging only")


def _alert_log_path() -> Path:
    return Path(settings.LOG_FILE).expanduser().resolve().with_name("alerts.jsonl")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sanitize(payload), ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


class AlertManager:
    """Best-effort alert delivery with fingerprint de-duplication.

    A failure to deliver an alert is logged but never raised to the caller, so
    monitoring can never break a customer request.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_sent: dict[str, float] = {}
        self._occurrences: dict[str, deque[float]] = {}

    @property
    def configured(self) -> bool:
        return bool(
            settings.ALERT_WEBHOOK_URL.strip()
            or (
                settings.ALERT_EMAIL_SMTP_HOST.strip()
                and settings.ALERT_EMAIL_TO.strip()
                and settings.ALERT_EMAIL_FROM.strip()
            )
        )

    def notify(
        self,
        severity: str,
        category: str,
        message: str,
        fields: dict[str, Any] | None = None,
    ) -> bool:
        severity = (severity or "error").lower()
        min_severity = (settings.ALERT_MIN_SEVERITY or "error").lower()
        if _SEVERITY_ORDER.get(severity, 40) < _SEVERITY_ORDER.get(min_severity, 40):
            return False

        fields = sanitize(fields or {})
        fingerprint = hashlib.sha256(
            f"{category}|{message}|{fields.get('module', '')}|{fields.get('path', '')}".encode("utf-8")
        ).hexdigest()[:16]
        now = time.time()
        cooldown = max(1, int(settings.ALERT_COOLDOWN_MINUTES)) * 60

        with self._lock:
            bucket = self._occurrences.setdefault(fingerprint, deque())
            bucket.append(now)
            while bucket and now - bucket[0] > 3600:
                bucket.popleft()
            occurrences = len(bucket)
            last = self._last_sent.get(fingerprint, 0.0)
            if now - last < cooldown:
                return False
            self._last_sent[fingerprint] = now

        alert = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "severity": severity,
            "category": category,
            "message": sanitize_text(message),
            "request_id": request_id_ctx.get(),
            "fingerprint": fingerprint,
            "occurrences_last_hour": occurrences,
            "details": fields,
            "delivery": "queued" if self.configured else "not_configured",
        }
        _append_jsonl(_alert_log_path(), alert)
        if not self.configured:
            return True

        thread = threading.Thread(
            target=self._deliver,
            args=(dict(alert),),
            name="pf-alert-delivery",
            daemon=True,
        )
        thread.start()
        return True

    def _deliver(self, alert: dict[str, Any]) -> None:
        try:
            if settings.ALERT_WEBHOOK_URL.strip():
                self._send_webhook(alert)
            if (
                settings.ALERT_EMAIL_SMTP_HOST.strip()
                and settings.ALERT_EMAIL_TO.strip()
                and settings.ALERT_EMAIL_FROM.strip()
            ):
                self._send_email(alert)
        except Exception as exc:  # delivery must never break the request
            log_event(
                "warning",
                "alerting",
                "alert delivery failed",
                alert=False,
                channel="webhook" if settings.ALERT_WEBHOOK_URL.strip() else "email",
                error_type=type(exc).__name__,
            )

    def _alert_text(self, alert: dict[str, Any]) -> str:
        return (
            f"[{alert['severity'].upper()}] {alert['category']}: {alert['message']}\n"
            f"request_id={alert.get('request_id') or '-'}\n"
            f"fingerprint={alert.get('fingerprint')}\n"
            f"occurrences_last_hour={alert.get('occurrences_last_hour')}\n"
            f"details={json.dumps(alert.get('details') or {}, ensure_ascii=False)}"
        )

    def _send_webhook(self, alert: dict[str, Any]) -> None:
        text = self._alert_text(alert)
        kind = (settings.ALERT_WEBHOOK_TYPE or "generic").lower()
        if kind in ("slack", "discord"):
            payload = {"text": text, "content": text}
        else:
            payload = {"text": text, "alert": alert}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urlrequest.Request(
            settings.ALERT_WEBHOOK_URL.strip(),
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "PixelForensics-Monitor/1.0",
            },
        )
        with urlrequest.urlopen(req, timeout=15) as response:
            response.read(1024)

    def _send_email(self, alert: dict[str, Any]) -> None:
        message = EmailMessage()
        message["Subject"] = f"[PixelForensics] {alert['severity'].upper()}: {alert['category']}"
        message["From"] = settings.ALERT_EMAIL_FROM.strip()
        message["To"] = settings.ALERT_EMAIL_TO.strip()
        message.set_content(self._alert_text(alert))

        with smtplib.SMTP(
            settings.ALERT_EMAIL_SMTP_HOST.strip(),
            int(settings.ALERT_EMAIL_SMTP_PORT),
            timeout=15,
        ) as smtp:
            if settings.ALERT_EMAIL_USE_TLS:
                smtp.starttls()
            if settings.ALERT_EMAIL_SMTP_USER.strip():
                smtp.login(
                    settings.ALERT_EMAIL_SMTP_USER.strip(),
                    settings.ALERT_EMAIL_SMTP_PASSWORD,
                )
            smtp.send_message(message)


alert_manager = AlertManager()


def log_event(
    severity: str,
    category: str,
    message: str,
    *,
    alert: bool = True,
    recovered: bool = False,
    **fields: Any,
) -> None:
    """Write a structured event and (for errors) queue an alert."""
    severity = (severity or "info").lower()
    level = getattr(logging, severity.upper(), logging.INFO)
    module_name = str(fields.get("module") or "application")
    request_id = str(fields.pop("request_id", request_id_ctx.get()) or "-")
    logger.log(
        level,
        message,
        extra={
            "severity": severity,
            "category": category,
            "module_name": module_name,
            "request_id": request_id,
            "fields": sanitize(fields),
            "recovered": recovered,
        },
    )
    if alert and severity in ("error", "critical"):
        alert_manager.notify(severity, category, message, fields)


def log_exception(
    exc: BaseException,
    category: str,
    message: str,
    *,
    severity: str = "error",
    recovered: bool = False,
    alert: bool = True,
    **fields: Any,
) -> None:
    """Log a technical exception securely (full detail only in the log file)."""
    fields = sanitize(fields)
    level = getattr(logging, severity.upper(), logging.ERROR)
    logger.log(
        level,
        message,
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={
            "severity": severity,
            "category": category,
            "module_name": str(fields.get("module") or "application"),
            "request_id": str(fields.get("request_id") or request_id_ctx.get() or "-"),
            "fields": fields,
            "recovered": recovered,
        },
    )
    if alert and severity in ("error", "critical"):
        alert_manager.notify(severity, category, message, fields)


def _read_jsonl_tail(path: Path, max_bytes: int = 1_000_000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            start = max(0, size - max_bytes)
            handle.seek(start)
            data = handle.read().decode("utf-8", "ignore")
    except OSError:
        return []

    lines = data.splitlines()
    if size > max_bytes and lines:
        lines = lines[1:]  # first line may be partial

    out: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def _parse_ts(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def get_recent_errors(limit: int = 10, since_minutes: int | None = None) -> list[dict[str, Any]]:
    """Recent error/critical events safe to show in the admin dashboard."""
    cutoff = None
    if since_minutes:
        cutoff = datetime.now(timezone.utc).timestamp() - since_minutes * 60

    rows: list[dict[str, Any]] = []
    for item in reversed(_read_jsonl_tail(Path(settings.LOG_FILE).expanduser().resolve())):
        if str(item.get("severity", "")).lower() not in ("error", "critical"):
            continue
        if cutoff is not None:
            ts = _parse_ts(item.get("timestamp"))
            if ts is not None and ts.timestamp() < cutoff:
                continue
        rows.append(
            {
                "timestamp": item.get("timestamp"),
                "severity": item.get("severity"),
                "category": item.get("category"),
                "module": item.get("module"),
                "message": item.get("message"),
                "request_id": item.get("request_id"),
                "recovered": item.get("recovered", False),
                "status_code": (item.get("details") or {}).get("status_code"),
                "path": (item.get("details") or {}).get("path"),
            }
        )
        if len(rows) >= max(1, limit):
            break
    return rows


def count_recent_errors(category: str | None = None, since_minutes: int = 1440) -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - max(1, since_minutes) * 60
    count = 0
    for item in _read_jsonl_tail(Path(settings.LOG_FILE).expanduser().resolve()):
        if str(item.get("severity", "")).lower() not in ("error", "critical"):
            continue
        if category and item.get("category") != category:
            continue
        ts = _parse_ts(item.get("timestamp"))
        if ts is not None and ts.timestamp() >= cutoff:
            count += 1
    return count


def get_recent_alerts(limit: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in reversed(_read_jsonl_tail(_alert_log_path())):
        rows.append(
            {
                "timestamp": item.get("timestamp"),
                "severity": item.get("severity"),
                "category": item.get("category"),
                "message": item.get("message"),
                "fingerprint": item.get("fingerprint"),
                "occurrences_last_hour": item.get("occurrences_last_hour"),
                "delivery": item.get("delivery"),
            }
        )
        if len(rows) >= max(1, limit):
            break
    return rows


def _request_id(value: str | None) -> str:
    if value and re.fullmatch(r"[A-Za-z0-9._-]{8,64}", value):
        return value
    return uuid.uuid4().hex


def _private_path(path: str) -> bool:
    return path.startswith(("/api/analysis", "/api/report", "/api/admin", "/api/auth", "/api/compare"))


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Correlation IDs, security headers, safe 500 responses and error logging."""

    async def dispatch(self, request: Request, call_next):
        rid = _request_id(request.headers.get("x-request-id"))
        token = request_id_ctx.set(rid)
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                log_exception(
                    exc,
                    "unhandled",
                    "unhandled application error",
                    module="middleware",
                    path=request.url.path,
                    method=request.method,
                    request_id=rid,
                )
                response = JSONResponse(
                    status_code=500,
                    content={
                        "detail": "Something went wrong. Please try again.",
                        "request_id": rid,
                    },
                )
                self._add_cors_headers(request, response)
            else:
                if response.status_code >= 500:
                    log_event(
                        "error",
                        "http",
                        "server error response",
                        module="middleware",
                        status_code=response.status_code,
                        path=request.url.path,
                        method=request.method,
                        request_id=rid,
                    )
                elif response.status_code in (401, 403) and request.url.path not in (
                    "/api/auth/login",
                    "/api/auth/register",
                ):
                    log_event(
                        "warning",
                        "auth",
                        "access denied",
                        alert=False,
                        module="middleware",
                        status_code=response.status_code,
                        path=request.url.path,
                        method=request.method,
                        request_id=rid,
                    )
                elif response.status_code == 429:
                    log_event(
                        "warning",
                        "rate_limit",
                        "request rate limited",
                        alert=False,
                        module="middleware",
                        path=request.url.path,
                        method=request.method,
                        request_id=rid,
                    )

            response.headers["X-Request-ID"] = rid
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            if _private_path(request.url.path):
                response.headers["Cache-Control"] = "no-store"
                response.headers["Pragma"] = "no-cache"
            return response
        finally:
            request_id_ctx.reset(token)

    @staticmethod
    def _add_cors_headers(request: Request, response: Response) -> None:
        origin = request.headers.get("origin")
        if origin and origin in settings.cors_origins_list:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"