"""Plain-English narrative of a completed analysis.

``build_narrative`` turns the numeric report into a readable account: what the
image looks like, how the verdict was reached, which detectors pushed the score
and which pulled against it, where local anomalies sit, and what a reader should
(and should not) conclude from the numbers.

It derives everything from the stored report JSON, so it can be regenerated for
analyses created before this module existed.
"""
from __future__ import annotations

from .scoring import CALIBRATION, SHARPNESS, THRESHOLD_FAKE, THRESHOLD_REAL, WEIGHTS

# What each detector actually looks at, in language a non-specialist can follow.
# "low"/"high" describe what a low or high score means for that detector.
DETECTOR_GUIDE: dict[str, dict] = {
    "GENERATIVE": {
        "title": "AI-content cues",
        "measures": ("statistical fingerprints of generative models: missing sensor grain in "
                     "flat areas, over-clean colour gradients and residual energy that does "
                     "not behave like a physical sensor"),
        "low": "the texture and noise statistics look synthesised",
        "high": "the texture and noise statistics look photographic",
    },
    "NOISE_RESIDUAL": {
        "title": "Sensor-noise floor",
        "measures": ("the strength and character of the high-frequency noise every real sensor "
                     "leaves behind; cameras add grain, renderers and denoisers remove it"),
        "low": "the frame is unusually clean or denoised, as generators and filters tend to be",
        "high": "the frame carries a healthy, camera-like noise floor",
    },
    "PRNU": {
        "title": "PRNU consistency",
        "measures": ("photo-response non-uniformity, the fixed pixel-level fingerprint of a "
                     "sensor; without reference frames it can only be checked for internal "
                     "consistency across the frame"),
        "low": "the residual is smoother or more correlated than raw sensor noise",
        "high": "the residual behaves like raw sensor noise",
    },
    "LOCAL": {
        "title": "Local noise consistency",
        "measures": ("whether every region of the frame shares the same noise statistics; "
                     "pasted, cloned or repainted areas usually stand out from their neighbours"),
        "low": "some regions differ strongly from the rest of the frame",
        "high": "noise is spread evenly across the frame",
    },
    "TEXTURE": {
        "title": "GLCM texture",
        "measures": ("grey-level co-occurrence statistics, i.e. how neighbouring pixels vary; "
                     "real photographs have busy, irregular micro-texture"),
        "low": "micro-texture is unusually smooth or uniform",
        "high": "micro-texture is naturally irregular",
    },
    "FREQUENCY": {
        "title": "Frequency domain",
        "measures": ("the energy distribution of the noise residual across spatial frequencies; "
                     "generated content often leaves periodic peaks or banding"),
        "low": "the spectrum shows peaks or an energy imbalance typical of processing or synthesis",
        "high": "the spectrum is broadband and smooth, as camera noise usually is",
    },
    "WAVELET": {
        "title": "Wavelet bands",
        "measures": ("how detail energy splits across scales (LL/LH/HL/HH sub-bands); "
                     "synthesisers leave atypical high-frequency structure"),
        "low": "high-frequency detail distribution is atypical (over-smooth or spiky)",
        "high": "detail energy is distributed the way camera detail usually is",
    },
    "ELA": {
        "title": "Error-level analysis",
        "measures": ("re-saving at a known JPEG quality and measuring where compression error "
                     "differs; edited regions recompress differently from untouched areas"),
        "low": "regions respond unevenly to recompression, hinting at editing",
        "high": "compression error is uniform, as an untouched JPEG usually is",
    },
    "JPEG": {
        "title": "JPEG compression structure",
        "measures": ("quantisation tables and block statistics; a single-origin JPEG has one "
                     "consistent compression history"),
        "low": "the compression structure is unusual or inconsistent",
        "high": "the compression structure looks like a normal single-pass JPEG",
    },
    "METADATA": {
        "title": "EXIF metadata",
        "measures": ("camera make/model, capture timestamp, editing software and GPS tags "
                     "embedded in the file"),
        "low": "metadata is missing or names a generative tool",
        "high": "metadata names a camera body and looks consistent",
    },
}

_VERDICT_LABEL = {
    "LIKELY_REAL": "Likely real (camera capture)",
    "LIKELY_AI_MANIPULATED": "Likely AI-generated or manipulated",
    "INCONCLUSIVE": "Inconclusive",
}



def _pct(value, digits: int = 0) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "n/a"


def _detector_guide(method: str) -> dict:
    return DETECTOR_GUIDE.get(method, {
        "title": str(method).replace("_", " ").title(),
        "measures": "an independent statistical test of the image signal",
        "low": "the signal leans synthetic",
        "high": "the signal leans camera-like",
    })


def _label(entry: dict) -> str:
    return entry.get("label") or _detector_guide(entry.get("method", ""))["title"]


def _reading(entry: dict) -> str:
    """One short sentence describing what a detector's score means here."""
    score = float(entry.get("score") or 0.0)
    guide = _detector_guide(entry.get("method", ""))
    if score < 0.35:
        return f"read {_pct(score)} - {guide['low']}."
    if score > 0.65:
        return f"read {_pct(score)} - {guide['high']}."
    return f"read {_pct(score)} - neither strongly camera-like nor strongly synthetic."


def _strength_word(strength: float) -> str:
    if strength >= 0.6:
        return "strong"
    if strength >= 0.3:
        return "moderate"
    if strength >= 0.1:
        return "mild"
    return "marginal"


def _verdict_sentence(verdict: str, final: float, conf: float) -> str:
    if verdict == "LIKELY_REAL":
        return (f"The combined evidence favours a camera origin: the weighted score reached "
                f"{_pct(final)} camera-likeness, above the {_pct(THRESHOLD_REAL)} 'likely real' "
                f"boundary, at {_pct(conf)} confidence.")
    if verdict == "LIKELY_AI_MANIPULATED":
        return (f"The combined evidence favours a synthetic or manipulated origin: the weighted "
                f"score fell to {_pct(final)} camera-likeness, below the {_pct(THRESHOLD_FAKE)} "
                f"'likely AI/manipulated' boundary, at {_pct(conf)} confidence.")
    return (f"The evidence is genuinely mixed: the weighted score landed at {_pct(final)} "
            f"camera-likeness, inside the {_pct(THRESHOLD_FAKE)} to {_pct(THRESHOLD_REAL)} "
            f"indeterminate band, so no verdict is asserted. Confidence in that inconclusive "
            f"call is {_pct(conf)}.")


def _evidence_phrase(entry: dict) -> str:
    """Explain how much a detector moved the verdict, and in which direction."""
    cal = float(entry.get("calibrated") or 0.0)
    weight = float(entry.get("weight") or 0.0)
    center = float(CALIBRATION.get(entry.get("method", ""), {}).get("center", 0.5))
    push = "towards a camera origin" if cal > 0 else "towards a synthetic/manipulated origin"
    return (f"Its neutral point is {_pct(center)}; scoring {_pct(entry.get('score'))} converted "
            f"into {cal:+.2f} evidence, which with a {_pct(weight)} weight pulls the final "
            f"score {push} ({_strength_word(abs(cal) * weight)} influence).")


def _explain_entry(entry: dict) -> str:
    """Two-sentence deep explanation of one detector's contribution."""
    guide = _detector_guide(entry.get("method", ""))
    note = str(entry.get("interpretation") or "").strip().rstrip(".")
    body = (f"{_label(entry)} examines {guide['measures']}. "
            f"{_evidence_phrase(entry)}")
    if note:
        body += f" The detector reported: '{note}'."
    return body


def build_narrative(result: dict) -> dict:
    """Build the long-form narrative for a stored analysis result."""
    verdict = str(result.get("verdict") or "INCONCLUSIVE")
    final = float(result.get("final_score") or 0.5)
    conf = float(result.get("confidence") or 0.5)
    info = result.get("image_info") or {}
    profile = result.get("image_profile") or {}
    regions = result.get("regions") or []
    detectors = {d.get("method"): d for d in (result.get("detectors") or [])}

    breakdown = [b for b in (result.get("breakdown") or []) if b.get("applied", True)]
    ranked = sorted(breakdown, key=lambda b: abs(float(b.get("calibrated") or 0.0) *
                                                 float(b.get("weight") or 0.0)), reverse=True)
    for_real = [b for b in ranked if float(b.get("calibrated") or 0.0) > 0.02]
    against = [b for b in ranked if float(b.get("calibrated") or 0.0) < -0.02]
    neutral = [b for b in ranked if abs(float(b.get("calibrated") or 0.0)) <= 0.02]

    fmt = str(info.get("format") or "image").upper()
    width, height = int(info.get("width") or 0), int(info.get("height") or 0)
    size_kb = float(info.get("size_bytes") or 0) / 1024.0
    megapixels = profile.get("megapixels") or round((width * height) / 1_000_000, 2)

    sections: list[dict] = []

    # ---------------------------------------------------------------- 1. subject
    physical = (f"The submitted file is a {fmt} image of {width}x{height} pixels "
                f"({megapixels} MP) weighing {size_kb:.1f} KB on disk.")
    if profile.get("scene_description"):
        subject = (profile["scene_description"] + " " + physical +
                   " Those figures are measured directly from the pixel data - luminance, colour "
                   "clustering, edge density and micro-contrast - so they describe the visual "
                   "character of the frame rather than recognising objects in it.")
        if profile.get("dominant_colours"):
            names = ", ".join(f"{c['name']} ({c['hex']}, {c['share']:.0%})"
                              for c in profile["dominant_colours"][:3])
            subject += f" The three dominant colour clusters are {names}."
    else:
        subject = (physical + " No stored visual profile exists for this analysis, so the "
                   "description below rests on the detector evidence alone.")

    meta = (detectors.get("METADATA") or {}).get("details") or {}
    cam = " ".join(str(x) for x in (meta.get("make"), meta.get("model")) if x)
    if cam:
        subject += (f" EXIF metadata names a camera body ({cam})"
                    + (f", captured {meta['datetime']}" if meta.get("datetime") else "")
                    + " - supportive, but EXIF can be edited or stripped.")
    elif meta.get("software"):
        subject += (f" EXIF carries a software tag ('{meta['software']}') but no camera body, "
                    "which is more typical of an exported or processed file.")
    else:
        subject += (" No camera make or model appears in EXIF, which is normal for AI output, "
                    "screenshots and social-media re-uploads, and therefore neutral evidence "
                    "rather than proof of manipulation.")
    if meta.get("has_gps"):
        subject += " GPS coordinates were present and are withheld from this report for privacy."
    sections.append({"title": "1. The image under examination", "body": subject})


    # ---------------------------------------------------------------- 2. method
    top_weights = ", ".join(f"{_detector_guide(m)['title']} {_pct(w)}"
                            for m, w in sorted(WEIGHTS.items(), key=lambda kv: -kv[1])[:4])
    method = (f"Each detector returns a score from 0% to 100%, where higher means more "
              f"camera-like. PixelForensics deliberately does not average those raw scores: "
              f"detectors do not share a scale, and several sit near 10-25% even on genuine "
              f"photographs. Instead every score is compared with that detector's measured "
              f"neutral point, converted into evidence between -1 and +1, multiplied by a weight "
              f"({top_weights}, plus small weights for the remaining checks), averaged over the "
              f"detectors that apply to this {fmt} file, and passed through a sigmoid with slope "
              f"{SHARPNESS}. That produces the final camera-likeness score. A score of "
              f"{_pct(THRESHOLD_REAL)} or more is reported as likely real, below "
              f"{_pct(THRESHOLD_FAKE)} as likely AI-generated or manipulated, and anything "
              f"between the two is reported as inconclusive rather than guessed.")
    sections.append({"title": "2. How the verdict is computed", "body": method})

    # ---------------------------------------------------------------- 3. verdict
    supporting = for_real if verdict == "LIKELY_REAL" else against
    opposing = against if verdict == "LIKELY_REAL" else for_real
    side = "camera origin" if verdict == "LIKELY_REAL" else "synthetic/manipulated origin"
    verdict_body = _verdict_sentence(verdict, final, conf)
    verdict_body += (f" In total {len(for_real)} detector(s) leaned towards a camera and "
                     f"{len(against)} leaned away from one")
    verdict_body += (f"; the remaining {len(neutral)} sat within two points of their neutral "
                     f"point and contributed almost nothing." if neutral else ".")
    if supporting:
        verdict_body += f" The decisive evidence for a {side} is set out below."
        for entry in supporting[:3]:
            verdict_body += " " + _explain_entry(entry)
    else:
        verdict_body += (" No detector produced decisive evidence in either direction, which is "
                         "why the result is reported as inconclusive rather than forced into a "
                         "binary answer.")
    sections.append({"title": "3. What drove this result", "body": verdict_body})

    # ---------------------------------------------------------------- 4. counter
    if opposing:
        counter = (f"Fair reporting requires the other side of the argument. "
                   f"{len(opposing)} detector(s) pushed against the reported verdict, and they "
                   f"are recorded here rather than discarded - they are simply outvoted.")
        for entry in opposing[:3]:
            counter += " " + _explain_entry(entry)
        weakest = opposing[0]
        counter += (f" The strongest of them, {_label(weakest)}, carries a "
                     f"{_pct(float(weakest.get('weight') or 0.0))} weight, so even a complete "
                     f"reversal of that single check would not flip this verdict on its own. "
                     f"Counter-evidence matters most in borderline cases; here it is logged so a "
                     f"reviewer can see exactly what disagreed.")
    else:
        counter = ("No applicable detector produced meaningful evidence against the reported "
                   "verdict on this file - every applicable check agreed in direction. That "
                   "unanimity is worth noting, but it still reflects statistical tendencies "
                   "rather than certainty.")
    sections.append({"title": "4. Evidence that points the other way", "body": counter})



    # ---------------------------------------------------------------- 5. regions
    if regions:
        reg = (f"{len(regions)} localised region(s) carried noise statistics that differ from "
               f"the rest of the frame: ")
        reg += "; ".join(f"#{r.get('id')} at ({r.get('x')},{r.get('y')}) sized "
                         f"{r.get('width')}x{r.get('height')}px" for r in regions[:5])
        reg += (". Each is a candidate for closer inspection - cloning, patching, inpainting or "
                "selective denoising all leave this signature - but so does ordinary content, "
                "such as smooth sky beside foliage. Treat the boxes as pointers for a human "
                "reviewer, not as convictions.")
    else:
        reg = ("No region of this frame stood out from the global noise model, so there is no "
               "localised tamper signal to point at. That is equally expected for fully "
               "synthetic images (uniform everywhere) and for untouched camera files, so the "
               "absence of boxes is not evidence of authenticity.")
    sections.append({"title": "5. Localised anomalies", "body": reg})

    # ---------------------------------------------------------------- 6. noise / sensor
    noise_entries = [b for b in breakdown
                     if b.get("method") in ("NOISE_RESIDUAL", "PRNU", "LOCAL", "TEXTURE")]
    if noise_entries:
        parts = [f"{_label(b)} read {_pct(b.get('score'))} camera-likeness"
                 + (" (not applicable to this format)" if not b.get("applied", True) else "")
                 for b in noise_entries]
        noise_body = ("Sensor and micro-texture checks: " + "; ".join(parts) + ". "
                      "Together they test whether the frame carries the fine, irregular grain a "
                      "physical sensor leaves behind, and whether every region shares the same "
                      "noise statistics. Low scores here suggest denoising, synthesis or local "
                      "editing; high scores are consistent with an untouched capture. A highly "
                      "compressed, screenshot or social-media re-encoded image can lose this "
                      "signal entirely, so a low score on its own is not proof of manipulation.")
        sections.append({"title": "6. Noise and sensor-pattern analysis", "body": noise_body})

    # ---------------------------------------------------------------- 7. frequency / wavelet
    fw_entries = [b for b in breakdown if b.get("method") in ("FREQUENCY", "WAVELET")]
    if fw_entries:
        parts = [f"{_label(b)} read {_pct(b.get('score'))} camera-likeness"
                 + (" (not applicable to this format)" if not b.get("applied", True) else "")
                 for b in fw_entries]
        fw_body = ("Frequency and multi-scale detail: " + "; ".join(parts) + ". "
                   "These checks look at how energy is distributed across spatial frequencies "
                   "and across wavelet sub-bands (LL/LH/HL/HH). Camera noise is usually "
                   "broadband and spreads naturally across scales; periodic peaks, ringing or "
                   "an over-smooth high-frequency band are more typical of resampling, "
                   "upsampling or synthetic generation. A single frequency artifact is rarely "
                   "decisive on its own.")
        sections.append({"title": "7. Frequency and wavelet findings", "body": fw_body})

    # ---------------------------------------------------------------- 8. compression / editing
    comp_entries = [b for b in breakdown if b.get("method") in ("ELA", "JPEG")]
    if comp_entries:
        parts = [f"{_label(b)} read {_pct(b.get('score'))} camera-likeness"
                 + (" (not applicable to this format)" if not b.get("applied", True) else "")
                 for b in comp_entries]
        comp_body = ("Compression and editing indicators: " + "; ".join(parts) + ". "
                     "Error-level analysis re-saves the image at a known quality and measures "
                     "where recompression error differs; JPEG structure analysis checks "
                     "quantisation tables and 8x8 block statistics. Edited or spliced regions "
                     "usually recompress differently from untouched areas, while a single, "
                     "uniform compression history looks like one untouched JPEG. These checks "
                     "only apply to JPEG sources; PNG and WEBP files have no JPEG compression "
                     "history, so they abstain rather than voting.")
        sections.append({"title": "8. Compression and editing indicators", "body": comp_body})

    # ---------------------------------------------------------------- 9. metadata
    meta = (detectors.get("METADATA") or {}).get("details") or {}
    meta_bits = []
    if meta.get("make") or meta.get("model"):
        meta_bits.append(f"camera body '{' '.join(str(x) for x in (meta.get('make'), meta.get('model')) if x)}'")
    if meta.get("datetime"):
        meta_bits.append(f"capture time {meta['datetime']}")
    if meta.get("software"):
        meta_bits.append(f"software tag '{meta['software']}'")
    if meta.get("has_gps"):
        meta_bits.append("GPS coordinates present (withheld for privacy)")
    meta_body = ("Metadata findings: " + (", ".join(meta_bits) + "." if meta_bits
                 else "no camera make/model, capture time, software or GPS tag was found."))
    meta_body += (" Metadata is supporting evidence only: it can be stripped by social "
                  "networks and messaging apps, and it can be edited or forged, so a missing "
                  "or suspicious tag is never treated as proof on its own.")
    sections.append({"title": "9. Metadata findings", "body": meta_body})

    # ---------------------------------------------------------------- 10. agreement
    agree_body = (f"Detector agreement and disagreement: {len(for_real)} detector(s) leaned "
                  f"towards a camera origin and {len(against)} leaned away from one"
                  + (f"; the remaining {len(neutral)} sat within two points of their neutral "
                     f"point and contributed almost nothing." if neutral else "."))
    if for_real:
        agree_body += (" The strongest camera-leaning signal is "
                       f"{_label(for_real[0])} at {_pct(for_real[0].get('score'))} "
                       f"camera-likeness.")
    if against:
        agree_body += (" The strongest synthetic-leaning signal is "
                       f"{_label(against[0])} at {_pct(against[0].get('score'))} "
                       f"camera-likeness.")
    agree_body += (" Unanimous direction is encouraging but still reflects statistical "
                   "tendencies rather than certainty; a single strong detector can be "
                   "misled by heavy recompression or a convincing generator.")
    sections.append({"title": "10. Detector agreement and disagreement", "body": agree_body})

    # ---------------------------------------------------------------- 11. limits (renumbered)
    limits = (f"PixelForensics reports evidence, not proof. The confidence figure ({_pct(conf)}) "
              f"expresses how far the weighted evidence sits from the decision boundary "
              f"(0.50 + 1.5 x distance, capped at 97%); it is not the probability that the image "
              f"is fake. Every detector here is classical digital image processing - no neural "
              f"classifier is involved, so nothing is recognised or captioned. Traces are fragile: "
              f"resizing, screenshotting and heavy recompression destroy the sensor noise that "
              f"PRNU and noise-floor analysis depend on, and a generator paired with a good "
              f"denoiser can imitate camera grain. PNG and WEBP files have no JPEG compression "
              f"history at all, so error-level analysis cannot contribute for them.")
    sections.append({"title": "11. What this does - and does not - prove", "body": limits})

    # ---------------------------------------------------------------- 12. conclusion
    conclusion = (_verdict_sentence(verdict, final, conf) + " "
                  + f"In total {len(for_real)} detector(s) leaned towards a camera and "
                  f"{len(against)} leaned away from one"
                  + (f", with {len(neutral)} effectively neutral." if neutral else "."))
    if regions:
        conclusion += (f" {len(regions)} localised region(s) carried noise statistics that "
                       f"differ from the rest of the frame and are listed as pointers for human "
                       f"review, not as convictions.")
    conclusion += (" Read the result as calibrated evidence about this file, not as a "
                   "certificate of authenticity, and keep a human in the loop for anything "
                   "consequential.")
    sections.append({"title": "12. Overall conclusion", "body": conclusion})

    # ---------------------------------------------------------------- 13. next steps (renumbered)
    next_steps = [
        "Obtain the original file as exported by the device or camera, not a copy that passed "
        "through a chat app, a screenshot or a social network.",
        "Compare the result with other confirmed images from the same device: consistent EXIF "
        "make/model and matching noise behaviour are far stronger than any single check.",
        "Run the multi-image comparison tool on the disputed file and one or two reference "
        "images to test residual similarity between them.",
        "Ask the publisher for provenance (original camera roll entry, RAW file or signed "
        "content-credential manifest) before drawing a conclusion.",
        "Keep a human in the loop for anything consequential: use this report as one input to "
        "review, never as the sole basis for an accusation.",
    ]
    steps_body = ("A short, practical checklist for confirming this result: " +
                  " ".join(f"({i + 1}) {s}" for i, s in enumerate(next_steps)))
    sections.append({"title": "13. Recommended next steps", "body": steps_body})



    # ---------------------------------------------------------------- key findings
    key_findings = []
    for entry in ranked[:4]:
        cal = float(entry.get("calibrated") or 0.0)
        direction = ("supports_camera" if cal > 0 else
                     "supports_ai" if cal < 0 else "neutral")
        key_findings.append({
            "title": _label(entry),
            "detail": (f"{_pct(entry.get('score'))} camera-likeness, weight "
                       f"{_pct(float(entry.get('weight') or 0.0))}, evidence {cal:+.2f}. "
                       f"{entry.get('interpretation') or ''}").strip(),
            "direction": direction,
            "strength": round(abs(cal * float(entry.get("weight") or 0.0)), 3),
        })

    detector_notes = []
    for entry in sorted(breakdown, key=lambda b: -float(b.get("weight") or 0.0)):
        cal = float(entry.get("calibrated") or 0.0)
        guide = _detector_guide(entry.get("method", ""))
        detector_notes.append({
            "method": entry.get("method"),
            "title": _label(entry),
            "what_it_measures": guide["measures"],
            "reading": _reading(entry),
            "interpretation": entry.get("interpretation") or "",
            "score": round(float(entry.get("score") or 0.0), 4),
            "confidence": round(float(entry.get("confidence") or 0.0), 4),
            "weight": round(float(entry.get("weight") or 0.0), 4),
            "evidence": round(cal, 3),
            "direction": ("supports_camera" if cal > 0 else
                          "supports_ai" if cal < 0 else "neutral"),
            "applied": bool(entry.get("applied", True)),
        })

    # ---------------------------------------------------------------- headline
    if verdict == "LIKELY_REAL":
        headline = f"The frame reads as a camera capture at {_pct(final)} camera-likeness"
        if for_real:
            headline += (f", led by {_label(for_real[0])} at "
                         f"{_pct(for_real[0].get('score'))} camera-likeness")
        if against:
            headline += (f", against {_label(against[0])} at "
                         f"{_pct(against[0].get('score'))} on the other side")
        headline += "."
    elif verdict == "LIKELY_AI_MANIPULATED":
        headline = (f"The frame reads as synthetic or manipulated at {_pct(final)} "
                    f"camera-likeness")
        if against:
            headline += (f", driven by {_label(against[0])} at "
                         f"{_pct(against[0].get('score'))} camera-likeness")
        if for_real:
            headline += (f"; {_label(for_real[0])} at {_pct(for_real[0].get('score'))} is the "
                         f"main counter-signal")
        headline += "."
    else:
        headline = (f"Evidence is split at {_pct(final)} camera-likeness, so the result is "
                    f"reported as inconclusive rather than forced into a verdict.")

    summary = _verdict_sentence(verdict, final, conf)
    if profile.get("scene_description"):
        summary += " " + profile["scene_description"]
    if against and for_real:
        summary += (f" The strongest synthetic-leaning signal is {_label(against[0])} at "
                    f"{_pct(against[0].get('score'))} camera-likeness, while {_label(for_real[0])} "
                    f"argues the opposite at {_pct(for_real[0].get('score'))}.")
    elif against:
        summary += (f" The strongest synthetic-leaning signal is {_label(against[0])} at "
                    f"{_pct(against[0].get('score'))} camera-likeness.")
    elif for_real:
        summary += (f" The strongest camera-leaning signal is {_label(for_real[0])} at "
                    f"{_pct(for_real[0].get('score'))} camera-likeness.")
    summary += (" Read the result as calibrated evidence about this file, not as a certificate "
                "of authenticity.")

    confidence_note = (
        f"Confidence {_pct(conf)} describes how far the weighted evidence sits from the decision "
        f"boundary, and is capped at 97% because no single-image statistical test can be "
        f"certain. It is not the probability that the image is fake or real."
    )

    return {
        "headline": headline,
        "summary": summary,
        "verdict_label": _VERDICT_LABEL.get(verdict, verdict),
        "final_score": round(final, 4),
        "confidence": round(conf, 4),
        "sections": sections,
        "key_findings": key_findings,
        "detector_notes": detector_notes,
        "next_steps": next_steps,
        "confidence_note": confidence_note,
        "regions_flagged": len(regions),
        "engine": "pixel-forensics narrative engine v1 (classical DIP, no CNN)",
    }


