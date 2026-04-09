# tools/pdf_exporter.py
# Genera reportes PDF de proyectos de ingeniería
# Incluye: esquemático SVG, componentes, firmware, decisiones de diseño, notas

import io
import os
from datetime import datetime
from typing import Optional

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Preformatted,
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Paleta Stratum
# ─────────────────────────────────────────────────────────────────────────────

COLOR_GREEN  = colors.HexColor("#a4ffb9")
COLOR_BLUE   = colors.HexColor("#00cbfe")
COLOR_DARK   = colors.HexColor("#0e0e0e")
COLOR_GRAY   = colors.HexColor("#494847")
COLOR_WHITE  = colors.white
COLOR_ACCENT = colors.HexColor("#8eff71")


def generate_project_pdf(
    circuit_id: int,
    include_firmware: bool = True,
    include_decisions: bool = True,
) -> bytes:
    """
    Genera un PDF del proyecto de ingeniería.
    Retorna bytes del PDF o lanza RuntimeError si reportlab no está instalado.
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError(
            "reportlab no está instalado. Ejecutá: pip install reportlab"
        )

    from database.circuit_design import CircuitDesignDB
    from database.design_decisions import get_decisions_db
    from database.hardware_memory import hardware_memory

    circuit_db = CircuitDesignDB()
    design = circuit_db.get_design(circuit_id)
    if not design:
        raise ValueError(f"Circuito ID {circuit_id} no encontrado")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
        title=f"Stratum — {design['name']}",
        author="Stratum Engineering Assistant",
    )

    styles = getSampleStyleSheet()
    style_normal = styles["Normal"]
    style_normal.fontName = "Courier"
    style_normal.fontSize = 9

    style_h1 = ParagraphStyle(
        "H1", parent=styles["Heading1"],
        fontSize=16, textColor=COLOR_DARK, spaceAfter=4,
    )
    style_h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=12, textColor=COLOR_DARK, spaceBefore=8, spaceAfter=4,
    )
    style_mono = ParagraphStyle(
        "Mono", parent=styles["Code"],
        fontName="Courier", fontSize=8,
        backColor=colors.HexColor("#f5f5f5"),
        leftIndent=4, rightIndent=4,
        spaceAfter=6,
    )
    style_label = ParagraphStyle(
        "Label", parent=styles["Normal"],
        fontSize=8, textColor=COLOR_GRAY,
    )

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("STRATUM // ENGINEERING REPORT", style_label))
    story.append(Paragraph(design["name"], style_h1))
    story.append(Paragraph(
        f"Generado: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | "
        f"Circuito ID: {circuit_id}",
        style_label,
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_GRAY))
    story.append(Spacer(1, 4*mm))

    # ── Descripción ───────────────────────────────────────────────────────────
    if design.get("description"):
        story.append(Paragraph("DESCRIPCIÓN", style_h2))
        story.append(Paragraph(design["description"], style_normal))
        story.append(Spacer(1, 4*mm))

    # ── Componentes ───────────────────────────────────────────────────────────
    components = design.get("components", [])
    if components:
        story.append(Paragraph(f"COMPONENTES ({len(components)})", style_h2))
        table_data = [["Ref", "Tipo", "Valor", "Package"]]
        for c in components:
            table_data.append([
                str(c.get("ref", c.get("id", ""))),
                str(c.get("type", c.get("description", ""))),
                str(c.get("value", "")),
                str(c.get("footprint", "")),
            ])
        t = Table(table_data, colWidths=[25*mm, 55*mm, 40*mm, 40*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), COLOR_DARK),
            ("TEXTCOLOR",    (0, 0), (-1, 0), COLOR_GREEN),
            ("FONTNAME",     (0, 0), (-1, 0), "Courier-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 8),
            ("FONTNAME",     (0, 1), (-1, -1), "Courier"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, colors.HexColor("#f9f9f9")]),
            ("GRID",         (0, 0), (-1, -1), 0.5, COLOR_GRAY),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ]))
        story.append(t)
        story.append(Spacer(1, 4*mm))

    # ── Redes ─────────────────────────────────────────────────────────────────
    nets = design.get("nets", [])
    if nets:
        story.append(Paragraph(f"REDES / NETS ({len(nets)})", style_h2))
        net_lines = []
        for n in nets:
            conns = ", ".join(n.get("connections", n.get("pins", [])))
            net_lines.append(f"{n.get('name', '?')}: {conns}" if conns else n.get("name", "?"))
        story.append(Preformatted("\n".join(net_lines), style_mono))
        story.append(Spacer(1, 4*mm))

    # ── Firmware ──────────────────────────────────────────────────────────────
    if include_firmware:
        device_name = design["name"].lower().replace(" ", "_")
        firmware_hist = hardware_memory.get_firmware_history(device_name, limit=1)
        if firmware_hist:
            fw = firmware_hist[0]
            story.append(Paragraph("FIRMWARE", style_h2))
            story.append(Paragraph(
                f"Tarea: {fw.get('task', '')} | "
                f"Fecha: {fw.get('timestamp', '')} | "
                f"Estado: {'OK' if fw.get('success') else 'ERROR'}",
                style_label,
            ))
            code = fw.get("code", "")
            if code:
                story.append(Preformatted(code[:1500], style_mono))
            story.append(Spacer(1, 4*mm))

    # ── Decisiones de diseño ─────────────────────────────────────────────────
    if include_decisions:
        decisions_db = get_decisions_db()
        decisions = decisions_db.get_by_project(design["name"])
        if not decisions:
            decisions = decisions_db.get_all(limit=10)

        if decisions:
            story.append(Paragraph(f"DECISIONES DE DISEÑO ({len(decisions)})", style_h2))
            for d in decisions:
                story.append(Paragraph(
                    f"<b>{d.get('component') or 'General'}</b> — {d.get('decision', '')}",
                    style_normal,
                ))
                story.append(Paragraph(d.get("reasoning", ""), style_normal))
                story.append(Paragraph(
                    f"Proyecto: {d.get('project', '')} | {d.get('created_at', '')[:10]}",
                    style_label,
                ))
                story.append(Spacer(1, 2*mm))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_GRAY))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "Generado por Stratum — Engineering Memory Engine",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7, textColor=COLOR_GRAY, alignment=TA_CENTER),
    ))

    doc.build(story)
    return buf.getvalue()
