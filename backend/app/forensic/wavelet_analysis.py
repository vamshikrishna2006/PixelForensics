"""Wavelet decomposition LL/LH/HL/HH + high-frequency energy analysis."""
import cv2
import numpy as np
import pywt
from .common import to_gray, detector_result, encode_png_b64


def analyze_wavelet(img_rgb: np.ndarray) -> dict:
    gray = to_gray(img_rgb).astype(np.float32)
    LL, (LH, HL, HH) = pywt.dwt2(gray, "db4")
    e = lambda a: float((a ** 2).mean())
    eLL, eLH, eHL, eHH = e(LL), e(LH), e(HL), e(HH)
    tot = eLH + eHL + eHH + 1e-8
    hf_share = (eLH + eHL + eHH) / (eLL + tot + 1e-8)
    # natural photos: moderate HF share; over-smooth AI images: very low; noisy: very high
    score = float(np.clip(1.0 - abs(hf_share - 0.08) * 8.0, 0, 1))
    interp = (
        "Wavelet sub-bands show natural texture energy distribution."
        if score > 0.6 else
        "Wavelet high-frequency distribution is atypical (over-smooth or spiky)."
        if score < 0.4 else "Wavelet evidence is mixed."
    )
    thumbs = {k: encode_png_b64(v) for k, v in {"LL": LL, "LH": LH, "HL": HL, "HH": HH}.items()}
    return detector_result("WAVELET", score, 0.66, interp, {
        "eLL": round(eLL, 2), "eLH": round(eLH, 2), "eHL": round(eHL, 2),
        "eHH": round(eHH, 2), "hf_share": round(float(hf_share), 4), "thumbs": thumbs})
