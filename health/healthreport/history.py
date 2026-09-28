"""精简的历史存档（CSV）。

Health Auto Export 每天在 Drive 里写一个 HealthAutoExport-YYYY-MM-DD.json。算 28 天基线需要一个月的
数据，但每天早上把 30 个文件都下载一遍又慢又浪费。所以每次生成报告后，把最近 60 天“每天每个指标一个数”
存成一个小 CSV（history-YYYY-MM-DD.csv，约 10 KB）放回 Drive；第二天只要下载这个存档和最近几天的
导出文件就够了。存档里只有按天汇总后的数字，没有原始样本。
"""

import csv
import io
import os
import re
from datetime import date, timedelta

from .catalog import METRICS
from .store import DayData, SleepNight
from .timeutil import parse_dt

KEEP_DAYS = 60
SLEEP_KEYS = ("sleep_h", "sleep_deep_h", "sleep_rem_h", "sleep_core_h", "sleep_awake_h", "sleep_inbed_h")
NAME_RE = re.compile(r"history-(\d{4}-\d{2}-\d{2})", re.I)


def dump(store, end_day, days=KEEP_DAYS):
    start = end_day - timedelta(days=days - 1)
    keys = [k for k in METRICS if any(
        store.get(d, k) is not None and (d, k) not in store.manual_filled
        for d in (start + timedelta(days=i) for i in range(days)))]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["day"] + keys + ["sleep_start", "sleep_end"])
    for i in range(days):
        d = start + timedelta(days=i)
        row = [d.isoformat()]
        has = False
        for k in keys:
            v = store.get(d, k)
            partial = d == end_day and METRICS[k].agg == "sum" and not k.startswith("sleep")
            if v is None or (d, k) in store.manual_filled or partial:   # 当天的累计值还不完整，不存
                row.append("")
                continue
            has = True
            dec = METRICS[k].decimals + 1
            row.append(f"{v:.{dec}f}".rstrip("0").rstrip(".") if dec else str(round(v)))
        n = store.sleep.get(d)
        row.append(n.start.isoformat(timespec="minutes") if n and n.start else "")
        row.append(n.end.isoformat(timespec="minutes") if n and n.end else "")
        if has or n:
            w.writerow(row)
    return buf.getvalue()


def parse(text, tz, source_name="history"):
    dd = DayData(source_name=source_name)   # latest=None → 合并时排在最前，被新导出的数据覆盖
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    for r in rows:
        try:
            d = date.fromisoformat(r.get("day", ""))
        except ValueError:
            continue
        for k, v in r.items():
            if k in METRICS and k not in SLEEP_KEYS and v not in ("", None):
                try:
                    dd.values[d][k] = float(v)
                except ValueError:
                    pass
        sv = {k: float(r[k]) for k in SLEEP_KEYS if r.get(k) not in ("", None)}
        if sv.get("sleep_h"):
            dd.sleep[d] = SleepNight(
                day=d, total_h=sv.get("sleep_h"), deep_h=sv.get("sleep_deep_h"), rem_h=sv.get("sleep_rem_h"),
                core_h=sv.get("sleep_core_h"), awake_h=sv.get("sleep_awake_h"), inbed_h=sv.get("sleep_inbed_h"),
                start=parse_dt(r.get("sleep_start"), tz), end=parse_dt(r.get("sleep_end"), tz),
                source="历史存档")
    return dd


def load(path, tz):
    with open(path, encoding="utf-8-sig") as f:
        return parse(f.read(), tz, os.path.basename(path))


def is_history(path):
    return bool(NAME_RE.search(os.path.basename(path)))


def pick_latest(paths):
    """多个存档时只用日期最新的那个（旧存档的内容都包含在新存档里）。"""
    hs = [(NAME_RE.search(os.path.basename(p)).group(1), p) for p in paths if is_history(p)]
    return max(hs)[1] if hs else None
