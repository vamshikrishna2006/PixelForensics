"""Local noise-consistency + heatmap + suspicious regions + splicing hints."""
import cv2
import numpy as np
from .common import detector_result, encode_png_b64
from .noise_residual import extract_residual


def local_consistency(img_rgb: np.ndarray, grid: int = 12):
    gray_small = cv2.resize(cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY), (grid * 32, grid * 32))
    r = extract_residual(cv2.cvtColor(gray_small, cv2.COLOR_GRAY2RGB))["residual"]
    bh, bw = r.shape[0] // grid, r.shape[1] // grid
    varmap = np.zeros((grid, grid))
    for i in range(grid):
        for j in range(grid):
            varmap[i, j] = r[i*bh:(i+1)*bh, j*bw:(j+1)*bw].var()
    med = np.median(varmap) + 1e-8
    ratio = varmap / med  # ~1.0 = consistent
    anomaly = np.abs(np.log10(ratio + 1e-8))  # symmetric anomaly strength
    heat = cv2.resize((anomaly / (anomaly.max() + 1e-8) * 255).astype(np.uint8),
                      (img_rgb.shape[1], img_rgb.shape[0]), interpolation=cv2.INTER_CUBIC)
    heat_color = cv2.applyColorMap(heat, cv2.COLORMAP_JET)
    heat_color = cv2.cvtColor(heat_color, cv2.COLOR_BGR2RGB)
    return varmap, ratio, anomaly, heat, heat_color


def analyze_local(img_rgb: np.ndarray) -> tuple[dict, list[dict], str, str]:
    varmap, ratio, anomaly, heat, heat_color = local_consistency(img_rgb)
    flat = anomaly.ravel()
    frac_high = float((flat > 0.35).mean())
    score = float(np.clip(1.0 - frac_high * 2.2, 0, 1))
    interp = ("Noise is spatially consistent — no strong local-tamper signal."
              if score > 0.6 else
              "Some regions differ strongly from global noise — potential localized manipulation."
              if score < 0.4 else "Local consistency is borderline.")
    # suspicious regions: connected components of high-anomaly mask
    mask = (cv2.resize(anomaly.astype(np.float32), (img_rgb.shape[1], img_rgb.shape[0])) > 0.35).astype(np.uint8) * 255
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    H, W = img_rgb.shape[:2]
    regions = []
    for k in range(1, n):
        x, y, w, h, area = stats[k]
        if area < (H * W) * 0.002 or area > (H * W) * 0.5:
            continue
        regions.append({"id": len(regions) + 1, "x": int(x), "y": int(y),
                        "width": int(w), "height": int(h),
                        "reason": "Local noise statistics differ from surrounding regions."})
        if len(regions) >= 5:
            break
    det = detector_result("LOCAL", score, 0.64, interp,
                          {"frac_high_anomaly": round(frac_high, 4),
                           "n_regions": len(regions)})
    return det, regions, encode_png_b64(heat_color, normalize=False), encode_png_b64(heat, normalize=False)
