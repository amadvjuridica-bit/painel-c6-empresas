import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
NAVY = colors.HexColor("#25284F")
GOLD = colors.HexColor("#B89455")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#657084")
LINE = colors.HexColor("#D9DEE8")
SOFT = colors.HexColor("#F7F8FB")
BLUE = colors.HexColor("#285F9F")
WHITE = colors.white


def load_payload():
    text = (WEB / "data.js").read_text(encoding="utf-8")
    match = re.search(r"window\.C6_DASHBOARD_DATA\s*=\s*(.*);\s*$", text, re.S)
    return json.loads(match.group(1))


def fmt(n):
    return f"{int(n or 0):,}".replace(",", ".")


def pct(n):
    return f"{float(n or 0):.1f}%".replace(".", ",")


def date_pt(value):
    if not value:
        return "-"
    y, m, d = value.split("-")
    return f"{d}/{m}/{y}"


def date_time_pt(value):
    if not value:
        return "-"
    return datetime.fromisoformat(value).strftime("%d/%m/%Y às %H:%M")


def month_pt(value):
    y, m = value.split("-")
    names = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    return f"{names[int(m) - 1]}/{y}"


def week_name(row):
    return row.get("label") or f"{date_pt(row.get('startDate'))} a {date_pt(row.get('endDate'))}"


def ref_stamp(value):
    return (value or "").replace("-", "")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(1.4 * cm, 1.15 * cm, 28.3 * cm, 1.15 * cm)
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(1.4 * cm, 0.88 * cm, "CONFIDENCIAL")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(14.85 * cm, 0.88 * cm, "Todos os direitos reservados à Assis & Mollerke")
    canvas.drawRightString(28.2 * cm, 0.88 * cm, f"Página {doc.page}")
    canvas.restoreState()


def table(data, widths, font_size=7.2):
    tbl = Table(data, colWidths=widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("GRID", (0, 0), (-1, -1), 0.25, LINE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return tbl


def cards(items):
    cells = []
    style = ParagraphStyle("Card", alignment=TA_CENTER, leading=16)
    empty = Paragraph("", style)
    for title, value, sub in items:
        cells.append(
            Paragraph(
                f'<font color="#657084" size="7">{title}</font><br/>'
                f'<font color="#25284F" size="18"><b>{value}</b></font><br/>'
                f'<font color="#657084" size="7">{sub}</font>',
                style,
            )
        )
    while len(cells) % 4:
        cells.append(empty)
    rows = [cells[i : i + 4] for i in range(0, len(cells), 4)]
    tbl = Table(rows, colWidths=[6.55 * cm] * 4)
    tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 13),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 13),
            ]
        )
    )
    return tbl


def line_chart(rows):
    width, height = 720, 190
    d = Drawing(width, height)
    x0, y0, w, h = 45, 35, 640, 120
    d.add(Line(x0, y0, x0 + w, y0, strokeColor=LINE))
    d.add(Line(x0, y0, x0, y0 + h, strokeColor=LINE))
    max_val = max(1, *[max(r["indicated"], r["opened"]) for r in rows])

    def points(key):
        pts = []
        for i, r in enumerate(rows):
            x = x0 + (w / max(len(rows) - 1, 1)) * i
            y = y0 + (r[key] / max_val) * h
            pts.extend([x, y])
        return pts

    d.add(PolyLine(points("indicated"), strokeColor=BLUE, strokeWidth=2.2))
    d.add(PolyLine(points("opened"), strokeColor=GOLD, strokeWidth=2.2))
    for i, r in enumerate(rows):
        x = x0 + (w / max(len(rows) - 1, 1)) * i
        d.add(String(x, 16, r["date"][8:], fontSize=7, fillColor=MUTED, textAnchor="middle"))
    d.add(String(x0, height - 18, "Leads enviados", fontSize=8, fillColor=BLUE))
    d.add(String(x0 + 120, height - 18, "Contas convertidas", fontSize=8, fillColor=GOLD))
    return d


def hour_chart(hours):
    width, height = 720, 205
    d = Drawing(width, height)
    ranked = sorted([h for h in hours if h["interactions"]], key=lambda h: h["interactions"], reverse=True)[:8]
    max_val = max(1, *[h["interactions"] for h in ranked])
    y = height - 28
    for idx, h in enumerate(ranked, 1):
        bar_w = (h["interactions"] / max_val) * 470
        d.add(String(18, y + 2, str(idx), fontSize=8, fillColor=NAVY))
        d.add(String(45, y + 2, h["hour"], fontSize=8, fillColor=INK))
        d.add(Rect(95, y, 470, 9, fillColor=SOFT, strokeColor=LINE, strokeWidth=0.2))
        d.add(Rect(95, y, bar_w, 9, fillColor=GOLD, strokeColor=GOLD, strokeWidth=0))
        d.add(String(585, y + 2, f"{fmt(h['interactions'])} interessados", fontSize=8, fillColor=INK))
        y -= 21
    return d


def build_pdf():
    payload = load_payload()
    month = payload["months"][-1]
    daily = [r for r in payload["daily"] if r["month"] == month]
    selected = daily[-1]
    monthly = next(r for r in payload["monthly"] if r["period"] == month)
    foundation = [a for a in payload.get("foundationMonths", []) if a["month"] == month]
    monthly_interest = (monthly["interactions"] / monthly["positiveSent"] * 100) if monthly.get("positiveSent") else 0
    output = WEB / "relatorio_c6_empresas_v2.pdf"

    doc = SimpleDocTemplate(
        str(output),
        pagesize=landscape(A4),
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.4 * cm,
        title="Relatório C6 Empresas V2 - Assis & Mollerke",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("V2Title", parent=styles["Title"], textColor=NAVY, fontSize=19, leading=23, alignment=TA_LEFT))
    styles.add(ParagraphStyle("V2Sub", parent=styles["Normal"], textColor=MUTED, fontSize=9, leading=12, alignment=TA_LEFT))
    styles.add(ParagraphStyle("V2Section", parent=styles["Heading2"], textColor=NAVY, fontSize=14, leading=17, spaceBefore=9, spaceAfter=6))
    styles.add(ParagraphStyle("V2Body", parent=styles["Normal"], textColor=INK, fontSize=9, leading=12, alignment=TA_LEFT))

    story = []
    logo = WEB / "assets" / "logo.png"
    logo_flow = Image(str(logo), width=4.2 * cm, height=2.58 * cm) if logo.exists() else Paragraph("Assis & Mollerke", styles["V2Sub"])
    header = Table(
        [
            [
                [
                    Paragraph(f"Painel Diário de Campanhas WhatsApp - {date_pt(selected['date'])}", styles["V2Title"]),
                    Paragraph(
                        f"C6 Empresas | Assis & Mollerke<br/>"
                        f"Dia de referência: {date_pt(selected['date'])} | "
                        f"Referência: {month_pt(month)} | Última importação: {date_time_pt(payload.get('lastImportAt') or payload.get('generatedAt'))}",
                        styles["V2Sub"],
                    ),
                ],
                logo_flow,
            ]
        ],
        colWidths=[20.4 * cm, 5.8 * cm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    story.append(header)
    story.append(Spacer(1, 0.12 * cm))

    story.append(
        cards(
            [
                ("Envios", fmt(selected["sent"]), f"Mês: {fmt(monthly['sent'])}"),
                ("Envios contas abertas", fmt(selected["qualificationSent"]), f"{pct(selected['qualificationRate'])} dos envios"),
                ("Envios positivos", fmt(selected["positiveSent"]), f"{pct(selected['positiveRate'])} no dia"),
                ("Interações totais", fmt(selected["buttonInteractions"]), f"{pct(selected['buttonInteractionRate'])} dos positivos"),
                ("Contatos interessados", fmt(selected["interactions"]), f"{pct(selected['interactionRate'])} dos positivos"),
                ("Leads enviados", fmt(selected["indicated"]), f"{pct(selected['indicationRate'])} dos interessados"),
                ("Contas convertidas", fmt(selected["opened"]), f"{pct(selected['openingRate'])} dos leads"),
                ("Abertas no período", fmt(selected["openedInPeriod"]), "pela data da abertura"),
                ("Pix conv.", fmt(selected["pixOpen"]), f"{pct(selected['pixRate'])} das convertidas"),
                ("Pix abertas", fmt(selected["pixOpenInPeriod"]), f"{pct(selected['pixInPeriodRate'])} das abertas"),
                ("% conversão mês", pct(monthly["openingRate"]), f"{fmt(monthly['opened'])} conversões"),
            ]
        )
    )

    story.append(Paragraph("Resumo executivo", styles["V2Section"]))
    story.append(
        Paragraph(
            f"O painel consolida a evolução diária das campanhas de WhatsApp do C6 Empresas. Na data de referência, "
            f"também foram realizados {fmt(selected['qualificationSent'])} envios para clientes com conta aberta. "
            f"Foram apuradas {fmt(selected['buttonInteractions'])} interações totais, equivalentes a "
            f"{pct(selected['buttonInteractionRate'])} dos envios positivos. Desse volume, "
            f"{fmt(selected['interactions'])} corresponderam a contatos interessados. "
            f"Também foram identificados {fmt(selected['indicated'])} leads enviados, "
            f"{fmt(selected['opened'])} contas convertidas pela data original da indicação e "
            f"{fmt(selected['openedInPeriod'])} contas abertas pela data real de abertura.",
            styles["V2Body"],
        )
    )

    story.append(Paragraph("Funil de conversão", styles["V2Section"]))
    story.append(
        table(
            [
                ["Envios", "Contas abertas", "Positivos", "Lidos", "Interações", "Interessados", "Leads", "Convertidas", "Abertas", "Pix conv.", "Pix abertas"],
                [fmt(selected[k]) for k in ["sent", "qualificationSent", "positiveSent", "read", "buttonInteractions", "interactions", "indicated", "opened", "openedInPeriod", "pixOpen", "pixOpenInPeriod"]],
            ],
            [2.2 * cm] * 11,
            7.5,
        )
    )

    story.append(PageBreak())
    story.append(KeepTogether([Paragraph("Evolução diária", styles["V2Section"]), line_chart(daily)]))

    story.append(Paragraph("Comparativo dia a dia", styles["V2Section"]))
    daily_table = [["Data", "Envios", "Base aberta", "Positivos", "Não env.", "Interações", "Interessados", "Leads", "Convert.", "Abertas", "Pix conv.", "Pix abertas", "% Inter.", "% Interesse", "% Conv."]]
    for r in daily:
        daily_table.append([date_pt(r["date"]), fmt(r["sent"]), fmt(r["qualificationSent"]), fmt(r["positiveSent"]), fmt(r["undelivered"]), fmt(r["buttonInteractions"]), fmt(r["interactions"]), fmt(r["indicated"]), fmt(r["opened"]), fmt(r["openedInPeriod"]), fmt(r["pixOpen"]), fmt(r["pixOpenInPeriod"]), pct(r["buttonInteractionRate"]), pct(r["interactionRate"]), pct(r["openingRate"])])
    story.append(table(daily_table, [1.5 * cm, 1.6 * cm, 1.6 * cm, 1.6 * cm, 1.35 * cm, 1.6 * cm, 1.7 * cm, 1.3 * cm, 1.3 * cm, 1.3 * cm, 1.2 * cm, 1.2 * cm, 1.25 * cm, 1.35 * cm, 1.25 * cm], 5.2))

    story.append(KeepTogether([Paragraph("Melhores horários de retorno", styles["V2Section"]), hour_chart(payload["hours"])]))

    story.append(PageBreak())
    story.append(Paragraph("Evolução semanal e mensal", styles["V2Section"]))
    weeks = [w for w in payload["weekly"] if any(d["week"] == w["period"] for d in daily)]
    weekly_table = [["Período", "Envios", "Base aberta", "Positivos", "Interações", "Interessados", "Leads", "Convert.", "Abertas", "Pix conv.", "Pix abertas"]]
    for w in weeks:
        weekly_table.append([week_name(w), fmt(w["sent"]), fmt(w["qualificationSent"]), fmt(w["positiveSent"]), fmt(w["buttonInteractions"]), fmt(w["interactions"]), fmt(w["indicated"]), fmt(w["opened"]), fmt(w["openedInPeriod"]), fmt(w["pixOpen"]), fmt(w["pixOpenInPeriod"])])
    weekly_table.append([monthly.get("label") or month_pt(month), fmt(monthly["sent"]), fmt(monthly["qualificationSent"]), fmt(monthly["positiveSent"]), fmt(monthly["buttonInteractions"]), fmt(monthly["interactions"]), fmt(monthly["indicated"]), fmt(monthly["opened"]), fmt(monthly["openedInPeriod"]), fmt(monthly["pixOpen"]), fmt(monthly["pixOpenInPeriod"])])
    story.append(table(weekly_table, [3.55 * cm, 1.9 * cm, 2.0 * cm, 1.9 * cm, 2.0 * cm, 2.1 * cm, 1.55 * cm, 1.55 * cm, 1.55 * cm, 1.35 * cm, 1.35 * cm], 6.0))

    story.append(Paragraph("Mês de fundação das empresas com conta aberta no período", styles["V2Section"]))
    foundation_table = [["Mês de fundação", "Abertas no período", "Com Pix", "% Pix"]]
    for a in foundation:
        pix_rate = (a["pixOpen"] / a["opened"] * 100) if a["opened"] else 0
        foundation_table.append([a["foundationMonth"], fmt(a["opened"]), fmt(a["pixOpen"]), pct(pix_rate)])
    story.append(table(foundation_table, [6.5 * cm, 5.0 * cm, 5.0 * cm, 5.0 * cm], 8))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    shutil.copy2(output, WEB / f"relatorio_c6_empresas_v2_{ref_stamp(selected['date'])}.pdf")
    print(output)


if __name__ == "__main__":
    build_pdf()

