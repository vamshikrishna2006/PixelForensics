"""PRNU-inspired sensor-noise consistency analysis (single-image, no reference camera)."""
import cv2
import numpy as np
from .common import to_gray, detector_result
from .noise_residual import extract_residual


def _block_stats(residual: np.ndarray, grid: int = 8) -> np.ndarray:
    h, w = residual.shape
    bh, bw = h // grid, w // grid
    vars_ = []
    for i in range(grid):
        for j in range(grid):
            b = residual[i*bh:(i+1)*bh, j*bw:(j+1)*bw]
            vars_.append(b.var())
    return np.array(vars_, dtype=np.float64)


def analyze_prnu(img_rgb: np.ndarray) -> dict:
    r = extract_residual(img_rgb)
    res = r["residual"]
    # 1) spatial autocorrelation of residual at lag-1 (sensor noise ~ white => low autocorr)
    a = res - res.mean()
    denom = float((a ** 2).sum()) + 1e-8
    ac_h = float((a[:, :-1] * a[:, 1:]).sum() / denom)
    ac_v = float((a[:-1, :] * a[1:, :]).sum() / denom)
    ac = abs(ac_h) + abs(ac_v)  # white noise => ~0
    white_score = float(np.clip(1.0 - ac * 4.0, 0, 1))
    # 2) block variance uniformity — natural photos vary smoothly; splices create outliers
    bv = _block_stats(res)
    cv = float(bv.std() / (bv.mean() + 1e-8))  # coefficient of variation
    uniformity = float(np.clip(1.0 - max(0.0, cv - 0.35) * 1.2, 0, 1))
    # 3) residual energy term from noise module
    energy = r["score"]
    score = 0.45 * white_score + 0.30 * uniformity + 0.25 * energy
    interp = (
        "Residual behaves like white camera sensor noise with consistent spatial statistics."
        if score > 0.6 else
        "Residual shows correlated/smooth structure atypical of raw camera sensor noise."
        if score < 0.4 else
        "PRNU evidence is mixed; residual is only partly camera-like."
    )
    return detector_result("PRNU", score, 0.78, interp, {
        "autocorr_h": round(ac_h, 4), "autocorr_v": round(ac_v, 4),
        "block_cv": round(cv, 4), "residual_variance": r["variance"]})
