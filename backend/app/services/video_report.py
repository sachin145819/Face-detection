"""TruthLens video forensic PDF report. Shares styling / chrome with the image report (report.py)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from app.services import storage
from app.services.report import (
    CONTENT_W,
    LINE,
    MUTED,
    PANEL,
    VERDICT_COLORS,
    VERDICT_LABELS,
    ScoreBar,
    SignalBar,
    _build_pdf,
    _disclaimer_block,
    _f,
    _fmt_dt,
    _image_flowable,
    _pct,
    _section,
    _styles,
    _table,
    _txt,
)

SERIES = (
    ("suspicion", "Fused suspicion", colors.HexColor("#DC2626")),
    ("deepfake_probability", "Face deepfake probability", colors.HexColor("#F59E0B")),
    ("ai_generated_probability", "AI-generated probability", colors.HexColor("#7C3AED")),
)


def _opt_float(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _fmt_duration(sec: Any) -> str:
    s = _f(sec)
    if s <= 0:
        return "—"
    m, rem = divmod(s, 60)
    return f"{int(m)}:{rem:05.2f}" if m else f"{rem:.2f} s"


def _fmt_size(n: Any) -> str:
    b = _f(n)
    return f"{b / (1024 * 1024):.1f} MB" if b >= 1024 * 1024 else f"{b / 1024:.0f} KB"


def _frames(r: dict) -> list[dict]:
    return [f for f in (r.get("frames") or []) if isinstance(f, dict)]


def _timeline_chart(frames: list[dict], duration: float, width: float, height: float = 62 * mm):
    """Line chart of per-frame suspicion / deepfake / AI probability vs timestamp."""
    series = []
    for key, label, col in SERIES:
        pts = []
        for f in frames:
            t, y = _opt_float(f.get("timestamp_s")), _opt_float(f.get(key))
            if t is not None and y is not None:
                pts.append((t, max(0.0, min(1.0, y))))
        if pts:
            series.append((sorted(pts), label, col))
    if not series:
        return None

    d = Drawing(width, height)
    lp = LinePlot()
    lp.x, lp.y = 30, 34
    lp.width, lp.height = width - 40, height - 46
    lp.data = [s[0] for s in series]
    max_t = max(max(p[0] for p in s[0]) for s in series)
    x_max = max(duration, max_t, 0.001)
    lp.xValueAxis.valueMin = 0
    lp.xValueAxis.valueMax = x_max
    lp.xValueAxis.valueSteps = None
    lp.xValueAxis.labelTextFormat = lambda v: f"{v:.1f}s"
    lp.xValueAxis.labels.fontName = "Helvetica"
    lp.xValueAxis.labels.fontSize = 6.5
    lp.xValueAxis.labels.fillColor = MUTED
    lp.xValueAxis.strokeColor = LINE
    lp.yValueAxis.valueMin = 0
    lp.yValueAxis.valueMax = 1
    lp.yValueAxis.valueSteps = [0, 0.25, 0.5, 0.75, 1.0]
    lp.yValueAxis.labelTextFormat = lambda v: f"{v * 100:.0f}%"
    lp.yValueAxis.labels.fontName = "Helvetica"
    lp.yValueAxis.labels.fontSize = 6.5
    lp.yValueAxis.labels.fillColor = MUTED
    lp.yValueAxis.strokeColor = LINE
    lp.yValueAxis.visibleGrid = True
    lp.yValueAxis.gridStrokeColor = LINE
    lp.yValueAxis.gridStrokeWidth = 0.4
    for i, (_pts, _label, col) in enumerate(series):
        lp.lines[i].strokeColor = col
        lp.lines[i].strokeWidth = 1.6 if i == 0 else 1.1
        lp.lines[i].symbol = makeMarker("FilledCircle", size=2.6, fillColor=col, strokeColor=col)
    d.add(lp)

    legend = Legend()
    legend.x, legend.y = 30, 10
    legend.dx, legend.dy = 7, 7
    legend.fontName = "Helvetica"
    legend.fontSize = 7
    legend.alignment = "right"
    legend.columnMaximum = 1
    legend.deltax = 120
    legend.colorNamePairs = [(col, label) for _pts, label, col in series]
    d.add(legend)
    d.add(String(width - 4, height - 8, "0% = clean · 100% = suspicious", fontName="Helvetica", fontSize=6.5,
                 fillColor=MUTED, textAnchor="end"))
    return d


def generate_video_report_pdf(analysis, user, output_path: str) -> str:
    """Render the forensic report for a VideoAnalysis (ORM object with .video loaded) to PDF."""
    st = _styles()
    r: dict[str, Any] = analysis.result_json or {}
    video = analysis.video
    vinfo = r.get("video") if isinstance(r.get("video"), dict) else {}
    report_id = f"TLV-{analysis.id:06d}"
    now = datetime.now(timezone.utc)
    verdict = analysis.verdict
    vcolor = VERDICT_COLORS.get(verdict, MUTED)
    frames = _frames(r)
    story: list = []

    # ---- title block
    story.append(Paragraph("TruthLens Video Forensic Report",
                           ParagraphStyle("title", parent=st["body"], fontName="Helvetica-Bold",
                                          fontSize=22, leading=27, spaceAfter=2)))
    story.append(Paragraph("Video deepfake and AI-generation analysis across sampled frames", st["muted"]))
    story.append(Spacer(1, 5 * mm))

    meta_rows = [
        [Paragraph("REPORT ID", st["label"]), Paragraph(report_id, st["cellb"]),
         Paragraph("GENERATED", st["label"]), Paragraph(_fmt_dt(now), st["cell"])],
        [Paragraph("ANALYST", st["label"]), Paragraph(f"{_txt(user.name)} &lt;{_txt(user.email)}&gt;", st["cell"]),
         Paragraph("ANALYSED", st["label"]), Paragraph(_fmt_dt(analysis.created_at), st["cell"])],
        [Paragraph("FILE", st["label"]), Paragraph(_txt(video.original_filename, 80), st["cell"]),
         Paragraph("ANALYSIS ID", st["label"]), Paragraph(str(analysis.id), st["cell"])],
        [Paragraph("SHA-256", st["label"]),
         Paragraph(f"<font face='Courier' size='7'>{_txt(video.sha256)}</font>", st["cell"]), "", ""],
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

    # ---- verdict panel: video details | verdict + scores
    codec = vinfo.get("codec")
    fmt = vinfo.get("format")
    details = [
        ("Duration", _fmt_duration(video.duration_s or vinfo.get("duration_s"))),
        ("Resolution", f"{video.width}×{video.height} px"),
        ("Frame rate", f"{_f(video.fps or vinfo.get('fps')):.2f} fps"),
        ("Frames", str(video.frame_count or vinfo.get("frame_count") or "—")),
        ("Codec", _txt(codec) if codec else "—"),
        ("Container", _txt(fmt) if fmt else _txt(video.mime_type)),
        ("File size", _fmt_size(video.size_bytes)),
        ("Frames sampled", str(len(frames))),
        ("Frames with faces", str(r.get("faces_detected_frames", "—"))),
    ]
    tf_idx = (r.get("top_frames") or [None])[0]
    poster = None
    if isinstance(tf_idx, int) and not isinstance(tf_idx, bool) and 0 <= tf_idx < len(frames):
        poster = storage.existing(frames[tf_idx].get("thumbnail_path"))
    elif frames:
        poster = storage.existing(frames[0].get("thumbnail_path"))
    left: list = []
    pfl = _image_flowable(poster, 70 * mm, 45 * mm) if poster else None
    if pfl:
        left += [pfl, Paragraph("Most suspicious sampled frame", st["caption"]), Spacer(1, 3 * mm)]
    dt = Table([[Paragraph(k.upper(), st["label"]), Paragraph(v, st["cell"])] for k, v in details],
               colWidths=[36 * mm, 34 * mm])
    dt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                            ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    left.append(dt)

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
    story.append(Paragraph("Each signal reports a suspicion score from 0 (no evidence of manipulation) to 1 "
                           "(strong evidence), aggregated across the sampled frames. Unavailable signals are "
                           "excluded from the weighted verdict.", st["muted"]))
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

    # ---- suspicion over time
    story += _section("Suspicion over time", st)
    chart = _timeline_chart(frames, _f(video.duration_s or vinfo.get("duration_s")), CONTENT_W)
    if chart is not None:
        story.append(KeepTogether([chart, Paragraph(
            "Per-frame scores for evenly sampled frames. Gaps mean the value was unavailable for that frame "
            "(e.g. no face analysed).", st["muted"])]))
    else:
        story.append(Paragraph("No per-frame scores were reported.", st["muted"]))

    # ---- top suspicious frames
    top = [i for i in (r.get("top_frames") or [])
           if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(frames)][:4]
    if top:
        story += _section("Most suspicious frames", st)
        for rank, i in enumerate(top, 1):
            f = frames[i]
            thumb = storage.existing(f.get("thumbnail_path"))
            heat = storage.existing(f.get("heatmap_path"))
            boxes = [(fc.get("box", []), (220, 38, 38)) for fc in (f.get("faces") or []) if isinstance(fc, dict)]
            imgs, caps = [], []
            n = 2 if heat else 1
            cw = (CONTENT_W - 50 * mm) / n
            fl = _image_flowable(thumb, cw - 4 * mm, 55 * mm, boxes) if thumb else None
            imgs.append(fl or Paragraph("thumbnail unavailable", st["muted"]))
            caps.append(Paragraph("Frame", st["caption"]))
            if heat:
                hf = _image_flowable(heat, cw - 4 * mm, 55 * mm)
                imgs.append(hf or Paragraph("heatmap unavailable", st["muted"]))
                caps.append(Paragraph("Heatmap overlay", st["caption"]))
            pics = Table([imgs, caps], colWidths=[cw] * n)
            pics.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            info = [Paragraph(f"#{rank} · frame {_txt(f.get('index', i))}", st["cellb"]),
                    Paragraph(f"Time: {_f(f.get('timestamp_s')):.2f} s", st["cell"]),
                    Paragraph(f"Suspicion: <b>{_pct(f.get('suspicion'))}</b>", st["cell"]),
                    Paragraph(f"Deepfake: {_pct(f.get('deepfake_probability'))}", st["cell"]),
                    Paragraph(f"AI-generated: {_pct(f.get('ai_generated_probability'))}", st["cell"]),
                    Paragraph(f"Faces: {len(f.get('faces') or [])}", st["cell"])]
            t = Table([[info, pics]], colWidths=[50 * mm, CONTENT_W - 50 * mm])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                                   ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            story += [KeepTogether(t), Spacer(1, 3 * mm)]

    # ---- per-frame table
    story += _section("Per-frame results", st)
    if frames:
        rows = [[Paragraph(h, st["th"]) for h in ("#", "Time", "Suspicion", "Deepfake", "AI-generated", "Faces")]]
        for i, f in enumerate(frames[:200]):
            rows.append([Paragraph(_txt(f.get("index", i)), st["cell"]),
                         Paragraph(f"{_f(f.get('timestamp_s')):.2f} s", st["cell"]),
                         Paragraph(_pct(f.get("suspicion")), st["cellb"]),
                         Paragraph(_pct(f.get("deepfake_probability")), st["cell"]),
                         Paragraph(_pct(f.get("ai_generated_probability")), st["cell"]),
                         Paragraph(str(len(f.get("faces") or [])), st["cell"])])
        cw = CONTENT_W / 6
        story.append(_table(rows, [cw] * 6))
    else:
        story.append(Paragraph("No frames were analysed.", st["muted"]))

    # ---- metadata
    md = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
    story += _section("Container metadata", st)
    rows = [[Paragraph(h, st["th"]) for h in ("Field", "Value")]]
    rows.append([Paragraph("Encoder", st["cellb"]), Paragraph(_txt(md.get("encoder"), 200), st["cell"])])
    rows.append([Paragraph("Generator hint", st["cellb"]), Paragraph(_txt(md.get("generator_hint"), 200), st["cell"])])
    tags = md.get("tags") or {}
    if isinstance(tags, dict):
        for k, v in list(tags.items())[:40]:
            rows.append([Paragraph(_txt(k, 60), st["cellb"]), Paragraph(_txt(v, 160), st["cell"])])
        if len(tags) > 40:
            rows.append([Paragraph("…", st["cell"]), Paragraph(f"{len(tags) - 40} more tags omitted", st["muted"])])
    story.append(_table(rows, [45 * mm, CONTENT_W - 45 * mm]))
    mv = r.get("model_versions") or {}
    if isinstance(mv, dict) and mv:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Models: " + "; ".join(f"{_txt(k)}: {_txt(v or 'not loaded')}" for k, v in mv.items())
                               + f" · processing time {analysis.processing_ms} ms", st["muted"]))

    # ---- closing disclaimer
    story += _disclaimer_block(
        st,
        "TruthLens analyses a sample of video frames with machine-learning detectors; every score is a "
        "probability estimate that can be wrong, especially for heavily compressed, low-resolution or novel "
        "content. Classical image forensics are not applied to video frames because codecs destroy those traces. "
        "Findings should be weighed alongside provenance, context and expert review.",
    )
    return _build_pdf(story, output_path, report_id, title=f"TruthLens Video Forensic Report {report_id}",
                      subject="Video forensic analysis", subtitle="AI Video Forensics")
