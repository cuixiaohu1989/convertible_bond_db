"""交易日判断：周末 + 年度休市日。本地兜底，可运行时补充。"""
import datetime
import json
import os

# 当前文件所在目录（core/），向上一级找 holidays.json
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_holidays():
    path = os.path.join(_BASE, "holidays.json")
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        days = set()
        for _year, lst in data.items():
            if isinstance(lst, list):
                days.update(lst)
        return days
    except Exception:
        return set()


def is_trading_day(date=None):
    """判断给定日期（datetime.date，默认今天）是否为 A 股交易日。"""
    if date is None:
        date = datetime.date.today()
    if isinstance(date, str):
        date = datetime.date.fromisoformat(date)
    # 1) 周末不交易
    if date.weekday() >= 5:  # 5=Sat, 6=Sun
        return False
    # 2) 年度休市日
    holidays = _load_holidays()
    if date.isoformat() in holidays:
        return False
    return True


def next_trading_day(date=None):
    """返回不早于 date 的下一个交易日（含 date 本身）。"""
    if date is None:
        date = datetime.date.today()
    while not is_trading_day(date):
        date = date + datetime.timedelta(days=1)
    return date
