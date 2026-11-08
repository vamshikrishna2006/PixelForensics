"""Re-calibrate detector weights and centres from your own labelled samples.

Usage (from the backend/ directory, with the project venv):

    python tools/calibrate.py
    python tools/calibrate.py --real dataset/real --ai dataset/ai --min 4

Put camera photos in backend/dataset/real/ and generated images in
backend/dataset/ai/. Any mix of JPEG/PNG/WEBP works. More samples = better
calibration; 20+ per class is a reasonable start.

The script runs the real pipeline on every file, measures each detector's
AUC (how well it ranks real above AI), and prints:

  * per-detector AUC / means
  * a WEIGHTS dict (how much each detector should vote)
  * a CALIBRATION dict (centre + gain per detector)
  * achieved balanced accuracy at the current thresholds

Paste the printed blocks into app/forensic/scoring.py. Nothing is written
automatically, so you can inspect the numbers first.

Caveat: with a small sample set the numbers are indicative. AUC is a ranking
measure, so it is more stable than accuracy, but 5-10 images per class still
cannot characterise every camera, editor and generator.
"""
import argparse
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.forensic.pipeline import run_full_analysis  # noqa: E402
from app.forensic.scoring import THRESHOLD_FAKE, THRESHOLD_REAL, WEIGHTS  # noqa: E402


def auc(pos, neg) -> float:
    """P(score(real) > score(ai)), ties counted as half."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return float("nan")
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())


def load(path: str) -> list[str]:
    if os.path.isdir(path):
        files = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.JPG", "*.JPEG", "*.PNG"):
            files.extend(glob.glob(os.path.join(path, ext)))
        return sorted(set(files))
    return sorted(glob.glob(path))


def mime_of(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", default=os.path.join("dataset", "real"), help="real/camera sample dir")
    ap.add_argument("--ai", default=os.path.join("dataset", "ai"), help="AI/generated sample dir")
    ap.add_argument("--min", type=float, default=4.0, help="minimum samples per class")
    args = ap.parse_args()

    real_files, ai_files = load(args.real), load(args.ai)
    if len(real_files) < args.min or len(ai_files) < args.min:
        print(f"Need at least {args.min:.0f} images in each folder.")
        print(f"  {args.real}: {len(real_files)} file(s)")
        print(f"  {args.ai}:   {len(ai_files)} file(s)")
        return 1

    per = {}
    finals = {"real": [], "ai": []}
    for label, files in (("real", real_files), ("ai", ai_files)):
        for path in files:
            with open(path, "rb") as fh:
                raw = fh.read()
            try:
                out = run_full_analysis(raw, os.path.basename(path), mime_of(path))
            except Exception as exc:  # unreadable file should not abort calibration
                print(f"  skip {os.path.basename(path)}: {exc}")
                continue
            finals[label].append(out["final_score"])
            for d in out["detectors"]:
                per.setdefault(d["method"], {"real": [], "ai": []})[label].append(d["score"])
            print(f"  {label:4s} {os.path.basename(path):28s} final={out['final_score']:.3f} {out['verdict']}")

    print(f"\nn = {len(finals['real'])} real / {len(finals['ai'])} ai\n")
    print(f"{'detector':18s}{'mean real':>10s}{'mean ai':>9s}{'AUC':>7s}{'suggested w':>13s}")
    aucs = {}
    for method in WEIGHTS:
        d = per.get(method)
        if not d or not d["real"] or not d["ai"]:
            print(f"{method:18s}{'—':>10s}{'—':>9s}{'—':>7s}{0.0:13.3f}")
            aucs[method] = 0.5
            continue
        a = auc(d["real"], d["ai"])
        aucs[method] = a
        # Chance-level detectors get no vote. Strength grows quadratically above chance.
        strength = max(0.0, 2.0 * a - 1.0) ** 2
        print(f"{method:18s}{np.mean(d['real']):10.3f}{np.mean(d['ai']):9.3f}{a:7.3f}{strength:13.3f}")

    strengths = {m: max(0.0, 2.0 * a - 1.0) ** 2 for m, a in aucs.items()}
    if sum(strengths.values()) <= 0:
        print("\nEvery detector is at chance on this sample set — keeping the current weights.")
        return 1
    # Keep every detector visible in the report, but give noise-level ones a 0.01 floor.
    raw = {m: max(s, 0.01) for m, s in strengths.items()}
    total = sum(raw.values())
    weights = {m: round(s / total, 4) for m, s in raw.items()}

    calibration = {}
    for method, d in per.items():
        if not d["real"] or not d["ai"]:
            continue
        center = (np.mean(d["real"]) + np.mean(d["ai"])) / 2.0
        a = aucs.get(method, 0.5)
        # Amplify only the detectors that actually separate the classes. A
        # chance-level detector gets the minimum gain, otherwise its noise is
        # blown up into a strong (and meaningless) vote.
        gain = min(6.0, max(0.5, 6.0 * (2.0 * a - 1.0)))
        calibration[method] = {"center": round(float(center), 3), "gain": round(float(gain), 2)}

    print("\nPaste into app/forensic/scoring.py:\n")
    print("WEIGHTS = {")
    for m, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        print(f'    "{m}": {w:.2f},')
    print("}\n")
    print("CALIBRATION = {")
    for m, c in sorted(calibration.items()):
        print(f'    "{m}": {{"center": {c["center"]}, "gain": {c["gain"]}}},')
    print("}")

    # What would the *current* thresholds achieve on this set?
    rs, as_ = finals["real"], finals["ai"]
    if rs and as_:
        real_ok = np.mean([f >= THRESHOLD_REAL for f in rs])
        ai_ok = np.mean([f < THRESHOLD_FAKE for f in as_])
        print(f"\nWith current thresholds ({THRESHOLD_REAL:.2f} / {THRESHOLD_FAKE:.2f}): "
              f"real correct {real_ok:.0%}, ai correct {ai_ok:.0%}, "
              f"balanced accuracy {(real_ok + ai_ok) / 2:.0%}")
        print("(Images inside the band count as neither; that is intentional.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
