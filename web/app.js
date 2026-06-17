const DATA = window.C6_DASHBOARD_DATA;
let selectedMonth = DATA.months.at(-1);
let selectedDay = null;
const monitorRoute = ["/banco", "/monitor"].includes(window.location.pathname);
let bankMode = monitorRoute;

const brDate = new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Cuiaba" });
const brNumber = new Intl.NumberFormat("pt-BR");
const brPercent = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function fmt(n) {
  return brNumber.format(Number(n || 0));
}

function pct(n) {
  return `${brPercent.format(Number(n || 0))}%`;
}

function datePt(value) {
  if (!value) return "-";
  const [y, m, d] = value.split("-").map(Number);
  return brDate.format(new Date(y, m - 1, d));
}

function monthPt(value) {
  if (!value) return "-";
  const [y, m] = value.split("-").map(Number);
  return new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" }).format(new Date(y, m - 1, 1));
}

function refStamp() {
  const day = currentDay();
  return day?.date ? day.date.replaceAll("-", "") : selectedMonth.replace("-", "");
}

function byId(id) {
  return document.getElementById(id);
}

function monthRows() {
  return DATA.daily.filter((row) => row.month === selectedMonth);
}

function currentDay() {
  const rows = monthRows();
  return rows.find((row) => row.date === selectedDay) || rows.at(-1) || DATA.daily.at(-1);
}

function previousDay() {
  const rows = monthRows();
  const idx = rows.findIndex((row) => row.date === selectedDay);
  return idx > 0 ? rows[idx - 1] : null;
}

function weekDisplay(row) {
  if (row?.label) return row.label;
  return row?.startDate && row?.endDate ? `${datePt(row.startDate)} a ${datePt(row.endDate)}` : "Semana";
}

function deltaHtml(delta) {
  const val = Number(delta || 0);
  const cls = val > 0 ? "up" : val < 0 ? "down" : "";
  const sign = val > 0 ? "+" : "";
  return `<div class="delta ${cls}">${sign}${fmt(val)} vs dia anterior</div>`;
}

function cellValue(value, numeric = false) {
  if (value === null || value === undefined || value === "") return "";
  return numeric && typeof value === "number" ? fmt(value) : value;
}

function renderFilters() {
  byId("monthSelect").innerHTML = DATA.months
    .map((m) => `<option value="${m}" ${m === selectedMonth ? "selected" : ""}>${monthPt(m)}</option>`)
    .join("");

  const days = monthRows();
  selectedDay = selectedDay && days.some((d) => d.date === selectedDay) ? selectedDay : days.at(-1)?.date;
  byId("daySelect").innerHTML = days
    .map((d) => `<option value="${d.date}" ${d.date === selectedDay ? "selected" : ""}>${datePt(d.date)}</option>`)
    .join("");
}

function renderHeader() {
  const day = currentDay();
  byId("periodLabel").textContent = day ? datePt(day.date) : "-";
  byId("generatedAt").textContent = new Date(DATA.generatedAt).toLocaleString("pt-BR");
  byId("modeLabel").textContent = bankMode ? "Banco C6 | somente leitura" : "Master";
  byId("bankModeBtn").textContent = bankMode ? "Sair da visão Banco" : "Visão Banco";
  document.body.classList.toggle("bank-mode", bankMode);
  document.body.classList.toggle("monitor-route", monitorRoute);
}

function renderKpis() {
  const day = currentDay();
  const prev = previousDay();
  const items = [
    { label: "Envios", value: day.sent, delta: day.sentDelta },
    { label: "Envios para contas abertas", value: day.qualificationSent, delta: day.qualificationSentDelta },
    { label: "Envios positivos", value: day.positiveSent, delta: day.positiveSentDelta },
    { label: "Não enviados", value: day.undelivered, delta: day.undeliveredDelta },
    { label: "Interações totais", value: day.buttonInteractions, delta: day.buttonInteractionsDelta },
    { label: "Contatos interessados", value: day.interactions, delta: day.interactionsDelta },
    { label: "Leads enviados", value: day.indicated, delta: day.indicatedDelta },
    { label: "Contas convertidas", value: day.opened, delta: day.openedDelta },
    { label: "Abertas no período", value: day.openedInPeriod, delta: day.openedInPeriodDelta },
    { label: "Com Pix", value: day.pixOpen, delta: day.pixOpenDelta },
    { label: "% interações", value: day.buttonInteractionRate, previous: prev?.buttonInteractionRate, percent: true },
    { label: "% interesse", value: day.interactionRate, previous: prev?.interactionRate, percent: true },
    { label: "% conversão", value: day.openingRate, previous: prev?.openingRate, percent: true },
  ];

  byId("kpis").innerHTML = items
    .map((item) => {
      const footer = item.percent
        ? `<div class="delta">Dia anterior: ${item.previous === undefined ? "-" : pct(item.previous)}</div>`
        : deltaHtml(item.delta);
      return `<article class="kpi"><span>${item.label}</span><strong>${item.percent ? pct(item.value) : fmt(item.value)}</strong>${footer}</article>`;
    })
    .join("");
}

function renderFunnel() {
  const day = currentDay();
  const steps = [
    ["Envios", day.sent, "total"],
    ["Contas abertas", day.qualificationSent, pct(day.qualificationRate)],
    ["Positivos", day.positiveSent, pct(day.positiveRate)],
    ["Lidos", day.read, pct(day.readRate)],
    ["Interações", day.buttonInteractions, pct(day.buttonInteractionRate)],
    ["Interessados", day.interactions, pct(day.interactionRate)],
    ["Leads", day.indicated, pct(day.indicationRate)],
    ["Convertidas", day.opened, pct(day.openingRate)],
    ["Abertas", day.openedInPeriod, "data abertura"],
    ["Pix", day.pixOpen, pct(day.pixRate)],
  ];
  byId("funnelChart").innerHTML = steps
    .map(([label, value, sub]) => `<div class="funnel-step"><span>${label}</span><strong>${fmt(value)}</strong><span>${sub}</span></div>`)
    .join("");
}

function pathFor(rows, key, x0, y0, w, h, max) {
  return rows
    .map((row, i) => {
      const x = x0 + (rows.length === 1 ? w / 2 : (i / (rows.length - 1)) * w);
      const y = y0 + h - (Number(row[key] || 0) / max) * h;
      return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function renderDailyChart() {
  const rows = monthRows();
  const max = Math.max(1, ...rows.map((r) => Math.max(r.indicated, r.opened, r.openedInPeriod, r.interactions)));
  const x0 = 54;
  const y0 = 24;
  const w = 880;
  const h = 205;
  const grid = [0, 0.25, 0.5, 0.75, 1]
    .map((p) => `<line class="axis" x1="${x0}" x2="${x0 + w}" y1="${y0 + h - p * h}" y2="${y0 + h - p * h}"></line>`)
    .join("");
  const labels = rows
    .map((r, i) => {
      const x = x0 + (rows.length === 1 ? w / 2 : (i / (rows.length - 1)) * w);
      return `<text class="chart-label" x="${x}" y="260" text-anchor="middle">${r.date.slice(8)}</text>`;
    })
    .join("");
  byId("dailyChart").innerHTML = `
    ${grid}
    <path class="line-indicated" d="${pathFor(rows, "indicated", x0, y0, w, h, max)}"></path>
    <path class="line-open" d="${pathFor(rows, "opened", x0, y0, w, h, max)}"></path>
    <text class="chart-label" x="54" y="18">Leads enviados (azul) | Contas convertidas (dourado)</text>
    <text class="chart-label" x="54" y="248">Dias do mês</text>
    ${labels}
  `;
}

function renderWeekly() {
  const weeks = DATA.weekly.filter((r) => monthRows().some((d) => d.week === r.period));
  const max = Math.max(1, ...weeks.map((r) => r.opened));
  byId("weeklyBars").innerHTML = weeks
    .map((r) => {
      const label = weekDisplay(r);
      return `<div class="bar-row"><strong>${label}</strong><div class="bar-track"><div class="bar-fill" style="width:${(r.opened / max) * 100}%"></div></div><span>${fmt(r.opened)} convertidas | ${fmt(r.openedInPeriod)} abertas | ${fmt(r.indicated)} leads</span></div>`;
    })
    .join("");
}

function renderMonthTotals() {
  const row = DATA.monthly.find((r) => r.period === selectedMonth) || {};
  byId("monthTotals").innerHTML = [
    [row.label || monthPt(selectedMonth), ""],
    ["Envios", row.sent],
    ["Contas abertas", row.qualificationSent],
    ["Positivos", row.positiveSent],
    ["Interações", row.buttonInteractions],
    ["Interessados", row.interactions],
    ["Leads", row.indicated],
    ["Convertidas", row.opened],
    ["Abertas no período", row.openedInPeriod],
    ["Pix", row.pixOpen],
    ["Conversão", pct(row.openingRate)],
  ]
    .map(([label, value]) => `<div class="total-card"><span>${label}</span><strong>${value === "" ? "" : typeof value === "string" ? value : fmt(value)}</strong></div>`)
    .join("");
}

function renderTable(id, columns, rows) {
  const head = `<thead><tr>${columns.map((c) => `<th class="${c.num ? "num" : ""}">${c.label}</th>`).join("")}</tr></thead>`;
  const body = rows
    .map(
      (row) =>
        `<tr>${columns
          .map((c) => `<td class="${c.num ? "num" : ""}">${cellValue(typeof c.value === "function" ? c.value(row) : row[c.key], c.num)}</td>`)
          .join("")}</tr>`
    )
    .join("");
  byId(id).innerHTML = head + `<tbody>${body}</tbody>`;
}

function renderComparison() {
  renderTable(
    "comparisonTable",
    [
      { label: "Data", value: (r) => datePt(r.date) },
      { label: "Envios", key: "sent", num: true },
      { label: "Contas abertas", key: "qualificationSent", num: true },
      { label: "Positivos", key: "positiveSent", num: true },
      { label: "Não enviados", key: "undelivered", num: true },
      { label: "Interações", key: "buttonInteractions", num: true },
      { label: "Interessados", key: "interactions", num: true },
      { label: "Leads", key: "indicated", num: true },
      { label: "Convertidas", key: "opened", num: true },
      { label: "Abertas", key: "openedInPeriod", num: true },
      { label: "Pix", key: "pixOpen", num: true },
      { label: "% interações", value: (r) => pct(r.buttonInteractionRate) },
      { label: "% interesse", value: (r) => pct(r.interactionRate) },
      { label: "% conversão", value: (r) => pct(r.openingRate) },
      { label: "Variação conversões", key: "openedDelta", num: true },
      { label: "Variação abertas", key: "openedInPeriodDelta", num: true },
    ],
    monthRows()
  );
}

function renderHours() {
  const ranked = [...DATA.hours].filter((h) => h.sent || h.interactions || h.read).sort((a, b) => b.interactions - a.interactions).slice(0, 8);
  const max = Math.max(1, ...ranked.map((h) => h.interactions));
  byId("hourBars").innerHTML = ranked
    .map(
      (h, idx) => `<div class="rank-row">
        <div class="rank-pos">${idx + 1}</div>
        <div class="rank-main">
          <div class="rank-top"><strong>${h.hour}</strong><span>${fmt(h.interactions)} contatos interessados</span></div>
          <div class="rank-track"><div style="width:${(h.interactions / max) * 100}%"></div></div>
          <div class="rank-sub">${fmt(h.read)} lidos | ${fmt(h.sent)} envios | ${pct(h.responseRate)} sobre envios</div>
        </div>
      </div>`
    )
    .join("");

  const bestVolume = [...DATA.hours].sort((a, b) => b.interactions - a.interactions).slice(0, 3);
  const bestRate = [...DATA.hours].filter((h) => h.sent >= 50).sort((a, b) => b.responseRate - a.responseRate).slice(0, 3);
  byId("hourInsights").innerHTML = `
    <div class="insight"><strong>Maior volume</strong><br>${bestVolume.map((h) => `${h.hour} (${fmt(h.interactions)})`).join(", ")}</div>
    <div class="insight"><strong>Melhor taxa</strong><br>${bestRate.map((h) => `${h.hour} (${pct(h.responseRate)})`).join(", ")}</div>
    <div class="insight"><strong>Critério</strong><br>Ranking por contatos interessados em cada horário.</div>
  `;
}

function renderAccounts() {
  const rows = DATA.foundationMonths.filter((row) => row.month === selectedMonth);
  renderTable(
    "accountsTable",
    [
      { label: "Mês de fundação", key: "foundationMonth" },
      { label: "Abertas no período", key: "opened", num: true },
      { label: "Com Pix", key: "pixOpen", num: true },
      { label: "% Pix", value: (r) => pct((r.pixOpen / Math.max(r.opened, 1)) * 100) },
    ],
    rows
  );
}

function renderExecutive() {
  const day = currentDay();
  const month = DATA.monthly.find((r) => r.period === selectedMonth) || {};
  byId("executiveSummary").innerHTML = [
    ["Resultado diário", `${fmt(day.interactions)} contatos interessados em ${datePt(day.date)}.`],
    ["Contas abertas", `${fmt(day.qualificationSent)} envios para clientes que já possuem conta aberta.`],
    ["Interações", `${fmt(day.buttonInteractions)} interações totais, equivalentes a ${pct(day.buttonInteractionRate)} dos envios positivos.`],
    ["Conversão", `${pct(day.openingRate)} dos leads viraram contas convertidas pela data da indicação.`],
    ["Aberturas", `${fmt(day.openedInPeriod)} contas foram abertas pela data real de abertura.`],
    ["Regra de data", "Conversão usa data da indicação; aberturas do período usam data da abertura da conta."],
    ["Acumulado mensal", `${fmt(month.sent)} envios, ${fmt(month.indicated)} leads, ${fmt(month.opened)} conversões e ${fmt(month.openedInPeriod)} aberturas.`],
  ]
    .map(([title, text]) => `<div class="exec-card"><strong>${title}</strong>${text}</div>`)
    .join("");
}

function tableData(kind) {
  const day = currentDay();
  const month = DATA.monthly.find((r) => r.period === selectedMonth) || {};
  const funnel = [
    { etapa: "Envios", valor: day.sent },
    { etapa: "Envios para contas abertas", valor: day.qualificationSent },
    { etapa: "Envios positivos", valor: day.positiveSent },
    { etapa: "Não enviados", valor: day.undelivered },
    { etapa: "Interações totais", valor: day.buttonInteractions },
    { etapa: "Contatos interessados", valor: day.interactions },
    { etapa: "Leads enviados", valor: day.indicated },
    { etapa: "Contas convertidas", valor: day.opened },
    { etapa: "Abertas no período", valor: day.openedInPeriod },
    { etapa: "Com chave Pix", valor: day.pixOpen },
  ];
  const mapRows = (rows) =>
    rows.map((r) => ({
      data: r.date || r.period,
      envios: r.sent,
      envios_contas_abertas: r.qualificationSent,
      positivos: r.positiveSent,
      nao_enviados: r.undelivered,
      lidos: r.read,
      interacoes_totais: r.buttonInteractions,
      contatos_interessados: r.interactions,
      leads_enviados: r.indicated,
      contas_convertidas: r.opened,
      contas_abertas_periodo: r.openedInPeriod,
      pix: r.pixOpen,
      perc_interesse: r.interactionRate,
      perc_interacoes_sobre_positivos: r.buttonInteractionRate,
      perc_conversao: r.openingRate,
    }));
  if (kind === "funnel") return funnel;
  if (kind === "daily" || kind === "comparison") return mapRows(monthRows());
  if (kind === "weekly") return mapRows(DATA.weekly.filter((r) => monthRows().some((d) => d.week === r.period)));
  if (kind === "monthly") return mapRows([month]);
  if (kind === "hours") return DATA.hours;
  if (kind === "accounts") return DATA.foundationMonths.filter((a) => a.month === selectedMonth);
  return [];
}

function downloadExcel(kind) {
  const rows = tableData(kind);
  const headers = Object.keys(rows[0] || {});
  const title = {
    funnel: "Funil do dia",
    daily: "Evolução diária",
    comparison: "Comparativo dia a dia",
    weekly: "Evolução semanal",
    monthly: "Resumo mensal",
    hours: "Análise de horários",
    accounts: "Mês de fundação das empresas",
  }[kind] || "Exportação";
  const period = byId("periodLabel").textContent;
  const html = `
    <html>
      <head>
        <meta charset="utf-8">
        <style>
          body { font-family: Aptos, Segoe UI, Arial, sans-serif; color: #151b2d; }
          table { border-collapse: collapse; width: 100%; }
          th { background: #25284f; color: #fff; font-weight: 700; }
          td, th { border: 1px solid #dbe0ea; padding: 8px; font-size: 11pt; }
          .meta td { border: 0; padding: 4px 0; }
          .confidential { color: #25284f; font-weight: 700; letter-spacing: 1px; }
        </style>
      </head>
      <body>
        <table class="meta">
          <tr><td><strong>Assis & Mollerke</strong></td></tr>
          <tr><td><strong>${title}</strong></td></tr>
          <tr><td>Período: ${period}</td></tr>
          <tr><td>Gerado em: ${new Date(DATA.generatedAt).toLocaleString("pt-BR")}</td></tr>
          <tr><td class="confidential">CONFIDENCIAL - uso restrito</td></tr>
          <tr><td>Todos os direitos reservados à Assis & Mollerke.</td></tr>
        </table>
        <br>
        <table>
          <thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
          <tbody>${rows.map((r) => `<tr>${headers.map((h) => `<td>${r[h] ?? ""}</td>`).join("")}</tr>`).join("")}</tbody>
        </table>
      </body>
    </html>`;
  const blob = new Blob([html], { type: "application/vnd.ms-excel;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `c6_${kind}_${selectedMonth}.xls`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function renderAll() {
  renderFilters();
  renderHeader();
  renderKpis();
  renderFunnel();
  renderDailyChart();
  renderWeekly();
  renderMonthTotals();
  renderComparison();
  renderHours();
  renderAccounts();
  renderExecutive();
}

byId("monthSelect").addEventListener("change", (event) => {
  selectedMonth = event.target.value;
  selectedDay = null;
  renderAll();
});

byId("daySelect").addEventListener("change", (event) => {
  selectedDay = event.target.value;
  renderAll();
});

byId("bankModeBtn").addEventListener("click", () => {
  if (monitorRoute) return;
  bankMode = !bankMode;
  renderAll();
});

byId("pdfBtn").addEventListener("click", () => {
  window.open(`/relatorio_c6_empresas_v2_${refStamp()}.pdf?v=${Date.now()}`, "_blank");
});

byId("analyticBtn").addEventListener("click", () => {
  window.open(`/relatorio_analitico_contas_abertas_${refStamp()}.xlsx?v=${Date.now()}`, "_blank");
});

document.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-export]");
  if (btn) downloadExcel(btn.dataset.export);
});

renderAll();
