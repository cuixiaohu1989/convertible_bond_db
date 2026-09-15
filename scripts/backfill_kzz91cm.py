"""一次性任务：从 kzz.91cm.cn（转债罗盘）补采历史可转债快照数据。

用法（项目根目录执行）：
    python scripts/backfill_kzz91cm.py            # 补采最近 20 个交易日
    python scripts/backfill_kzz91cm.py 5          # 补采最近 5 个交易日

行为：
- 从「今日」往前逐日回溯，周末自动跳过；该日接口无数据则跳过（不计入天数）。
- 采集到 N 个有数据的交易日即停止。
- 结果写入 docs/data/<YYYY-MM-DD>.json（与每日自动采集同一格式），
  并合并更新 docs/index.json 的 available_dates / total_days。
- source 标记为 "kzz91cm"，与自动采集的 eastmoney / tencent_fallback 区分。

本脚本为一次性用途，不参与 GitHub Actions 定时流程。
"""
import os
import sys
import json
import time
import datetime
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DATA_DIR = os.path.join(ROOT, "docs", "data")
INDEX_PATH = os.path.join(ROOT, "docs", "index.json")

API = "http://kzz.91cm.cn/stock/snapshot/data/list"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://kzz.91cm.cn/snapshots",
}
PAGE_MAX = 60        # 单日最多翻页数（实际约 33 页）
SLEEP = 0.4          # 翻页间隔，防频率限制
DAYS_BACK_MAX = 60   # 最多回溯日历天数


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def fetch_day(date_str):
    """取单日全部记录。返回 (rows_raw, 是否有数据)。"""
    seen = {}
    for page in range(1, PAGE_MAX + 1):
        params = {
            "beginDate": date_str,
            "page": page,
            "pageSize": 1000,          # 服务端实际按 10 条/页返回
            "sortField": "curTrade.rank",
            "orderType": "ASC",
        }
        try:
            r = requests.get(API, params=params, headers=HEADERS, timeout=20)
            payload = r.json()
        except Exception as e:
            log(f"  ! {date_str} 第{page}页请求异常: {e}")
            break
        rows = payload.get("data") or []
        if not rows:
            break
        for it in rows:
            code = it.get("code")
            if code:
                seen[code] = it
        time.sleep(SLEEP)
    return list(seen.values()), bool(seen)


def _f(v):
    """转 float，非法值返回 None。"""
    if v is None:
        return None
    try:
        s = float(v)
        return s
    except (TypeError, ValueError):
        return None


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s not in ("-", "--") else None


def map_row(it):
    """转债罗盘单条 → 站点标准字段（缺失字段一律 null，前端显示「—」）。"""
    ct = it.get("curTrade") or {}
    kzz = it.get("kzz") or {}
    kzinfo = kzz.get("kzzInfo") or {}
    stinfo = kzz.get("stockInfo") or {}

    symbol = _s(it.get("symbol")) or ""      # 形如 sz127080
    market = "sh" if symbol.startswith("sh") else "sz"

    price = _f(ct.get("trade"))
    pct = _f(ct.get("changePercent"))
    amount = _f(ct.get("amount"))
    # 单价金额异常小（疑似单位不同）时保持原值，不做猜测换算
    premium = _f(it.get("premiumRate"))
    if premium is None:
        premium = _f(kzinfo.get("premiumRate"))

    rec = {
        # —— 核心 6 字段 ——
        "code": _s(it.get("code")),
        "name": _s(it.get("name")),
        "price": price,
        "change_pct": pct,
        "amount": amount,
        "premium_rate": premium,
        # —— 附带可得字段 ——
        "market": market,
        "change_amt": _f(ct.get("pricechange")),
        "high": _f(ct.get("high")),
        "low": _f(ct.get("low")),
        "open": _f(ct.get("open")),
        "prev_close": _f(ct.get("settlement")),
        "volume": _f(ct.get("volume")),
        "pure_bond_value": _f(it.get("pureBondValue")),
        "stock_code": _s((stinfo.get("symbol") or "").replace("sh", "").replace("sz", "")) or None,
        "stock_name": _s(stinfo.get("name")),
        "stock_price": _f(stinfo.get("trade")),
        "stock_change_pct": _f(stinfo.get("changepercent")),
        # —— 该源不提供 ——
        "convert_price": None,
        "convert_value": None,
        "bond_premium_rate": None,
        "put_price": None,
        "redeem_price": None,
        "maturity_price": None,
        "list_date": None,
        "convert_start_date": None,
        "ipo_date": None,
    }
    rec["double_low"] = round(price + premium, 2) if (price is not None and premium is not None) else None
    return rec


def pct_desc_key(r):
    v = r.get("change_pct")
    return (v is not None, v if v is not None else -1e18)


def write_day(date_str, rows):
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {
        "date": date_str,
        "source": "kzz91cm",
        "data": rows,
    }
    path = os.path.join(DATA_DIR, f"{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return path


def update_index(new_dates):
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, encoding="utf-8") as f:
            idx = json.load(f)
    else:
        idx = {}
    dates = set(idx.get("available_dates") or [])
    dates.update(new_dates)
    idx["available_dates"] = sorted(dates)
    idx["total_days"] = len(idx["available_dates"])
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    return idx


def main():
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    today = datetime.date.today()
    collected = []
    skipped = []
    day = today - datetime.timedelta(days=1)   # 不含今日（今日由每日自动采集覆盖）

    for _ in range(DAYS_BACK_MAX):
        if len(collected) >= want:
            break
        if day.weekday() >= 5:                 # 周末不交易
            day -= datetime.timedelta(days=1)
            continue
        ds = day.isoformat()
        log(f"查询 {ds}（已采集 {len(collected)}/{want}）")
        raws, ok = fetch_day(ds)
        if not ok:
            log(f"  无数据，跳过")
            skipped.append(ds)
            day -= datetime.timedelta(days=1)
            continue
        rows = [map_row(it) for it in raws]
        rows.sort(key=pct_desc_key, reverse=True)
        write_day(ds, rows)
        miss_prem = sum(1 for r in rows if r["premium_rate"] is None)
        log(f"  写入 {len(rows)} 条（溢价率缺失 {miss_prem}）")
        collected.append(ds)
        day -= datetime.timedelta(days=1)

    if collected:
        idx = update_index(collected)
        log(f"完成：新增 {len(collected)} 个交易日 → 共 {idx['total_days']} 天")
        log("日期：" + ", ".join(sorted(collected)))
    else:
        log("未采集到任何数据")
    if skipped:
        log(f"无数据跳过 {len(skipped)} 天：{', '.join(skipped)}")


if __name__ == "__main__":
    main()
