/* 可转债数据库前端逻辑：日历选日期 + 搜索 + 排序 + 分页 + CSV导出 + 手动刷新(跳转Actions) + 来源标记 */

// ===== 配置 =====
// 手动刷新不需要任何 token：按钮直接打开 GitHub Actions 页面由用户点击 Run workflow。
// OWNER/REPO 从 Pages 域名自动推断（<owner>.github.io/<repo>），无需配置。
let CONFIG = {
  OWNER: "你的GitHub用户名",
  REPO: "convertible_bond_db"
};
try { if (window.__CB_CONFIG__) CONFIG = Object.assign({}, CONFIG, window.__CB_CONFIG__); } catch (e) {}

// 表头列定义：[标题, 标准键, 类型]
// type: text=文本, pct=涨跌幅(带色彩), num=数值, wan=数值/1万, none=无排序
const COLUMNS = [
  ["代码", "code", "text"],
  ["名称", "name", "text"],
  ["现价", "price", "num"],
  ["涨跌幅%", "change_pct", "pct"],
  ["涨跌额", "change_amt", "num"],
  ["最高", "high", "num"],
  ["最低", "low", "num"],
  ["成交额(万)", "amount", "wan"],
  ["转股溢价率%", "premium_rate", "num"],
  ["双低", "double_low", "num"],
  ["转股价值", "convert_value", "num"],
  ["纯债价值", "pure_bond_value", "num"],
  ["正股", "stock_name", "text"],
];

let STATE = {
  index: null,
  current: [],      // 当日全量（已按 change_pct 降序）
  source: "",       // eastmoney / tencent_fallback
  date: "",
  filtered: [],
  page: 1,
  pageSize: 20,
  sortKey: "change_pct",
  sortDir: "desc",  // desc=高→低, asc=低→高
  search: "",
};

const $ = (id) => document.getElementById(id);

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2600);
}

function fmt(v, digits = 2) {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  if (Number.isNaN(n)) return null;
  return n.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function cls(v) {
  if (v === null || v === undefined) return "na";
  if (v > 0) return "up";
  if (v < 0) return "down";
  return "flat";
}

function cellHtml(col, rec) {
  const key = col[1], type = col[2];
  const v = rec[key];
  if (v === null || v === undefined) return '<td class="na">—</td>';
  if (type === "pct") {
    const sign = v > 0 ? "+" : "";
    return `<td class="${cls(v)}">${sign}${v.toFixed(2)}</td>`;
  }
  if (type === "num") {
    return `<td class="${cls(v)}">${fmt(v)}</td>`;
  }
  if (type === "wan") {
    return `<td>${fmt(v / 10000)}</td>`;
  }
  return `<td>${v}</td>`;
}

function buildHead() {
  const tr = $("headRow");
  tr.innerHTML = "";
  COLUMNS.forEach((c) => {
    const th = document.createElement("th");
    let arrow = "";
    if (STATE.sortKey === c[1]) arrow = STATE.sortDir === "desc" ? " ▼" : " ▲";
    th.innerHTML = `${c[0]}<span class="arrow">${arrow}</span>`;
    th.onclick = () => {
      if (STATE.sortKey === c[1]) {
        STATE.sortDir = STATE.sortDir === "desc" ? "asc" : "desc";
      } else {
        STATE.sortKey = c[1];
        STATE.sortDir = "desc";
      }
      applyAndRender();
    };
    tr.appendChild(th);
  });
}

function applyFilterSort() {
  let arr = STATE.current.slice();
  const q = STATE.search.trim().toLowerCase();
  if (q) {
    arr = arr.filter((r) =>
      [r.code, r.name, r.stock_code, r.stock_name]
        .some((x) => x && String(x).toLowerCase().includes(q))
    );
  }
  const k = STATE.sortKey, dir = STATE.sortDir === "desc" ? -1 : 1;
  arr.sort((a, b) => {
    const va = a[k], vb = b[k];
    if (va === null || va === undefined) return 1;
    if (vb === null || vb === undefined) return -1;
    if (typeof va === "string") return va.localeCompare(vb) * dir;
    return (va - vb) * dir;
  });
  STATE.filtered = arr;
  STATE.page = 1;
}

function renderPage() {
  const tbody = $("tbody");
  tbody.innerHTML = "";
  const total = STATE.filtered.length;
  const ps = STATE.pageSize;
  const pages = Math.max(1, Math.ceil(total / ps));
  if (STATE.page > pages) STATE.page = pages;
  const start = (STATE.page - 1) * ps;
  const slice = STATE.filtered.slice(start, start + ps);

  if (total === 0) {
    tbody.innerHTML = `<tr><td colspan="${COLUMNS.length}" class="empty">无数据</td></tr>`;
  } else {
    slice.forEach((r) => {
      const tr = document.createElement("tr");
      tr.innerHTML = COLUMNS.map((c) => cellHtml(c, r)).join("");
      tbody.appendChild(tr);
    });
  }
  renderPager(pages, total);
  const meta = $("meta");
  meta.innerHTML = `共 <b>${total}</b> 条 · 第 ${STATE.page}/${pages} 页`;
}

function renderPager(pages, total) {
  const p = $("pager");
  p.innerHTML = "";
  const mk = (label, page, opts = {}) => {
    const b = document.createElement("button");
    b.textContent = label;
    if (opts.active) b.classList.add("active");
    if (opts.disabled) b.disabled = true;
    if (!opts.disabled && !opts.active) b.onclick = () => { STATE.page = page; renderPage(); };
    return b;
  };
  p.appendChild(mk("« 首页", 1, { disabled: STATE.page === 1 }));
  p.appendChild(mk("‹ 上一页", STATE.page - 1, { disabled: STATE.page === 1 }));
  // 窗口化页码
  const win = 2;
  let lo = Math.max(1, STATE.page - win), hi = Math.min(pages, STATE.page + win);
  if (lo > 1) p.appendChild(mk("1", 1));
  if (lo > 2) { const s = document.createElement("span"); s.className = "info"; s.textContent = "…"; p.appendChild(s); }
  for (let i = lo; i <= hi; i++) p.appendChild(mk(String(i), i, { active: i === STATE.page }));
  if (hi < pages - 1) { const s = document.createElement("span"); s.className = "info"; s.textContent = "…"; p.appendChild(s); }
  if (hi < pages) p.appendChild(mk(String(pages), pages));
  p.appendChild(mk("下一页 ›", STATE.page + 1, { disabled: STATE.page === pages }));
  p.appendChild(mk("末页 »", pages, { disabled: STATE.page === pages }));
}

function applyAndRender() {
  applyFilterSort();
  buildHead();
  renderPage();
}

async function loadDay(date) {
  STATE.date = date;
  try {
    const resp = await fetch(`data/${date}.json`, { cache: "no-store" });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const json = await resp.json();
    STATE.current = json.data || [];
    STATE.source = json.source || "";
    STATE.search = "";
    $("search").value = "";
    showSource();
    applyAndRender();
  } catch (e) {
    $("tbody").innerHTML = `<tr><td colspan="${COLUMNS.length}" class="empty">加载 ${date} 失败：${e.message}</td></tr>`;
    $("pager").innerHTML = "";
  }
}

function showSource() {
  let tag;
  if (STATE.source === "tencent_fallback") {
    tag = '<span class="source-tag fallback">腾讯兜底（字段不全）</span>';
  } else if (STATE.source === "kzz91cm") {
    tag = '<span class="source-tag">转债罗盘（历史补采）</span>';
  } else {
    tag = '<span class="source-tag">东方财富</span>';
  }
  const hint = $("hint");
  if (STATE.source === "tencent_fallback") {
    hint.style.display = "block";
    hint.textContent = "当日主源（东方财富）采集失败，已用腾讯行情兜底：仅含价格/涨跌幅等基础字段，转股溢价率、纯债价值等比价字段显示为「—」。";
  } else if (STATE.source === "kzz91cm") {
    hint.style.display = "block";
    hint.textContent = "该日数据为历史补采（来源：转债罗盘 kzz.91cm.cn），含代码/名称/现价/涨跌幅/成交额/转股溢价率等字段，转股价值等少数字段缺失显示「—」。";
  } else {
    hint.style.display = "none";
  }
  $("meta").innerHTML = `数据来源 ${tag}`;
}

async function loadIndex() {
  const resp = await fetch("index.json", { cache: "no-store" });
  STATE.index = await resp.json();
  const dates = STATE.index.available_dates || [];
  if (dates.length === 0) {
    $("dateInput").value = "";
    const hint = $("hint");
    hint.style.display = "block";
    hint.textContent = "暂无任何交易日数据：采集可能尚未成功运行过，请点右上角「手动刷新」跳转 GitHub Actions 手动运行一次。";
    return;
  }
  STATE.dates = dates.slice();               // 升序
  AVAIL.clear();
  dates.forEach((d) => AVAIL.add(d));
  const latest = dates[dates.length - 1];
  setDate(latest, { load: true });
  const lu = STATE.index.last_update || "—";
  const lsMap = { eastmoney: "东方财富", tencent_fallback: "腾讯兜底", kzz91cm: "转债罗盘" };
  const ls = lsMap[STATE.index.last_source] || "暂无";
  $("dateInput").title = `最近更新：${lu} · 来源：${ls} · 共 ${STATE.index.total_days} 个交易日`;
  loadStatus();
}

// 读取诊断状态：若今日数据未覆盖（且非休市），前端红字告警，第一时间暴露定时任务未跑
async function loadStatus() {
  try {
    const r = await fetch("status.json", { cache: "no-store" });
    if (!r.ok) return;
    const s = await r.json();
    const banner = $("statusBanner");
    if (!banner) return;
    if (s.today_covered === false && s.reason && s.reason !== "non_trading_day") {
      banner.style.display = "block";
      banner.textContent = `⚠ 今日（${s.today}）数据尚未采集（状态：${s.reason}）。点右上角「手动刷新」运行一次，或等 17:10 安全网补采。`;
    } else {
      banner.style.display = "none";
    }
  } catch (e) {}
}

// ===== 日历日期选择 =====
const AVAIL = new Set();        // 有数据的日期 yyyy-mm-dd
const LATEST = () => (STATE.dates && STATE.dates.length) ? STATE.dates[STATE.dates.length - 1] : null;
let calY, calM;                 // 日历当前显示的 年 / 月(0-11)

function setDate(d, opts = {}) {
  STATE.date = d;
  $("dateInput").value = d;
  if (opts.load) loadDay(d);
}

function pad2(n) { return String(n).padStart(2, "0"); }

function buildCalHead() {
  const wd = $("calWd");
  wd.innerHTML = "";
  ["一", "二", "三", "四", "五", "六", "日"].forEach((x, i) => {
    const s = document.createElement("span");
    s.className = "wd" + (i >= 5 ? " weekend" : "");
    s.textContent = x;
    wd.appendChild(s);
  });
  $("calTitle").textContent = `${calY}年${pad2(calM + 1)}月`;
}

function renderCal() {
  buildCalHead();
  const grid = $("calGrid");
  grid.innerHTML = "";
  const sel = STATE.date;
  const todayStr = (() => {
    const t = new Date();
    return `${t.getFullYear()}-${pad2(t.getMonth() + 1)}-${pad2(t.getDate())}`;
  })();
  const first = new Date(calY, calM, 1);
  let lead = first.getDay() - 1;          // 周一为第一列
  if (lead < 0) lead = 6;
  const daysInMonth = new Date(calY, calM + 1, 0).getDate();
  for (let i = 0; i < lead; i++) grid.appendChild(document.createElement("span"));
  for (let d = 1; d <= daysInMonth; d++) {
    const key = `${calY}-${pad2(calM + 1)}-${pad2(d)}`;
    const el = document.createElement("div");
    el.className = "cal-day";
    el.textContent = d;
    const dow = new Date(calY, calM, d).getDay();
    if (dow === 0 || dow === 6) el.classList.add("weekend");
    if (key === todayStr) el.classList.add("today");
    if (key === sel) el.classList.add("sel");
    if (!AVAIL.has(key)) {
      el.classList.add("dim");
      el.title = "该日无数据";
    } else {
      el.title = "查询 " + key;
      el.onclick = () => {
        setDate(key, { load: true });
        closeCal();
      };
    }
    grid.appendChild(el);
  }
  const n = AVAIL.size;
  const foot = document.querySelector(".cal-empty");
  if (foot) foot.remove();
  const info = document.createElement("div");
  info.className = "cal-empty";
  info.textContent = `共 ${n} 个交易日有数据（深色为无数据日期）`;
  $("cal").insertBefore(info, $("calWd"));
}

function openCal() {
  if (!STATE.dates || !STATE.dates.length) { toast("暂无数据日期"); return; }
  const base = STATE.date || LATEST();
  const [y, m] = base.split("-").map(Number);
  calY = y; calM = m - 1;
  renderCal();
  const mask = $("calMask");
  mask.classList.add("open");
  // 定位：贴着输入框下方，避免溢出视口
  const r = $("dateInput").getBoundingClientRect();
  const cal = $("cal");
  cal.style.top = "0"; cal.style.left = "0";   // 先归零便于测量
  const w = cal.offsetWidth || 288;
  let left = r.left;
  if (left + w > window.innerWidth - 8) left = window.innerWidth - w - 8;
  cal.style.top = (r.bottom + 6) + "px";
  cal.style.left = Math.max(8, left) + "px";
}

function closeCal() { $("calMask").classList.remove("open"); }

function calShift(dMonth, dYear) {
  calM += dMonth;
  calY += dYear;
  if (calM < 0) { calM = 11; calY--; }
  if (calM > 11) { calM = 0; calY++; }
  renderCal();
}

// ===== 导出 CSV（Excel 友好：UTF-8 BOM） =====
function exportCsv() {
  if (!STATE.filtered || !STATE.filtered.length) { toast("当前无数据可导出"); return; }
  const esc = (s) => `"${String(s).replace(/"/g, '""')}"`;
  const headers = COLUMNS.map((c) => c[0]);
  const lines = [headers.map(esc).join(",")];
  STATE.filtered.forEach((r) => {
    const row = COLUMNS.map((c) => {
      let v = r[c[1]];
      if (v === null || v === undefined) return esc("");
      if (c[2] === "wan") v = (v / 10000).toFixed(2);
      else if (c[2] === "num" || c[2] === "pct") v = Number(v).toFixed(2);
      return esc(v);
    });
    lines.push(row.join(","));
  });
  const csv = "\uFEFF" + lines.join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `可转债_${STATE.date}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
  toast(`已导出 ${STATE.filtered.length} 条（含搜索/排序结果）`);
}

// 手动刷新：跳转 GitHub Actions 页面点 Run workflow（浏览器直连 API 需在公开页面暴露 PAT，不安全，已弃用）
function inferOwnerRepo() {
  try {
    const h = location.hostname;            // cuixiaohu1989.github.io
    const seg = location.pathname.split("/").filter(Boolean); // ["convertible_bond_db"]
    if (h.endsWith(".github.io") && seg.length) {
      return { owner: h.split(".")[0], repo: seg[0] };
    }
  } catch (e) {}
  return { owner: CONFIG.OWNER, repo: CONFIG.REPO };
}

function triggerRefresh() {
  const { owner, repo } = inferOwnerRepo();
  const url = `https://github.com/${owner}/${repo}/actions/workflows/crawl.yml`;
  toast("已打开 GitHub Actions 页，请点右侧 Run workflow");
  window.open(url, "_blank");
}

// 事件绑定
$("queryBtn").onclick = () => { if (STATE.date) loadDay(STATE.date); };
$("pageSize").onchange = () => { STATE.pageSize = Number($("pageSize").value); renderPage(); };
$("search").oninput = () => { STATE.search = $("search").value; applyAndRender(); };
$("refreshBtn").onclick = triggerRefresh;
$("exportBtn").onclick = exportCsv;
$("dateInput").onclick = openCal;
$("calMask").onclick = (e) => { if (e.target === $("calMask")) closeCal(); };
$("calClose").onclick = closeCal;
$("calPrevMonth").onclick = () => calShift(-1, 0);
$("calNextMonth").onclick = () => calShift(1, 0);
$("calPrevYear").onclick = () => calShift(0, -1);
$("calNextYear").onclick = () => calShift(0, 1);
$("calLatest").onclick = () => {
  const d = LATEST();
  if (d) { setDate(d, { load: true }); closeCal(); }
};
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeCal(); });

loadIndex();
