/* 可转债数据库前端逻辑：日期查询 + 搜索 + 排序 + 分页 + 手动刷新(6690) + 来源标记 */

// ===== 配置 =====
// 安全红线：GH_TOKEN（PAT）绝不能硬编码进本文件再 push 到公开仓库（全网可见 = 账号可被接管）。
// 正确做法：在同目录新建 docs/config.js（已被 .gitignore 忽略，不进仓库），内容如下：
//   window.__CB_CONFIG__ = { OWNER:"你的用户名", REPO:"convertible_bond_db", GH_TOKEN:"ghp_xxx", REFRESH_PASSWORD:"6690" };
// 该文件仅本机有效；不创建时手动刷新功能自动降级（按钮提示未配置），每日自动定时抓取不受影响。
let CONFIG = {
  OWNER: "你的GitHub用户名",
  REPO: "convertible_bond_db",
  GH_TOKEN: "",
  REFRESH_PASSWORD: "6690"
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
  const tag = STATE.source === "tencent_fallback"
    ? '<span class="source-tag fallback">腾讯兜底（字段不全）</span>'
    : '<span class="source-tag">东方财富</span>';
  const hint = $("hint");
  if (STATE.source === "tencent_fallback") {
    hint.style.display = "block";
    hint.textContent = "当日主源（东方财富）采集失败，已用腾讯行情兜底：仅含价格/涨跌幅等基础字段，转股溢价率、纯债价值等比价字段显示为「—」。";
  } else {
    hint.style.display = "none";
  }
  $("meta").innerHTML = `数据来源 ${tag}`;
}

async function loadIndex() {
  const resp = await fetch("index.json", { cache: "no-store" });
  STATE.index = await resp.json();
  const sel = $("dateSel");
  sel.innerHTML = "";
  const dates = STATE.index.available_dates || [];
  if (dates.length === 0) {
    sel.innerHTML = '<option value="">暂无数据</option>';
    return;
  }
  dates.slice().reverse().forEach((d) => {
    const o = document.createElement("option");
    o.value = d; o.textContent = d;
    sel.appendChild(o);
  });
  sel.value = dates[dates.length - 1]; // 默认最新
  const lu = STATE.index.last_update || "—";
  const ls = STATE.index.last_source === "tencent_fallback" ? "腾讯兜底" : "东方财富";
  sel.title = `最近更新：${lu} · 来源：${ls} · 共 ${STATE.index.total_days} 个交易日`;
  loadDay(sel.value);
}

// 手动刷新：密码 6690 鉴权 → 触发 workflow_dispatch
function openModal() { $("modalMask").style.display = "flex"; $("pwInput").value = ""; $("pwInput").focus(); }
function closeModal() { $("modalMask").style.display = "none"; }

async function triggerRefresh() {
  const pw = $("pwInput").value;
  if (pw !== CONFIG.REFRESH_PASSWORD) { toast("密码错误"); return; }
  closeModal();
  if (!CONFIG.GH_TOKEN || CONFIG.GH_TOKEN.startsWith("ghp_xxxx")) {
    toast("请在 app.js 配置 GH_TOKEN"); return;
  }
  toast("正在触发采集…");
  try {
    const url = `https://api.github.com/repos/${CONFIG.OWNER}/${CONFIG.REPO}/actions/workflows/crawl.yml/dispatches`;
    const r = await fetch(url, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${CONFIG.GH_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: "main", inputs: { password: pw } }),
    });
    if (r.status === 204) toast("已触发，稍后刷新页面查看");
    else toast("触发失败：HTTP " + r.status);
  } catch (e) {
    toast("触发异常：" + e.message);
  }
}

// 事件绑定
$("queryBtn").onclick = () => loadDay($("dateSel").value);
$("dateSel").onchange = () => loadDay($("dateSel").value);
$("pageSize").onchange = () => { STATE.pageSize = Number($("pageSize").value); renderPage(); };
$("search").oninput = () => { STATE.search = $("search").value; applyAndRender(); };
$("refreshBtn").onclick = openModal;
$("pwCancel").onclick = closeModal;
$("pwOk").onclick = triggerRefresh;
$("modalMask").onclick = (e) => { if (e.target === $("modalMask")) closeModal(); };

loadIndex();
