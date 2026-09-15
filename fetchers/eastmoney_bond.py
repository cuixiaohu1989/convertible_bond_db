"""东方财富可转债比价表接口（主源）。纯 requests。"""
import time
import datetime
import requests

from core.logger import info, warn, error

# 比价表板块过滤：可转债
FS = "b:MK0354"

# 26 个东财字段 → 标准键
FIELDS = [
    "f12", "f14",      # code, name
    "f2", "f3", "f4",  # price, change_pct, change_amt
    "f15", "f16", "f17", "f18",  # high, low, open, prev_close
    "f5", "f6",        # volume, amount
    "f230", "f231", "f232", "f233",  # stock_price, stock_change_pct, stock_code, stock_name
    "f234", "f235", "f236", "f237",  # convert_price, convert_value, premium_rate, bond_premium_rate
    "f229",            # pure_bond_value
    "f238", "f239", "f240",  # put_price, redeem_price, maturity_price
    "f227", "f241", "f242",  # list_date, convert_start_date, ipo_date
]

# 东财字段 → 标准键（数值字段统一转 float，字符串字段保留）
NUMERIC_FIELDS = {
    "f2": "price", "f3": "change_pct", "f4": "change_amt",
    "f15": "high", "f16": "low", "f17": "open", "f18": "prev_close",
    "f5": "volume", "f6": "amount",
    "f230": "stock_price", "f231": "stock_change_pct",
    "f234": "convert_price", "f235": "convert_value",
    "f236": "premium_rate", "f237": "bond_premium_rate",
    "f229": "pure_bond_value",
    "f238": "put_price", "f239": "redeem_price", "f240": "maturity_price",
}
STRING_FIELDS = {
    "f12": "code", "f14": "name",
    "f232": "stock_code", "f233": "stock_name",
    "f227": "list_date", "f241": "convert_start_date", "f242": "ipo_date",
}

URL = "https://push2.eastmoney.com/api/qt/clist/get"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}

# 东财公开 ut 令牌（与 AKShare bond_cov_comparison 一致；缺它部分网关返回 data:null）
UT = "bd1d9ddb04089700cf9c27f6f7426281"

TIMEOUT = 15
MAX_RETRY = 3


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s in ("", "-", "--", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_str(v):
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "-", "--", "None"):
        return None
    return s


def _market_of(code):
    """转债代码 11* 为沪市，12* 为深市。"""
    if not code:
        return "sh"
    return "sh" if code.startswith("11") else "sz"


def _pct_desc_key(r):
    """涨跌幅降序键：None 置底，0.0 不被 or 误判为假值。"""
    v = r.get("change_pct")
    return (v is not None, v if v is not None else -1e18)


def _map_row(item):
    """将东财 diff 单条映射为标准键字典。"""
    rec = {}
    for fid, key in NUMERIC_FIELDS.items():
        rec[key] = _to_float(item.get(fid))
    for fid, key in STRING_FIELDS.items():
        rec[key] = _to_str(item.get(fid))
    # 派生：双低 = 价格 + 转股溢价率
    price = rec.get("price")
    premium = rec.get("premium_rate")
    if price is not None and premium is not None:
        rec["double_low"] = round(price + premium, 2)
    else:
        rec["double_low"] = None
    rec["market"] = _market_of(rec.get("code"))
    return rec


def _params(variant):
    """三组参数变体：0=标准(带ut) 1=AKShare同款pz 2=去掉fltt/invt。"""
    p = {
        "pn": 1,
        "pz": 5000,
        "po": 1,          # 按 fid 降序（涨跌幅高→低）
        "np": 1,
        "ut": UT,
        "fltt": 2,        # 数值字段返回可读浮点
        "invt": 2,
        "fid": "f3",      # 涨跌幅
        "fs": FS,
        "fields": ",".join(FIELDS),
    }
    if variant == 1:
        p["pz"] = 50000
    elif variant == 2:
        p.pop("fltt", None)
        p.pop("invt", None)
    return p


def fetch_eastmoney():
    """抓取东方财富可转债比价表全量。失败抛异常（由调用方重试/兜底）。"""
    last_err = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            params = _params(attempt - 1)
            info(f"东财请求 第{attempt}次 attempt(变体{attempt - 1})", "EM")
            resp = requests.get(URL, params=params, headers=HEADERS,
                                timeout=TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            # data 可能是 null（缺 ut / 网关拦截），必须 or {} 兜住
            data = payload.get("data") or {}
            diff = data.get("diff") or []
            if not diff:
                snippet = resp.text[:200].replace("\n", " ")
                raise ValueError(
                    f"data.diff 为空 rc={payload.get('rc')} body={snippet}")
            rows = [_map_row(it) for it in diff]
            # 接口已按涨跌幅降序(po=1)，代码兜底再排一次
            rows.sort(key=_pct_desc_key, reverse=True)
            info(f"东财成功获取 {len(rows)} 条", "EM")
            return {"data": rows}
        except Exception as e:
            last_err = e
            warn(f"东财第{attempt}次失败: {e}", "EM")
            if attempt < MAX_RETRY:
                time.sleep(2 ** attempt)  # 指数退避
    raise last_err if last_err else RuntimeError("东财未知失败")
