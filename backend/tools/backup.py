"""Run a database + storage backup from an external scheduler.

Examples:
    python tools/backup.py
    python tools/backup.py --verify
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.backups import create_backup, run_restore_verification  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="PixelForensics backup")
    parser.add_argument("--verify", action="store_true", help="run an isolated restore check")
    parser.add_argument("--trigger", default="cli", help="label stored in the backup record")
    args = parser.parse_args()

    try:
        record = create_backup(trigger=args.trigger)
        result = {"backup": record}
        if args.verify:
            verification = run_restore_verification(record["id"])
            result["restore_verification"] = {
                "id": verification.get("id"),
                "status": verification.get("status"),
                "reason": verification.get("reason"),
                "error": verification.get("error"),
            }
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"status": "failed", "error": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())