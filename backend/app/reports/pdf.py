"""Professional PDF report builder (ReportLab).

The document is a branded, multi-section A4 report rather than a text dump:

* cover page with hero band, verdict card, subject facts and the exhibit;
* numbered narrative sections (image description, method, decisive evidence,
  counter-evidence, local anomalies, limits, next steps);
* a colour-coded detector evidence table;
* every proof artifact as a captioned exhibit (original frame, noise residual,
  heatmap, region overlay, ELA, frequency spectrum, wavelet sub-bands);
* suspicious-region and EXIF tables;
* an HMAC-signed authenticity block, and a diagonal PixelForensics watermark
  plus numbered footer on every page.
"""
from __future__ import annotations

import base64
import io
from datetime import datetime

import cv2
import numpy as np
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (Image as RLImage, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)
from xml.sax.saxutils import escape

from app.core.config import get_settings
from app.forensic.narrative import build_narrative
from .naming import report_basename
from .signing import sign_meta

settings = get_settings()

SITE_LABEL = "PixelForensics"
SITE_TAGLINE = "Digital image forensics"
COLOR_W, COLOR_H = A4
CONTENT_W = COLOR_W - 36 * mm

INK = colors.HexColor("#0F172A")
BODY = colors.HexColor("#334155")
MUTED = colors.HexColor("#64748B")
ACCENT = colors.HexColor("#7C3AED")
ACCENT_DARK = colors.HexColor("#4C1D95")
ACCENT_SOFT = colors.HexColor("#F3EEFF")
PANEL = colors.HexColor("#F8FAFC")
LINE = colors.HexColor("#E2E8F0")
GREEN = colors.HexColor("#15803D")
RED = colors.HexColor("#B91C1C")
AMBER = colors.HexColor("#B45309")

_VERDICT_STYLE = {
    # verdict -> (label, ink hex, tint hex, border hex)
    "LIKELY_REAL": ("Likely real", "#15803D", "#ECFDF5", "#A7F3D0"),
    "LIKELY_AI_MANIPULATED": ("Likely AI-generated / manipulated", "#B91C1C", "#FEF2F2", "#FECACA"),
    "INCONCLUSIVE": ("Inconclusive", "#B45309", "#FFFBEB", "#FDE68A"),
}


def _t(value) -> str:
    """Escape for Paragraph and drop glyphs the base-14 fonts cannot encode."""
    text = "" if value is None else str(value)
    text = text.encode("cp1252", "replace").decode("cp1252")
    return escape(text)



def _styles() -> dict:
    ss = getSampleStyleSheet()
    return {
        "hero_kicker": ParagraphStyle("hero_kicker", fontName="Helvetica-Bold", fontSize=8.5,
                                      leading=11, textColor=colors.HexColor("#C4B5FD")),
        "hero_title": ParagraphStyle("hero_title", fontName="Helvetica-Bold", fontSize=23,
                                     leading=27, textColor=colors.white),
        "hero_sub": ParagraphStyle("hero_sub", fontName="Helvetica", fontSize=9.4, leading=13,
                                   textColor=colors.HexColor("#DDD6FE")),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.2,
                             leading=16, textColor=ACCENT_DARK, spaceBefore=10, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold", fontSize=9.6,
                             leading=13, textColor=INK, spaceBefore=4, spaceAfter=2),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.3, leading=14,
                               textColor=BODY, alignment=0, spaceAfter=6),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8, leading=11,
                                textColor=MUTED),
        "caption": ParagraphStyle("caption", fontName="Helvetica-Oblique", fontSize=7.4, leading=10,
                                  textColor=MUTED),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=7.8, leading=10.2,
                               textColor=BODY),
        "cell_b": ParagraphStyle("cell_b", fontName="Helvetica-Bold", fontSize=7.8, leading=10.2,
                                 textColor=INK),
        "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=7.4, leading=9.6,
                             textColor=colors.white),
        "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=7.4, leading=9.6,
                                textColor=MUTED),
        "verdict_big": ParagraphStyle("verdict_big", fontName="Helvetica-Bold", fontSize=15,
                                      leading=18),
        "verdict_note": ParagraphStyle("verdict_note", fontName="Helvetica", fontSize=8.2,
                                       leading=11.2, textColor=BODY),
        "score_big": ParagraphStyle("score_big", fontName="Helvetica-Bold", fontSize=21,
                                    leading=23, alignment=2, textColor=INK),
        "score_note": ParagraphStyle("score_note", fontName="Helvetica", fontSize=6.8, leading=9,
                                     alignment=2, textColor=MUTED),
        "mono": ParagraphStyle("mono", fontName="Courier", fontSize=7.2, leading=9.6,
                               textColor=BODY),
        "white": ParagraphStyle("white", fontName="Helvetica", fontSize=8, leading=11,
                                textColor=colors.white),
    }


def _png_bytes(source, max_side: int = 1400) -> bytes | None:
    """Load bytes/path through PIL and re-encode to PNG (so any input format works)."""
    try:
        if isinstance(source, (bytes, bytearray)):
            im = PILImage.open(io.BytesIO(bytes(source)))
        else:
            im = PILImage.open(str(source))
        im.load()
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side), PILImage.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _b64_png(b64: str | None, max_side: int = 800) -> bytes | None:
    if not b64:
        return None
    try:
        return _png_bytes(base64.b64decode(b64), max_side=max_side)
    except Exception:
        return None


def _flow_image(png: bytes | None, max_w: float, max_h: float) -> RLImage | None:
    if not png:
        return None
    try:
        with PILImage.open(io.BytesIO(png)) as im:
            w, h = im.size
    except Exception:
        return None
    if not w or not h:
        return None
    scale = min(max_w / w, max_h / h)
    return RLImage(io.BytesIO(png), width=w * scale, height=h * scale)


def _spectrum_png(spectrum) -> bytes | None:
    try:
        arr = np.asarray(spectrum, dtype=np.float32)
        if arr.ndim != 2 or arr.size == 0:
            return None
        arr = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        colour = cv2.applyColorMap(arr, cv2.COLORMAP_INFERNO)
        colour = cv2.resize(colour, (256, 256), interpolation=cv2.INTER_CUBIC)
        ok, buf = cv2.imencode(".png", colour)
        return buf.tobytes() if ok else None
    except Exception:
        return None


def _overlay_regions(original_png: bytes | None, regions: list[dict],
                     analyzed_size: tuple[int, int] | None) -> bytes | None:
    """Draw the reported suspicious boxes onto a copy of the original frame."""
    if not original_png or not regions:
        return None
    try:
        pil = PILImage.open(io.BytesIO(original_png)).convert("RGB")
        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        h, w = img.shape[:2]
        aw, ah = analyzed_size or (w, h)
        sx, sy = (w / aw if aw else 1.0), (h / ah if ah else 1.0)
        thickness = max(2, int(round(min(w, h) / 320)))
        for region in regions:
            x = int(int(region.get("x") or 0) * sx)
            y = int(int(region.get("y") or 0) * sy)
            bw = int(int(region.get("width") or 0) * sx)
            bh = int(int(region.get("height") or 0) * sy)
            if bw <= 1 or bh <= 1:
                continue
            cv2.rectangle(img, (x, y), (x + bw, y + bh), (60, 40, 235), thickness)
            label = f"R{region.get('id', '')}"
            cv2.putText(img, label, (x + 6, max(22, y + 22)), cv2.FONT_HERSHEY_SIMPLEX, 0.75,
                        (255, 255, 255), 3, cv2.LINE_AA)
            cv2.putText(img, label, (x + 6, max(22, y + 22)), cv2.FONT_HERSHEY_SIMPLEX, 0.75,
                        (60, 40, 235), 1, cv2.LINE_AA)
        out = PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        out.thumbnail((1400, 1400), PILImage.LANCZOS)
        buf = io.BytesIO()
        out.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def _as_dt(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _iso_minute(value) -> str:
    dt = _as_dt(value)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else ""


def _fmt_dt(value) -> str:
    dt = _as_dt(value)
    return dt.strftime("%d %b %Y, %H:%M UTC") if dt else "n/a"


def _kv_table(rows, s, label_w: float = 46 * mm) -> Table:
    data = [[Paragraph(_t(k), s["label"]), Paragraph(_t(v), s["cell"])] for k, v in rows]
    table = Table(data, colWidths=[label_w, CONTENT_W - label_w])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), PANEL),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
    ]))
    return table


def _exhibit_cell(png, title: str, caption: str, s, cell_w: float, max_h: float = 58 * mm):
    parts = []
    image = _flow_image(png, cell_w - 14, max_h)
    if image is not None:
        parts.append(image)
    else:
        parts.append(Paragraph("<i>Artifact unavailable for this analysis.</i>", s["caption"]))
    parts.append(Spacer(1, 3))
    parts.append(Paragraph(_t(title), s["cell_b"]))
    parts.append(Paragraph(_t(caption), s["caption"]))
    return parts


def _exhibit_row(left, right, s, full_width: bool = False) -> Table:
    if full_width or right is None:
        table = Table([[left]], colWidths=[CONTENT_W])
    else:
        gap = 6
        cell_w = (CONTENT_W - gap) / 2
        table = Table([[left, right]], colWidths=[cell_w, cell_w])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table



def build_pdf(meta: dict, result: dict) -> bytes:
    """Render the full forensic report and return the PDF bytes."""
    result = result or {}
    narrative = result.get("narrative") or {}
    if not narrative.get("sections"):
        narrative = build_narrative(result)

    verdict = str(meta.get("verdict") or result.get("verdict") or "INCONCLUSIVE")
    final = float(meta["final_score"] if meta.get("final_score") is not None
                  else (result.get("final_score") or 0.0))
    conf = float(meta["confidence"] if meta.get("confidence") is not None
                 else (result.get("confidence") or 0.0))
    filename = str(meta.get("filename") or "upload")
    report_id = str(meta.get("id") or "")
    created = _as_dt(meta.get("created_at"))
    generated = datetime.utcnow()
    profile = result.get("image_profile") or {}
    info = result.get("image_info") or {}
    artifacts = result.get("artifacts") or {}
    regions = result.get("regions") or []
    detectors = {d.get("method"): d for d in (result.get("detectors") or [])}
    breakdown = [b for b in (result.get("breakdown") or []) if b.get("applied", True)]
    base = report_basename(filename, profile, created)
    label, colour_hex, tint_hex, border_hex = _VERDICT_STYLE.get(
        verdict, _VERDICT_STYLE["INCONCLUSIVE"])
    colour = colors.HexColor(colour_hex)
    s = _styles()

    sig = sign_meta({
        "id": report_id,
        "filename": filename,
        "verdict": verdict,
        "final_score": final,
        "confidence": conf,
        "created_at": _iso_minute(created) or str(meta.get("created_at") or ""),
        "algorithm_version": settings.FORENSIC_ALGORITHM_VERSION,
    })

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=22 * mm,
        title=f"{base} - Forensic Report", author=SITE_LABEL,
        subject="Digital image forensic analysis", creator=SITE_LABEL,
        keywords=f"{report_id}, {verdict}, HMAC-SHA256 {sig['signature_id']}",
    )

    def decorate(canv, _doc):
        """Watermark + brand rails, drawn on every page before the content."""
        canv.saveState()
        canv.setFillColor(colors.HexColor("#FCFBFF"))
        canv.rect(0, 0, COLOR_W, COLOR_H, stroke=0, fill=1)
        canv.saveState()
        canv.translate(COLOR_W / 2, COLOR_H / 2 - 6 * mm)
        canv.rotate(40)
        canv.setFillColor(colors.HexColor("#EAE3FB"))
        canv.setFont("Helvetica-Bold", 38)
        canv.drawCentredString(0, 6 * mm, "PIXELFORENSICS")
        canv.setFont("Helvetica", 8.4)
        canv.setFillColor(colors.HexColor("#D8CDF4"))
        canv.drawCentredString(0, -2 * mm,
                               f"{SITE_LABEL}  -  {SITE_TAGLINE}  -  authenticated report")
        canv.restoreState()
        canv.setFillColor(colors.HexColor("#22D3EE"))
        canv.rect(0, COLOR_H - 5 * mm, 44 * mm, 5 * mm, stroke=0, fill=1)
        canv.setFillColor(colors.HexColor("#7C3AED"))
        canv.rect(44 * mm, COLOR_H - 5 * mm, COLOR_W - 44 * mm, 5 * mm, stroke=0, fill=1)
        canv.restoreState()

    class _NumberedCanvas(canvas.Canvas):
        """Canvas that knows the total page count, for 'Page X of Y'."""

        def __init__(self, *args, **kwargs):
            canvas.Canvas.__init__(self, *args, **kwargs)
            self._saved_pages = []

        def showPage(self):
            self._saved_pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_pages)
            for state in self._saved_pages:
                self.__dict__.update(state)
                self._footer(total)
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

        def _footer(self, total):
            self.saveState()
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.6)
            self.line(18 * mm, 14 * mm, COLOR_W - 18 * mm, 14 * mm)
            self.setFont("Helvetica", 7)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawString(18 * mm, 9.6 * mm,
                            f"{SITE_LABEL} - authenticated forensic report - "
                            f"HMAC-SHA256 {sig['signature_id']}")
            ref = report_id[:8].upper() or "--------"
            self.drawRightString(COLOR_W - 18 * mm, 9.6 * mm,
                                 f"Ref {ref}   |   Page {self._pageNumber} of {total}")
            self.restoreState()

    story: list = []


    # ------------------------------------------------------------------ cover
    hero = Table([
        [Paragraph(_t(f"{SITE_LABEL.upper()}   |   {SITE_TAGLINE.upper()}"), s["hero_kicker"])],
        [Paragraph("Forensic Image Analysis Report", s["hero_title"])],
        [Paragraph("An evidence-weighted assessment of one image file, with every proof "
                   "artifact attached", s["hero_sub"])],
    ], colWidths=[CONTENT_W])
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#3B1178")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10 * mm),
        ("TOPPADDING", (0, 0), (0, 0), 9 * mm),
        ("TOPPADDING", (0, 1), (-1, -1), 2.4 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, 1), 0),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 9 * mm),
    ]))
    story += [Spacer(1, 3 * mm), hero, Spacer(1, 6 * mm)]

    headline = str(narrative.get("headline") or result.get("explanation") or "")
    card = Table([
        [Paragraph(f'<font color="{colour_hex}">{_t(label)}</font>', s["verdict_big"]),
         Paragraph(f"{conf:.0%}", s["score_big"])],
        [Paragraph(_t(headline), s["verdict_note"]),
         Paragraph("confidence", s["score_note"])],
    ], colWidths=[CONTENT_W - 42 * mm, 42 * mm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tint_hex)),
        ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor(border_hex)),
        ("LINEBEFORE", (0, 0), (0, -1), 4, colour),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 7 * mm),
        ("LEFTPADDING", (1, 0), (1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [card, Spacer(1, 6 * mm)]

    detector_count = len(result.get("detectors") or [])
    facts = [
        ("Report reference", report_id or "n/a"),
        ("Report file", f"{base}-Forensic-Report.pdf"),
        ("Subject file", filename),
        ("Prepared for", str(meta.get("owner") or "registered user")),
        ("Analysis completed", _fmt_dt(created)),
        ("Processing time",
         f"{float(meta.get('processing_time_s') or result.get('processing_time_s') or 0):.2f} s"),
        ("Detector suite",
         f"PixelForensics v{settings.APP_VERSION} - {detector_count} classical detectors, no CNN"),
        ("Final score", f"{final:.1%} camera-likeness (below 45% = AI/manipulated, "
                        f"60% and above = real)"),
    ]
    story += [_kv_table(facts, s), Spacer(1, 6 * mm)]

    original_png = (_png_bytes(meta.get("image_path"), max_side=1100)
                    if meta.get("image_path") else None)
    cover_img = _flow_image(original_png, CONTENT_W - 28 * mm, 58 * mm)
    if cover_img is not None:
        cover_img.hAlign = "CENTER"
        story += [
            Paragraph("Exhibit A - the analysed frame", s["h3"]),
            Paragraph(_t(f"{filename}  |  {info.get('width')}x{info.get('height')} px  |  "
                         f"{float(info.get('size_bytes') or 0) / 1024:.1f} KB  |  "
                         f"format {info.get('format')}"), s["caption"]),
            Spacer(1, 2 * mm),
            cover_img,
            Spacer(1, 3 * mm),
        ]

    strip = Table([[
        Paragraph(f"<b>Digitally signed by {SITE_LABEL}</b><br/>{_t(sig['signature_id'])}",
                  s["cell"]),
        Paragraph(f"HMAC-SHA256<br/>issued {_t(_fmt_dt(generated))}<br/>"
                  f"tamper-evident digest", s["small"]),
    ]], colWidths=[CONTENT_W - 56 * mm, 56 * mm])
    strip.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT),
        ("BOX", (0, 0), (-1, -1), 0.7, ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [strip, PageBreak()]


    # ------------------------------------------------------ executive summary
    story.append(Paragraph("Executive summary", s["h2"]))
    if narrative.get("headline"):
        story.append(Paragraph(f"<b>{_t(narrative['headline'])}</b>", s["body"]))
    if narrative.get("summary"):
        story.append(Paragraph(_t(narrative["summary"]), s["body"]))

    metrics = Table([[
        [Paragraph(f'<font color="{colour_hex}">{_t(label.split(" / ")[0])}</font>',
                   s["verdict_big"]), Paragraph("verdict", s["small"])],
        [Paragraph(f"{final:.1%}", s["verdict_big"]), Paragraph("camera-likeness", s["small"])],
        [Paragraph(f"{conf:.0%}", s["verdict_big"]), Paragraph("confidence", s["small"])],
        [Paragraph(str(len(regions)), s["verdict_big"]),
         Paragraph("flagged regions", s["small"])],
    ]], colWidths=[CONTENT_W / 4] * 4)
    metrics.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [Spacer(1, 2 * mm), metrics, Spacer(1, 2 * mm)]

    # ------------------------------------------------------ narrative sections
    for section in narrative.get("sections") or []:
        title = str(section.get("title") or "").strip()
        body = str(section.get("body") or "").strip()
        if not body:
            continue
        story.append(Paragraph(_t(title), s["h2"]))
        story.append(Paragraph(_t(body), s["body"]))

    # ------------------------------------------------------ key findings table
    findings = narrative.get("key_findings") or []
    if findings:
        direction_meta = {
            "supports_camera": ("Supports camera", "#15803D"),
            "supports_ai": ("Supports synthetic", "#B91C1C"),
            "neutral": ("Neutral", "#B45309"),
        }
        rows = [[Paragraph(h, s["th"]) for h in ("Finding", "Direction", "Detail")]]
        for item in findings:
            text, hexc = direction_meta.get(item.get("direction"),
                                            ("Neutral", "#B45309"))
            rows.append([
                Paragraph(_t(item.get("title")), s["cell_b"]),
                Paragraph(f'<font color="{hexc}">{text}</font>', s["cell"]),
                Paragraph(_t(item.get("detail")), s["cell"]),
            ])
        table = Table(rows, colWidths=[42 * mm, 30 * mm, CONTENT_W - 72 * mm],
                      repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT_DARK),
            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL]),
        ]))
        story += [Paragraph("Key findings at a glance", s["h2"]), table]

    # ------------------------------------------------------ detector evidence
    if breakdown:
        story.append(Paragraph("Detector evidence", s["h2"]))
        story.append(Paragraph(_t(
            "Every applicable check is listed. Score is raw camera-likeness (higher = more "
            "camera-like); confidence is how sure the detector is of its own measurement; weight "
            "is its influence on the final score; evidence is the calibrated contribution after "
            "centring (-1 to +1). Rows are ordered by weight, not by how favourable they are."),
            s["body"]))
        rows = [[Paragraph(h, s["th"])
                 for h in ("Detector", "Score", "Conf.", "Weight", "Evidence",
                           "What the detector reported")]]
        for entry in sorted(breakdown, key=lambda x: -float(x.get("weight") or 0)):
            score = float(entry.get("score") or 0.0)
            hexc = "#15803D" if score > 0.6 else "#B91C1C" if score < 0.4 else "#B45309"
            rows.append([
                Paragraph(_t(entry.get("label") or entry.get("method")), s["cell_b"]),
                Paragraph(f'<font color="{hexc}"><b>{score:.0%}</b></font>', s["cell"]),
                Paragraph(f"{float(entry.get('confidence') or 0.0):.0%}", s["cell"]),
                Paragraph(f"{float(entry.get('weight') or 0.0):.0%}", s["cell"]),
                Paragraph(f"{float(entry.get('calibrated') or 0.0):+.2f}", s["cell"]),
                Paragraph(_t(entry.get("interpretation") or ""), s["cell"]),
            ])
        table = Table(rows, colWidths=[33 * mm, 12 * mm, 12 * mm, 13 * mm, 15 * mm,
                                       CONTENT_W - 85 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT_DARK),
            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 1), (4, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL]),
        ]))
        story += [table, Spacer(1, 3 * mm)]


    # ------------------------------------------------------------ exhibits
    story.append(PageBreak())
    story.append(Paragraph("Visual exhibits - the proof behind the scores", s["h2"]))
    story.append(Paragraph(_t(
        "Every exhibit below is generated from this exact file at analysis time. Captions say "
        "what the artifact shows and how to read it; nothing here is illustrative or stock."),
        s["body"]))

    analyzed_size = (int(info.get("width") or 0), int(info.get("height") or 0))
    residual_png = _b64_png(artifacts.get("residual_b64"))
    heatmap_png = _b64_png(artifacts.get("heatmap_b64"))
    ela_png = _b64_png(artifacts.get("ela_b64"))
    spectrum_png = _spectrum_png(artifacts.get("spectrum"))
    overlay_png = _overlay_regions(original_png, regions, analyzed_size)
    cell_w = (CONTENT_W - 6) / 2

    story.append(Paragraph("A. The frame and the flagged regions", s["h3"]))
    story.append(KeepTogether([_exhibit_row(
        _exhibit_cell(original_png, "Exhibit A - submitted frame",
                      f"The file as received ({info.get('width')} x {info.get('height')} px, "
                      f"{info.get('format')}). All measurements in this report were taken from "
                      f"this image.", s, cell_w),
        _exhibit_cell(overlay_png, "Exhibit B - flagged regions",
                      "Red boxes mark the areas whose local noise statistics differ most from "
                      "the rest of the frame. Pointers for review, not proof of editing.",
                      s, cell_w), s)]))

    story.append(Paragraph("B. Noise and local anomaly maps", s["h3"]))
    story.append(KeepTogether([_exhibit_row(
        _exhibit_cell(residual_png, "Exhibit C - noise residual",
                      "The high-frequency signal left after removing scene content. Natural "
                      "captures show fine, evenly spread grain; synthesis and denoising flatten "
                      "it.", s, cell_w),
        _exhibit_cell(heatmap_png, "Exhibit D - anomaly heatmap",
                      "Blue is consistent with the rest of the frame, red/yellow marks regions "
                      "that deviate. Look for tight clusters rather than broad smooth areas.",
                      s, cell_w), s)]))

    story.append(Paragraph("C. Compression and frequency evidence", s["h3"]))
    story.append(KeepTogether([_exhibit_row(
        _exhibit_cell(ela_png, "Exhibit E - error level analysis",
                      "Recompression error per region. Edited areas usually recompress "
                      "differently; uniform error suggests a single compression history. Only "
                      "meaningful for JPEG sources.", s, cell_w),
        _exhibit_cell(spectrum_png, "Exhibit F - frequency spectrum",
                      "Log-magnitude of the residual spectrum (inferno colour map). Smooth "
                      "radial falloff is camera-like; bright rings or spokes suggest periodic "
                      "artifacts from generation or resampling.", s, cell_w), s)]))


    wavelets = artifacts.get("wavelet") or {}
    if wavelets:
        tiles = []
        for key in ("LL", "LH", "HL", "HH"):
            tile = _flow_image(_b64_png(wavelets.get(key)), 38 * mm, 30 * mm)
            tiles.append([tile] if tile is not None
                         else [Paragraph(_t(f"{key} unavailable"), s["caption"])])
        grid = Table([tiles], colWidths=[CONTENT_W / 4] * 4)
        grid.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        wavelet_cell = [grid, Spacer(1, 3),
                        Paragraph("Exhibit G - wavelet sub-bands (LL / LH / HL / HH)", s["cell_b"]),
                        Paragraph(_t("Detail energy split by scale. LH/HL/HH carry the fine "
                                     "structure: an over-smooth HH with busy LL is typical of "
                                     "upscaled or generated content, while clean grain spreads "
                                     "energy naturally across all four bands."), s["caption"])]
        story.append(Paragraph("D. Multi-scale detail", s["h3"]))
        story.append(KeepTogether([_exhibit_row(wavelet_cell, None, s)]))

    # ------------------------------------------------------------ regions
    if regions:
        rows = [[Paragraph(h, s["th"]) for h in
                 ("#", "Position (x, y)", "Size (w x h)", "Why it was flagged")]]
        for region in regions:
            rows.append([
                Paragraph(_t(region.get("id")), s["cell_b"]),
                Paragraph(f"{region.get('x')}, {region.get('y')}", s["cell"]),
                Paragraph(f"{region.get('width')} x {region.get('height')}", s["cell"]),
                Paragraph(_t(region.get("reason")), s["cell"]),
            ])
        table = Table(rows, colWidths=[10 * mm, 34 * mm, 32 * mm, CONTENT_W - 76 * mm],
                      repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT_DARK),
            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL]),
        ]))
        story += [Paragraph("Suspicious regions", s["h2"]), table, Spacer(1, 2 * mm)]

    # ------------------------------------------------------------ metadata
    meta_info = (detectors.get("METADATA") or {}).get("details") or {}
    meta_rows = [
        ("File name", filename),
        ("Format / dimensions", f"{info.get('format')} - {info.get('width')} x {info.get('height')} px"),
        ("File size", f"{float(info.get('size_bytes') or 0) / 1024:.1f} KB"),
        ("Camera make", meta_info.get("make") or "not present"),
        ("Camera model", meta_info.get("model") or "not present"),
        ("Captured (EXIF)", meta_info.get("datetime") or "not present"),
        ("Software tag", meta_info.get("software") or "not present"),
        ("GPS", "present - withheld for privacy" if meta_info.get("has_gps") else "not present"),
    ]
    if profile:
        meta_rows += [
            ("Tone / palette", f"{profile.get('tone')} - {profile.get('colour_family')} - "
                               f"{profile.get('vividness')}"),
            ("Framing", f"{profile.get('framing')} ({profile.get('aspect_ratio')})"),
            ("Detail density", f"{profile.get('detail')} (edge coverage "
                               f"{float(profile.get('edge_density') or 0):.1%})"),
            ("Dominant colours", ", ".join(f"{c['name']} {c['hex']}"
                                           for c in (profile.get("dominant_colours") or [])[:3])
             or "n/a"),
        ]
    story += [Paragraph("File, metadata and visual profile", s["h2"]),
              _kv_table(meta_rows, s), Spacer(1, 2 * mm)]
    story.append(Paragraph(_t("Metadata can be stripped or forged, so it is used as supporting "
                              "context only and never as proof on its own."), s["small"]))


    # ------------------------------------------------------------ method notes
    story.append(Paragraph("Method notes and limitations", s["h2"]))
    chain = ("decode - resize to max 1024 px - generative-cue statistics - PRNU - noise residual - "
             "FFT - wavelet - ELA - JPEG structure - GLCM texture - EXIF - local noise consistency - "
             "weighted evidence aggregation")
    story.append(Paragraph(_t(
        f"Pipeline: {SITE_LABEL} v{settings.APP_VERSION}, algorithm version "
        f"{settings.FORENSIC_ALGORITHM_VERSION}. Chain: {chain}. All detectors are classical "
        f"digital image processing; no neural network is involved and no object recognition is "
       
        f"performed."), s["small"]))
    if breakdown:
        weights_txt = ", ".join(
            f"{b.get('label') or b.get('method')} {float(b.get('weight') or 0.0):.0%}"
            for b in sorted(breakdown, key=lambda x: -float(x.get("weight") or 0.0)))
        story.append(Paragraph(_t(
            f"Weights applied to this file: {weights_txt}. Checks that cannot apply to the source "
            f"format (for example ELA and JPEG structure on a PNG) are excluded from the weighted "
            f"average instead of being scored as zero, because a neutral vote would bias the "
            f"result."), s["small"]))
    story.append(Paragraph(_t(
        "Limitations: statistical evidence is not absolute proof. Recompression, resizing, "
        "screenshots and social-media processing destroy the sensor traces that several detectors "
        "depend on; metadata can be edited; and a determined generator can imitate camera noise. "
        "Confidence describes distance from the decision boundary, not the probability of "
        "manipulation. Use this report alongside provenance evidence and human review."), s["small"]))

    # ------------------------------------------------------------ signature
    story.append(PageBreak())
    story.append(Paragraph("Authenticity and digital signature", s["h2"]))
    story.append(Paragraph(_t(
        "Every report is signed at issuance. The signature is an HMAC-SHA256 digest over a "
        "canonical description of this report - its reference, subject file, verdict, scores, "
        "creation time and algorithm version. If any of those values were changed after issuance, "
        "the digest no longer matches the one held by the service, so the alteration is detectable."),
        s["body"]))

    sig_rows = [
        ("Issuer", f"{SITE_LABEL} - automated forensic reporting service"),
        ("Document", f"{base}-Forensic-Report.pdf"),
        ("Report reference", report_id or "n/a"),
        ("Subject file", filename),
        ("Issued at", _fmt_dt(generated)),
        ("Algorithm", "HMAC-SHA256 (secret-keyed) over the canonical payload"),
        ("Signature ID", sig["signature_id"]),
    ]
    story += [_kv_table(sig_rows, s, 38 * mm), Spacer(1, 4 * mm)]

    digest = sig["digest"]
    story.append(Paragraph("SHA-256 report digest", s["label"]))
    story.append(Paragraph("<br/>".join(_t(digest[i:i + 32]) for i in range(0, len(digest), 32)),
                           s["mono"]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Canonical signed payload", s["label"]))
    story.append(Paragraph(_t(sig["payload"]), s["mono"]))
    story.append(Spacer(1, 4 * mm))

    verify = Table([[Paragraph(
        f"<b>How to verify this copy.</b> Authenticate to the service and request "
        f"GET /api/report/{report_id}/signature. The digest returned there must equal the digest "
        f"printed above, character for character. A mismatch means the PDF, or the values quoted "
        f"in it, were altered after issuance - treat that copy as unauthentic.", s["cell"])]],
        colWidths=[CONTENT_W])
    verify.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT),
        ("BOX", (0, 0), (-1, -1), 0.8, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [verify, Spacer(1, 6 * mm)]

    story.append(Paragraph("Declaration", s["h3"]))
    story.append(Paragraph(_t(
        "This report was produced automatically from the uploaded file by the PixelForensics "
        "pipeline described above. It presents statistical evidence and a calibrated verdict; it is "
        "not a court certification and does not identify the device or the person who created the "
        "image. The signature identifies the issuing service, not an individual human examiner."),
        s["small"]))
    story.append(Spacer(1, 6 * mm))

    sign_off = Table([[
        Paragraph(f"<b>{SITE_LABEL}</b><br/>Automated forensic issuance<br/>{_t(_fmt_dt(generated))}",
                  s["cell"]),
        Paragraph(f"<b>{_t(sig['signature_id'])}</b><br/>"
                  f"<font color='#64748B'>HMAC-SHA256 - verify against "
                  f"/api/report/{_t(report_id[:8])}/signature</font>", s["small"]),
    ]], colWidths=[CONTENT_W * 0.45, CONTENT_W * 0.55])
    sign_off.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(sign_off)

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate, canvasmaker=_NumberedCanvas)
    return buf.getvalue()
