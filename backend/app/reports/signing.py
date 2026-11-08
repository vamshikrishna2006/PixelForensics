"""Tamper-evident signature for generated reports.

Each PDF carries an HMAC-SHA256 digest over a canonical description of the
report (id, subject file, verdict, scores, creation time and algorithm version).
The same digest is served by ``GET /api/report/{id}/signature``, so a printed or
forwarded PDF can be checked against the issuing deployment: if the values in
the document were altered, the digest no longer matches.

HMAC (rather than a public-key signature) is used because the deployment only
has a symmetric ``SECRET_KEY``. It proves the document was produced by this
server; it does not give third-party non-repudiation.
"""
from __future__ import annotations

import hashlib
import hmac

from app.core.config import get_settings

settings = get_settings()

ALGORITHM = "HMAC-SHA256"
ISSUER = "PixelForensics"


def canonical_payload(meta: dict) -> str:
    """Stable string that identifies this report's content."""
    return "|".join([
        f"report={meta.get('id', '')}",
        f"file={meta.get('filename', '')}",
        f"verdict={meta.get('verdict', '')}",
        f"final={float(meta.get('final_score') or 0.0):.4f}",
        f"confidence={float(meta.get('confidence') or 0.0):.4f}",
        f"created={meta.get('created_at', '')}",
        f"algorithm={meta.get('algorithm_version') or settings.FORENSIC_ALGORITHM_VERSION}",
    ])


def sign_meta(meta: dict) -> dict:
    """Return the signature block embedded in the PDF and exposed by the API."""
    payload = canonical_payload(meta)
    digest = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"),
                      hashlib.sha256).hexdigest()
    grouped = "-".join(digest[i:i + 8].upper() for i in range(0, 32, 8))
    return {
        "issuer": ISSUER,
        "algorithm": ALGORITHM,
        "digest": digest,
        "signature_id": f"PF-{grouped}",
        "payload": payload,
        "algorithm_version": meta.get("algorithm_version") or settings.FORENSIC_ALGORITHM_VERSION,
    }
