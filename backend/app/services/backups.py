"""Automated database + storage backups with isolated restore verification.

The module is deliberately dependency-free (standard library only) so it works
in the existing deployment without adding packages.

Supported sources
-----------------
* SQLite (the default local database): online backup API, gzip-compressed.
* PostgreSQL / Supabase: ``pg_dump`` custom-format dump.  ``pg_dump`` must be
  installed on the host running the backup.
* Local uploaded-image storage: content-addressed objects + a per-run manifest,
  so unchanged files are stored only once across daily backups.

Safety
------
* Backups live outside the uploads directory and are never served by the web
  application.
* Restore tests for PostgreSQL require an explicit, separate
  ``RESTORE_TEST_DATABASE_URL`` whose database name contains ``test`` or
  ``restore``.  Production is never used for restore tests.
* A lock file prevents two backup jobs from running at once.
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.core.config import get_settings
from app.core.observability import log_event, log_exception, sanitize_text

settings = get_settings()

REQUIRED_TABLES = (
    "profiles",
    "analyses",
    "analysis_results",
    "suspicious_regions",
    "audit_logs",
)


class BackupError(RuntimeError):
    """Raised when a backup or verification cannot be completed."""


class BackupBusy(BackupError):
    """Another backup job currently holds the lock."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _paths(
    backup_dir: str | None = None,
    storage_path: str | None = None,
) -> tuple[Path, Path]:
    backups = Path(backup_dir or settings.BACKUP_DIR).expanduser().resolve()
    storage = Path(storage_path or settings.LOCAL_STORAGE_PATH).expanduser().resolve()
    if backups == storage or backups.is_relative_to(storage):
        raise BackupError("BACKUP_DIR must not be inside LOCAL_STORAGE_PATH.")
    return backups, storage


def _record_id() -> str:
    return _utcnow().strftime("%Y%m%dT%H%M%SZ")


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
    os.replace(temp, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _database_kind(url: str) -> str:
    if url.startswith("sqlite:///"):
        return "sqlite"
    if url.startswith(("postgresql://", "postgres://", "postgresql+asyncpg://")):
        return "postgres"
    raise BackupError("Unsupported DATABASE_URL for backup.")


def _sqlite_path(url: str) -> Path:
    raw = url.replace("sqlite:///", "", 1)
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _parse_postgres(url: str) -> dict[str, Any]:
    raw = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(raw)
    query = parse_qs(parsed.query or "")
    return {
        "host": parsed.hostname or "",
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": (parsed.path or "/postgres").lstrip("/") or "postgres",
        "sslmode": (query.get("sslmode") or [""])[0],
    }


def _backup_sqlite(url: str, destination: Path) -> None:
    source_path = _sqlite_path(url)
    if not source_path.exists():
        raise BackupError("SQLite database file was not found.")
    temp_db = destination.with_suffix(".tmp.db")
    try:
        source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
        target = sqlite3.connect(temp_db)
        try:
            source.backup(target)
            target.commit()
        finally:
            target.close()
            source.close()
        with temp_db.open("rb") as src, gzip.open(destination, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
    finally:
        try:
            temp_db.unlink()
        except OSError:
            pass


def _backup_postgres(url: str, destination: Path) -> None:
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise BackupError("pg_dump is not installed on this host.")
    info = _parse_postgres(url)
    env = os.environ.copy()
    env["PGPASSWORD"] = info["password"]
    if info["sslmode"]:
        env["PGSSLMODE"] = info["sslmode"]
    command = [
        pg_dump,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--file",
        str(destination),
        "-h",
        info["host"],
        "-p",
        str(info["port"]),
        "-U",
        info["user"],
        "-d",
        info["database"],
    ]
    completed = subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
        timeout=max(60, int(settings.BACKUP_PG_DUMP_TIMEOUT_SECONDS)),
    )
    if completed.returncode != 0:
        raise BackupError(
            sanitize_text((completed.stderr or "pg_dump failed").strip()[-500:])
        )


def _json_value(value: Any) -> Any:
    """Convert psycopg2 values to JSON-safe values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    return str(value)


def _backup_logical(url: str, destination: Path) -> int:
    """Read-only logical dump of the application tables.

    This fallback is used when ``pg_dump`` is unavailable.  It streams one JSON
    object per row into a gzip file, so large ``analysis_results`` rows are not
    held in memory.  Only the five application tables are included.
    """
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as exc:
        raise BackupError("psycopg2 is not installed; cannot create a logical backup.") from exc

    raw_url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = psycopg2.connect(raw_url, connect_timeout=20)
    # Use an explicit read-only transaction instead of session-level
    # ``set_session(readonly=True)``.  Supabase's transaction pooler can reuse a
    # server session, and a session-level read-only flag must never leak into
    # the application's write connections.
    connection.autocommit = False
    total_rows = 0
    try:
        with gzip.open(destination, "wt", encoding="utf-8", compresslevel=6) as handle:
            handle.write(
                json.dumps(
                    {
                        "type": "meta",
                        "format": "logical",
                        "version": 1,
                        "created_at": _iso(_utcnow()),
                        "tables": list(REQUIRED_TABLES),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                for table in REQUIRED_TABLES:
                    cursor.execute(f'SELECT * FROM public."{table}" LIMIT 0')
                    columns = [item[0] for item in cursor.description or []]
                    if not columns:
                        raise BackupError(f"Table {table} has no readable columns.")
                    handle.write(
                        json.dumps(
                            {"type": "table", "table": table, "columns": columns},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    cursor.execute(f'SELECT * FROM public."{table}" ORDER BY 1')
                    while True:
                        batch = cursor.fetchmany(500)
                        if not batch:
                            break
                        for row in batch:
                            handle.write(
                                json.dumps(
                                    {
                                        "type": "row",
                                        "table": table,
                                        "data": {key: _json_value(value) for key, value in dict(row).items()},
                                    },
                                    ensure_ascii=False,
                                    default=str,
                                )
                                + "\n"
                            )
                            total_rows += 1
        connection.rollback()
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        raise
    finally:
        connection.close()
    return total_rows


def _should_use_pg_dump() -> bool:
    mode = (settings.BACKUP_POSTGRES_MODE or "auto").lower()
    if mode == "logical":
        return False
    if mode == "pg_dump":
        if not shutil.which("pg_dump"):
            raise BackupError("BACKUP_POSTGRES_MODE=pg_dump but pg_dump is not installed.")
        return True
    return bool(shutil.which("pg_dump"))


def _backup_storage(storage: Path, backups: Path) -> dict[str, Any]:
    manifest_entries: list[dict[str, Any]] = []
    new_objects = 0
    reused_objects = 0

    if storage.is_dir():
        for root, dirs, files in os.walk(storage):
            dirs[:] = [d for d in dirs if not Path(root, d).is_symlink()]
            for name in files:
                path = Path(root) / name
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    path.resolve().relative_to(backups)
                    continue  # never back up the backup directory itself
                except ValueError:
                    pass
                try:
                    rel = path.relative_to(storage).as_posix()
                    digest = _sha256_file(path)
                    size = path.stat().st_size
                except OSError as exc:
                    raise BackupError(f"Could not read storage file: {type(exc).__name__}") from exc

                object_path = backups / "storage" / "objects" / digest[:2] / digest
                if object_path.exists() and object_path.stat().st_size == size:
                    reused_objects += 1
                else:
                    object_path.parent.mkdir(parents=True, exist_ok=True)
                    temp = object_path.with_suffix(".tmp")
                    shutil.copy2(path, temp)
                    os.replace(temp, object_path)
                    new_objects += 1
                manifest_entries.append({"path": rel, "sha256": digest, "size": size})

    return {
        "files": manifest_entries,
        "file_count": len(manifest_entries),
        "total_bytes": sum(item["size"] for item in manifest_entries),
        "new_objects": new_objects,
        "reused_objects": reused_objects,
    }


def _cleanup_retention(
    backups: Path,
    retention_days: int,
) -> dict[str, int]:
    removed_records = 0
    removed_objects = 0
    if retention_days <= 0:
        return {"records": 0, "objects": 0}

    cutoff = _utcnow() - timedelta(days=retention_days)
    records_dir = backups / "records"
    records: list[tuple[Path, dict[str, Any]]] = []
    if records_dir.is_dir():
        for path in records_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            records.append((path, data))

    records.sort(key=lambda item: str(item[1].get("finished_at") or ""))
    latest_success = next(
        ((path, data) for path, data in reversed(records) if data.get("status") == "success"),
        None,
    )

    keep_ids: set[str] = set()
    for path, data in records:
        finished = str(data.get("finished_at") or "")
        is_latest = latest_success is not None and path == latest_success[0]
        try:
            finished_dt = datetime.fromisoformat(finished.replace("Z", "+00:00"))
        except ValueError:
            finished_dt = cutoff
        if finished_dt >= cutoff or is_latest:
            keep_ids.add(path.stem)
            continue
        # Remove the database copy and manifest referenced by this record.
        db_info = data.get("database") or {}
        storage_info = data.get("storage") or {}
        for relative in (db_info.get("file"), storage_info.get("manifest")):
            if relative:
                try:
                    (backups / str(relative)).unlink()
                except OSError:
                    pass
        try:
            path.unlink()
            removed_records += 1
        except OSError:
            pass

    referenced: set[str] = set()
    for path, data in records:
        if path.stem not in keep_ids:
            continue
        manifest_rel = (data.get("storage") or {}).get("manifest")
        if not manifest_rel:
            continue
        try:
            manifest = json.loads((backups / str(manifest_rel)).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for item in manifest.get("files") or []:
            digest = item.get("sha256")
            if digest:
                referenced.add(str(digest))

    objects_dir = backups / "storage" / "objects"
    if objects_dir.is_dir():
        for object_path in objects_dir.rglob("*"):
            if not object_path.is_file():
                continue
            if object_path.name not in referenced:
                try:
                    object_path.unlink()
                    removed_objects += 1
                except OSError:
                    pass

    return {"records": removed_records, "objects": removed_objects}


def create_backup(
    trigger: str = "manual",
    *,
    database_url: str | None = None,
    storage_path: str | None = None,
    backup_dir: str | None = None,
    retention_days: int | None = None,
) -> dict[str, Any]:
    """Create a database + storage backup and return its (safe) record."""
    backups, storage = _paths(backup_dir, storage_path)
    backups.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(backups, 0o700)
    except OSError:
        pass
    lock_path = backups / ".backup.lock"
    lock_fd: int | None = None
    try:
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, str(os.getpid()).encode("ascii", "ignore"))
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0
            if age < 6 * 3600:
                raise BackupBusy("A backup is already running.")
            try:
                lock_path.unlink()
            except OSError:
                pass
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, str(os.getpid()).encode("ascii", "ignore"))

        started = _utcnow()
        record_id = _record_id()
        while (backups / "records" / f"{record_id}.json").exists():
            record_id = f"{_record_id()}-{uuid.uuid4().hex[:6]}"

        db_url = database_url or settings.DATABASE_URL
        kind = _database_kind(db_url)
        db_format = kind
        if kind == "sqlite":
            db_relative = f"db/{record_id}.sqlite.gz"
        elif _should_use_pg_dump():
            db_format = "pg_dump"
            db_relative = f"db/{record_id}.dump"
        else:
            db_format = "logical"
            db_relative = f"db/{record_id}.jsonl.gz"
        db_path = backups / db_relative
        db_path.parent.mkdir(parents=True, exist_ok=True)

        record: dict[str, Any] = {
            "id": record_id,
            "status": "running",
            "trigger": trigger,
            "started_at": _iso(started),
            "finished_at": None,
            "duration_s": None,
            "database": {"kind": kind, "format": db_format, "file": db_relative},
            "storage": {},
            "retention_days": int(retention_days if retention_days is not None else settings.BACKUP_RETENTION_DAYS),
            "error": None,
        }

        try:
            if kind == "sqlite":
                _backup_sqlite(db_url, db_path)
            elif db_format == "logical":
                record["database"]["row_count"] = _backup_logical(db_url, db_path)
            else:
                _backup_postgres(db_url, db_path)

            storage_info = _backup_storage(storage, backups)
            manifest_relative = f"storage/manifests/{record_id}.json"
            _atomic_write(
                backups / manifest_relative,
                {
                    "backup_id": record_id,
                    "created_at": record["started_at"],
                    "files": storage_info["files"],
                    "file_count": storage_info["file_count"],
                    "total_bytes": storage_info["total_bytes"],
                },
            )
            record["database"].update(
                {
                    "sha256": _sha256_file(db_path),
                    "size_bytes": db_path.stat().st_size,
                }
            )
            record["storage"] = {
                "manifest": manifest_relative,
                "file_count": storage_info["file_count"],
                "total_bytes": storage_info["total_bytes"],
                "new_objects": storage_info["new_objects"],
                "reused_objects": storage_info["reused_objects"],
            }
            record["status"] = "success"
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = sanitize_text(f"{type(exc).__name__}: {exc}")[:500]
            log_exception(
                exc,
                "backup",
                "backup failed",
                module="backups",
                trigger=trigger,
                backup_id=record_id,
            )
            raise
        finally:
            finished = _utcnow()
            record["finished_at"] = _iso(finished)
            record["duration_s"] = round((finished - started).total_seconds(), 2)
            _atomic_write(backups / "records" / f"{record_id}.json", record)

        try:
            cleanup = _cleanup_retention(backups, int(record["retention_days"]))
            record["retention"] = cleanup
            _atomic_write(backups / "records" / f"{record_id}.json", record)
        except Exception as exc:  # cleanup must not invalidate a good backup
            log_exception(
                exc,
                "backup",
                "backup retention cleanup failed",
                module="backups",
                backup_id=record_id,
            )

        log_event(
            "info",
            "backup",
            "backup completed",
            alert=False,
            module="backups",
            backup_id=record_id,
            trigger=trigger,
            database_kind=kind,
            storage_files=record["storage"].get("file_count", 0),
            duration_s=record["duration_s"],
        )
        return public_record(record)
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
        try:
            lock_path.unlink()
        except OSError:
            pass


def _read_records(backups: Path) -> list[dict[str, Any]]:
    records_dir = backups / "records"
    if not records_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in records_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            records.append(data)
    records.sort(key=lambda item: str(item.get("finished_at") or ""))
    return records


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    """Strip internal paths before returning a record to an API/CLI."""
    database = record.get("database") or {}
    storage = record.get("storage") or {}
    return {
        "id": record.get("id"),
        "status": record.get("status"),
        "trigger": record.get("trigger"),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at"),
        "duration_s": record.get("duration_s"),
        "database": {
            "kind": database.get("kind"),
            "format": database.get("format"),
            "size_bytes": database.get("size_bytes"),
            "sha256": database.get("sha256"),
            "row_count": database.get("row_count"),
        },
        "storage": {
            "file_count": storage.get("file_count", 0),
            "total_bytes": storage.get("total_bytes", 0),
            "new_objects": storage.get("new_objects", 0),
            "reused_objects": storage.get("reused_objects", 0),
        },
        "retention_days": record.get("retention_days"),
        "error": sanitize_text(record.get("error")) if record.get("error") else None,
    }


def backup_status(
    *,
    backup_dir: str | None = None,
) -> dict[str, Any]:
    backups, _storage = _paths(backup_dir, None)
    records = _read_records(backups)
    latest = records[-1] if records else None
    last_success = next(
        (item for item in reversed(records) if item.get("status") == "success"),
        None,
    )
    latest_restore = get_latest_restore(backup_dir=backup_dir)
    return {
        "enabled": bool(settings.BACKUP_ENABLED),
        "retention_days": int(settings.BACKUP_RETENTION_DAYS),
        "scheduled_hour_utc": int(settings.BACKUP_HOUR_UTC),
        "verify_after_run": bool(settings.BACKUP_VERIFY_AFTER_RUN),
        "latest": public_record(latest) if latest else None,
        "last_success": public_record(last_success) if last_success else None,
        "latest_restore": latest_restore,
        "record_count": len(records),
    }


def _restore_record_path(backups: Path, record_id: str | None) -> Path | None:
    if record_id:
        path = backups / "records" / f"{record_id}.json"
        return path if path.exists() else None
    records = _read_records(backups)
    for record in reversed(records):
        if record.get("status") == "success":
            return backups / "records" / f"{record['id']}.json"
    return None


def _sqlite_checks(restored: Path) -> dict[str, Any]:
    connection = sqlite3.connect(restored)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise BackupError("SQLite integrity_check failed.")
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise BackupError("SQLite foreign_key_check reported inconsistencies.")

        existing = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table'"
            ).fetchall()
        }
        missing = [table for table in REQUIRED_TABLES if table not in existing]
        if missing:
            raise BackupError(f"Restored database is missing tables: {', '.join(missing)}")

        counts = {
            table: int(connection.execute(f"select count(*) from {table}").fetchone()[0])
            for table in REQUIRED_TABLES
        }
        # Prove that rows are readable, not just countable.
        sample_profile = connection.execute(
            "select id, username from profiles order by created_at limit 1"
        ).fetchone()
        sample_analysis = connection.execute(
            "select id, filename from analyses order by created_at limit 1"
        ).fetchone()
        orphan_analyses = int(
            connection.execute(
                "select count(*) from analyses a "
                "left join profiles p on p.id = a.user_id where p.id is null"
            ).fetchone()[0]
        )
        if orphan_analyses:
            raise BackupError("Restored database contains analyses without an owner.")
        return {
            "integrity_check": "ok",
            "foreign_key_check": "ok",
            "tables": counts,
            "sample_profile_readable": sample_profile is not None,
            "sample_analysis_readable": sample_analysis is not None,
            "orphan_analyses": orphan_analyses,
        }
    finally:
        connection.close()


def _verify_sqlite_backup(db_path: Path, workdir: Path) -> dict[str, Any]:
    restored = workdir / "restored.sqlite"
    with gzip.open(db_path, "rb") as src, restored.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    return _sqlite_checks(restored)


def _verify_logical_backup(db_path: Path, workdir: Path) -> dict[str, Any]:
    """Restore the read-only JSONL dump into a temporary SQLite database."""
    from datetime import datetime as datetime_type

    from sqlalchemy import DateTime, JSON, create_engine

    import app.models.models  # noqa: F401 - register tables on Base.metadata
    from app.core.database import Base

    restored = workdir / "restored-logical.sqlite"
    engine = create_engine(f"sqlite:///{restored.as_posix()}")
    expected_counts: dict[str, int] = {}
    try:
        Base.metadata.create_all(engine)

        rows_by_table: dict[str, list[dict[str, Any]]] = {table: [] for table in REQUIRED_TABLES}
        seen_tables: set[str] = set()
        with gzip.open(db_path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                kind = item.get("type")
                table = item.get("table")
                if kind == "table" and table in rows_by_table:
                    seen_tables.add(table)
                elif kind == "row" and table in rows_by_table:
                    rows_by_table[table].append(item.get("data") or {})

        missing = [table for table in REQUIRED_TABLES if table not in seen_tables]
        if missing:
            raise BackupError(f"Logical backup is missing tables: {', '.join(missing)}")

        with engine.begin() as connection:
            for table_name in REQUIRED_TABLES:
                table = Base.metadata.tables[table_name]
                rows = rows_by_table.get(table_name) or []
                expected_counts[table_name] = len(rows)
                if not rows:
                    continue
                converted: list[dict[str, Any]] = []
                for row in rows:
                    output: dict[str, Any] = {}
                    for column in table.columns:
                        if column.name not in row:
                            continue
                        value = row[column.name]
                        if isinstance(column.type, DateTime) and isinstance(value, str):
                            try:
                                value = datetime_type.fromisoformat(value.replace("Z", "+00:00"))
                            except ValueError:
                                pass
                        elif isinstance(column.type, JSON) and isinstance(value, str):
                            try:
                                value = json.loads(value)
                            except ValueError:
                                pass
                        output[column.name] = value
                    converted.append(output)
                for start in range(0, len(converted), 500):
                    connection.execute(table.insert(), converted[start:start + 500])

        checks = _sqlite_checks(restored)
        if checks["tables"] != expected_counts:
            raise BackupError("Logical restore row counts do not match the backup stream.")
        checks["logical_row_counts"] = expected_counts
        return checks
    finally:
        engine.dispose()


def _verify_postgres_backup(
    dump_path: Path,
    restore_url: str,
) -> dict[str, Any]:
    if not restore_url:
        return {
            "status": "pending",
            "reason": "RESTORE_TEST_DATABASE_URL is not configured.",
        }
    prod = _parse_postgres(settings.DATABASE_URL)
    test = _parse_postgres(restore_url)
    if test["database"] == prod["database"] and test["host"] == prod["host"]:
        raise BackupError("RESTORE_TEST_DATABASE_URL points at the production database.")
    if not any(marker in test["database"].lower() for marker in ("test", "restore")):
        raise BackupError("Restore database name must contain 'test' or 'restore'.")

    pg_restore = shutil.which("pg_restore")
    psql = shutil.which("psql")
    if not pg_restore or not psql:
        return {
            "status": "pending",
            "reason": "pg_restore/psql are not installed on this host.",
        }

    env = os.environ.copy()
    env["PGPASSWORD"] = test["password"]
    if test["sslmode"]:
        env["PGSSLMODE"] = test["sslmode"]
    # Use a list, not a shell string, so the password never appears in argv.
    restore_cmd = [
        pg_restore,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "-h",
        test["host"],
        "-p",
        str(test["port"]),
        "-U",
        test["user"],
        "-d",
        test["database"],
        str(dump_path),
    ]
    completed = subprocess.run(
        restore_cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=max(60, int(settings.BACKUP_PG_DUMP_TIMEOUT_SECONDS)),
    )
    if completed.returncode != 0:
        raise BackupError(
            sanitize_text((completed.stderr or "pg_restore failed").strip()[-500:])
        )

    query = (
        "select "
        + ", ".join(f"(select count(*) from {table})" for table in REQUIRED_TABLES)
    )
    check_cmd = [
        psql,
        "-h",
        test["host"],
        "-p",
        str(test["port"]),
        "-U",
        test["user"],
        "-d",
        test["database"],
        "-At",
        "-c",
        query,
    ]
    checked = subprocess.run(
        check_cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if checked.returncode != 0:
        raise BackupError(
            sanitize_text((checked.stderr or "postgres verification failed").strip()[-500:])
        )
    values = [int(value) for value in checked.stdout.strip().split("|") if value.strip()]
    return {
        "status": "success",
        "tables": dict(zip(REQUIRED_TABLES, values)),
        "integrity_check": "restored",
        "foreign_key_check": "database constraints restored",
    }


def _verify_storage_backup(
    backups: Path,
    manifest_relative: str | None,
    workdir: Path,
) -> dict[str, Any]:
    if not manifest_relative:
        raise BackupError("Backup record has no storage manifest.")
    manifest_path = backups / manifest_relative
    if not manifest_path.exists():
        raise BackupError("Storage manifest is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("files") or []
    restored_root = workdir / "storage"
    restored_root.mkdir(parents=True, exist_ok=True)
    verified = 0
    total_bytes = 0
    for item in entries:
        digest = str(item.get("sha256") or "")
        if not digest:
            raise BackupError("Storage manifest contains an entry without a hash.")
        object_path = backups / "storage" / "objects" / digest[:2] / digest
        if not object_path.exists():
            raise BackupError("A storage object referenced by the manifest is missing.")
        if _sha256_file(object_path) != digest:
            raise BackupError("A restored storage object failed its hash check.")
        target = restored_root / str(item.get("path") or "unknown")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(object_path, target)
        verified += 1
        total_bytes += int(item.get("size") or 0)
    return {
        "status": "success",
        "files_verified": verified,
        "total_bytes": total_bytes,
    }


def run_restore_verification(
    record_id: str | None = None,
    *,
    backup_dir: str | None = None,
    restore_test_database_url: str | None = None,
) -> dict[str, Any]:
    """Restore a backup into an isolated workspace and verify it."""
    backups, _storage = _paths(backup_dir, None)
    record_path = _restore_record_path(backups, record_id)
    if record_path is None:
        result = {
            "id": _record_id(),
            "status": "pending",
            "reason": "No successful backup is available to verify.",
            "backup_id": None,
            "started_at": _iso(_utcnow()),
            "finished_at": _iso(_utcnow()),
        }
        _atomic_write(backups / "restores" / f"{result['id']}.json", result)
        return result

    record = json.loads(record_path.read_text(encoding="utf-8"))
    backup_id = str(record.get("id") or record_path.stem)
    started = _utcnow()
    result: dict[str, Any] = {
        "id": _record_id(),
        "status": "failed",
        "backup_id": backup_id,
        "started_at": _iso(started),
        "finished_at": None,
        "checks": {},
        "error": None,
    }
    workdir = backups / ".restore-work" / result["id"]
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        database = record.get("database") or {}
        kind = database.get("kind")
        db_relative = database.get("file")
        if not db_relative:
            raise BackupError("Backup record has no database file.")
        db_path = backups / str(db_relative)
        if not db_path.exists():
            raise BackupError("Backup database file is missing.")

        if kind == "sqlite":
            result["checks"]["database"] = _verify_sqlite_backup(db_path, workdir)
        elif kind == "postgres":
            db_format = str(database.get("format") or "pg_dump")
            if db_format == "logical":
                result["checks"]["database"] = _verify_logical_backup(db_path, workdir)
            else:
                pg_check = _verify_postgres_backup(
                    db_path,
                    restore_test_database_url or settings.RESTORE_TEST_DATABASE_URL,
                )
                result["checks"]["database"] = pg_check
                if pg_check.get("status") == "pending":
                    result["status"] = "pending"
                    result["reason"] = pg_check.get("reason")
        else:
            raise BackupError("Unknown database kind in backup record.")

        storage_info = record.get("storage") or {}
        result["checks"]["storage"] = _verify_storage_backup(
            backups,
            storage_info.get("manifest"),
            workdir,
        )
        if result["status"] != "pending":
            result["status"] = "success"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = sanitize_text(f"{type(exc).__name__}: {exc}")[:500]
        log_exception(
            exc,
            "restore",
            "backup restore verification failed",
            module="backups",
            backup_id=backup_id,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        finished = _utcnow()
        result["finished_at"] = _iso(finished)
        result["duration_s"] = round((finished - started).total_seconds(), 2)
        _atomic_write(backups / "restores" / f"{result['id']}.json", result)

    if result["status"] == "success":
        log_event(
            "info",
            "restore",
            "backup restore verification succeeded",
            alert=False,
            module="backups",
            backup_id=backup_id,
            duration_s=result.get("duration_s"),
        )
    elif result["status"] == "pending":
        log_event(
            "warning",
            "restore",
            "backup restore verification pending",
            alert=False,
            module="backups",
            backup_id=backup_id,
            reason=result.get("reason"),
        )
    return result


def get_latest_restore(*, backup_dir: str | None = None) -> dict[str, Any] | None:
    backups, _storage = _paths(backup_dir, None)
    restores_dir = backups / "restores"
    if not restores_dir.is_dir():
        return None
    latest: dict[str, Any] | None = None
    for path in restores_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if latest is None or str(data.get("finished_at") or "") > str(latest.get("finished_at") or ""):
            latest = data
    if not latest:
        return None
    return {
        "id": latest.get("id"),
        "status": latest.get("status"),
        "backup_id": latest.get("backup_id"),
        "started_at": latest.get("started_at"),
        "finished_at": latest.get("finished_at"),
        "duration_s": latest.get("duration_s"),
        "reason": latest.get("reason"),
        "error": sanitize_text(latest.get("error")) if latest.get("error") else None,
        "checks": latest.get("checks") or {},
    }


def _last_success_record(backups: Path) -> dict[str, Any] | None:
    records = _read_records(backups)
    return next(
        (item for item in reversed(records) if item.get("status") == "success"),
        None,
    )


def should_run_scheduled(*, backup_dir: str | None = None) -> bool:
    if not settings.BACKUP_ENABLED:
        return False
    now = _utcnow()
    if now.hour < max(0, min(23, int(settings.BACKUP_HOUR_UTC))):
        return False
    backups, _storage = _paths(backup_dir, None)
    last = _last_success_record(backups)
    if not last:
        return True
    try:
        finished = datetime.fromisoformat(str(last.get("finished_at")).replace("Z", "+00:00"))
    except ValueError:
        return True
    return finished.date() < now.date()


def scheduled_backup() -> dict[str, Any]:
    result = create_backup(trigger="scheduled")
    if settings.BACKUP_VERIFY_AFTER_RUN:
        verification = run_restore_verification(result["id"])
        result["restore_verification"] = {
            "status": verification.get("status"),
            "id": verification.get("id"),
        }
    return result


async def backup_scheduler_loop() -> None:
    """Hourly wake-up; runs once per UTC day after BACKUP_HOUR_UTC."""
    interval = max(300, int(settings.BACKUP_CHECK_INTERVAL_MINUTES) * 60)
    while True:
        try:
            if should_run_scheduled():
                await asyncio.to_thread(scheduled_backup)
        except asyncio.CancelledError:
            raise
        except BackupBusy:
            log_event(
                "info",
                "backup",
                "scheduled backup skipped because another job is running",
                alert=False,
                module="backup-scheduler",
            )
        except Exception as exc:
            log_exception(
                exc,
                "backup",
                "scheduled backup failed",
                module="backup-scheduler",
            )
        await asyncio.sleep(interval)