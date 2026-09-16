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
    "f230", "f231", "f232", "f233",  # stock_price, stock_change_pct, stock_code, stock_flag(0/1)
    "f234", "f235", "f236", "f237",  # stock_name, convert_value, premium_rate, bond_premium_rate
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
    "f232": "stock_code", "f234": "stock_name",
    "f227": "list_date", "f241": "convert_start_date", "f242": "ipo_date",
}

# 主机轮换：push2 对 GitHub Actions 等数据中心 IP 返回 502，
# push2delay（延迟行情镜像）与数字 CDN 镜像是替代入口，字段与排序完全一致。
HOSTS = [
    "https://push2delay.eastmoney.com/api/qt/clist/get",
    "https://82.push2.eastmoney.com/api/qt/clist/get",
    "https://23.push2.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
]
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
# push2delay 等主机单页上限约 100 条，需分页拉全
PAGE_SIZE = 100
MAX_PAGES = 12  # 全市场约 316 条 ≈ 4 页，留足余量


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


def _params(page_no):
    """单页请求参数：按涨跌幅降序。"""
    return {
        "pn": page_no,
        "pz": PAGE_SIZE,
        "po": 1,          # 按 fid 降序（涨跌幅高→低）
        "np": 1,
        "ut": UT,
        "fltt": 2,        # 数值字段返回可读浮点
        "invt": 2,
        "fid": "f3",      # 涨跌幅
        "fs": FS,
        "fields": ",".join(FIELDS),
    }


def _fetch_page(url, page_no):
    """取单页，返回 (rows_mapped, total)。失败抛异常。"""
    resp = requests.get(url, params=_params(page_no), headers=HEADERS,
                        timeout=TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    # data 可能是 null（网关拦截），必须 or {} 兜住
    data = payload.get("data") or {}
    diff = data.get("diff") or []
    if isinstance(diff, dict):  # 部分端点返回 dict{index: row}
        diff = list(diff.values())
    return diff, int(data.get("total") or 0)


def fetch_eastmoney():
    """抓取东方财富可转债比价表全量（多主机轮换 + 分页）。失败抛异常。"""
    last_err = None
    for url in HOSTS:
        host = url.split("/")[2]
        for attempt in range(1, MAX_RETRY + 1):
            try:
                info(f"请求 {host} 第{attempt}次", "EM")
                # 第 1 页探测总量
                diff, total = _fetch_page(url, 1)
                if not diff:
                    snippet = ""
                    raise ValueError(f"data.diff 为空 host={host}")
                all_diff = list(diff)
                pages = min(MAX_PAGES, max(1, -(-total // PAGE_SIZE)))
                for pn in range(2, pages + 1):
                    time.sleep(1.5)  # 防频率限制
                    d2, _ = _fetch_page(url, pn)
                    if not d2:
                        break
                    all_diff.extend(d2)
                rows = [_map_row(it) for it in all_diff]
                # 去重（分页边界偶有重叠）
                seen = set()
                uniq = []
                for r in rows:
                    if r["code"] not in seen:
                        seen.add(r["code"])
                        uniq.append(r)
                rows = uniq
                if len(rows) < 100:
                    raise ValueError(f"记录数过少 {len(rows)}，疑似不完整")
                # 接口已按涨跌幅降序(po=1)，代码兜底再排一次
                rows.sort(key=_pct_desc_key, reverse=True)
                info(f"{host} 成功获取 {len(rows)} 条（total={total}）", "EM")
                return {"data": rows, "host": host}
            except Exception as e:
                last_err = e
                warn(f"{host} 第{attempt}次失败: {e}", "EM")
                if attempt < MAX_RETRY:
                    time.sleep(2 ** attempt)  # 指数退避
    raise last_err if last_err else RuntimeError("东财全部主机失败")
