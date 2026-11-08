"""External-safe readiness check for a cron job or uptime monitor.

Usage:
    HEALTHCHECK_URL=https://your-site.example/api/ready python tools/healthcheck.py

Returns 0 when ready, 1 when unavailable. If alert delivery is configured, a
failure queues an alert through the same AlertManager used by the API.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib import request as urlrequest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.observability import alert_manager  # noqa: E402


def main() -> int:
    url = os.getenv("HEALTHCHECK_URL", "http://127.0.0.1:8000/api/ready")
    try:
        with urlrequest.urlopen(url, timeout=10) as response:
            if 200 <= response.status < 300:
                print("ready")
                return 0
            raise RuntimeError(f"HTTP {response.status}")
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        alert_manager.notify(
            "critical",
            "availability",
            "PixelForensics readiness check failed",
            {"module": "healthcheck", "error_type": type(exc).__name__},
        )
        print(f"unavailable: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())