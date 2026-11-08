"""Human-readable, image-specific report names.

Downloads used to arrive as ``report.pdf`` every time. The report is now named
after the image it describes:

* if the upload has a meaningful stem ("Late-Night Study_Discipline Builds
  Freedom.png") the stem is cleaned and used;
* if the stem is meaningless ("IMG_4821", "Screenshot 2026-10-23 104512",
  "1234567890", "4f7a9c8b2e...") the name is derived from the measured scene
  profile ("LowLight-Warm-Widescreen") plus the analysis date.

Output is slug-safe ASCII (letters, digits, single hyphens) so it survives every
browser, mail client and file system.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

# Tokens that carry no information about the picture itself.
_GENERIC = {
    "img", "imgs", "image", "images", "dsc", "dscf", "dscn", "dcim", "pxl", "mvimg",
    "photo", "photos", "picture", "pictures", "pic", "pics", "shot", "shots",
    "screenshot", "screen", "snip", "capture", "camera", "file", "files", "tmp",
    "temp", "input", "output", "upload", "uploads", "download", "downloads",
    "untitled", "new", "copy", "edited", "edit", "export", "exported", "final",
    "whatsapp", "telegram", "signal", "messenger", "facebook", "instagram",
    "scan", "scanned", "document", "doc", "sample", "test", "default", "blob",
}

_HEX_RE = re.compile(r"^[0-9a-f]{12,}$")
_DATE_RE = re.compile(r"^(19|20)\d{6}$")
_TIME_RE = re.compile(r"^\d{5,6}$")


def _strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _meaningful_token(token: str) -> bool:
    low = token.lower()
    if low in _GENERIC:
        return False
    if low.isdigit():
        return False
    if _HEX_RE.match(low) or _DATE_RE.match(low) or _TIME_RE.match(low):
        return False
    if len(low) < 3:
        return False
    if not any(ch.isalpha() for ch in low):
        return False
    # Reject hex-like fragments (e.g. "2c4c", "9e98", "03f7d970163c") that come
    # from UUIDs or content hashes: they are all hex digits and carry no meaning.
    if re.fullmatch(r"[0-9a-f]{3,}", low):
        return False
    return True


def _title(token: str) -> str:
    token = token.strip("-")
    if not token:
        return ""
    return token[:1].upper() + token[1:].lower()


def clean_stem(stem: str, max_words: int = 6) -> str:
    """Turn a file stem into a readable, slug-safe base name ('' if meaningless)."""
    text = _strip_accents(str(stem or ""))
    text = re.sub(r"[_\-.+()\[\]{}]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = [w for w in text.split(" ") if _meaningful_token(w)]
    if not words:
        return ""
    joined = "".join(words)
    if len(joined) < 4 or not any(len(w) >= 3 for w in words):
        return ""
    base = "-".join(_title(w) for w in words[:max_words])
    return base[:64].strip("-")


def _date_str(when=None) -> str:
    if isinstance(when, datetime):
        return when.strftime("%Y-%m-%d")
    if isinstance(when, str) and len(when) >= 10:
        try:
            return datetime.fromisoformat(when.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except ValueError:
            return when[:10]
    return datetime.utcnow().strftime("%Y-%m-%d")


def scene_basename(profile: dict | None, when=None) -> str:
    """Name a report after what the frame looks like, when the filename tells us nothing."""
    profile = profile or {}
    label = str(profile.get("scene_label") or "").strip()
    parts = [p for p in re.split(r"[_\-]+", label) if p]
    readable = "-".join(_title(p) for p in parts) if parts else "Unclassified-Scene"
    mp = profile.get("megapixels")
    if mp:
        readable += f"-{float(mp):.1f}MP".replace(".0MP", "MP")
    return f"{readable}-{_date_str(when)}"


def report_basename(filename: str | None, profile: dict | None = None, when=None) -> str:
    """Base name for the report, without extension or fixed suffix."""
    import os

    stem = os.path.splitext(os.path.basename(str(filename or "")))[0]
    base = clean_stem(stem)
    if base:
        return base
    return scene_basename(profile, when)


def report_name_from_result(result: dict) -> str:
    """Convenience wrapper: derive the base name from a stored analysis JSON."""
    info = result.get("image_info") or {}
    detectors = {d.get("method"): d for d in (result.get("detectors") or [])}
    filename = ((detectors.get("METADATA") or {}).get("details") or {}).get("filename")
    return report_basename(filename, result.get("image_profile"), result.get("created_at"))


def download_name(base: str, extension: str) -> str:
    safe = base or "PixelForensics-Report"
    ext = extension.lower().lstrip(".")
    return f"{safe}-Forensic-Report.{ext}"
