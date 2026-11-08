"""Full forensic pipeline — orchestrates every detector + comparison."""
import time
import numpy as np
from .common import decode_image_bytes, resize_max, encode_png_b64
from .noise_residual import extract_residual, analyze_noise_residual
from .prnu import analyze_prnu
from .frequency_analysis import analyze_frequency
from .wavelet_analysis import analyze_wavelet
from .ela import analyze_ela
from .jpeg_analysis import analyze_jpeg
from .cooccurrence import analyze_cooccurrence
from .metadata import analyze_metadata
from .suspicious_regions import analyze_local
from .generative import analyze_generative
from .image_profile import profile_image
from .narrative import build_narrative
from .scoring import aggregate


def guess_format(raw: bytes, filename: str) -> str:
    fn = filename.lower()
    if fn.endswith(".png"): return "PNG"
    if fn.endswith(".webp"): return "WEBP"
    return "JPEG"


def run_full_analysis(raw: bytes, filename: str, mime: str) -> dict:
    t0 = time.time()
    img = resize_max(decode_image_bytes(raw))
    fmt = guess_format(raw, filename)
    detectors = [
        analyze_generative(img, raw, fmt),
        analyze_prnu(img),
        analyze_noise_residual(img),
        analyze_frequency(img),
        analyze_wavelet(img),
        analyze_ela(img, fmt),
        analyze_jpeg(img, raw, fmt),
        analyze_cooccurrence(img),
        analyze_metadata(raw, filename, mime),
    ]
    local_det, regions, heat_b64, heat_gray_b64 = analyze_local(img)
    detectors.append(local_det)
    scoring = aggregate(detectors, fmt)
    residual = extract_residual(img)["residual"]
    result = {
        "verdict": scoring["verdict"],
        "confidence": scoring["confidence"],
        "final_score": scoring["final_score"],
        "detectors": detectors,
        "breakdown": scoring["breakdown"],
        "explanation": scoring["explanation"],
        "weights": scoring["weights"],
        "thresholds": scoring["thresholds"],
        "regions": regions,
        "artifacts": {
            "residual_b64": encode_png_b64(residual),
            "heatmap_b64": heat_b64,
        },
        "image_info": {"width": int(img.shape[1]), "height": int(img.shape[0]),
                       "format": fmt, "size_bytes": len(raw)},
        "image_profile": profile_image(img),
        "processing_time_s": round(time.time() - t0, 2),
    }
    # attach per-detector artifacts needed by frontend (spectrum, wavelet thumbs, ela)
    for d in detectors:
        if d["method"] == "FREQUENCY":
            result["artifacts"]["spectrum"] = d["details"].pop("spectrum64")
        elif d["method"] == "WAVELET":
            result["artifacts"]["wavelet"] = d["details"].pop("thumbs")
        elif d["method"] == "ELA":
            result["artifacts"]["ela_b64"] = d["details"].pop("ela_b64")
    # long-form plain-English narration of the result (never blocks an analysis)
    try:
        result["narrative"] = build_narrative(result)
    except Exception as e:  # pragma: no cover - defensive
        print(f"[narrative] skipped: {type(e).__name__}: {e}")
        result["narrative"] = {}
    return result


def residual_fingerprint(raw: bytes) -> np.ndarray:
    img = resize_max(decode_image_bytes(raw), 512)
    r = extract_residual(img)["residual"]
    r = r - r.mean()
    n = float((r ** 2).sum()) ** 0.5 + 1e-8
    return (r / n).astype(np.float32)


def run_comparison(images: list[tuple[str, bytes]]) -> dict:
    """Compare 2+ images via normalized residual cross-correlation."""
    fps = [residual_fingerprint(b) for _, b in images]
    n = len(fps)
    # resize all to smallest shape
    h = min(f.shape[0] for f in fps); w = min(f.shape[1] for f in fps)
    fps = [f[:h, :w] for f in fps]
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            corr = float((fps[i] * fps[j]).sum() / (fps[i].size))
            pairs.append({"a": images[i][0], "b": images[j][0],
                          "correlation": round(corr, 4),
                          "interpretation": "High residual similarity — may share a source/processing pipeline."
                          if corr > 0.15 else "Low residual similarity — likely different sources."
                          if corr < 0.03 else "Moderate similarity — inconclusive."})
    avg = float(np.mean([p["correlation"] for p in pairs])) if pairs else 0.0
    verdict = ("SIMILAR_SOURCE" if avg > 0.15 else "DIFFERENT_SOURCE" if avg < 0.03 else "INCONCLUSIVE")
    return {"pairs": pairs, "mean_correlation": round(avg, 4), "verdict": verdict,
            "note": "Single-image PRNU correlation is indicative only; same-camera proof needs reference frames."}
