"""Wavelet-based denoising + noise residual extraction (core of PRNU pipeline)."""
import cv2
import numpy as np
import pywt
from .common import to_gray, detector_result


def wavelet_denoise(gray: np.ndarray, wavelet: str = "db8", level: int = 2) -> np.ndarray:
    coeffs = pywt.wavedec2(gray.astype(np.float32), wavelet, level=level)
    # BayesShrink-like threshold on detail coeffs
    detail = np.concatenate([c.ravel() for _, (cH, cV, cD) in [(None, t) for t in coeffs[1:]] for c in (cH, cV, cD)])
    sigma = np.median(np.abs(detail)) / 0.6745 + 1e-8
    thr = sigma * np.sqrt(2 * np.log(max(gray.size, 2)))
    out = [coeffs[0]]
    for cH, cV, cD in coeffs[1:]:
        out.append(tuple(pywt.threshold(c, thr, mode="soft") for c in (cH, cV, cD)))
    rec = pywt.waverec2(out, wavelet)
    return np.clip(rec[: gray.shape[0], : gray.shape[1]], 0, 255)


def extract_residual(img_rgb: np.ndarray) -> dict:
    """Returns denoised image + residual + stats."""
    gray = to_gray(img_rgb)
    denoised = wavelet_denoise(gray)
    residual = gray.astype(np.float32) - denoised
    # zero-mean
    residual = residual - residual.mean()
    var = float(residual.var())
    mad = float(np.median(np.abs(residual)) / 0.6745)
    # camera-like residuals have moderate variance; flat/AI-smooth images have tiny variance
    # map variance -> score via log scale
    score = float(np.clip((np.log10(var + 1.0)) / np.log10(400.0), 0, 1)) if var > 0 else 0.0
    return {
        "gray": gray, "denoised": denoised, "residual": residual,
        "variance": var, "mad": mad, "score": score,
    }


def analyze_noise_residual(img_rgb: np.ndarray) -> dict:
    r = extract_residual(img_rgb)
    interp = (
        "Residual energy consistent with camera sensor noise."
        if r["score"] > 0.55 else
        "Residual energy is low/smooth — more consistent with synthetic or heavily denoised content."
        if r["score"] < 0.35 else
        "Residual energy is borderline; evidence is mixed."
    )
    return detector_result("NOISE_RESIDUAL", r["score"], 0.72, interp,
                           {"variance": r["variance"], "mad": r["mad"]})
