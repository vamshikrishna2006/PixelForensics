"""Transparent weighted scoring engine.

Scores are combined as calibrated *evidence* rather than as a plain average:

    e_i       = clip((score_i - center_i) * gain_i, -1, +1)
    evidence  = SUM w_i * e_i / SUM w_i                  range -1..+1
    final     = sigmoid(SHARPNESS * evidence)            range 0..1

Why not average the raw scores? The old engine did that and it pulled every
result toward 0.5: detectors that are neutral on a given image (or simply not
applicable, e.g. JPEG analysis on a PNG) still voted, and each detector has its
own idea of "0.5". Averaging scores is only valid if they are all calibrated to
the same scale. They are not — measured on a labelled set, several detectors sit
near 0.1-0.25 even for camera photos.

`center` is the score that detector normally produces for a *typical* image, and
`gain` converts its spread into evidence strength. Both come from the measured
per-detector distributions (backend/tools/calibrate.py) and should be recomputed
whenever the detectors or the sample set change.

Weights reflect measured discriminative power (AUC on the labelled set). The
generative-content detector carries the decision; sensor-noise analysis
supports it; the remaining detectors are reported for completeness with small
weights so they can only nudge a borderline case, never overturn clear evidence.
"""

WEIGHTS = {  # must sum to 1.0
    "GENERATIVE": 0.66,
    "NOISE_RESIDUAL": 0.12,
    "PRNU": 0.05,
    "LOCAL": 0.05,
    "TEXTURE": 0.04,
    "FREQUENCY": 0.03,
    "WAVELET": 0.02,
    "ELA": 0.01,
    "JPEG": 0.01,
    "METADATA": 0.01,
}

# center = typical score for a mixed real/AI image, gain = evidence per score unit.
# A gain of ~0 means "measured at chance level, do not let it vote".
CALIBRATION = {
    "GENERATIVE":       {"center": 0.49, "gain": 6.0},
    "NOISE_RESIDUAL":   {"center": 0.29, "gain": 3.0},
    "PRNU":             {"center": 0.24, "gain": 1.0},
    "LOCAL":            {"center": 0.21, "gain": 1.5},
    "TEXTURE":          {"center": 0.05, "gain": 1.0},
    "FREQUENCY":        {"center": 0.69, "gain": 1.0},
    "WAVELET":          {"center": 0.39, "gain": 1.0},
    "ELA":              {"center": 0.70, "gain": 1.0},
    "JPEG":             {"center": 0.96, "gain": 1.0},
    "METADATA":         {"center": 0.69, "gain": 1.0},
}

# Detectors that only mean something for one source format.
FORMAT_GATED = {
    "ELA": ("JPEG", "JPG"),
    "JPEG": ("JPEG", "JPG"),
}

# Verdict boundaries. Set from the measured final-score distributions: the
# highest-scoring generated sample and the lowest-scoring re-encoded camera
# photo sit ~0.03 apart, so the boundary goes between them. Real captures with
# heavy recompression are deliberately left INCONCLUSIVE rather than guessed.
THRESHOLD_REAL = 0.60      # final >= this        => LIKELY REAL
THRESHOLD_FAKE = 0.45      # final <  this        => LIKELY AI/MANIPULATED
SHARPNESS = 3.0            # slope of the evidence -> probability mapping

VERDICTS = ("LIKELY_REAL", "LIKELY_AI_MANIPULATED", "INCONCLUSIVE")

_LABELS = {
    "GENERATIVE": "AI-content cues",
    "NOISE_RESIDUAL": "Sensor-noise floor",
    "PRNU": "PRNU consistency",
    "LOCAL": "Local noise consistency",
    "TEXTURE": "GLCM texture",
    "FREQUENCY": "Frequency domain",
    "WAVELET": "Wavelet bands",
    "ELA": "Error level analysis",
    "JPEG": "JPEG compression",
    "METADATA": "Metadata",
}


def _sigmoid(x: float) -> float:
    import math
    return 1.0 / (1.0 + math.exp(-x))


def _evidence(method: str, score: float) -> float:
    cal = CALIBRATION.get(method, {"center": 0.5, "gain": 1.0})
    return max(-1.0, min(1.0, (float(score) - cal["center"]) * cal["gain"]))


def aggregate(detectors: list[dict], fmt: str = "JPEG") -> dict:
    by = {d["method"]: d for d in detectors}
    fmt_u = (fmt or "").upper()

    num, den = 0.0, 0.0
    parts = []
    for m, w in WEIGHTS.items():
        d = by.get(m)
        if not d:
            continue
        allowed = FORMAT_GATED.get(m)
        applicable = True if allowed is None else fmt_u in allowed

        e = _evidence(m, d["score"]) if applicable else 0.0
        if applicable:
            num += w * e
            den += w

        parts.append({
            "method": m,
            "label": _LABELS.get(m, m),
            "score": d["score"],
            "confidence": d["confidence"],
            "weight": w,
            "calibrated": round(e, 3),
            "contribution": round(w * e, 4),
            "applied": applicable,
            "interpretation": d["interpretation"] + ("" if applicable else
                                                      " (not applicable to this file format)"),
        })

    evidence = (num / den) if den else 0.0
    final = _sigmoid(SHARPNESS * evidence)

    if final >= THRESHOLD_REAL:
        verdict = "LIKELY_REAL"
    elif final < THRESHOLD_FAKE:
        verdict = "LIKELY_AI_MANIPULATED"
    else:
        verdict = "INCONCLUSIVE"

    conf = min(0.97, 0.50 + 1.5 * abs(final - 0.5))

    # Plain-English explanation from the strongest evidence for and against.
    applied = [p for p in parts if p["applied"] and p["weight"] > 0]
    so = sorted(applied, key=lambda p: p["contribution"], reverse=True)
    support, oppose = (so[0], so[-1]) if so else (None, None)
    if support is None:
        why = "Not enough applicable evidence to form a verdict."
    elif verdict == "LIKELY_REAL":
        why = (f"Signal points to a camera capture. Strongest evidence: "
               f"{support['label']} ({support['score']:.0%}). Weakest: "
               f"{oppose['label']} ({oppose['score']:.0%}).")
    elif verdict == "LIKELY_AI_MANIPULATED":
        why = (f"Signal points to synthetic or manipulated content. Strongest evidence "
               f"against a camera: {oppose['label']} ({oppose['score']:.0%}). "
               f"Best counter-evidence: {support['label']} ({support['score']:.0%}).")
    else:
        why = (f"Evidence is genuinely mixed: {support['label']} looks camera-like "
               f"({support['score']:.0%}) while {oppose['label']} does not "
               f"({oppose['score']:.0%}). Treat as inconclusive, not proof either way.")

    return {
        "final_score": round(float(final), 4),
        "confidence": round(float(conf), 4),
        "verdict": verdict,
        "breakdown": parts,
        "explanation": why,
        "weights": WEIGHTS,
        "thresholds": {"real": THRESHOLD_REAL, "fake": THRESHOLD_FAKE, "sharpness": SHARPNESS},
        "evidence": round(float(evidence), 4),
    }
