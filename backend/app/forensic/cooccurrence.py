"""GLCM texture / co-occurrence analysis."""
import numpy as np
import cv2
from skimage.feature import graycomatrix, graycoprops
from .common import to_gray, detector_result


def analyze_cooccurrence(img_rgb: np.ndarray) -> dict:
    gray = to_gray(img_rgb)
    small = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_AREA)
    q = (small // 32).astype(np.uint8)  # 8 levels
    glcm = graycomatrix(q, distances=[1, 2], angles=[0, np.pi/4, np.pi/2, 3*np.pi/4],
                        levels=8, symmetric=True, normed=True)
    contrast = float(graycoprops(glcm, "contrast").mean())
    homogeneity = float(graycoprops(glcm, "homogeneity").mean())
    energy = float(graycoprops(glcm, "energy").mean())
    correlation = float(graycoprops(glcm, "correlation").mean())
    # natural photos: moderate contrast+energy; synthetic smooth: very high homogeneity + low contrast
    score = float(np.clip(0.5 + (0.5 - homogeneity) * 1.4 + (contrast - 0.35) * 0.5, 0, 1))
    interp = ("Texture statistics look natural." if score > 0.6 else
              "Texture is unusually smooth/uniform — consistent with synthetic generation."
              if score < 0.4 else "Texture evidence is mixed.")
    return detector_result("TEXTURE", score, 0.60, interp, {
        "contrast": round(contrast, 4), "homogeneity": round(homogeneity, 4),
        "energy": round(energy, 4), "correlation": round(correlation, 4)})
