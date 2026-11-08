"""EXIF / metadata extraction. Metadata is supporting evidence only."""
import io
from PIL import Image, ExifTags
from .common import detector_result

GPS_IFD = 34853
TAG_NAMES = {v: k for k, v in ExifTags.TAGS.items()}


def analyze_metadata(raw: bytes, filename: str, mime: str) -> dict:
    info: dict = {"filename": filename, "mime": mime, "size_bytes": len(raw),
                  "has_exif": False, "make": None, "model": None,
                  "datetime": None, "software": None, "has_gps": False}
    try:
        pil = Image.open(io.BytesIO(raw))
        info["format"] = pil.format
        info["width"], info["height"] = pil.size
        info["mode"] = pil.mode
        exif = pil.getexif()
        if exif:
            info["has_exif"] = True
            get = lambda name: exif.get(TAG_NAMES.get(name))
            info["make"] = str(get("Make") or "") or None
            info["model"] = str(get("Model") or "") or None
            info["datetime"] = str(get("DateTimeOriginal") or get("DateTime") or "") or None
            info["software"] = str(get("Software") or "") or None
            gps = exif.get_ifd(GPS_IFD) if hasattr(exif, "get_ifd") else None
            info["has_gps"] = bool(gps)
    except Exception:
        pass
    ai_software = any(s in (info.get("software") or "").lower()
                      for s in ("stable diffusion", "midjourney", "dall", "firefly", "comfyui", "automatic1111"))
    if ai_software:
        score, interp, conf = 0.1, "Software tag references a generative tool — strong manipulation indicator.", 0.85
    elif info["make"] or info["model"]:
        score, interp, conf = 0.85, "Camera make/model present — supports authentic capture (but EXIF can be forged).", 0.55
    elif info["has_exif"]:
        score, interp, conf = 0.6, "Some EXIF present but no camera make/model.", 0.45
    else:
        score, interp, conf = 0.4, "No camera EXIF found — common for AI images, screenshots, and social-media downloads.", 0.4
    info["warning"] = "Metadata can be stripped or forged; never treat as proof." + (
        " GPS coordinates detected — hidden from display for privacy." if info["has_gps"] else "")
    return detector_result("METADATA", score, conf, interp, info)
