"""Error Level Analysis (ELA) — JPEG recompression-difference detector."""
import cv2
import io
import numpy as np
from PIL import Image
from .common import detector_result, encode_png_b64


def ela_image(img_rgb: np.ndarray, quality: int = 90) -> np.ndarray:
    pil = Image.fromarray(img_rgb)
    buf = io.BytesIO()
    pil.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    recomp = np.array(Image.open(buf).convert("RGB"))
    diff = np.abs(img_rgb.astype(np.int16) - recomp.astype(np.int16)).astype(np.uint8)
    return diff


def analyze_ela(img_rgb: np.ndarray, orig_format: str = "JPEG") -> dict:
    diff = ela_image(img_rgb)
    gray = cv2.cvtColor(diff, cv2.COLOR_RGB2GRAY).astype(np.float32)
    mean_e = float(gray.mean())
    std_e = float(gray.std())
    # uniform high ELA error or extreme local spikes => suspicious
    score = float(np.clip(1.0 - abs(mean_e - 6.0) / 18.0 - max(0.0, std_e - 14.0) / 40.0, 0, 1))
    if orig_format.upper() not in ("JPG", "JPEG"):
        interp = "Source was not JPEG; ELA is less conclusive (recompression history differs)."
        conf = 0.45
    else:
        interp = ("ELA error is even and low — consistent with a single JPEG pass."
                  if score > 0.6 else
                  "ELA shows localized error differences — potential local retouch/splice."
                  if score < 0.4 else "ELA evidence is mixed.")
        conf = 0.62
    return detector_result("ELA", score, conf, interp,
                           {"mean_error": round(mean_e, 2), "std_error": round(std_e, 2),
                            "ela_b64": encode_png_b64((gray * 6).clip(0, 255), normalize=False)})
