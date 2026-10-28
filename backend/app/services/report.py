"""TruthLens forensic PDF report (ReportLab / platypus)."""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from PIL import ImageDraw
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    Image as RLImage,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services import storage

DISCLAIMER = "Probabilistic evidence, corroborated by human review — never a substitute for it."

# ---- palette ----
INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
PANEL = colors.HexColor("#F8FAFC")
BRAND = colors.HexColor("#4F46E5")
VERDICT_COLORS = {
    "authentic": colors.HexColor("#16A34A"),
    "manipulated": colors.HexColor("#D97706"),
    "deepfake": colors.HexColor("#DC2626"),
    "ai_generated": colors.HexColor("#7C3AED"),
}
VERDICT_LABELS = {
    "authentic": "Likely Authentic",
    "manipulated": "Likely Manipulated",
    "deepfake": "Likely Deepfake",
    "ai_generated": "Likely AI-Generated",
}

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


# ---------------------------------------------------------------- helpers
def _txt(v: Any, limit: int = 300) -> str:
    """Stringify, truncate, XML-escape and keep it renderable in the base-14 fonts."""
    if v is None:
        s = "—"
    elif isinstance(v, float):
        s = f"{v:.4g}"
    elif isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False, default=str)
    elif isinstance(v, bytes):
        s = f"<{len(v)} bytes>"
    else:
        s = str(v)
    s = "".join(ch if ch.isprintable() else " " for ch in s).strip()
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    # Characters outside cp1252 cannot be drawn by Helvetica; replace them.
    s = s.encode("cp1252", errors="replace").decode("cp1252")
    return escape(s)


def _f(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _fmt_dt(dt: datetime | None) -> str:
    return _aware(dt).strftime("%Y-%m-%d %H:%M UTC") if dt else "—"


def _pct(v: Any) -> str:
    try:
        return f"{float(v) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def _image_flowable(path: Path | str | bytes | None, max_w: float, max_h: float,
                    boxes: Iterable[tuple[list, tuple]] = ()) -> RLImage | None:
    """Load an image with Pillow (so WebP works), optionally draw boxes, scale to fit."""
    if path is None:
        return None
    try:
        src = io.BytesIO(path) if isinstance(path, bytes) else path
        with PILImage.open(src) as im:
            im = im.convert("RGB")
            boxes = list(boxes)
            if boxes:
                draw = ImageDraw.Draw(im)
                lw = max(2, round(min(im.size) / 200))
                for box, rgb in boxes:
                    try:
                        x, y, w, h = (float(b) for b in box[:4])
                    except (TypeError, ValueError):
                        continue
                    draw.rectangle([x, y, x + w, y + h], outline=rgb, width=lw)
            im.thumbnail((1400, 1400))
            buf = io.BytesIO()
            im.save(buf, "PNG")
            w, h = im.size
    except Exception:
        return None
    buf.seek(0)
    scale = min(max_w / w, max_h / h)
    return RLImage(buf, width=w * scale, height=h * scale)


class ScoreBar(Flowable):
    """Horizontal 0–100 authenticity bar with a marker."""

    def __init__(self, score: float, width: float, height: float = 9):
        super().__init__()
        self.score = max(0.0, min(100.0, float(score)))
        self.width = width
        self.height = height + 10

    def draw(self) -> None:
        c = self.canv
        h = self.height - 10
        segs = [(0.0, 0.35, "#DC2626"), (0.35, 0.65, "#F59E0B"), (0.65, 1.0, "#16A34A")]
        for a, b, col in segs:
            c.setFillColor(colors.HexColor(col))
            c.rect(a * self.width, 10, (b - a) * self.width, h, stroke=0, fill=1)
        x = self.score / 100 * self.width
        c.setFillColor(INK)
        c.setStrokeColor(colors.white)
        c.setLineWidth(1.2)
        p = c.beginPath()
        p.moveTo(x, 10 + h + 1)
        p.lineTo(x - 4, 10 + h + 8)
        p.lineTo(x + 4, 10 + h + 8)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        c.drawString(0, 1, "0 · fabricated")
        c.drawRightString(self.width, 1, "100 · authentic")


class SignalBar(Flowable):
    """Small suspicion bar (0 = clean, 1 = suspicious)."""

    def __init__(self, score: Any, available: bool, width: float = 22 * mm, height: float = 5):
        super().__init__()
        try:
            self.score = max(0.0, min(1.0, float(score)))
        except (TypeError, ValueError):
            self.score = 0.0
        self.available = available
        self.width, self.height = width, height

    def draw(self) -> None:
        c = self.canv
        c.setFillColor(LINE)
        c.roundRect(0, 0, self.width, self.height, 2, stroke=0, fill=1)
        if not self.available:
            return
        col = "#16A34A" if self.score < 0.35 else ("#F59E0B" if self.score < 0.65 else "#DC2626")
        c.setFillColor(colors.HexColor(col))
        c.roundRect(0, 0, max(2, self.width * self.score), self.height, 2, stroke=0, fill=1)


# ---------------------------------------------------------------- styles
def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    s: dict[str, ParagraphStyle] = {}
    s["body"] = ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5,
                               leading=13.5, textColor=INK)
    s["small"] = ParagraphStyle("small", parent=s["body"], fontSize=7.8, leading=10)
    s["muted"] = ParagraphStyle("muted", parent=s["small"], textColor=MUTED)
    s["cell"] = ParagraphStyle("cell", parent=s["body"], fontSize=8, leading=10)
    s["cellb"] = ParagraphStyle("cellb", parent=s["cell"], fontName="Helvetica-Bold")
    s["th"] = ParagraphStyle("th", parent=s["cell"], fontName="Helvetica-Bold", textColor=colors.white)
    s["h2"] = ParagraphStyle("h2", parent=s["body"], fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                             textColor=INK, spaceBefore=10, spaceAfter=5)
    s["label"] = ParagraphStyle("label", parent=s["small"], textColor=MUTED, fontName="Helvetica-Bold")
    s["big"] = ParagraphStyle("big", parent=s["body"], fontName="Helvetica-Bold", fontSize=26, leading=30)
    s["verdict"] = ParagraphStyle("verdict", parent=s["body"], fontName="Helvetica-Bold", fontSize=15,
                                  leading=19, textColor=colors.white, alignment=TA_CENTER)
    s["caption"] = ParagraphStyle("caption", parent=s["muted"], alignment=TA_CENTER)
    s["left"] = ParagraphStyle("left", parent=s["body"], alignment=TA_LEFT)
    return s


def _section(title: str, st) -> list:
    return [CondPageBreak(30 * mm), Paragraph(escape(title), st["h2"])]


def _table(rows: list[list], col_widths: list[float], header: bool = True, zebra: bool = True) -> Table:
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
    ]
    if header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), INK)]
    if zebra:
        start = 1 if header else 0
        for i in range(start, len(rows)):
            if (i - start) % 2 == 1:
                cmds.append(("BACKGROUND", (0, i), (-1, i), PANEL))
    t.setStyle(TableStyle(cmds))
    return t


# ---------------------------------------------------------------- page chrome
def _make_page_cb(report_id: str, subtitle: str = "AI Image Forensics"):
    def on_page(canvas, doc):
        canvas.saveState()
        # header band
        canvas.setFillColor(INK)
        canvas.rect(0, PAGE_H - 14 * mm, PAGE_W, 14 * mm, stroke=0, fill=1)
        canvas.setFillColor(BRAND)
        canvas.rect(0, PAGE_H - 14 * mm, 4 * mm, 14 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(MARGIN, PAGE_H - 9 * mm, "TruthLens")
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(colors.HexColor("#CBD5E1"))
        canvas.drawString(MARGIN + canvas.stringWidth("TruthLens", "Helvetica-Bold", 11) + 3 * mm,
                          PAGE_H - 9 * mm, subtitle)
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 9 * mm, f"Report {report_id}")
        # footer
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
        canvas.setFont("Helvetica-Oblique", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 9.5 * mm, DISCLAIMER)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(PAGE_W - MARGIN, 9.5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return on_page


def _disclaimer_block(st, body: str) -> list:
    disc = Table([[Paragraph(f"<b>Disclaimer.</b> {escape(DISCLAIMER)} {body}", st["small"])]],
                 colWidths=[CONTENT_W])
    disc.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                              ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                              ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    return [Spacer(1, 6 * mm), KeepTogether(disc)]


def _build_pdf(story: list, output_path: str, report_id: str, title: str, subject: str,
               subtitle: str = "AI Image Forensics") -> str:
    """Render `story` atomically (tmp file + rename) with the shared header/footer chrome."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".pdf.tmp")
    doc = SimpleDocTemplate(
        str(tmp), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=22 * mm, bottomMargin=20 * mm,
        title=title, author="TruthLens", subject=subject,
    )
    cb = _make_page_cb(report_id, subtitle)
    try:
        doc.build(story, onFirstPage=cb, onLaterPages=cb)
        tmp.replace(out)
    finally:
        if tmp.exists():
            tmp.unlink()
    return str(out)


# ---------------------------------------------------------------- main
def generate_report_pdf(analysis, user, output_path: str) -> str:
    """Render the forensic report for `analysis` (ORM object, image/restorations loaded) to PDF."""
    st = _styles()
    r: dict[str, Any] = analysis.result_json or {}
    img = analysis.image
    report_id = f"TL-{analysis.id:06d}"
    now = datetime.now(timezone.utc)
    verdict = analysis.verdict
    vcolor = VERDICT_COLORS.get(verdict, MUTED)
    story: list = []

    # ---- title block
    story.append(Paragraph("TruthLens Forensic Report",
                           ParagraphStyle("title", parent=st["body"], fontName="Helvetica-Bold",
                                          fontSize=22, leading=27, spaceAfter=2)))
    story.append(Paragraph("Image authenticity, deepfake and manipulation analysis", st["muted"]))
    story.append(Spacer(1, 5 * mm))

    meta_rows = [
        [Paragraph("REPORT ID", st["label"]), Paragraph(report_id, st["cellb"]),
         Paragraph("GENERATED", st["label"]), Paragraph(_fmt_dt(now), st["cell"])],
        [Paragraph("ANALYST", st["label"]), Paragraph(f"{_txt(user.name)} &lt;{_txt(user.email)}&gt;", st["cell"]),
         Paragraph("ANALYSED", st["label"]), Paragraph(_fmt_dt(analysis.created_at), st["cell"])],
        [Paragraph("FILE", st["label"]), Paragraph(_txt(img.original_filename, 80), st["cell"]),
         Paragraph("ANALYSIS ID", st["label"]), Paragraph(str(analysis.id), st["cell"])],
        [Paragraph("SHA-256", st["label"]),
         Paragraph(f"<font face='Courier' size='7'>{_txt(img.sha256)}</font>", st["cell"]), "", ""],
    ]
    mt = Table(meta_rows, colWidths=[24 * mm, 68 * mm, 26 * mm, CONTENT_W - 118 * mm])
    mt.setStyle(TableStyle([
        ("SPAN", (1, 3), (3, 3)),
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    story += [mt, Spacer(1, 6 * mm)]

    # ---- verdict panel: thumbnail | verdict + scores
    boxes = [(reg.get("box", []), (245, 158, 11)) for reg in (r.get("regions") or []) if isinstance(reg, dict)]
    boxes += [(f.get("box", []), (220, 38, 38)) for f in (r.get("faces") or []) if isinstance(f, dict)]
    thumb = _image_flowable(storage.upload_path(img.stored_filename), 70 * mm, 70 * mm, boxes)
    left = [thumb or Paragraph("Image unavailable", st["muted"]),
            Spacer(1, 2),
            Paragraph(f"{img.width}×{img.height} px · {_txt(img.mime_type)} · {img.size_bytes / 1024:.0f} KB",
                      st["caption"])]
    if boxes:
        left.append(Paragraph("<font name='ZapfDingbats' color='#F59E0B'>n</font> suspicious region &nbsp; "
                              "<font name='ZapfDingbats' color='#DC2626'>n</font> detected face", st["caption"]))

    right_w = CONTENT_W - 76 * mm
    vbadge = Table([[Paragraph(escape(VERDICT_LABELS.get(verdict, verdict.replace("_", " ").title())),
                               st["verdict"])]], colWidths=[right_w])
    vbadge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), vcolor),
                                ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    score_tbl = Table([
        [Paragraph("AUTHENTICITY SCORE", st["label"]), Paragraph("CONFIDENCE", st["label"])],
        [Paragraph(f"{analysis.authenticity_score:.0f}<font size='11' color='#64748B'> / 100</font>", st["big"]),
         Paragraph(f"{_pct(analysis.confidence)}", st["big"])],
    ], colWidths=[right_w * 0.55, right_w * 0.45])
    score_tbl.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    right = [vbadge, Spacer(1, 4 * mm), score_tbl, Spacer(1, 2 * mm), ScoreBar(analysis.authenticity_score, right_w),
             Spacer(1, 4 * mm),
             Paragraph("SUMMARY", st["label"]),
             Paragraph(_txt(r.get("summary"), 1200), st["body"]),
             Spacer(1, 3 * mm)]
    if r.get("uncertainty_note"):
        note = Table([[Paragraph(f"<b>Uncertainty.</b> {_txt(r.get('uncertainty_note'), 1200)}", st["small"])]],
                     colWidths=[right_w])
        note.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFBEB")),
                                  ("LINEBEFORE", (0, 0), (0, -1), 2.5, colors.HexColor("#F59E0B")),
                                  ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        right.append(note)
    panel = Table([[left, right]], colWidths=[76 * mm, right_w])
    panel.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 6 * mm)]))
    story.append(panel)

    # ---- signals
    signals = [s for s in (r.get("signals") or []) if isinstance(s, dict)]
    story += _section("Forensic signals", st)
    story.append(Paragraph("Each signal reports a suspicion score from 0 (no evidence of tampering) to 1 "
                           "(strong evidence). Unavailable signals are excluded from the weighted verdict.",
                           st["muted"]))
    story.append(Spacer(1, 2 * mm))
    if signals:
        rows = [[Paragraph(h, st["th"]) for h in ("Signal", "Suspicion", "Weight", "Status", "Explanation")]]
        for s in signals:
            avail = bool(s.get("available"))
            rows.append([
                Paragraph(_txt(s.get("label") or s.get("key"), 60), st["cellb"]),
                [Paragraph(f"{_f(s.get('score')):.2f}" if avail else "—", st["cell"]), Spacer(1, 2),
                 SignalBar(s.get("score"), avail, width=20 * mm)],
                Paragraph(f"{_f(s.get('weight')):.2f}" if avail else "—", st["cell"]),
                Paragraph("<font color='#16A34A'>available</font>" if avail
                          else "<font color='#94A3B8'>unavailable</font>", st["cell"]),
                Paragraph(_txt(s.get("explanation"), 500), st["cell"]),
            ])
        story.append(_table(rows, [32 * mm, 26 * mm, 15 * mm, 20 * mm, CONTENT_W - 93 * mm]))
    else:
        story.append(Paragraph("No signals were reported.", st["muted"]))

    # ---- faces
    faces = [f for f in (r.get("faces") or []) if isinstance(f, dict)]
    story += _section("Faces", st)
    if faces:
        rows = [[Paragraph(h, st["th"]) for h in ("#", "Box (x, y, w, h)", "Deepfake probability")]]
        for i, f in enumerate(faces, 1):
            rows.append([Paragraph(str(i), st["cell"]),
                         Paragraph(_txt(", ".join(str(int(round(_f(b)))) for b in (f.get("box") or [])[:4])),
                                   st["cell"]),
                         Paragraph(_pct(f.get("deepfake_probability")), st["cellb"])])
        story.append(_table(rows, [12 * mm, 70 * mm, CONTENT_W - 82 * mm]))
    else:
        story.append(Paragraph("No faces were detected in this image.", st["muted"]))

    # ---- explainability images
    heat = storage.existing(analysis.heatmap_path)
    ela = storage.existing(analysis.ela_path)
    if heat or ela:
        story += _section("Explainability", st)
        cells, caps = [], []
        n = (1 if heat else 0) + (1 if ela else 0)
        cw = CONTENT_W / n
        for p, cap in ((heat, "Suspicion heatmap overlay"), (ela, "Error Level Analysis (ELA)")):
            if p:
                fl = _image_flowable(p, cw - 6 * mm, 85 * mm)
                cells.append(fl or Paragraph("unavailable", st["muted"]))
                caps.append(Paragraph(cap, st["caption"]))
        t = Table([cells, caps], colWidths=[cw] * n)
        t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(KeepTogether(t))

    # ---- metadata
    md = r.get("metadata") or {}
    story += _section("Metadata & EXIF", st)
    rows = [[Paragraph(h, st["th"]) for h in ("Field", "Value")]]
    for k in ("format", "width", "height", "software"):
        if k in md:
            rows.append([Paragraph(k.title(), st["cellb"]), Paragraph(_txt(md.get(k), 200), st["cell"])])
    exif = md.get("exif") or {}
    if isinstance(exif, dict):
        for k, v in list(exif.items())[:60]:
            rows.append([Paragraph(_txt(k, 60), st["cellb"]), Paragraph(_txt(v, 160), st["cell"])])
        if len(exif) > 60:
            rows.append([Paragraph("…", st["cell"]), Paragraph(f"{len(exif) - 60} more EXIF fields omitted", st["muted"])])
    if not exif:
        rows.append([Paragraph("EXIF", st["cellb"]),
                     Paragraph("No EXIF metadata present (common for screenshots, edited, re-encoded or "
                               "AI-generated images).", st["cell"])])
    story.append(_table(rows, [45 * mm, CONTENT_W - 45 * mm]))
    mv = r.get("model_versions") or {}
    if isinstance(mv, dict) and mv:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Models: " + "; ".join(f"{_txt(k)}: {_txt(v or 'not loaded')}" for k, v in mv.items())
                               + f" · processing time {analysis.processing_ms} ms", st["muted"]))

    # ---- restorations
    rests = list(analysis.restorations or [])
    if rests:
        story += _section("AI restorations", st)
        story.append(Paragraph("<b>Restored images are AI reconstructions, not original evidence.</b> They are "
                               "included for illustration only and must not be used as proof of the original "
                               "content.", st["small"]))
        story.append(Spacer(1, 2 * mm))
        for rs in rests:
            fl = _image_flowable(storage.existing(rs.restored_path), 80 * mm, 70 * mm)
            info = [Paragraph(f"Restoration #{rs.id}", st["cellb"]),
                    Paragraph(f"Method: {_txt(rs.method)}", st["cell"]),
                    Paragraph(f"Created: {_fmt_dt(rs.created_at)}", st["cell"]),
                    Paragraph(_txt(rs.note, 300), st["muted"])]
            t = Table([[fl or Paragraph("file unavailable", st["muted"]), info]],
                      colWidths=[86 * mm, CONTENT_W - 86 * mm])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                                   ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            story += [KeepTogether(t), Spacer(1, 3 * mm)]

    # ---- closing disclaimer
    story += _disclaimer_block(
        st,
        "TruthLens combines classical image forensics with machine-learning "
        "detectors; every score is a probability estimate that can be wrong, especially for heavily compressed, "
        "resized or novel content. Findings should be weighed alongside provenance, context and expert review.",
    )
    return _build_pdf(story, output_path, report_id, title=f"TruthLens Forensic Report {report_id}",
                      subject="Image forensic analysis")
