import json
import math
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "web"
ASSETS = OUT / "assets"
DATA_STORE = Path(__import__("os").environ.get("DATA_DIR", ROOT / "data_store")).resolve()

FILES = {
    "envios": DATA_STORE / "envios_historico.csv",
    "botoes": DATA_STORE / "botoes_historico.csv",
    "leads": DATA_STORE / "leads_atual.xlsx",
    "visao": DATA_STORE / "visao_atual.xlsx",
    "logo": ASSETS / "logo.png",
}


def parse_date(series, dayfirst=True):
    return pd.to_datetime(series, errors="coerce", dayfirst=dayfirst)


def date_key(value):
    if pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def month_key(value):
    if pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m")


MONTH_NAMES = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def date_short(value):
    if not value:
        return ""
    ts = pd.Timestamp(value)
    return ts.strftime("%d/%m")


def month_label(value):
    if not value:
        return ""
    year, month = value.split("-")
    return f"{MONTH_NAMES[int(month) - 1].capitalize()}/{year}"


def week_of_month(value):
    ts = pd.Timestamp(value)
    first = ts.replace(day=1)
    return int(((ts.day + first.weekday() - 1) // 7) + 1)


def week_label(days):
    ordered = sorted(days)
    if not ordered:
        return "Semana"
    start = ordered[0]
    end = ordered[-1]
    wom = week_of_month(start)
    month_name = MONTH_NAMES[pd.Timestamp(start).month - 1]
    return f"Semana {wom} de {month_name} ({date_short(start)} a {date_short(end)})"


def hour_label(value):
    if pd.isna(value):
        return None
    return f"{int(pd.Timestamp(value).hour):02d}:00"


def digits(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return re.sub(r"\D+", "", str(value))


def cnpj_fmt(value):
    raw = digits(value).zfill(14)[-14:]
    if len(raw) != 14:
        return str(value or "")
    return f"{raw[:2]}.{raw[2:5]}.{raw[5:8]}/{raw[8:12]}-{raw[12:]}"


def phone_from_contact_id(value):
    raw = str(value or "")
    match = re.search(r"(\d{12,14})$", raw)
    return match.group(1) if match else digits(raw)


VALID_BUTTON_STATUS = {"Aceito", "Abrir Conta", "Abrir Conta - Empresa Antiga", "Saber mais / Conhecer mais"}
POSITIVE_SEND_STATUS = {"read", "delivered", "sent"}


def safe_text(value):
    if pd.isna(value):
        return ""
    text = str(value)
    return "" if text.lower() in {"nan", "nat", "'-", "-"} else text


def pct(num, den):
    return round((num / den) * 100, 2) if den else 0.0


def load_data():
    envios = pd.read_csv(FILES["envios"], sep=";", dtype=str, encoding="utf-8")
    envios_all = envios.copy()
    botoes = pd.read_csv(FILES["botoes"], dtype=str, encoding="utf-8")
    leads = pd.read_excel(FILES["leads"], dtype=str)
    visao = pd.read_excel(FILES["visao"], dtype=str)

    envios = envios[
        envios["broadcast_description"].fillna("").str.contains("C6", case=False, regex=False)
    ].copy()
    botoes = botoes[botoes["area"].fillna("").str.contains("C6", case=False, regex=False)].copy()
    leads = leads[leads["NOME_PARCEIRO"].fillna("").str.contains("AM ASSESSORIA|ASSIS", case=False, regex=True)].copy()
    visao = visao[visao["NOME_PARCEIRO"].fillna("").str.contains("ASSIS|MOLLERKE|AM", case=False, regex=True)].copy()

    envios["dt"] = parse_date(envios["message_date_time"])
    envios["date"] = envios["dt"].map(date_key)
    envios["month"] = envios["dt"].map(month_key)
    envios["hour"] = envios["dt"].map(hour_label)
    envios["status_norm"] = envios["message_status"].fillna("").str.lower().str.strip()
    envios["phone"] = envios["contact_id"].map(phone_from_contact_id)

    envios_all["dt"] = parse_date(envios_all["message_date_time"])
    envios_all["date"] = envios_all["dt"].map(date_key)
    envios_all["status_norm"] = envios_all["message_status"].fillna("").str.lower().str.strip()

    botoes["dt"] = parse_date(botoes["date_time"])
    botoes["date"] = botoes["dt"].map(date_key)
    botoes["month"] = botoes["dt"].map(month_key)
    botoes["hour"] = botoes["dt"].map(hour_label)
    botoes["phone"] = botoes["contact_id"].map(phone_from_contact_id)
    botoes["status_clean"] = botoes["status"].fillna("").str.strip()
    botoes["is_intent"] = botoes["status_clean"].isin(VALID_BUTTON_STATUS)

    leads["dt_indicacao"] = parse_date(leads["DATA_HORA_CADASTRO"], dayfirst=False)
    leads["dt_abertura"] = parse_date(leads["DT_CONTA_ABERTA"], dayfirst=False)
    leads["date_indicacao"] = leads["dt_indicacao"].map(date_key)
    leads["date_abertura"] = leads["dt_abertura"].map(date_key)
    leads["month_indicacao"] = leads["dt_indicacao"].map(month_key)
    leads["month_abertura"] = leads["dt_abertura"].map(month_key)
    leads["cnpj"] = leads["CNPJ_CLIENTE"].map(digits)
    leads["phone"] = leads["CELULAR_RESPONSAVEL"].map(digits)
    leads["is_open"] = leads["FL_CONTA_ABERTA"].fillna("0").astype(str).str.strip().eq("1")

    visao["dt_fundacao"] = parse_date(visao["DT_FUNDACAO_EMPRESA"], dayfirst=False)
    visao["dt_conta"] = parse_date(visao["DT_CONTA_CRIADA"], dayfirst=False)
    visao["date_conta"] = visao["dt_conta"].map(date_key)
    visao["month_conta"] = visao["dt_conta"].map(month_key)
    visao["cnpj"] = visao["CD_CPF_CNPJ_CLIENTE"].map(digits)
    visao["pix_status"] = visao["CHAVES_PIX_FORTE"].map(safe_text)
    visao["has_pix"] = visao["pix_status"].str.len().gt(0)
    visao["fundacao_mes"] = visao["dt_fundacao"].dt.strftime("%m/%Y")

    return envios, envios_all, botoes, leads, visao


def attributed_sources(botoes, leads, visao):
    valid_buttons = botoes[botoes["is_intent"] & botoes["phone"].ne("")].copy()
    daily_interactions = (
        valid_buttons.drop_duplicates(["date", "phone"])
        .groupby("date")["phone"]
        .nunique()
    )
    valid_phones = set(valid_buttons["phone"].dropna())

    whatsapp_leads = leads[leads["phone"].isin(valid_phones) & leads["cnpj"].ne("")].copy()
    lead_by_day = whatsapp_leads.groupby("date_indicacao")["cnpj"].nunique()

    lead_cohort = (
        whatsapp_leads[whatsapp_leads["date_indicacao"].notna()]
        .sort_values(["dt_indicacao", "cnpj"])
        .drop_duplicates("cnpj")
        [[
            "cnpj",
            "dt_indicacao",
            "date_indicacao",
            "phone",
            "NOME_CLIENTE",
            "NOME_RESPONSAVEL",
            "STATUS_FINAL",
            "STATUS_ABERTURA_CONTA",
        ]]
    )
    whatsapp_accounts = visao[visao["cnpj"].isin(set(lead_cohort["cnpj"])) & visao["date_conta"].notna()].copy()
    whatsapp_accounts = whatsapp_accounts.merge(lead_cohort, on="cnpj", how="left", suffixes=("", "_lead"))
    whatsapp_accounts = whatsapp_accounts[
        whatsapp_accounts["dt_indicacao"].notna()
        & whatsapp_accounts["dt_conta"].notna()
        & (whatsapp_accounts["dt_conta"] >= whatsapp_accounts["dt_indicacao"])
    ].copy()
    whatsapp_accounts = (
        whatsapp_accounts.sort_values(["dt_indicacao", "dt_conta", "cnpj"], na_position="last")
        .drop_duplicates("cnpj")
        .reset_index(drop=True)
    )
    whatsapp_accounts["cohort_date"] = whatsapp_accounts["date_indicacao"]
    account_by_day = whatsapp_accounts.groupby("cohort_date")["cnpj"].nunique()
    pix_by_day = whatsapp_accounts[whatsapp_accounts["has_pix"]].groupby("cohort_date")["cnpj"].nunique()

    return valid_buttons, whatsapp_leads, whatsapp_accounts, daily_interactions, lead_by_day, account_by_day, pix_by_day


def build_daily(envios, envios_all, botoes, leads, visao):
    (
        valid_buttons,
        whatsapp_leads,
        whatsapp_accounts,
        daily_interactions,
        lead_by_day,
        account_by_day,
        pix_by_day,
    ) = attributed_sources(botoes, leads, visao)
    rows = []
    qualification_mask = (
        (
            envios_all["broadcast_description"].fillna("").str.contains("abertas", case=False, regex=False)
            | envios_all["broadcast_description"].fillna("").str.contains("auto", case=False, regex=False)
            | envios_all["broadcast_description"].fillna("").str.contains("automa", case=False, regex=False)
        )
        & envios_all["status_norm"].isin(POSITIVE_SEND_STATUS)
    )
    qualification_by_day = envios_all[qualification_mask].groupby("date").size()
    dates = sorted(set(envios["date"].dropna()) | set(qualification_by_day.index.dropna()))

    for d in dates:
        e = envios[envios["date"] == d]
        b = botoes[botoes["date"] == d]
        sent = len(e)
        qualification_sent = int(qualification_by_day.get(d, 0))
        positive = int(e["status_norm"].isin(POSITIVE_SEND_STATUS).sum())
        undelivered = int(e["status_norm"].eq("undelivered").sum())
        delivered = int(e["status_norm"].isin(["delivered", "read"]).sum())
        read = int(e["status_norm"].eq("read").sum())
        button_interactions = int(len(b))
        interactions = int(daily_interactions.get(d, 0))
        indicated = int(lead_by_day.get(d, 0))
        opened = int(account_by_day.get(d, 0))
        pix_open = int(pix_by_day.get(d, 0))
        rows.append(
            {
                "date": d,
                "month": d[:7],
                "week": pd.Timestamp(d).strftime("%G-W%V"),
                "sent": sent,
                "qualificationSent": qualification_sent,
                "positiveSent": positive,
                "undelivered": undelivered,
                "delivered": delivered,
                "read": read,
                "buttonInteractions": button_interactions,
                "interactions": interactions,
                "indicated": indicated,
                "opened": opened,
                "pixOpen": pix_open,
                "withoutPix": max(opened - pix_open, 0),
                "positiveRate": pct(positive, sent),
                "qualificationRate": pct(qualification_sent, sent),
                "deliveryRate": pct(delivered, sent),
                "readRate": pct(read, positive),
                "buttonInteractionRate": pct(button_interactions, positive),
                "interactionRate": pct(interactions, positive),
                "intentShareRate": pct(interactions, button_interactions),
                "indicationRate": pct(indicated, interactions),
                "openingRate": pct(opened, indicated),
                "pixRate": pct(pix_open, opened),
            }
        )

    for i, row in enumerate(rows):
        prev = rows[i - 1] if i > 0 else None
        for key in ["sent", "qualificationSent", "positiveSent", "undelivered", "buttonInteractions", "interactions", "indicated", "opened", "pixOpen", "positiveRate", "qualificationRate", "buttonInteractionRate", "interactionRate", "intentShareRate", "indicationRate", "openingRate", "pixRate"]:
            row[f"{key}Delta"] = round(row[key] - (prev[key] if prev else 0), 2)
    return rows


def aggregate(rows, by):
    groups = {}
    for row in rows:
        key = row[by]
        acc = groups.setdefault(
            key,
            {"period": key, "sent": 0, "qualificationSent": 0, "positiveSent": 0, "undelivered": 0, "delivered": 0, "read": 0, "buttonInteractions": 0, "interactions": 0, "indicated": 0, "opened": 0, "pixOpen": 0, "dates": []},
        )
        acc["dates"].append(row["date"])
        for metric in ["sent", "qualificationSent", "positiveSent", "undelivered", "delivered", "read", "buttonInteractions", "interactions", "indicated", "opened", "pixOpen"]:
            acc[metric] += row[metric]
    out = []
    for key in sorted(groups):
        row = groups[key]
        row["startDate"] = min(row["dates"])
        row["endDate"] = max(row["dates"])
        row["label"] = week_label(row["dates"]) if by == "week" else month_label(key)
        del row["dates"]
        row["positiveRate"] = pct(row["positiveSent"], row["sent"])
        row["qualificationRate"] = pct(row["qualificationSent"], row["sent"])
        row["buttonInteractionRate"] = pct(row["buttonInteractions"], row["positiveSent"])
        row["interactionRate"] = pct(row["interactions"], row["positiveSent"])
        row["intentShareRate"] = pct(row["interactions"], row["buttonInteractions"])
        row["indicationRate"] = pct(row["indicated"], row["interactions"])
        row["openingRate"] = pct(row["opened"], row["indicated"])
        row["pixRate"] = pct(row["pixOpen"], row["opened"])
        out.append(row)
    return out


def build_accounts(botoes, leads, visao):
    _, _, whatsapp_accounts, *_ = attributed_sources(botoes, leads, visao)
    rows = []
    today = pd.Timestamp(datetime.now().date())
    for _, r in whatsapp_accounts.sort_values(["dt_conta", "cnpj"], na_position="last").iterrows():
        fund = r.get("dt_fundacao")
        age_years = ""
        if pd.notna(fund):
            age_years = round((today - pd.Timestamp(fund)).days / 365.25, 1)
        rows.append(
            {
                "cnpj": cnpj_fmt(r.get("cnpj")),
                "razaoSocial": safe_text(r.get("NOME_CLIENTE")) or safe_text(r.get("NOME_CLIENTE_lead")) or safe_text(r.get("NOME_RESPONSAVEL")),
                "fundacao": date_key(fund) or "",
                "mesFundacao": safe_text(r.get("fundacao_mes")) or "",
                "idadeEmpresa": age_years,
                "dataIndicacao": date_key(r.get("dt_indicacao")) or "",
                "dataAbertura": date_key(r.get("dt_conta")) or "",
                "statusPix": safe_text(r.get("pix_status")) or "Sem chave",
                "statusConta": safe_text(r.get("STATUS_CC")),
            }
        )
    return rows


def build_analytic_accounts_excel(botoes, leads, visao, daily):
    _, _, whatsapp_accounts, *_ = attributed_sources(botoes, leads, visao)
    report_dates = {row.get("date") for row in daily if row.get("date")}
    if report_dates:
        whatsapp_accounts = whatsapp_accounts[whatsapp_accounts["cohort_date"].isin(report_dates)].copy()
    rows = []
    for _, r in whatsapp_accounts.sort_values(["dt_indicacao", "dt_conta", "cnpj"], na_position="last").iterrows():
        data_indicacao = date_key(r.get("dt_indicacao")) or ""
        data_abertura = date_key(r.get("dt_conta")) or ""
        dias_abertura = ""
        if pd.notna(r.get("dt_indicacao")) and pd.notna(r.get("dt_conta")):
            dias_abertura = int((pd.Timestamp(r.get("dt_conta")).normalize() - pd.Timestamp(r.get("dt_indicacao")).normalize()).days)
        pix_status = safe_text(r.get("pix_status"))
        rows.append(
            {
                "Data da indicação": data_indicacao,
                "Data da abertura da conta": data_abertura,
                "CNPJ": cnpj_fmt(r.get("cnpj")),
                "Razão social": safe_text(r.get("NOME_CLIENTE")) or safe_text(r.get("NOME_CLIENTE_lead")) or safe_text(r.get("NOME_RESPONSAVEL")),
                "Telefone": safe_text(r.get("phone")),
                "Status do lead": safe_text(r.get("STATUS_FINAL")),
                "Status de abertura no lead": safe_text(r.get("STATUS_ABERTURA_CONTA")),
                "Status da conta": safe_text(r.get("STATUS_CC")),
                "Possui chave Pix": "Sim" if bool(r.get("has_pix")) else "Não",
                "Status da chave Pix": pix_status or "Sem chave",
                "Data de fundação da empresa": date_key(r.get("dt_fundacao")) or "",
                "CNAE / ramo de atuação": safe_text(r.get("RAMO_ATUACAO")),
                "Dias entre indicação e abertura": dias_abertura,
                "Mês de referência": data_indicacao[:7],
                "Origem do cruzamento": "Telefone WhatsApp > Lead C6 > CNPJ Visão Cliente",
            }
        )

    df = pd.DataFrame(rows)
    columns = [
        "Data da indicação",
        "Data da abertura da conta",
        "CNPJ",
        "Razão social",
        "Telefone",
        "Status do lead",
        "Status de abertura no lead",
        "Status da conta",
        "Possui chave Pix",
        "Status da chave Pix",
        "Data de fundação da empresa",
        "CNAE / ramo de atuação",
        "Dias entre indicação e abertura",
        "Mês de referência",
        "Origem do cruzamento",
    ]
    for column in columns:
        if column not in df:
            df[column] = ""
    df = df[columns]

    ref = daily[-1]["date"] if daily else datetime.now().strftime("%Y-%m-%d")
    ref_stamp = ref.replace("-", "")
    out_file = OUT / "relatorio_analitico_contas_abertas.xlsx"
    dated_file = OUT / f"relatorio_analitico_contas_abertas_{ref_stamp}.xlsx"
    summary = pd.DataFrame(
        [
            {"Indicador": "Data de referência", "Valor": ref},
            {"Indicador": "Total de contas abertas no PDF/painel", "Valor": sum(int(row.get("opened", 0)) for row in daily)},
            {"Indicador": "Total de CNPJs no analítico", "Valor": len(df)},
            {"Indicador": "Contas com chave Pix", "Valor": int((df["Possui chave Pix"] == "Sim").sum())},
            {"Indicador": "Contas sem chave Pix", "Valor": int((df["Possui chave Pix"] != "Sim").sum())},
            {"Indicador": "Regra", "Valor": "Mesmo critério do PDF: CNPJ único, atribuído à data original da indicação."},
        ]
    )

    for target in (out_file, dated_file):
        with pd.ExcelWriter(target, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Contas abertas", index=False)
            summary.to_excel(writer, sheet_name="Resumo", index=False)
            workbook = writer.book
            for worksheet in workbook.worksheets:
                worksheet.freeze_panes = "A2"
                for column_cells in worksheet.columns:
                    max_len = max(len(str(cell.value or "")) for cell in column_cells)
                    width = min(max(max_len + 2, 12), 42)
                    worksheet.column_dimensions[column_cells[0].column_letter].width = width
                for cell in worksheet[1]:
                    cell.font = cell.font.copy(bold=True)
    return {"file": str(out_file), "datedFile": str(dated_file), "rows": len(df), "referenceDate": ref}


def build_foundation_months(accounts):
    rows = {}
    for account in accounts:
        open_month = (account.get("dataIndicacao") or "")[:7]
        foundation_month = account.get("mesFundacao") or "Sem data"
        if not open_month:
            continue
        key = (open_month, foundation_month)
        row = rows.setdefault(
            key,
            {"month": open_month, "foundationMonth": foundation_month, "opened": 0, "pixOpen": 0},
        )
        row["opened"] += 1
        if account.get("statusPix") and account.get("statusPix") != "Sem chave":
            row["pixOpen"] += 1
    return sorted(rows.values(), key=lambda r: (r["month"], r["foundationMonth"]))


def build_hours(envios, botoes):
    hours = [f"{h:02d}:00" for h in range(24)]
    sent = envios.groupby("hour").size()
    read = envios[envios["status_norm"].eq("read")].groupby("hour").size()
    interactions = botoes[botoes["is_intent"]].drop_duplicates(["date", "phone"]).groupby("hour").size()
    return [
        {
            "hour": h,
            "sent": int(sent.get(h, 0)),
            "read": int(read.get(h, 0)),
            "interactions": int(interactions.get(h, 0)),
            "responseRate": pct(int(interactions.get(h, 0)), int(sent.get(h, 0))),
        }
        for h in hours
    ]


def build_campaigns(envios):
    rows = []
    grouped = envios.groupby("broadcast_description", dropna=False)
    for name, g in grouped:
        sent = len(g)
        delivered = int(g["status_norm"].isin(["delivered", "read"]).sum())
        read = int(g["status_norm"].eq("read").sum())
        rows.append(
            {
                "campaign": safe_text(name),
                "date": date_key(g["dt"].min()) or "",
                "sent": sent,
                "delivered": delivered,
                "read": read,
                "deliveryRate": pct(delivered, sent),
                "readRate": pct(read, delivered),
            }
        )
    return sorted(rows, key=lambda r: (r["date"], r["campaign"]))


def main():
    OUT.mkdir(exist_ok=True)
    ASSETS.mkdir(exist_ok=True)
    envios, envios_all, botoes, leads, visao = load_data()
    daily = build_daily(envios, envios_all, botoes, leads, visao)
    accounts = build_accounts(botoes, leads, visao)
    report_dates = {row.get("date") for row in daily if row.get("date")}
    if report_dates:
        accounts = [account for account in accounts if account.get("dataIndicacao") in report_dates]
    analytic_accounts = build_analytic_accounts_excel(botoes, leads, visao, daily)
    foundation_months = build_foundation_months(accounts)
    hours = build_hours(envios, botoes)
    campaigns = build_campaigns(envios)
    months = sorted({row["month"] for row in daily if row.get("month")})

    now = datetime.now().isoformat(timespec="seconds")
    payload = {
        "generatedAt": now,
        "lastImportAt": now,
        "sourceFiles": {k: str(v) for k, v in FILES.items() if k != "logo"},
        "months": months,
        "daily": daily,
        "weekly": aggregate(daily, "week"),
        "monthly": aggregate(daily, "month"),
        "accounts": accounts,
        "analyticAccounts": analytic_accounts,
        "foundationMonths": foundation_months,
        "hours": hours,
        "campaigns": campaigns,
        "notes": [
            "Campanhas de WhatsApp filtradas por lotes que contem C6 no nome.",
            "Envios medem somente mensageria; resultados comerciais sao atribuidos por telefone unico/dia nos botoes Aceito, Abrir Conta e Abrir Conta - Empresa Antiga.",
            "Leads WhatsApp sao cruzados por telefone com o Analitico Leads. Contas abertas sao cruzadas por CNPJ na Visao Cliente e atribuidas ao dia original da indicacao.",
            "Como a Visao Cliente informa o status atual da chave Pix, sem data historica de cadastro, Pix representa contas abertas que ja constam com chave Pix na base.",
        ],
    }

    data_js = "window.C6_DASHBOARD_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    (OUT / "data.js").write_text(data_js, encoding="utf-8")
    logo_source = Path(FILES["logo"])
    logo_target = ASSETS / "logo.png"
    if logo_source.exists():
        try:
            if logo_source.resolve() != logo_target.resolve():
                shutil.copy2(logo_source, logo_target)
        except FileNotFoundError:
            pass
    print(json.dumps({"daily": len(daily), "accounts": len(accounts), "campaigns": len(campaigns), "out": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
