"""Shared forensic helpers — all detectors use these."""
import base64
import io
import cv2
import numpy as np
from PIL import Image


def decode_image_bytes(raw: bytes) -> np.ndarray:
    """Decode bytes -> RGB uint8 array. Raises ValueError on failure."""
    arr = np.frombuffer(raw, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        # fallback through PIL (supports webp/png better)
        try:
            pil = Image.open(io.BytesIO(raw)).convert("RGB")
            return np.array(pil)
        except Exception as e:
            raise ValueError(f"Cannot decode image: {e}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return img


def resize_max(img: np.ndarray, max_side: int = 1024) -> np.ndarray:
    h, w = img.shape[:2]
    s = min(1.0, max_side / max(h, w))
    if s >= 1.0:
        return img
    return cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)


def encode_png_b64(img: np.ndarray, normalize: bool = True) -> str:
    """Encode gray/RGB array as base64 PNG for API transport."""
    if normalize:
        m, M = float(img.min()), float(img.max())
        if M > m:
            img = ((img - m) / (M - m) * 255).astype(np.uint8)
        else:
            img = np.zeros_like(img, dtype=np.uint8)
    elif img.dtype != np.uint8:
        img = np.clip(img, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if img.ndim == 3 else img)
    if not ok:
        raise RuntimeError("PNG encode failed")
    return base64.b64encode(buf.tobytes()).decode()


def detector_result(method: str, score: float, confidence: float, interpretation: str, details: dict | None = None):
    """Standard detector envelope. score 0..1 (1 = camera-real-like)."""
    return {
        "method": method,
        "score": round(float(np.clip(score, 0, 1)), 4),
        "confidence": round(float(np.clip(confidence, 0, 1)), 4),
        "interpretation": interpretation,
        "details": details or {},
    }
