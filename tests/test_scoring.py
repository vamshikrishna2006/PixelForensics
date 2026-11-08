"""Scoring engine tests — pure python, no heavy deps."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.forensic.scoring import aggregate, WEIGHTS, THRESHOLD_REAL, THRESHOLD_FAKE, CALIBRATION


def _det(method, score, conf=0.7):
    return {"method": method, "score": score, "confidence": conf,
            "interpretation": "t", "details": {}}


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_all_real_scores_gives_likely_real():
    dets = [_det(m, 0.95) for m in WEIGHTS]
    out = aggregate(dets)
    assert out["verdict"] == "LIKELY_REAL"
    assert out["confidence"] > 0.5


def test_all_fake_scores_gives_manipulated():
    dets = [_det(m, 0.05) for m in WEIGHTS]
    out = aggregate(dets)
    assert out["verdict"] == "LIKELY_AI_MANIPULATED"


def test_mixed_scores_gives_inconclusive():
    # Scores at each detector's calibrated centre produce zero evidence.
    dets = [_det(m, CALIBRATION[m]["center"]) for m in WEIGHTS]
    out = aggregate(dets)
    assert out["verdict"] == "INCONCLUSIVE"
    assert THRESHOLD_FAKE <= out["final_score"] < THRESHOLD_REAL


def test_breakdown_covers_all_methods():
    dets = [_det(m, 0.6) for m in WEIGHTS]
    out = aggregate(dets)
    assert {b["method"] for b in out["breakdown"]} == set(WEIGHTS)
    assert out["explanation"]
