import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

NAVY = colors.HexColor("#25284F")
GOLD = colors.HexColor("#B89455")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#657084")
LINE = colors.HexColor("#D9DEE8")
SOFT = colors.HexColor("#F7F8FB")
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


def month_pt(value):
    y, m = value.split("-")
    names = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    return f"{names[int(m) - 1]}/{y}"


def week_name(row):
    return row.get("label") or f"{date_pt(row.get('startDate'))} a {date_pt(row.get('endDate'))}"


def ref_stamp(value):
    return (value or "").replace("-", "")


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(1.4 * cm, 1.15 * cm, 28.3 * cm, 1.15 * cm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(NAVY)
    canvas.drawString(1.4 * cm, 0.88 * cm, "CONFIDENCIAL")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(14.85 * cm, 0.88 * cm, "Todos os direitos reservados à Assis & Mollerke")
    canvas.drawRightString(28.2 * cm, 0.88 * cm, f"Página {doc.page}")
    canvas.restoreState()


def table(data, widths=None, font_size=8, first_col_left=True):
    tbl = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("GRID", (0, 0), (-1, -1), 0.25, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (0, 1), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if first_col_left:
        style.append(("ALIGN", (0, 1), (0, -1), "CENTER"))
    tbl.setStyle(TableStyle(style))
    return tbl


def card_table(items):
    cells = []
    empty = Paragraph("", ParagraphStyle("CardEmpty"))
    for title, value, sub in items:
        cells.append(
            Paragraph(
                f'<font color="#657084" size="7">{title}</font><br/>'
                f'<font color="#25284F" size="18"><b>{value}</b></font><br/>'
                f'<font color="#657084" size="7">{sub}</font>',
                ParagraphStyle("Card", leading=17, alignment=TA_CENTER),
            )
        )
    while len(cells) % 4:
        cells.append(empty)
    rows = [cells[i : i + 4] for i in range(0, len(cells), 4)]
    tbl = Table(rows, colWidths=[6.55 * cm] * 4)
    tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 13),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 13),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return tbl


def build_pdf():
    payload = load_payload()
    month = payload["months"][-1]
    daily = [r for r in payload["daily"] if r["month"] == month]
    selected = daily[-1]
    monthly = next(r for r in payload["monthly"] if r["period"] == month)
    monthly_interest = (monthly["interactions"] / monthly["positiveSent"] * 100) if monthly.get("positiveSent") else 0
    foundation = [a for a in payload.get("foundationMonths", []) if a["month"] == month]
    output = WEB / "relatorio_c6_empresas.pdf"

    doc = SimpleDocTemplate(
        str(output),
        pagesize=landscape(A4),
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.4 * cm,
        title="Relatório C6 Empresas - Assis & Mollerke",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("TitleAM", parent=styles["Title"], textColor=NAVY, fontSize=21, leading=25, alignment=TA_CENTER, spaceAfter=5))
    styles.add(ParagraphStyle("TitleLeftAM", parent=styles["Title"], textColor=NAVY, fontSize=19, leading=23, alignment=TA_LEFT, spaceAfter=5))
    styles.add(ParagraphStyle("SubAM", parent=styles["Normal"], textColor=MUTED, fontSize=9, leading=12, alignment=TA_CENTER, spaceAfter=10))
    styles.add(ParagraphStyle("SubLeftAM", parent=styles["Normal"], textColor=MUTED, fontSize=9, leading=12, alignment=TA_LEFT, spaceAfter=10))
    styles.add(ParagraphStyle("SectionAM", parent=styles["Heading2"], textColor=NAVY, fontSize=14, leading=17, spaceBefore=9, spaceAfter=7))
    styles.add(ParagraphStyle("BodyAM", parent=styles["Normal"], textColor=INK, fontSize=9, leading=12, alignment=TA_LEFT))
    styles.add(ParagraphStyle("FineAM", parent=styles["Normal"], textColor=MUTED, fontSize=8, leading=10, alignment=TA_LEFT))

    story = []
    logo = WEB / "assets" / "logo.png"
    logo_flowable = Image(str(logo), width=4.2 * cm, height=2.58 * cm) if logo.exists() else Paragraph("Assis & Mollerke", styles["SubAM"])
    title_block = [
        Paragraph(f"Relatório Diário de Campanhas WhatsApp - {date_pt(selected['date'])}", styles["TitleLeftAM"]),
        Paragraph(
            f"C6 Empresas | Dia de referência: {date_pt(selected['date'])} | "
            f"Referência: {month_pt(month)} | Última importação: {datetime.fromisoformat(payload.get('lastImportAt') or payload.get('generatedAt')).strftime('%d/%m/%Y às %H:%M')}",
            styles["SubLeftAM"],
        ),
    ]
    header = Table([[title_block, logo_flowable]], colWidths=[20.2 * cm, 5.8 * cm])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 0.05 * cm))

    story.append(
        card_table(
            [
                ("Envios", fmt(selected["sent"]), f"Mês: {fmt(monthly['sent'])}"),
                ("Envios contas abertas", fmt(selected["qualificationSent"]), f"{pct(selected['qualificationRate'])} dos envios"),
                ("Envios positivos", fmt(selected["positiveSent"]), f"{pct(selected['positiveRate'])} no dia"),
                ("Interações totais", fmt(selected["buttonInteractions"]), f"{pct(selected['buttonInteractionRate'])} dos positivos"),
                ("Contatos interessados", fmt(selected["interactions"]), f"{pct(selected['interactionRate'])} dos positivos"),
                ("Leads enviados", fmt(selected["indicated"]), f"{pct(selected['indicationRate'])} dos interessados"),
                ("Contas criadas", fmt(selected["opened"]), f"{pct(selected['openingRate'])} dos leads"),
                ("Com Pix", fmt(selected["pixOpen"]), f"{pct(selected['pixRate'])} das contas"),
                ("% conversão mês", pct(monthly["openingRate"]), f"{fmt(monthly['opened'])} contas"),
            ]
        )
    )

    story.append(Paragraph("Funil de conversão", styles["SectionAM"]))
    funnel = [
        ["Envios", "Contas abertas", "Positivos", "Lidos", "Interações", "Interessados", "Leads", "Contas", "Pix"],
        [fmt(selected[k]) for k in ["sent", "qualificationSent", "positiveSent", "read", "buttonInteractions", "interactions", "indicated", "opened", "pixOpen"]],
    ]
    story.append(table(funnel, [2.7 * cm] * 9, 7.5, first_col_left=False))

    story.append(Paragraph("Resumo executivo", styles["SectionAM"]))
    story.append(
        Paragraph(
            f"O presente relatório consolida os resultados das campanhas de WhatsApp do C6 Empresas na data de referência "
            f"{date_pt(selected['date'])}. Também foram realizados {fmt(selected['qualificationSent'])} envios para clientes com conta aberta. "
            f"Foram apuradas {fmt(selected['buttonInteractions'])} interações totais, equivalentes a "
            f"{pct(selected['buttonInteractionRate'])} dos envios positivos. Desse volume, {fmt(selected['interactions'])} corresponderam a contatos interessados. "
            f"Também foram identificados {fmt(selected['indicated'])} leads enviados e "
            f"{fmt(selected['opened'])} contas criadas atribuídas à data original da indicação. No acumulado mensal, "
            f"registram-se {fmt(monthly['sent'])} envios, {fmt(monthly['indicated'])} leads enviados e "
            f"{fmt(monthly['opened'])} contas criadas, permitindo o acompanhamento objetivo da evolução da operação.",
            styles["BodyAM"],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("Comparativo dia a dia", styles["SectionAM"]))
    daily_table = [["Data", "Envios", "Base aberta", "Positivos", "Não env.", "Interações", "Interessados", "Leads", "Contas", "Pix", "% Inter.", "% Interesse", "% Conv."]]
    for r in daily:
        daily_table.append(
            [
                date_pt(r["date"]),
                fmt(r["sent"]),
                fmt(r["qualificationSent"]),
                fmt(r["positiveSent"]),
                fmt(r["undelivered"]),
                fmt(r["buttonInteractions"]),
                fmt(r["interactions"]),
                fmt(r["indicated"]),
                fmt(r["opened"]),
                fmt(r["pixOpen"]),
                pct(r["buttonInteractionRate"]),
                pct(r["interactionRate"]),
                pct(r["openingRate"]),
            ]
        )
    story.append(table(daily_table, [1.75 * cm, 1.85 * cm, 1.9 * cm, 1.85 * cm, 1.75 * cm, 1.85 * cm, 2.0 * cm, 1.55 * cm, 1.5 * cm, 1.3 * cm, 1.45 * cm, 1.55 * cm, 1.5 * cm], 6.0))

    story.append(Paragraph("Evolução semanal e mensal", styles["SectionAM"]))
    weeks = [w for w in payload["weekly"] if any(d["week"] == w["period"] for d in daily)]
    weekly_table = [["Período", "Envios", "Base aberta", "Positivos", "Interações", "Interessados", "Leads", "Contas", "Pix"]]
    for w in weeks:
        weekly_table.append([week_name(w), fmt(w["sent"]), fmt(w["qualificationSent"]), fmt(w["positiveSent"]), fmt(w["buttonInteractions"]), fmt(w["interactions"]), fmt(w["indicated"]), fmt(w["opened"]), fmt(w["pixOpen"])])
    weekly_table.append([monthly.get("label") or month_pt(month), fmt(monthly["sent"]), fmt(monthly["qualificationSent"]), fmt(monthly["positiveSent"]), fmt(monthly["buttonInteractions"]), fmt(monthly["interactions"]), fmt(monthly["indicated"]), fmt(monthly["opened"]), fmt(monthly["pixOpen"])])
    story.append(table(weekly_table, [4.5 * cm, 2.4 * cm, 2.5 * cm, 2.4 * cm, 2.5 * cm, 2.55 * cm, 2.0 * cm, 2.0 * cm, 1.75 * cm], 6.8))

    story.append(Paragraph("Mês de fundação das empresas com conta criada", styles["SectionAM"]))
    foundation_table = [["Mês de fundação", "Contas criadas", "Com Pix", "% Pix"]]
    for a in foundation:
        pix_rate = (a["pixOpen"] / a["opened"] * 100) if a["opened"] else 0
        foundation_table.append([a["foundationMonth"], fmt(a["opened"]), fmt(a["pixOpen"]), pct(pix_rate)])
    story.append(table(foundation_table, [6.5 * cm, 5.0 * cm, 5.0 * cm, 5.0 * cm], 8))

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    shutil.copy2(output, WEB / f"relatorio_c6_empresas_{ref_stamp(selected['date'])}.pdf")
    print(output)


if __name__ == "__main__":
    build_pdf()
