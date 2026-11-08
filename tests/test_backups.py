"""Backup + isolated restore verification tests (safe temporary databases only)."""
from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from app.services.backups import (
    BackupError,
    create_backup,
    run_restore_verification,
)


def _create_fixture_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            pragma foreign_keys = on;
            create table profiles (
              id text primary key,
              username text unique not null,
              email text unique not null,
              password_hash text,
              role text not null default 'CUSTOMER',
              status text not null default 'active',
              created_at text,
              updated_at text
            );
            create table analyses (
              id text primary key,
              user_id text not null references profiles(id) on delete cascade,
              filename text not null,
              storage_path text not null,
              mime text,
              size_bytes integer,
              status text,
              verdict text,
              confidence real,
              final_score real,
              processing_time_s real,
              created_at text,
              completed_at text
            );
            create table analysis_results (
              id text primary key,
              analysis_id text unique not null references analyses(id) on delete cascade,
              full_json text not null
            );
            create table suspicious_regions (
              id text primary key,
              analysis_id text not null references analyses(id) on delete cascade,
              x integer not null, y integer not null,
              width integer not null, height integer not null,
              reason text
            );
            create table audit_logs (
              id text primary key,
              user_id text references profiles(id) on delete set null,
              action text not null,
              detail text,
              created_at text
            );
            """
        )
        connection.execute(
            "insert into profiles values (?,?,?,?,?,?,?,?)",
            ("user-1", "customer_one", "one@example.com", "$2b$12$hash", "CUSTOMER", "active", "2026-01-01", "2026-01-01"),
        )
        connection.execute(
            "insert into analyses values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "analysis-1", "user-1", "photo.jpg", "user-1/photo.jpg", "image/jpeg",
                1234, "completed", "LIKELY_REAL", 0.9, 0.8, 1.2, "2026-01-01", "2026-01-01",
            ),
        )
        connection.execute(
            "insert into analysis_results values (?,?,?)",
            ("result-1", "analysis-1", '{"verdict":"LIKELY_REAL"}'),
        )
        connection.execute(
            "insert into suspicious_regions values (?,?,?,?,?,?,?)",
            ("region-1", "analysis-1", 1, 2, 3, 4, "test region"),
        )
        connection.execute(
            "insert into audit_logs values (?,?,?,?,?)",
            ("audit-1", "user-1", "login", "ok", "2026-01-01"),
        )
        connection.commit()
    finally:
        connection.close()


def test_backup_and_restore_verification(tmp_path: Path):
    database = tmp_path / "source.db"
    storage = tmp_path / "storage"
    backups = tmp_path / "backups"
    storage.mkdir()
    (storage / "user-1").mkdir()
    (storage / "user-1" / "photo.jpg").write_bytes(b"jpeg-bytes-1")
    (storage / "user-1" / "second.png").write_bytes(b"png-bytes-2")
    _create_fixture_db(database)

    url = f"sqlite:///{database.as_posix()}"
    record = create_backup(
        "test",
        database_url=url,
        storage_path=str(storage),
        backup_dir=str(backups),
        retention_days=14,
    )

    assert record["status"] == "success"
    assert record["database"]["kind"] == "sqlite"
    assert record["database"]["size_bytes"] > 0
    assert record["storage"]["file_count"] == 2
    assert "file" not in record["database"]  # internal path is not exposed
    assert "manifest" not in record["storage"]

    verification = run_restore_verification(record["id"], backup_dir=str(backups))
    assert verification["status"] == "success", verification
    checks = verification["checks"]
    assert checks["database"]["integrity_check"] == "ok"
    assert checks["database"]["foreign_key_check"] == "ok"
    assert checks["database"]["tables"]["profiles"] == 1
    assert checks["database"]["tables"]["analyses"] == 1
    assert checks["database"]["tables"]["analysis_results"] == 1
    assert checks["database"]["tables"]["suspicious_regions"] == 1
    assert checks["database"]["tables"]["audit_logs"] == 1
    assert checks["database"]["sample_profile_readable"] is True
    assert checks["database"]["sample_analysis_readable"] is True
    assert checks["storage"]["files_verified"] == 2


def test_unchanged_storage_files_are_deduplicated(tmp_path: Path):
    database = tmp_path / "source.db"
    storage = tmp_path / "storage"
    backups = tmp_path / "backups"
    storage.mkdir()
    (storage / "user-1").mkdir()
    (storage / "user-1" / "one.jpg").write_bytes(b"one")
    (storage / "user-1" / "two.jpg").write_bytes(b"two")
    _create_fixture_db(database)
    url = f"sqlite:///{database.as_posix()}"

    first = create_backup(
        "test", database_url=url, storage_path=str(storage),
        backup_dir=str(backups), retention_days=14,
    )
    assert first["storage"]["new_objects"] == 2
    assert first["storage"]["reused_objects"] == 0

    (storage / "user-1" / "three.jpg").write_bytes(b"three")
    second = create_backup(
        "test", database_url=url, storage_path=str(storage),
        backup_dir=str(backups), retention_days=14,
    )
    assert second["storage"]["new_objects"] == 1
    assert second["storage"]["reused_objects"] == 2

    verification = run_restore_verification(second["id"], backup_dir=str(backups))
    assert verification["status"] == "success"
    assert verification["checks"]["storage"]["files_verified"] == 3


def test_backup_dir_inside_storage_is_rejected(tmp_path: Path):
    database = tmp_path / "source.db"
    storage = tmp_path / "storage"
    _create_fixture_db(database)
    storage.mkdir()

    with pytest.raises(BackupError):
        create_backup(
            "test",
            database_url=f"sqlite:///{database.as_posix()}",
            storage_path=str(storage),
            backup_dir=str(storage / "backups"),
            retention_days=14,
        )


def test_restore_without_a_backup_is_pending(tmp_path: Path):
    result = run_restore_verification(backup_dir=str(tmp_path / "empty-backups"))
    assert result["status"] == "pending"
    assert result["backup_id"] is None


def test_retention_removes_old_records_and_unreferenced_objects(tmp_path: Path):
    from datetime import datetime, timedelta, timezone

    database = tmp_path / "source.db"
    storage = tmp_path / "storage"
    backups = tmp_path / "backups"
    storage.mkdir(parents=True)
    (storage / "user-1").mkdir()
    (storage / "user-1" / "photo.jpg").write_bytes(b"current-image")
    _create_fixture_db(database)

    (backups / "db").mkdir(parents=True)
    (backups / "records").mkdir(parents=True)
    (backups / "storage" / "manifests").mkdir(parents=True)
    old_payload = b"old-image"
    old_digest = hashlib.sha256(old_payload).hexdigest()
    old_object = backups / "storage" / "objects" / old_digest[:2] / old_digest
    old_object.parent.mkdir(parents=True)
    old_object.write_bytes(old_payload)
    old_db = backups / "db" / "old.jsonl.gz"
    old_db.write_bytes(b"old")
    old_manifest = backups / "storage" / "manifests" / "old.json"
    old_manifest.write_text(
        json.dumps({"files": [{"path": "old/photo.jpg", "sha256": old_digest, "size": len(old_payload)}]}),
        encoding="utf-8",
    )
    old_finished = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    old_record = backups / "records" / "old.json"
    old_record.write_text(
        json.dumps(
            {
                "id": "old",
                "status": "success",
                "trigger": "test",
                "finished_at": old_finished,
                "database": {"kind": "postgres", "format": "logical", "file": "db/old.jsonl.gz"},
                "storage": {"manifest": "storage/manifests/old.json", "file_count": 1},
            }
        ),
        encoding="utf-8",
    )

    create_backup(
        "test",
        database_url=f"sqlite:///{database.as_posix()}",
        storage_path=str(storage),
        backup_dir=str(backups),
        retention_days=1,
    )

    assert not old_record.exists()
    assert not old_db.exists()
    assert not old_manifest.exists()
    assert not old_object.exists()


def _logical_rows() -> list[dict]:
    return [
        {
            "type": "table",
            "table": "profiles",
            "columns": ["id", "username", "email", "password_hash", "role", "status", "created_at", "updated_at"],
        },
        {
            "type": "row",
            "table": "profiles",
            "data": {
                "id": "user-1", "username": "customer_one", "email": "one@example.com",
                "password_hash": "$2b$12$hash", "role": "CUSTOMER", "status": "active",
                "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
            },
        },
        {
            "type": "table",
            "table": "analyses",
            "columns": ["id", "user_id", "filename", "storage_path", "mime", "size_bytes", "status",
                        "verdict", "confidence", "final_score", "processing_time_s", "created_at", "completed_at"],
        },
        {
            "type": "row",
            "table": "analyses",
            "data": {
                "id": "analysis-1", "user_id": "user-1", "filename": "photo.jpg",
                "storage_path": "user-1/photo.jpg", "mime": "image/jpeg", "size_bytes": 4,
                "status": "completed", "verdict": "LIKELY_REAL", "confidence": 0.9,
                "final_score": 0.8, "processing_time_s": 1.2,
                "created_at": "2026-01-01T00:00:00Z", "completed_at": "2026-01-01T00:00:00Z",
            },
        },
        {
            "type": "table",
            "table": "analysis_results",
            "columns": ["id", "analysis_id", "full_json"],
        },
        {
            "type": "row",
            "table": "analysis_results",
            "data": {"id": "result-1", "analysis_id": "analysis-1", "full_json": {"verdict": "LIKELY_REAL"}},
        },
        {
            "type": "table",
            "table": "suspicious_regions",
            "columns": ["id", "analysis_id", "x", "y", "width", "height", "reason"],
        },
        {
            "type": "row",
            "table": "suspicious_regions",
            "data": {"id": "region-1", "analysis_id": "analysis-1", "x": 1, "y": 2, "width": 3, "height": 4, "reason": "test"},
        },
        {
            "type": "table",
            "table": "audit_logs",
            "columns": ["id", "user_id", "action", "detail", "created_at"],
        },
        {
            "type": "row",
            "table": "audit_logs",
            "data": {"id": "audit-1", "user_id": "user-1", "action": "login", "detail": "ok", "created_at": "2026-01-01T00:00:00Z"},
        },
    ]


def test_logical_postgres_backup_restores_without_postgres_tools(tmp_path: Path):
    backups = tmp_path / "backups"
    (backups / "db").mkdir(parents=True)
    (backups / "records").mkdir(parents=True)
    (backups / "storage" / "manifests").mkdir(parents=True)

    db_file = backups / "db" / "logical-test.jsonl.gz"
    with gzip.open(db_file, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "meta", "format": "logical", "version": 1}) + "\n")
        for item in _logical_rows():
            handle.write(json.dumps(item) + "\n")

    payload = b"image-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    object_path = backups / "storage" / "objects" / digest[:2] / digest
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(payload)
    manifest_path = backups / "storage" / "manifests" / "logical-test.json"
    manifest_path.write_text(
        json.dumps({"backup_id": "logical-test", "files": [{"path": "user-1/photo.jpg", "sha256": digest, "size": len(payload)}]}),
        encoding="utf-8",
    )
    record = {
        "id": "logical-test",
        "status": "success",
        "trigger": "test",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:00Z",
        "duration_s": 0.1,
        "database": {"kind": "postgres", "format": "logical", "file": "db/logical-test.jsonl.gz",
                     "size_bytes": db_file.stat().st_size, "sha256": "test"},
        "storage": {"manifest": "storage/manifests/logical-test.json", "file_count": 1, "total_bytes": len(payload)},
        "retention_days": 14,
        "error": None,
    }
    (backups / "records" / "logical-test.json").write_text(json.dumps(record), encoding="utf-8")

    verification = run_restore_verification("logical-test", backup_dir=str(backups))
    assert verification["status"] == "success", verification
    checks = verification["checks"]
    assert checks["database"]["logical_row_counts"]["profiles"] == 1
    assert checks["database"]["logical_row_counts"]["analyses"] == 1
    assert checks["database"]["logical_row_counts"]["analysis_results"] == 1
    assert checks["storage"]["files_verified"] == 1
