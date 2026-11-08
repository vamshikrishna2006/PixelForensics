"""Secure upload validation: MIME + magic bytes + real decode + size + traversal-safe names."""
import imghdr
import os
import re
import uuid
from pathlib import Path

MAGIC = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png", b"RIFF": "image/webp"}
MAX_BYTES_DEFAULT = 10 * 1024 * 1024


def sniff_mime(raw: bytes) -> str | None:
    for magic, mime in MAGIC.items():
        if raw.startswith(magic):
            if magic == b"RIFF" and raw[8:12] != b"WEBP":
                return None
            return mime
    kind = imghdr.what(None, raw)
    return {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(kind or "")


def validate_upload(raw: bytes, filename: str, content_type: str, allowed: list[str], max_bytes: int):
    if len(raw) > max_bytes:
        raise ValueError(f"File too large (max {max_bytes // 1024 // 1024} MB).")
    if len(raw) < 100:
        raise ValueError("File is empty or truncated.")
    sniffed = sniff_mime(raw)
    ext = os.path.splitext(filename)[1].lower()
    ext_ok = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    if sniffed not in allowed or content_type not in allowed:
        raise ValueError("Unsupported or mismatched image type. Use JPG, PNG or WEBP.")
    if ext not in ext_ok or ext_ok[ext] != sniffed:
        raise ValueError("File extension does not match image content.")
    # real decode check
    from app.forensic.common import decode_image_bytes
    try:
        decode_image_bytes(raw)
    except Exception:
        raise ValueError("File is corrupted or not a decodable image.")
    return sniffed


def safe_storage_name(user_id: str, ext: str) -> str:
    ext = ext.lower() if ext.lower() in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
    safe_user = re.sub(r"[^A-Za-z0-9_-]", "_", str(user_id))[:64] or "unknown"
    return f"{safe_user}/{uuid.uuid4().hex}{ext}"  # non-predictable, no user input in path


def storage_file_path(root: str, relative_path: str) -> Path:
    """Resolve a stored path and refuse anything outside the storage root."""
    base = Path(root).expanduser().resolve()
    target = (base / str(relative_path)).resolve()
    if target != base and base not in target.parents:
        raise ValueError("Invalid storage path.")
    return target
