"""Isolated scoring logic check — no imports, mirrors scoring.py constants."""
WEIGHTS = {"PRNU": 0.22, "NOISE_RESIDUAL": 0.14, "FREQUENCY": 0.14, "WAVELET": 0.10,
           "ELA": 0.12, "JPEG": 0.08, "TEXTURE": 0.10, "METADATA": 0.04, "LOCAL": 0.06}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "weights must sum to 1"

def aggregate(scores):
    total = sum(scores[m] * w for m, w in WEIGHTS.items())
    if total >= 0.62: return "LIKELY_REAL"
    if total < 0.42: return "LIKELY_AI_MANIPULATED"
    return "INCONCLUSIVE"

assert aggregate({m: 0.95 for m in WEIGHTS}) == "LIKELY_REAL"
assert aggregate({m: 0.05 for m in WEIGHTS}) == "LIKELY_AI_MANIPULATED"
assert aggregate({m: 0.5 for m in WEIGHTS}) == "INCONCLUSIVE"
print("scoring logic OK; thresholds 0.62/0.42; weights sum to 1.0")
