"""Generative-content cues.

Signals here are chosen because they survive the re-encoding that social media,
messaging apps and screenshots apply - the situations where classic sensor-noise
analysis (PRNU/ELA) stops working.

Each sub-score is 1.0 = looks camera-captured, 0.0 = looks synthetic.

Calibration notes (see backend/tools/calibrate.py and backend/dataset/README.md):
the squash centres below come from a small labelled set of camera photos vs
diffusion/GAN outputs, re-encoded to JPEG like real uploads. They are starting
points, not ground truth - re-run the calibration tool with your own samples.
"""
import io
import numpy as np
import cv2
from PIL import Image
from .common import to_gray, detector_result

# Common size of diffusion/GAN output; camera files rarely land exactly here.
_AI_SIZES = {
    (1024, 1024), (1024, 1536), (1536, 1024), (1024, 1792), (1792, 1024),
    (512, 512), (768, 768), (832, 1216), (1216, 832), (1344, 768), (768, 1344),
    (1152, 896), (896, 1152),
}
_AI_SOFTWARE = ("midjourney", "stable diffusion", "stablediffusion", "dall-e", "dalle",
                "firefly", "comfyui", "automatic1111", "flux", "grok", "ideogram", "leonardo")
# Maker/model strings written by generators. "sana" = NVIDIA Sana; several hosted
# APIs stamp their own name into Make/Model.
_AI_MAKERS = ("sana", "openai", "midjourney", "stability", "stablediffusion",
              "black forest", "blackforest", "flux", "ideogram", "recraft", "runway",
              "leonardo", "playground", "novelai", "krea", "firefly", "dall-e", "dalle")
# Keys that only appear when a prompt/seed/sampler was embedded in the file.
_PROMPT_HINTS = ("negative prompt", "negativeprompt", "cfg scale", "cfgscale",
                 "sampler", "denoising", "stable diffusion", "comfyui",
                 "automatic1111", "invokeai", "fooocus")


def _has_prompt_text(text: str) -> bool:
    if any(h in text for h in _PROMPT_HINTS):
        return True
    # JSON-ish prompt blobs, e.g. {"prompt": "...", "seed": 42}
    return '"prompt"' in text or "prompt:" in text or "'prompt'" in text


def _sig(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


def _kurtosis(a: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64).ravel()
    if a.size < 100:
        return 1.0
    a = a - a.mean()
    v = float((a ** 2).mean()) + 1e-12
    return float((a ** 4).mean() / (v * v))


def _encoder_prior(raw: bytes) -> tuple[float, dict]:
    """Metadata/format prior. Returns (score, details)."""
    info: dict = {"has_exif": False, "make": None, "model": None,
                  "software": None, "width": None, "height": None,
                  "prompt_text": False}
    try:
        pil = Image.open(io.BytesIO(raw))
        info["width"], info["height"] = pil.size
        exif = pil.getexif()
        if exif:
            info["has_exif"] = True
            info["make"] = (str(exif.get(271) or "") or None)
            info["model"] = (str(exif.get(272) or "") or None)
            info["software"] = (str(exif.get(305) or "") or None)
            # UserComment / ImageDescription / XPAuthor / XPTitle often hold the prompt
            blobs = [exif.get(t) for t in (37510, 270, 40092, 40093, 269)]
            text = " ".join(
                b.decode("utf-8", "ignore") if isinstance(b, (bytes, bytearray)) else str(b)
                for b in blobs if b
            ).lower()
            info["prompt_text"] = _has_prompt_text(text)
        # XMP / PNG text chunks
        extra = " ".join(str(v) for v in (pil.info or {}).values() if isinstance(v, str)).lower()
        if _has_prompt_text(extra):
            info["prompt_text"] = True
    except Exception:
        return 0.45, info

    stamp = " ".join(filter(None, [info["make"], info["model"], info["software"]])).lower()
    size = (info["width"], info["height"])

    # Hard evidence first.
    if info["prompt_text"]:
        return 0.02, info
    if any(t in stamp for t in _AI_SOFTWARE) or any(t in stamp for t in _AI_MAKERS):
        return 0.02, info
    if stamp.strip() and any(t in stamp for t in (
            "canon", "nikon", "sony", "fujifilm", "olympus", "panasonic", "leica",
            "pentax", "samsung", "apple", "google", "xiaomi", "oneplus", "huawei",
            "motorola", "oppo", "vivo", "realme", "dji", "gopro", "ricoh", "hasselblad")):
        return 0.90, info
    if info["make"] or info["model"]:
        return 0.80, info

    # Softer priors: a camera pipeline writes JPEG; diffusion tools default to PNG
    # at one of a handful of pixel dimensions.
    is_png = raw[:8] == b"\x89PNG\r\n\x1a\n"
    if size in _AI_SIZES:
        return (0.03 if is_png else 0.20), info
    if info["has_exif"]:
        return 0.55, info
    if is_png:
        return 0.35, info
    return 0.45, info


def _cues(img_rgb: np.ndarray) -> dict:
    g = to_gray(img_rgb).astype(np.float32)
    h, w = g.shape

    # Edge-preserving high-pass: median filter keeps edges, difference is noise+ringing.
    med = cv2.medianBlur(g.astype(np.uint8), 3).astype(np.float32)
    noise = g - med

    # Flattest 40% / edgiest 10% of pixels, selected by Sobel magnitude.
    sob = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)) + np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    order = np.argsort(sob.ravel())
    flat = np.zeros(sob.size, dtype=bool)
    flat[order[: int(0.40 * order.size)]] = True
    flat_noise = float(np.abs(noise.ravel()[flat]).mean()) if flat.any() else 0.0

    # Detail present even in the quietest blocks (camera noise/grain floor).
    bs = 16
    if h >= bs * 4 and w >= bs * 4:
        sd = np.array([g[i*bs:(i+1)*bs, j*bs:(j+1)*bs].std()
                       for i in range(h // bs) for j in range(w // bs)])
        detail_floor = float(np.percentile(sd, 10))
    else:
        detail_floor = float(g.std())

    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    saturation = float(hsv[:, :, 1].mean())

    n = noise - noise.mean()
    noise_ac = float((n[:, :-1] * n[:, 1:]).sum() / ((n ** 2).sum() + 1e-9))

    return {
        "noise_kurtosis": _kurtosis(noise),
        "flat_noise": flat_noise,
        "detail_floor": detail_floor,
        "saturation": saturation,
        "noise_ac": noise_ac,
    }


def analyze_generative(img_rgb: np.ndarray, raw: bytes, fmt: str) -> dict:
    c = _cues(img_rgb)
    enc_score, enc_info = _encoder_prior(raw)

    sub = {
        # Heavy tails in the noise residual = ringing/oversharpening, typical of
        # upsampling decoders. Camera noise is close to Gaussian.
        "noise_kurtosis": (1.0 - _sig((np.log10(c["noise_kurtosis"] + 1.0) - 2.25) * 1.5), 0.26),
        # Real captures keep a noise floor in flat areas; diffusion output is often
        # clinically smooth there once denoisers finish.
        "flat_noise": (_sig((c["flat_noise"] - 0.67) * 2.0), 0.19),
        "detail_floor": (_sig((c["detail_floor"] - 1.90) * 0.55), 0.13),
        # Generators oversaturate more often than cameras.
        "saturation": (1.0 - _sig((c["saturation"] - 113.0) * 0.04), 0.14),
        # Correlated residual: compression/upsampling structure rather than white noise.
        "noise_ac": (1.0 - _sig((c["noise_ac"] - 0.30) * 6.0), 0.10),
        # EXIF presence, camera make/model, generator software tag, native size.
        "encoder_prior": (enc_score, 0.18),
    }

    total_w = sum(w for _, w in sub.values())
    score = sum(s * w for s, w in sub.values()) / total_w

    if score >= 0.60:
        interp = ("Noise, texture and encoder cues look like a camera capture "
                  "(no residual ringing, noise floor present in flat areas).")
        conf = 0.80
    elif score <= 0.40:
        interp = ("Synthetic-content cues: residual ringing, missing noise floor in flat "
                  "regions and/or a generator fingerprint in the file metadata.")
        conf = 0.80
    else:
        interp = "Generative-content cues are mixed; this image is genuinely ambiguous."
        conf = 0.55

    details = {k: round(float(v[0]), 3) for k, v in sub.items()}
    details.update({"weighted_score": round(float(score), 3),
                    "raw": {k: round(float(v), 4) for k, v in c.items()},
                    "encoder": enc_info})
    return detector_result("GENERATIVE", score, conf, interp, details)
