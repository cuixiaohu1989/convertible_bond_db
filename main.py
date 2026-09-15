"""入口：编排采集 → 产出 results.json（含 source / trading_day 标记）。始终 exit 0。"""
import sys
import os

# 确保项目根在 sys.path，兼容 `python main.py` / `python scripts/build_db.py` 两种运行方式
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import datetime

from core.logger import info, warn, error
from core import date_utils
from fetchers.eastmoney_bond import fetch_eastmoney
from fetchers.tencent_bond import fetch_tencent, load_universe, save_universe


def main():
    today = datetime.date.today().isoformat()
    trading_day = date_utils.is_trading_day(today)
    info(f"今日 {today} 交易日={trading_day}", "MAIN")

    result = None
    source = "failed"
    errors = {}  # 各源失败原因，写入 results.json 便于事后排查（无需 Actions 日志权限）

    # 1) 主源：东方财富
    try:
        res = fetch_eastmoney()
        if res and len(res.get("data", [])) > 300:
            save_universe(res["data"])
            res["source"] = "eastmoney"
            result = res
            source = "eastmoney"
            info(f"主源东财成功：{len(res['data'])} 条", "MAIN")
        else:
            raise ValueError(f"东财返回不足全量（{len(res.get('data', [])) if res else 0} 条）")
    except Exception as e:
        errors["eastmoney"] = f"{type(e).__name__}: {e}"
        warn(f"东财失败: {e}，尝试腾讯兜底", "MAIN")

    # 2) 兜底源：腾讯
    if result is None:
        try:
            universe = load_universe()
            if not universe:
                raise ValueError("bond_universe.json 为空，无法兜底（词典依赖东财首次成功）")
            res = fetch_tencent(universe)
            res["source"] = "tencent_fallback"
            result = res
            source = "tencent_fallback"
            info(f"兜底腾讯成功：{len(res['data'])} 条", "MAIN")
        except Exception as e2:
            errors["tencent"] = f"{type(e2).__name__}: {e2}"
            error(f"双源皆失败: {e2}", "MAIN")
            result = {"source": "failed", "data": [], "date": today}

    # 3) 补充标记
    result["date"] = today
    result["trading_day"] = trading_day
    if errors:
        result["errors"] = errors

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    info(f"results.json 写出完成，source={source}", "MAIN")
    # 始终成功退出（数据质量告警通过 source 标记体现，不阻断 workflow）
    return 0


if __name__ == "__main__":
    main()
