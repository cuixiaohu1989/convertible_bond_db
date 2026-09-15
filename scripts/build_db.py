"""构建数据库：读 results.json → 写 docs/data/<date>.json + 更新 docs/index.json。"""
import sys
import os

# 确保项目根在 sys.path，兼容 `python scripts/build_db.py` 运行方式
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import datetime

from core.logger import info, warn, error


def _pct_desc_key(r):
    """涨跌幅降序键：None 置底，0.0 不被 or 误判为假值。"""
    v = r.get("change_pct")
    return (v is not None, v if v is not None else -1e18)


def _now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _load_index(index_path):
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_update": None,
        "last_source": None,
        "available_dates": [],
        "total_days": 0,
    }


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results_path = os.path.join(base, "results.json")
    docs_dir = os.path.join(base, "docs")
    data_dir = os.path.join(docs_dir, "data")
    index_path = os.path.join(docs_dir, "index.json")

    os.makedirs(data_dir, exist_ok=True)

    with open(results_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    date = result.get("date")
    source = result.get("source", "failed")
    trading_day = result.get("trading_day", False)
    data = result.get("data", [])

    index = _load_index(index_path)
    index["last_update"] = _now_iso()

    # 跳过条件：非交易日 / 双源失败 / 数据为空
    if not trading_day:
        info(f"非交易日（{date}），跳过写数据文件，仅更新 last_update", "BUILD")
    elif source == "failed":
        warn(f"source=failed（{date}），跳过写数据文件", "BUILD")
    elif not data:
        warn(f"data 为空（{date}），跳过写数据文件", "BUILD")
    else:
        # 兜底再按涨跌幅降序一次
        data.sort(key=_pct_desc_key, reverse=True)
        day_path = os.path.join(data_dir, f"{date}.json")
        with open(day_path, "w", encoding="utf-8") as f:
            json.dump({"date": date, "source": source, "data": data},
                      f, ensure_ascii=False, indent=2)
        info(f"已写出 {day_path}（{len(data)} 条）", "BUILD")

        # 更新日期索引（去重升序）
        if date not in index["available_dates"]:
            index["available_dates"].append(date)
        index["available_dates"] = sorted(set(index["available_dates"]))
        index["total_days"] = len(index["available_dates"])
        index["last_source"] = source

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    info(f"index.json 更新完成：total_days={index['total_days']}, "
         f"last_source={index['last_source']}", "BUILD")


if __name__ == "__main__":
    main()
