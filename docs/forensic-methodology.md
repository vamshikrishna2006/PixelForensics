# Forensic Methodology

## Detectors

1. **AI-content cues** (`app/forensic/generative.py`) — the primary signal. Six
   sub-scores that survive re-encoding:
   - noise-residual kurtosis (ringing / over-sharp upsampling vs. Gaussian sensor noise)
   - noise floor in the flattest 40% of pixels (denoisers flatten it, cameras keep grain)
   - detail floor (10th-percentile 16×16 block std — how smooth the quiet blocks are)
   - saturation (generators oversaturate more often)
   - residual autocorrelation (compression/upsampling structure)
   - encoder prior (EXIF `Make`/`Model`/`Software`, embedded prompt JSON,
     camera-vs-generator vendor names, canonical diffusion sizes, PNG-with-no-EXIF)
2. **Wavelet** denoise (db8, BayesShrink-ish) → noise residual.
3. **PRNU**: residual whiteness (lag-1 autocorr) + 8×8 block-variance CV + residual energy.
4. **FFT**: HF-band ratio + radial peakiness; 64×64 log-spectrum for the UI.
5. **Wavelet bands**: LL/LH/HL/HH energies (db4), HF-share vs natural ~0.08.
6. **ELA**: JPEG re-save at q90, mean/std error. Only applied to JPEG inputs.
7. **JPEG**: 8×8 blockiness, recompress-size monotonicity, q70 ghost correlation.
   Only applied to JPEG inputs.
8. **GLCM**: contrast/homogeneity/energy/correlation on 8-level 256px gray.
9. **Metadata**: EXIF make/model/software/GPS (supporting evidence only).
10. **Local**: 12×12 noise-variance anomaly map + JET heatmap + connected-component regions.

## Aggregation

Raw scores are **not** averaged — they live on different scales, and a detector
that is neutral on a given image (or not applicable, e.g. JPEG analysis on a PNG)
must not vote.

```
e_i       = clip((score_i - center_i) * gain_i, -1, +1)     # calibrated evidence
evidence  = Σ w_i · e_i / Σ w_i                             # -1 .. +1
final     = sigmoid(3 · evidence)                           # 0 .. 1
```

- `center`/`gain` come from the measured per-detector distributions; a
  chance-level detector gets a low gain so it can only nudge a borderline case.
- Weights reflect measured AUC: GENERATIVE 0.66, NOISE_RESIDUAL 0.12, PRNU 0.05,
  LOCAL 0.05, TEXTURE 0.04, FREQUENCY 0.03, WAVELET 0.02, ELA 0.01, JPEG 0.01,
  METADATA 0.01.
- Verdict: real if `final ≥ 0.60`, AI/manipulated if `final < 0.45`, otherwise
  inconclusive. Confidence = distance from the 0.5 centre.

The boundaries and centres are **calibrated on a small labelled set** and are
indicative, not universal. Re-run `backend/tools/calibrate.py` with your own
samples (see `backend/dataset/{real,ai}/README.md`) whenever you add images or
change a detector.

## Measured behaviour (19-image local benchmark)

10 Picsum photos + 2 Wikimedia camera originals vs 6 Pollinations images + 1
AI PNG. Before the rebuild: AUC 0.657, 0 real verdicts, 3 false "AI" calls.
After: AUC 1.000 in-sample, 8/8 decisive camera photos correct, 7/7 AI correct,
2 heavily re-compressed real photos left inconclusive, 0 wrong verdicts.

Treat that as a smoke test, not a validated accuracy figure: 19 images cannot
cover the space of cameras, editors and generators, and the calibration used the
same images.

## Known limits

- Heavy re-compression (WhatsApp, Instagram, screenshots) removes the sensor
  noise the physics-based detectors rely on. Expect INCONCLUSIVE, not a guess.
- Metadata is forgeable and is usually stripped; it is weighted accordingly.
- Screenshots and graphics are not camera photos, but the pipeline has no
  dedicated "not a photograph" category yet, so their verdicts are weak.
