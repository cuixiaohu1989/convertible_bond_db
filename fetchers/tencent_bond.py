"""腾讯行情接口（兜底源）。纯 requests + GBK 解码。

字段位置基于公开文档（qt.gtimg.cn），首次云端运行应通过 debug 样本校验。
若位置漂移导致解析失败，仅保留可解析的价格字段，其余填 null。
"""
import os
import json
import time
import datetime
import requests

from core.logger import info, warn, error

URL = "http://qt.gtimg.cn/q="
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://gu.qq.com/",
}
TIMEOUT = 15
MAX_RETRY = 3
BATCH = 80  # 每批代码数，避免 URL 过长

# 腾讯 `~` 分隔字段位置（与开工方案 4.2 一致）
POS = {
    "price": 3,
    "open": 4,
    "prev_close": 5,
    "change_amt": 30,
    "change_pct": 31,
    "volume": 32,
    "amount": 33,
}

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIVERSE_PATH = os.path.join(_BASE, "bond_universe.json")


def _to_float(v):
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "-", "--", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _pct_desc_key(r):
    """涨跌幅降序键：None 置底，0.0 不被 or 误判为假值。"""
    v = r.get("change_pct")
    return (v is not None, v if v is not None else -1e18)


def load_universe():
    """读取 bond_universe.json 返回转债清单。缺失返回空列表。"""
    if not os.path.exists(UNIVERSE_PATH):
        return []
    try:
        with open(UNIVERSE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("bonds", [])
    except Exception as e:
        warn(f"读取 bond_universe.json 失败: {e}", "TENCENT")
        return []


def save_universe(rows):
    """由东财标准记录写 bond_universe.json（仅 code/name/market）。"""
    bonds = [
        {"code": r.get("code"), "name": r.get("name"), "market": r.get("market")}
        for r in rows
        if r.get("code")
    ]
    payload = {"updated": datetime.date.today().isoformat(), "bonds": bonds}
    with open(UNIVERSE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    info(f"已刷新 bond_universe.json，共 {len(bonds)} 条", "TENCENT")


def _parse_line(line):
    """解析单行 v_sh113050="..."; 返回 (market_code, fields_list)。"""
    if "=" not in line:
        return None, None
    key, _, rest = line.partition("=")
    market_code = key[2:] if key.startswith("v_") else key  # 去前缀 v_
    rest = rest.strip().strip(";").strip("\"")
    if not rest:
        return market_code, None
    return market_code, rest.split("~")


def _map_code(market, code):
    return f"{market}{code}"


def fetch_tencent(bonds):
    """用 bond_universe 清单抓腾讯行情，降级返回基础字段。"""
    if not bonds:
        raise ValueError("universe 为空，无法兜底")
    # 按市场前缀分组
    by_market = {}
    for b in bonds:
        code = b.get("code")
        market = b.get("market") or ("sh" if str(code).startswith("11") else "sz")
        by_market.setdefault(market, []).append(b)

    results = {}
    for market, group in by_market.items():
        codes = [_map_code(market, b.get("code")) for b in group]
        # 分批请求
        for i in range(0, len(codes), BATCH):
            batch = codes[i:i + BATCH]
            q = ",".join(batch)
            for attempt in range(1, MAX_RETRY + 1):
                try:
                    resp = requests.get(URL + q, headers=HEADERS, timeout=TIMEOUT)
                    resp.encoding = "gbk"
                    text = resp.text
                    for line in text.strip().split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        mk, fields = _parse_line(line)
                        if fields is None:
                            continue
                        # 用 market_code 反查 universe 的 name
                        pure = mk[2:] if mk.startswith(("sh", "sz")) else mk
                        meta = next(
                            (g for g in group if str(g.get("code")) == pure), None
                        )
                        rec = {
                            "code": pure,
                            "name": meta.get("name") if meta else None,
                            "market": market,
                        }
                        for key, pos in POS.items():
                            rec[key] = _to_float(fields[pos]) if pos < len(fields) else None
                        # 比价表字段兜底为 null
                        for k in ("stock_price", "stock_change_pct", "stock_code",
                                  "stock_name", "convert_price", "convert_value",
                                  "premium_rate", "bond_premium_rate",
                                  "pure_bond_value", "put_price", "redeem_price",
                                  "maturity_price", "list_date", "convert_start_date",
                                  "ipo_date", "double_low"):
                            rec[k] = None
                        results[pure] = rec
                    break
                except Exception as e:
                    warn(f"腾讯第{attempt}次失败: {e}", "TENCENT")
                    if attempt < MAX_RETRY:
                        time.sleep(2 ** attempt)
                    else:
                        raise

    rows = list(results.values())
    if not rows:
        raise ValueError("腾讯未解析到任何记录")
    # 按涨跌幅降序
    rows.sort(key=_pct_desc_key, reverse=True)
    info(f"腾讯兜底获取 {len(rows)} 条", "TENCENT")
    return {"data": rows}
