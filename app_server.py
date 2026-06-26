import base64
import cgi
import html
import importlib
import json
import os
import smtplib
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from email.message import EmailMessage
from email.utils import formataddr, formatdate, getaddresses, make_msgid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
UPLOADS = Path(os.environ.get("UPLOADS_DIR", ROOT / "uploads")).resolve()
DATA_STORE = Path(os.environ.get("DATA_DIR", ROOT / "data_store")).resolve()
IMPORT_ARCHIVE = DATA_STORE / "imports"
ENVIOS_DAY_LAST = DATA_STORE / "envios_dia_ultima_consulta.json"

MASTER_USER = os.environ.get("MASTER_USER", "master")
MASTER_PASS = os.environ.get("MASTER_PASS", "")
MONITOR_USER = os.environ.get("MONITOR_USER", "banco")
MONITOR_PASS = os.environ.get("MONITOR_PASS", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "mail.amcob.com.br")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "am@amcob.com.br")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_CC = os.environ.get("SMTP_CC", "am@amcob.com.br")
REMOTE_BASE_URL = os.environ.get("REMOTE_BASE_URL", "https://painel-c6-empresas.onrender.com").rstrip("/")
SYNC_ENABLED = os.environ.get("SYNC_ENABLED", "1").strip().lower() not in {"0", "false", "no"}

CONSOLIDATED = {
    "envios": DATA_STORE / "envios_historico.csv",
    "botoes": DATA_STORE / "botoes_historico.csv",
    "leads": DATA_STORE / "leads_atual.xlsx",
    "visao": DATA_STORE / "visao_atual.xlsx",
}


pd = None
build_data = None
create_report_pdf = None
create_report_pdf_v2 = None


def get_pandas():
    global pd
    if pd is None:
        import pandas as pandas_module

        pd = pandas_module
    return pd


def reload_processing_modules():
    global build_data, create_report_pdf, create_report_pdf_v2
    if build_data is None:
        import build_data as build_data_module
    else:
        build_data_module = importlib.reload(build_data)
    if create_report_pdf is None:
        import create_report_pdf as create_report_pdf_module
    else:
        create_report_pdf_module = importlib.reload(create_report_pdf)
    if create_report_pdf_v2 is None:
        import create_report_pdf_v2 as create_report_pdf_v2_module
    else:
        create_report_pdf_v2_module = importlib.reload(create_report_pdf_v2)
    build_data = build_data_module
    create_report_pdf = create_report_pdf_module
    create_report_pdf_v2 = create_report_pdf_v2_module


def split_addresses(value):
    raw = (value or "").replace(";", ",")
    return [addr for _, addr in getaddresses([raw]) if addr]


def basic_auth_header(user, password):
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def web_manifest_files():
    allowed_suffixes = {".js", ".pdf", ".xlsx"}
    files = []
    if not WEB.exists():
        return files
    for path in sorted(WEB.iterdir()):
        if path.is_file() and path.suffix.lower() in allowed_suffixes:
            files.append(
                {
                    "name": path.name,
                    "size": path.stat().st_size,
                    "mtime": int(path.stat().st_mtime),
                }
            )
    return files


def remote_same_as_request(headers):
    if not REMOTE_BASE_URL:
        return True
    host = (headers.get("Host") or "").split(":", 1)[0].lower()
    remote_host = (urllib.parse.urlparse(REMOTE_BASE_URL).hostname or "").lower()
    return bool(host and remote_host and host == remote_host)


def should_proxy_upload_to_remote(headers):
    if not SYNC_ENABLED or not REMOTE_BASE_URL or not MASTER_PASS:
        return False
    return not remote_same_as_request(headers)


def multipart_form_data(files):
    boundary = f"----C6Sync{uuid.uuid4().hex}"
    chunks = []
    for field, item in files.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{field}"; '
                f'filename="{item["filename"]}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(item["content"])
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return boundary, b"".join(chunks)


def http_request(url, method="GET", data=None, content_type=None, timeout=600):
    headers = {"Authorization": basic_auth_header(MASTER_USER, MASTER_PASS)}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read()


def proxy_upload_to_remote(uploaded):
    boundary, body = multipart_form_data(uploaded)
    status, content = http_request(
        f"{REMOTE_BASE_URL}/upload",
        method="POST",
        data=body,
        content_type=f"multipart/form-data; boundary={boundary}",
        timeout=1200,
    )
    if status >= 400:
        raise RuntimeError(f"Falha ao importar no online: HTTP {status}")
    mirror_remote_artifacts()
    return content


def mirror_remote_artifacts():
    if not SYNC_ENABLED or not REMOTE_BASE_URL or not MASTER_PASS:
        return []
    status, content = http_request(f"{REMOTE_BASE_URL}/sync/manifest", timeout=120)
    if status != 200:
        raise RuntimeError(f"Falha ao ler manifesto online: HTTP {status}")
    manifest = json.loads(content.decode("utf-8"))
    WEB.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for item in manifest.get("files", []):
        name = Path(item.get("name", "")).name
        if not name or name != item.get("name"):
            continue
        target = WEB / name
        if target.exists() and target.stat().st_size == int(item.get("size", -1)):
            continue
        file_status, file_content = http_request(f"{REMOTE_BASE_URL}/sync/file/{urllib.parse.quote(name)}", timeout=180)
        if file_status == 200:
            target.write_bytes(file_content)
            downloaded.append(name)
    return downloaded


def send_pdf_email(message, recipients):
    errors = {}

    def attempt_ssl(target):
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.login(SMTP_USER, SMTP_PASS)
            return smtp.send_message(message, from_addr=SMTP_USER, to_addrs=[target])

    def attempt_tls(target):
        with smtplib.SMTP(SMTP_HOST, 587, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(SMTP_USER, SMTP_PASS)
            return smtp.send_message(message, from_addr=SMTP_USER, to_addrs=[target])

    for target in recipients:
        try:
            refused = attempt_ssl(target)
            if refused:
                refused = attempt_tls(target)
            if refused:
                errors[target] = refused.get(target) or refused
        except Exception as first_error:
            try:
                refused = attempt_tls(target)
                if refused:
                    errors[target] = refused.get(target) or refused
            except Exception as second_error:
                errors[target] = f"{first_error} | fallback 587: {second_error}"
    return errors


def report_reference_date():
    try:
        text = (WEB / "data.js").read_text(encoding="utf-8")
        match = __import__("re").search(r"window\.C6_DASHBOARD_DATA\s*=\s*(.*);\s*$", text, __import__("re").S)
        payload = json.loads(match.group(1))
        ref = (payload.get("daily") or [{}])[-1].get("date")
        if ref:
            year, month, day = ref.split("-")
            return f"{day}/{month}/{year}", f"{year}{month}{day}"
    except Exception:
        pass
    return "", ""


def dashboard_health_payload():
    pandas = get_pandas()
    text = (WEB / "data.js").read_text(encoding="utf-8")
    match = __import__("re").search(r"window\.C6_DASHBOARD_DATA\s*=\s*(.*);\s*$", text, __import__("re").S)
    payload = json.loads(match.group(1))
    daily = payload.get("daily") or []
    monthly = payload.get("monthly") or []
    reference = (daily[-1] if daily else {}).get("date", "")
    month_key = reference[:7]
    month = next((row for row in monthly if row.get("period") == month_key), {})
    stamp = reference.replace("-", "")
    excel_path = WEB / f"relatorio_analitico_contas_abertas_{stamp}.xlsx"
    if not excel_path.exists():
        excel_path = WEB / "relatorio_analitico_contas_abertas.xlsx"
    excel_rows = None
    excel_unique_cnpj = None
    if excel_path.exists():
        try:
            df = pandas.read_excel(excel_path, sheet_name="Contas abertas", dtype=str)
            excel_rows = int(len(df))
            excel_unique_cnpj = int(df["CNPJ"].nunique()) if "CNPJ" in df.columns else None
        except Exception:
            excel_rows = "erro ao ler"
            excel_unique_cnpj = "erro ao ler"
    opened_in_period = int(month.get("openedInPeriod", 0) or 0)
    return {
        "status": "ok",
        "generatedAt": payload.get("generatedAt"),
        "referenceDate": reference,
        "referenceMonth": month.get("label") or month_key,
        "monthly": {
            "convertedByIndicationDate": int(month.get("opened", 0) or 0),
            "openedByAccountDate": opened_in_period,
            "pixConvertedByIndicationDate": int(month.get("pixOpen", 0) or 0),
            "pixOpenedByAccountDate": int(month.get("pixOpenInPeriod", 0) or 0),
            "indicated": int(month.get("indicated", 0) or 0),
            "interested": int(month.get("interactions", 0) or 0),
            "positiveSent": int(month.get("positiveSent", 0) or 0),
        },
        "analyticExcel": {
            "file": excel_path.name if excel_path.exists() else None,
            "rows": excel_rows,
            "uniqueCnpj": excel_unique_cnpj,
            "matchesOpenedByAccountDate": excel_unique_cnpj == opened_in_period,
        },
        "rulesVersion": "conversion_by_indication_date_and_opened_by_account_date",
    }


def archive_upload(field, filename, content):
    IMPORT_ARCHIVE.mkdir(parents=True, exist_ok=True)
    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = IMPORT_ARCHIVE / f"{stamp}_{field}_{filename}"
    archive_path.write_bytes(content)
    return archive_path


def seed_history_from_existing_uploads():
    DATA_STORE.mkdir(exist_ok=True)
    seeds = {
        "envios": (UPLOADS / "envios.csv", CONSOLIDATED["envios"]),
        "botoes": (UPLOADS / "botoes.csv", CONSOLIDATED["botoes"]),
        "leads": (UPLOADS / "leads.xlsx", CONSOLIDATED["leads"]),
        "visao": (UPLOADS / "visao.xlsx", CONSOLIDATED["visao"]),
    }
    for _, (source, target) in seeds.items():
        if source.exists() and not target.exists():
            target.write_bytes(source.read_bytes())


def merge_csv_history(imported_path, target_path, sep):
    pandas = get_pandas()
    if target_path.exists():
        current = pandas.read_csv(target_path, sep=sep, dtype=str, encoding="utf-8")
        incoming = pandas.read_csv(imported_path, sep=sep, dtype=str, encoding="utf-8")
        merged = pandas.concat([current, incoming], ignore_index=True)
    else:
        merged = pandas.read_csv(imported_path, sep=sep, dtype=str, encoding="utf-8")
    merged = merged.drop_duplicates().reset_index(drop=True)
    merged.to_csv(target_path, sep=sep, index=False, encoding="utf-8")
    return len(merged)


def update_consolidated_files(saved):
    seed_history_from_existing_uploads()
    envios_rows = merge_csv_history(saved["envios"], CONSOLIDATED["envios"], ";")
    botoes_rows = merge_csv_history(saved["botoes"], CONSOLIDATED["botoes"], ",")
    CONSOLIDATED["leads"].write_bytes(saved["leads"].read_bytes())
    CONSOLIDATED["visao"].write_bytes(saved["visao"].read_bytes())
    return {
        "envios_rows": envios_rows,
        "botoes_rows": botoes_rows,
        "envios": CONSOLIDATED["envios"],
        "botoes": CONSOLIDATED["botoes"],
        "leads": CONSOLIDATED["leads"],
        "visao": CONSOLIDATED["visao"],
    }


def read_envios_csv(path):
    pandas = get_pandas()
    try:
        return pandas.read_csv(path, sep=";", dtype=str, encoding="utf-8")
    except UnicodeDecodeError:
        return pandas.read_csv(path, sep=";", dtype=str, encoding="latin1")


def status_key(value):
    text = str(value or "").strip().lower()
    if text in {"read", "delivered", "sent", "undelivered"}:
        return text
    return text or "sem_status"


def build_envios_day_rows(uploaded_path):
    pandas = get_pandas()
    df = read_envios_csv(uploaded_path)
    required = ["message_date_time", "broadcast_description", "message_status", "intention_description"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Colunas ausentes no arquivo de envios: {', '.join(missing)}")

    df = df.copy()
    df["dt"] = pandas.to_datetime(df["message_date_time"], errors="coerce", dayfirst=True)
    df["hora_envio"] = df["dt"].dt.strftime("%H:%M")
    df["status_clean"] = df["message_status"].map(status_key)
    df["broadcast_description"] = df["broadcast_description"].fillna("").astype(str).str.strip()
    df["intention_description"] = df["intention_description"].fillna("").astype(str).str.strip()

    rows = []
    grouped = df.groupby("broadcast_description", dropna=False)
    for description, group in grouped:
        statuses = group["status_clean"].value_counts().to_dict()
        intentions = sorted({x for x in group["intention_description"] if x and x.lower() != "nan"})
        hours = sorted({x for x in group["hora_envio"].dropna() if x and x.lower() != "nat"})
        rows.append(
            {
                "description": description or "Sem descrição",
                "hour": ", ".join(hours) if hours else "Sem informação",
                "intention": " | ".join(intentions) if intentions else "Sem informação",
                "sent": int(statuses.get("sent", 0)),
                "delivered": int(statuses.get("delivered", 0)),
                "read": int(statuses.get("read", 0)),
                "undelivered": int(statuses.get("undelivered", 0)),
                "total": int(len(group)),
            }
        )
    return sorted(rows, key=lambda r: (r["hour"], r["description"]))


def envios_day_table_html(rows):
    total = {
        "sent": sum(r["sent"] for r in rows),
        "delivered": sum(r["delivered"] for r in rows),
        "read": sum(r["read"] for r in rows),
        "undelivered": sum(r["undelivered"] for r in rows),
        "total": sum(r["total"] for r in rows),
    }
    def br_num(value):
        return f"{int(value):,}".replace(",", ".")

    body = "\n".join(
        f"""
        <tr>
          <td>{html.escape(r['description'])}</td>
          <td>{html.escape(r['hour'])}</td>
          <td>{html.escape(r['intention'])}</td>
          <td class="num">{br_num(r['sent'])}</td>
          <td class="num">{br_num(r['delivered'])}</td>
          <td class="num">{br_num(r['read'])}</td>
          <td class="num">{br_num(r['undelivered'])}</td>
          <td class="num">{br_num(r['total'])}</td>
        </tr>
        """
        for r in rows
    )
    total_row = f"""
        <tr class="total-row">
          <td><strong>Total</strong></td>
          <td></td>
          <td></td>
          <td class="num"><strong>{br_num(total['sent'])}</strong></td>
          <td class="num"><strong>{br_num(total['delivered'])}</strong></td>
          <td class="num"><strong>{br_num(total['read'])}</strong></td>
          <td class="num"><strong>{br_num(total['undelivered'])}</strong></td>
          <td class="num"><strong>{br_num(total['total'])}</strong></td>
        </tr>
    """
    return f"""
    <div class="summary-strip">
      <div><span>Lotes encontrados</span><strong>{br_num(len(rows))}</strong></div>
      <div><span>Total de linhas</span><strong>{br_num(total['total'])}</strong></div>
      <div><span>Lidos</span><strong>{br_num(total['read'])}</strong></div>
      <div><span>Não entregues</span><strong>{br_num(total['undelivered'])}</strong></div>
    </div>
    <div class="pdf-actions" style="margin: 14px 0;">
      <button type="button" id="downloadEnviosExcel">Baixar Excel</button>
    </div>
    <div class="table-wrap tall">
      <table id="enviosDayTable" class="sortable-table">
        <thead>
          <tr>
            <th data-type="text">Descrição do envio</th>
            <th data-type="text">Hora</th>
            <th data-type="text">Intenção</th>
            <th class="num" data-type="number">Enviado</th>
            <th class="num" data-type="number">Entregue</th>
            <th class="num" data-type="number">Lido</th>
            <th class="num" data-type="number">Não entregue</th>
            <th class="num" data-type="number">Total</th>
          </tr>
        </thead>
        <tbody>{body}{total_row}</tbody>
      </table>
    </div>
    <script>
      (() => {{
        const table = document.getElementById("enviosDayTable");
        if (!table) return;
        const numberValue = (text) => Number(String(text || "0").replace(/\\./g, "").replace(",", "."));
        table.querySelectorAll("th").forEach((th, index) => {{
          th.style.cursor = "pointer";
          th.title = "Clique para ordenar";
          th.addEventListener("click", () => {{
            const type = th.dataset.type || "text";
            const current = th.dataset.order === "asc" ? "desc" : "asc";
            table.querySelectorAll("th").forEach((h) => delete h.dataset.order);
            th.dataset.order = current;
            const rows = [...table.tBodies[0].rows];
            rows.sort((a, b) => {{
              const av = a.cells[index].innerText.trim();
              const bv = b.cells[index].innerText.trim();
              const result = type === "number" ? numberValue(av) - numberValue(bv) : av.localeCompare(bv, "pt-BR");
              return current === "asc" ? result : -result;
            }});
            rows.forEach((row) => table.tBodies[0].appendChild(row));
          }});
        }});

        document.getElementById("downloadEnviosExcel")?.addEventListener("click", () => {{
          const html = `<!doctype html><html><head><meta charset="utf-8">
            <style>table{{border-collapse:collapse;width:100%;font-family:Arial,sans-serif}}th{{background:#25284F;color:#fff}}td,th{{border:1px solid #d9dee8;padding:8px;font-size:11pt}}</style>
            </head><body><h2>Conferência diária de envios</h2>${{table.outerHTML}}</body></html>`;
          const blob = new Blob([html], {{ type: "application/vnd.ms-excel;charset=utf-8" }});
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = `conferencia_envios_dia_${{new Date().toISOString().slice(0,10).replaceAll("-", "")}}.xls`;
          a.click();
          URL.revokeObjectURL(a.href);
        }});
      }})();
    </script>
    """


def save_envios_day_last(rows):
    DATA_STORE.mkdir(exist_ok=True)
    payload = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "rows": rows,
    }
    ENVIOS_DAY_LAST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_envios_day_last():
    if not ENVIOS_DAY_LAST.exists():
        return None
    try:
        return json.loads(ENVIOS_DAY_LAST.read_text(encoding="utf-8"))
    except Exception:
        return None


def envios_day_page_html(rows=None, generated_at=""):
    result = ""
    if rows:
        stamp = html.escape(generated_at or "")
        result = f"""
        <section class="panel master-panel wide-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Última consulta salva</p>
              <h2>Resultado da conferência</h2>
              <span>{stamp}</span>
            </div>
          </div>
          {envios_day_table_html(rows)}
        </section>
        """
    return f"""
    <!doctype html>
    <html lang="pt-BR">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Conferência diária de envios | Assis & Mollerke</title>
        <link rel="stylesheet" href="/styles.css" />
      </head>
      <body class="master-page">
        <main class="master-main">
          <section class="panel master-panel">
            <div class="section-head">
              <div>
                <p class="eyebrow">Conferência diária</p>
                <h1>Resumo do arquivo de envios</h1>
              </div>
              <a class="link-button" href="/master">Voltar ao Master</a>
            </div>
            <form action="/envios-dia" method="post" enctype="multipart/form-data" class="upload-form">
              <label>Arquivo de envios do dia (.csv)
                <input type="file" name="envios_dia" accept=".csv" required />
              </label>
              <button type="submit">Visualizar conferência</button>
            </form>
            <div class="master-note">
              <strong>Uso independente:</strong> esta tela apenas lê o arquivo selecionado e exibe a conferência por lote. Ela não altera o painel principal, não atualiza histórico e não substitui bases.
            </div>
          </section>
          {result}
        </main>
      </body>
    </html>
    """


class DashboardHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if clean in {"", "monitor", "banco"}:
            clean = "index.html"
        return str(WEB / clean)

    def auth_ok(self, role):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            user, password = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8").split(":", 1)
        except Exception:
            return False
        if role == "master":
            return user == MASTER_USER and password == MASTER_PASS
        return (user, password) in {(MASTER_USER, MASTER_PASS), (MONITOR_USER, MONITOR_PASS)}

    def require_auth(self, role):
        if self.auth_ok(role):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Basic realm="C6 Empresas {role}"')
        self.end_headers()
        self.wfile.write(b"Acesso restrito.")
        return False

    def do_GET(self):
        if self.path.startswith("/sync/manifest"):
            if not self.require_auth("master"):
                return
            body = json.dumps({"files": web_manifest_files()}, ensure_ascii=False, indent=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        if self.path.startswith("/sync/file/"):
            if not self.require_auth("master"):
                return
            name = Path(urllib.parse.unquote(self.path.split("/sync/file/", 1)[1].split("?", 1)[0])).name
            target = WEB / name
            if not target.exists() or not target.is_file():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(target.read_bytes())
            return
        if self.path.startswith("/health"):
            try:
                body = json.dumps(dashboard_health_payload(), ensure_ascii=False, indent=2)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))
            except Exception:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                body = json.dumps({"status": "error", "detail": traceback.format_exc()}, ensure_ascii=False)
                self.wfile.write(body.encode("utf-8"))
            return
        if self.path.startswith("/envios-dia"):
            if not self.require_auth("master"):
                return
            last = load_envios_day_last()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            rows = (last or {}).get("rows") or []
            generated_at = (last or {}).get("generated_at") or ""
            self.wfile.write(envios_day_page_html(rows, generated_at).encode("utf-8"))
            return
        elif self.path.startswith("/master"):
            if not self.require_auth("master"):
                return
            if should_proxy_upload_to_remote(self.headers):
                try:
                    mirror_remote_artifacts()
                except Exception:
                    pass
            self.path = "/master.html"
        elif self.path in {"/", "/index.html", "/monitor", "/banco"}:
            if not self.require_auth("monitor"):
                return
            if should_proxy_upload_to_remote(self.headers):
                try:
                    mirror_remote_artifacts()
                except Exception:
                    pass
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path == "/envios-dia":
            return self.handle_envios_day()
        if self.path == "/send-email":
            return self.handle_send_email()
        if self.path != "/upload":
            self.send_error(404)
            return
        if not self.require_auth("master"):
            return

        try:
            UPLOADS.mkdir(exist_ok=True)
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
            required = {
                "envios": "envios.csv",
                "botoes": "botoes.csv",
                "leads": "leads.xlsx",
                "visao": "visao.xlsx",
            }
            uploaded = {}
            for field, filename in required.items():
                item = form[field] if field in form else None
                if item is None or not getattr(item, "file", None):
                    self.send_error(400, f"Arquivo ausente: {field}")
                    return
                content = item.file.read()
                uploaded[field] = {"filename": filename, "content": content}

            if should_proxy_upload_to_remote(self.headers):
                proxy_upload_to_remote(uploaded)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                body = """
                <!doctype html><meta charset="utf-8">
                <link rel="stylesheet" href="/styles.css">
                <main class="master-main"><section class="panel master-panel">
                <p class="eyebrow">Importação sincronizada</p>
                <h1>Painel online atualizado</h1>
                <p>Os arquivos foram enviados ao painel online oficial e este ambiente local foi espelhado com os artefatos publicados.</p>
                <p>
                  <a class="link-button" href="/index.html">Abrir painel local</a>
                  <a class="link-button" href="https://painel-c6-empresas.onrender.com/master">Abrir Master online</a>
                  <a class="link-button" href="https://painel-c6-empresas.onrender.com/banco">Abrir Banco online</a>
                </p>
                </section></main>
                """
                self.wfile.write(body.encode("utf-8"))
                return

            saved = {}
            for field, item in uploaded.items():
                content = item["content"]
                filename = item["filename"]
                target = UPLOADS / filename
                target.write_bytes(content)
                archive_upload(field, filename, content)
                saved[field] = target

            consolidated = update_consolidated_files(saved)
            reload_processing_modules()
            build_data.FILES["envios"] = consolidated["envios"]
            build_data.FILES["botoes"] = consolidated["botoes"]
            build_data.FILES["leads"] = consolidated["leads"]
            build_data.FILES["visao"] = consolidated["visao"]
            build_data.main()
            create_report_pdf.build_pdf()
            create_report_pdf_v2.build_pdf()
        except Exception as exc:
            details = html.escape(traceback.format_exc())
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            body = f"""
            <!doctype html><meta charset="utf-8">
            <link rel="stylesheet" href="/styles.css">
            <main class="master-main"><section class="panel master-panel">
            <p class="eyebrow">Falha na importação</p>
            <h1>Não foi possível processar os arquivos</h1>
            <p>O servidor recebeu os arquivos, mas encontrou um erro no processamento. Abaixo está o detalhe técnico para correção.</p>
            <pre style="white-space:pre-wrap;background:#f7f8fb;border:1px solid #d9dee8;padding:12px;border-radius:6px;max-height:360px;overflow:auto">{details}</pre>
            <p><a class="link-button" href="/master#envio-email">Voltar para envio de e-mail</a></p>
            </section></main>
            """
            self.wfile.write(body.encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        envios_fmt = f"{consolidated['envios_rows']:,}".replace(",", ".")
        botoes_fmt = f"{consolidated['botoes_rows']:,}".replace(",", ".")
        body = f"""
        <!doctype html><meta charset="utf-8">
        <link rel="stylesheet" href="/styles.css">
        <main class="master-main"><section class="panel master-panel">
        <p class="eyebrow">Importação concluída</p>
        <h1>Painel atualizado</h1>
        <p>Os arquivos foram processados com sucesso e incorporados à base histórica.</p>
        <p>Envios no histórico: {envios_fmt} | Interações no histórico: {botoes_fmt}</p>
        <p>
          <a class="link-button" href="/index.html">Abrir painel</a>
          <a class="link-button" href="/relatorio_analitico_contas_abertas.xlsx">Baixar Excel analítico</a>
          <a class="link-button" href="/master#envio-email">Enviar relatório por e-mail</a>
        </p>
        </section></main>
        """
        self.wfile.write(body.encode("utf-8"))

    def handle_envios_day(self):
        if not self.require_auth("master"):
            return
        try:
            UPLOADS.mkdir(exist_ok=True)
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
            item = form["envios_dia"] if "envios_dia" in form else None
            if item is None or not getattr(item, "file", None):
                self.send_error(400, "Arquivo de envios ausente")
                return
            target = UPLOADS / "envios_conferencia_dia.csv"
            target.write_bytes(item.file.read())
            rows = build_envios_day_rows(target)
            save_envios_day_last(rows)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            body = envios_day_page_html(rows, "Consulta gerada agora")
            self.wfile.write(body.encode("utf-8"))
        except Exception:
            details = html.escape(traceback.format_exc())
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            body = f"""
            <!doctype html><meta charset="utf-8">
            <link rel="stylesheet" href="/styles.css">
            <main class="master-main"><section class="panel master-panel">
            <p class="eyebrow">Falha na conferência</p>
            <h1>Não foi possível ler o arquivo de envios</h1>
            <pre style="white-space:pre-wrap;background:#f7f8fb;border:1px solid #d9dee8;padding:12px;border-radius:6px;max-height:360px;overflow:auto">{details}</pre>
            <p><a class="link-button" href="/envios-dia">Voltar</a></p>
            </section></main>
            """
            self.wfile.write(body.encode("utf-8"))

    def handle_send_email(self):
        if not self.require_auth("master"):
            return
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        to_addr = (form.getfirst("to") or "").strip()
        cc_addr = (form.getfirst("cc") or SMTP_CC).strip()
        to_list = split_addresses(to_addr)
        cc_list = split_addresses(cc_addr)
        subject = (form.getfirst("subject") or "Assis & Mollerke - Relatório C6 Empresas").strip()
        body = (form.getfirst("body") or "").strip()
        if not to_list:
            self.send_error(400, "Destinatários ausentes")
            return

        pdf_version = (form.getfirst("pdf_version") or "v2").strip().lower()
        pdf_path = WEB / ("relatorio_c6_empresas.pdf" if pdf_version == "v1" else "relatorio_c6_empresas_v2.pdf")
        if not pdf_path.exists():
            reload_processing_modules()
            if pdf_version == "v1":
                create_report_pdf.build_pdf()
            else:
                create_report_pdf_v2.build_pdf()
        excel_path = WEB / f"relatorio_analitico_contas_abertas_{report_reference_date()[1] or 'referencia'}.xlsx"
        if not excel_path.exists():
            excel_path = WEB / "relatorio_analitico_contas_abertas.xlsx"

        msg = EmailMessage()
        msg["From"] = formataddr(("Assis & Mollerke", SMTP_USER))
        msg["To"] = ", ".join(to_list)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="amcob.com.br")
        msg["Reply-To"] = SMTP_USER
        normalized_body = body.replace("\r\n", "\n").replace("\r", "\n")
        msg.set_content(normalized_body)
        html_body = "<br>".join(
            line if line.strip() else "&nbsp;"
            for line in normalized_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").split("\n")
        )
        msg.add_alternative(f"<html><body style='font-family: Arial, sans-serif; font-size: 14px; color: #172033;'>{html_body}</body></html>", subtype="html")
        msg.add_attachment(
            pdf_path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=f"Relatorio_C6_Empresas_{report_reference_date()[1] or 'referencia'}.pdf",
        )
        if excel_path.exists():
            msg.add_attachment(
                excel_path.read_bytes(),
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=f"Relatorio_Analitico_Contas_Abertas_{report_reference_date()[1] or 'referencia'}.xlsx",
            )

        try:
            recipients = list(dict.fromkeys(to_list + cc_list))
            errors = send_pdf_email(msg, recipients)
            if errors:
                raise RuntimeError(f"destinatários recusados: {errors}")
        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"Falha ao enviar e-mail: {exc}".encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        body_html = """
        <!doctype html><meta charset="utf-8">
        <link rel="stylesheet" href="/styles.css">
        <main class="master-main"><section class="panel master-panel">
        <p class="eyebrow">E-mail enviado</p>
        <h1>Relatório encaminhado com sucesso</h1>
        <p>O PDF V2 e o Excel analítico foram enviados aos destinatários informados, com cópia automática.</p>
        <p><a class="link-button" href="/master#envio-email">Voltar para envio de e-mail</a></p>
        </section></main>
        """
        self.wfile.write(body_html.encode("utf-8"))


def run():
    port = int(os.environ.get("PORT", "8766"))
    server = ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler)
    print(
        json.dumps(
            {
                "status": "running",
                "monitor_path": "/banco",
                "master_path": "/master",
                "port": port,
            }
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    run()
