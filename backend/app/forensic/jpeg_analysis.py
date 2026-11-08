"""JPEG compression + double-compression + ghost analysis."""
import io
import numpy as np
import cv2
from PIL import Image
from .common import to_gray, detector_result


def _jpeg_size(img_rgb: np.ndarray, q: int) -> int:
    buf = io.BytesIO()
    Image.fromarray(img_rgb).save(buf, "JPEG", quality=q)
    return len(buf.getvalue())


def analyze_jpeg(img_rgb: np.ndarray, raw: bytes, orig_format: str) -> dict:
    gray = to_gray(img_rgb)
    # blocking artifact measure: mean abs diff across 8x8 grid lines vs inside
    h, w = gray.shape
    g = gray.astype(np.float32)
    vert_lines = np.abs(np.diff(g[:, 7::8], axis=1)).mean() if w > 16 else 0
    vert_inside = np.abs(np.diff(g, axis=1)).mean() + 1e-8
    blockiness = float(vert_lines / vert_inside)
    # double-JPEG hint: recompress at several qualities, look for non-monotonic SSIM-ish curve
    sizes = [_jpeg_size(img_rgb, q) for q in (60, 75, 90)]
    mono = sizes[0] < sizes[1] < sizes[2]
    # ghost: recompress at q=70 and correlate with original blocks
    buf = io.BytesIO()
    Image.fromarray(img_rgb).save(buf, "JPEG", quality=70)
    buf.seek(0)
    ghost = np.array(Image.open(buf).convert("L")).astype(np.float32)
    gh, gw = min(h, ghost.shape[0]), min(w, ghost.shape[1])
    corr = float(np.corrcoef(gray[:gh, :gw].ravel()[::37], ghost[:gh, :gw].ravel()[::37])[0, 1])
    corr = 0.0 if np.isnan(corr) else corr
    if orig_format.upper() in ("JPG", "JPEG"):
        score = float(np.clip(0.55 + (0.15 if mono else -0.2) + np.clip((blockiness - 1.0), -0.3, 0.3), 0, 1))
        interp = "JPEG structure consistent with normal camera compression." if score > 0.55 else "JPEG statistics look re-saved/irregular — possible re-export after editing."
        conf = 0.60
    else:
        score, conf = 0.5, 0.35
        interp = "Image is not JPEG; compression analysis is limited."
    return detector_result("JPEG", score, conf, interp, {
        "blockiness": round(blockiness, 3), "recompress_sizes": sizes,
        "monotonic_sizes": bool(mono), "ghost_corr_q70": round(corr, 3)})
