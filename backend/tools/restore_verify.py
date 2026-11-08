"""Verify that a backup can be restored into an isolated workspace."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.backups import run_restore_verification  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="PixelForensics restore verification")
    parser.add_argument("--backup", default=None, help="backup record id (default: latest success)")
    args = parser.parse_args()

    result = run_restore_verification(args.backup)
    print(json.dumps(result, indent=2, default=str))
    if result.get("status") == "success":
        return 0
    if result.get("status") == "pending":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())