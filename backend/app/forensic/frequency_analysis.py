"""Frequency-domain (FFT) residual analysis."""
import numpy as np
from .common import detector_result
from .noise_residual import extract_residual


def analyze_frequency(img_rgb: np.ndarray) -> dict:
    res = extract_residual(img_rgb)["residual"]
    F = np.fft.fftshift(np.fft.fft2(res))
    mag = np.abs(F)
    h, w = mag.shape
    cy, cx = h // 2, w // 2
    yy, xx = np.ogrid[:h, :w]
    rad = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    rmax = rad.max()
    low = mag[rad < 0.15 * rmax].mean()
    mid = mag[(rad >= 0.15 * rmax) & (rad < 0.5 * rmax)].mean()
    high = mag[rad >= 0.5 * rmax].mean()
    tot = low + mid + high + 1e-8
    hf_ratio = float(high / tot)
    # natural residuals spread energy; GAN fingerprints often spike in mid/high bands
    # radial smoothness: std of angular-averaged spectrum
    nbins = 24
    bins = np.clip((rad / rmax * nbins).astype(int), 0, nbins - 1)
    radial = np.array([mag[bins == b].mean() for b in range(nbins)])
    radial = radial / (radial.mean() + 1e-8)
    peakiness = float(radial.std())
    hf_score = float(np.clip(1.0 - abs(hf_ratio - 0.30) * 3.0, 0, 1))
    peak_score = float(np.clip(1.0 - max(0.0, peakiness - 0.35) * 2.0, 0, 1))
    score = 0.5 * hf_score + 0.5 * peak_score
    interp = (
        "Residual spectrum is broadband and smooth, consistent with camera noise."
        if score > 0.6 else
        "Residual spectrum shows unusual peaks/imbalance, more consistent with generated or processed content."
        if score < 0.4 else
        "Frequency evidence is mixed."
    )
    # downsampled spectrum for frontend viz (64x64 log magnitude)
    import cv2
    logmag = np.log1p(mag)
    logmag = cv2.resize(logmag, (64, 64), interpolation=cv2.INTER_AREA)
    return detector_result("FREQUENCY", score, 0.70, interp, {
        "hf_ratio": round(hf_ratio, 4), "peakiness": round(peakiness, 4),
        "spectrum64": logmag.tolist()})
