"""统一日志：写 stdout，Actions 可见。含时间戳与来源标记。"""
import sys
import datetime


def _stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg, source="MAIN", level="INFO"):
    """写一条带时间戳与来源标记的结构化日志到 stdout。"""
    line = f"[{_stamp()}][{level}][{source}] {msg}"
    print(line, flush=True)
    sys.stdout.flush()


def info(msg, source="MAIN"):
    log(msg, source, "INFO")


def warn(msg, source="MAIN"):
    log(msg, source, "WARN")


def error(msg, source="MAIN"):
    log(msg, source, "ERROR")
