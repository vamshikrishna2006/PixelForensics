"""Descriptive per-image profile.

Purely descriptive: **nothing here votes on the verdict**. It gives the plain
English narrative and the PDF report a human-readable sense of what the picture
looks like -- tone, palette, detail density, framing -- so a reader can connect
the numeric evidence to the image sitting in front of them.

No object recognition is attempted (the project is classical DIP only). The
result is deliberately phrased as measured statistics about the frame, never as
a claim about what is depicted.
"""
from __future__ import annotations

import cv2
import numpy as np

# Named anchors used to turn an average RGB value into a word a human can read.
_PALETTE = {
    "black": (10, 10, 10),
    "grey": (128, 128, 128),
    "white": (245, 245, 245),
    "red": (200, 40, 40),
    "orange": (230, 130, 40),
    "brown": (120, 80, 50),
    "yellow": (230, 210, 60),
    "green": (60, 160, 80),
    "teal": (40, 160, 160),
    "blue": (50, 90, 200),
    "purple": (130, 70, 190),
    "pink": (230, 120, 180),
}


def _colour_name(rgb) -> str:
    r, g, b = [float(v) for v in rgb]
    best, best_d = "grey", None
    for name, (pr, pg, pb) in _PALETTE.items():
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if best_d is None or d < best_d:
            best, best_d = name, d
    return best


def _hex(rgb) -> str:
    r, g, b = [max(0, min(255, int(round(v)))) for v in rgb]
    return f"#{r:02X}{g:02X}{b:02X}"


def _dominant_colours(img_rgb: np.ndarray, k: int = 3) -> list[dict]:
    """Deterministic k-means over a small sample of the image."""
    small = cv2.resize(img_rgb, (96, 96), interpolation=cv2.INTER_AREA).reshape(-1, 3).astype(np.float32)
    cv2.setRNGSeed(7)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centres = cv2.kmeans(small, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k).astype(float)
    total = float(counts.sum()) or 1.0
    out = []
    for i in np.argsort(-counts):
        rgb = [int(round(float(v))) for v in centres[i]]
        out.append({"hex": _hex(rgb), "rgb": rgb, "name": _colour_name(rgb),
                    "share": round(float(counts[i] / total), 3)})
    return out


def _tone_label(luminance: float) -> str:
    if luminance < 0.20:
        return "very dark"
    if luminance < 0.38:
        return "low-light"
    if luminance < 0.60:
        return "mid-tone"
    if luminance < 0.82:
        return "bright"
    return "high-key"


def _framing(width: int, height: int) -> tuple[str, str]:
    aspect = width / height if height else 1.0
    if aspect >= 1.85:
        return "widescreen", f"{aspect:.2f}:1"
    if aspect > 1.15:
        return "landscape", f"{aspect:.2f}:1"
    if aspect >= 0.87:
        return "square", f"{aspect:.2f}:1"
    return "portrait", f"{aspect:.2f}:1"


def _detail_label(edge_density: float) -> str:
    if edge_density < 0.015:
        return "very sparse detail"
    if edge_density < 0.045:
        return "moderate detail"
    if edge_density < 0.10:
        return "dense detail"
    return "very dense detail"



def profile_image(img_rgb: np.ndarray) -> dict:
    """Return a descriptive profile of ``img_rgb`` (HxWx3, uint8)."""
    h, w = img_rgb.shape[:2]
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

    # Work on a bounded copy so profiling stays cheap on large uploads.
    work = gray
    if max(h, w) > 900:
        scale = 900.0 / max(h, w)
        work = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))),
                          interpolation=cv2.INTER_AREA)

    luminance = float(work.mean()) / 255.0
    contrast = float(work.std()) / 64.0
    sharpness_raw = float(cv2.Laplacian(work, cv2.CV_64F).var())
    edges = cv2.Canny(work, 60, 160)
    edge_density = float((edges > 0).mean())

    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    saturation = float(hsv[:, :, 1].mean()) / 255.0
    hues = hsv[:, :, 0][hsv[:, :, 1] > 40]
    hue_deg = (float(hues.mean()) / 180.0 * 360.0) if hues.size else 0.0

    if saturation < 0.10:
        palette_family = "near-neutral"
    elif 15 <= hue_deg < 75 or hue_deg >= 330:
        palette_family = "warm"
    elif 75 <= hue_deg < 170:
        palette_family = "green-leaning"
    else:
        palette_family = "cool"

    vividness = "vivid" if saturation >= 0.45 else "muted" if saturation < 0.20 else "balanced"
    framing, aspect = _framing(int(w), int(h))
    tones = work.reshape(-1)
    dark_share = float((tones < 64).mean())
    mid_share = float(((tones >= 64) & (tones <= 191)).mean())
    bright_share = float((tones > 191).mean())

    if sharpness_raw < 45:
        crispness = "soft / low micro-contrast"
    elif sharpness_raw < 260:
        crispness = "moderately sharp"
    else:
        crispness = "crisp, high micro-contrast"

    colours = _dominant_colours(img_rgb)
    top = colours[0] if colours else {"name": "grey", "hex": "#808080", "share": 0.0}
    second = colours[1] if len(colours) > 1 else top

    # Purely compositional label -- used for report naming, never for scoring.
    tone_word = _tone_label(luminance).replace("-", "").replace(" ", "")
    family_word = palette_family.split("-")[0]
    scene_label = f"{tone_word}-{family_word}-{framing}"

    sentence = (
        f"A {framing} frame ({w}x{h}px, aspect {aspect}) whose average luminance is "
        f"{luminance:.0%} ({_tone_label(luminance)}), dominated by {top['name']} "
        f"({top['share']:.0%} of the frame) with {second['name']} filling much of the rest. "
        f"The palette is {palette_family} and {vividness}, fine detail is "
        f"{_detail_label(edge_density)} (edges cover {edge_density:.1%} of pixels) and the "
        f"surface is {crispness}. Roughly {bright_share:.0%} of pixels sit in the bright band, "
        f"{mid_share:.0%} in mid-tones and {dark_share:.0%} in deep shadows."
    )

    return {
        "width": int(w),
        "height": int(h),
        "megapixels": round((w * h) / 1_000_000, 2),
        "aspect_ratio": aspect,
        "framing": framing,
        "orientation": "portrait" if h > w else "landscape" if w > h else "square",
        "luminance": round(luminance, 3),
        "tone": _tone_label(luminance),
        "contrast": round(min(1.0, contrast), 3),
        "saturation": round(saturation, 3),
        "colour_family": palette_family,
        "vividness": vividness,
        "sharpness_raw": round(sharpness_raw, 1),
        "crispness": crispness,
        "edge_density": round(edge_density, 4),
        "detail": _detail_label(edge_density),
        "dark_share": round(dark_share, 3),
        "mid_share": round(mid_share, 3),
        "bright_share": round(bright_share, 3),
        "dominant_colours": colours,
        "scene_label": scene_label,
        "scene_description": sentence,
    }
