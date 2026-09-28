"""命令行入口：python3 -m healthreport <命令>

  build    生成报告（HTML / Markdown / JSON / 邮件标题 / 给 Claude 的简报）
  weather  从 Open-Meteo 获取天气和空气质量，存成 weather.json
  collect  把 Google Drive 连接器下载的文件解码写到磁盘
  sample   生成示例数据
"""

import argparse
import glob
import json
import os
import sys
from datetime import date, datetime

from . import calendar_ctx, collect, history, ingest_applexml, ingest_hae, manual, render, weather
from .analysis import Analyzer
from .store import HealthStore
from .timeutil import get_tz

BEIJING = (39.9042, 116.4074)


def _files(paths):
    out = []
    for p in paths or []:
        if os.path.isdir(p):
            for ext in ("*.json", "*.zip", "*.xml", "*.csv"):
                out += glob.glob(os.path.join(p, "**", ext), recursive=True)
        elif os.path.exists(p):
            out.append(p)
    return sorted(set(out))


def _is_manual_csv(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            head = f.read(2000)
    except OSError:
        return False
    return ("日期" in head or "date" in head.lower()) and not history.is_history(path)


def load_store(paths, tz, today, log=print):
    """读取数据目录：HealthAutoExport JSON、苹果 export.zip/xml、历史存档 history-*.csv、手动记录 CSV。"""
    store = HealthStore()
    files = _files(paths)
    hist = history.pick_latest(files)
    parsed, manual_files = [], []
    for p in files:
        name = os.path.basename(p)
        try:
            if p.lower().endswith(".csv"):
                if history.is_history(p):
                    if p != hist:
                        continue
                    dd = history.load(p, tz)
                elif _is_manual_csv(p):
                    manual_files.append(p)
                    continue
                else:
                    log(f"  跳过 {name}（不认识的 CSV；请用 JSON 格式导出）")
                    continue
            elif p.lower().endswith((".zip", ".xml")):
                dd = ingest_applexml.parse(p, tz, today=today)
            else:
                dd = ingest_hae.load(p, tz)
                if dd is None:
                    log(f"  跳过 {name}（不是 Health Auto Export 的 JSON）")
                    continue
        except Exception as e:
            store.warnings.append(f"{name}: 读取失败（{e}）")
            log(f"  ! {name}: {e}")
            continue
        parsed.append(dd)
        log(f"  读取 {name}：{len(dd.values)} 天，{len(dd.sleep)} 晚睡眠，{len(dd.workouts)} 次运动")
    # 历史存档最先合并；导出时间越晚的文件越完整，放在后面覆盖
    parsed.sort(key=lambda dd: (dd.latest is not None, dd.latest or datetime.min, dd.source_name))
    for dd in parsed:
        store.merge(dd)
    return store, manual_files


def cmd_build(a):
    tz = get_tz(a.tz)
    today = date.fromisoformat(a.date) if a.date else datetime.now(tz).date()
    print(f"生成 {today} 的报告")
    store, manual_files = load_store(a.data, tz, today)
    if a.manual:
        manual_files = [a.manual] if os.path.exists(a.manual) else []
    for mf in manual_files[-1:]:
        entries = manual.load(mf)
        manual.merge_into(store, entries)
        print(f"  手动记录 {os.path.basename(mf)}：{len(entries)} 天")
    wx = None
    if a.weather and os.path.exists(a.weather):
        try:
            wx = weather.load(a.weather, today)
        except Exception as e:
            store.warnings.append(f"天气数据读取失败：{e}")
    cal = None
    if a.calendar and os.path.exists(a.calendar):
        try:
            cal = calendar_ctx.load(a.calendar, today, tz)
        except Exception as e:
            store.warnings.append(f"日程读取失败：{e}")
    r = Analyzer(store, today, tz, weather=wx, calendar=cal).run()
    narrative = None
    if a.narrative and os.path.exists(a.narrative):
        with open(a.narrative, encoding="utf-8") as f:
            narrative = f.read().strip() or None
    links = {"sheet": a.sheet_url, "folder": a.folder_url}
    os.makedirs(a.out, exist_ok=True)
    outputs = {
        "report.html": render.build_html(r, narrative, links),
        "report.md": render.build_markdown(r, narrative),
        "brief.json": render.build_brief(r),
        "subject.txt": render.subject(r),
        "summary.json": json.dumps(r, ensure_ascii=False, indent=1, default=str),
    }
    if store.latest_day():
        outputs[f"history-{today.isoformat()}.csv"] = history.dump(store, today)
    for name, content in outputs.items():
        with open(os.path.join(a.out, name), "w", encoding="utf-8") as f:
            f.write(content)
    print(f"  标题：{outputs['subject.txt']}")
    print(f"  提醒：" + "，".join(f"{k} {v}" for k, v in r["counts"].items() if v))
    for w in store.warnings[:10]:
        print(f"  ! {w}")
    print(f"  已写入 {a.out}/report.html（{len(outputs['report.html']) // 1024} KB）")
    return 0


def cmd_weather(a):
    raw = weather.fetch_open_meteo(a.lat, a.lon, a.tz)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
    if raw["errors"]:
        print("获取失败：" + "；".join(raw["errors"]), file=sys.stderr)
    ok = raw["forecast"] is not None or raw["air"] is not None
    print(("已写入 " + a.out) if ok else "没有拿到天气数据")
    return 0 if ok else 2


def cmd_collect(a):
    found = collect.scan(since_hours=a.hours, title_filter=a.match)
    written = collect.write(found, a.out)
    for p, n in written:
        print(f"  {p}（{n // 1024} KB）")
    print(f"共写出 {len(written)} 个文件")
    return 0 if written else 3


def cmd_sample(a):
    end = date.fromisoformat(a.end) if a.end else date.today()
    from .sample import write_demo
    p = write_demo(a.out, end, a.days, a.scenario)
    print(f"示例数据已写入 {p}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="healthreport", description="每日身体报告")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="生成报告")
    b.add_argument("--data", nargs="*", default=[], help="Health Auto Export JSON 文件或目录，也可以是 export.zip")
    b.add_argument("--manual", help="手动记录 CSV")
    b.add_argument("--calendar", help="今天的日程 JSON")
    b.add_argument("--weather", help="weather.json（weather 命令的输出或手写）")
    b.add_argument("--narrative", help="Claude 写的今日点评（纯文本）")
    b.add_argument("--date", help="报告日期 YYYY-MM-DD，默认今天")
    b.add_argument("--tz", default="Asia/Shanghai")
    b.add_argument("--sheet-url")
    b.add_argument("--folder-url")
    b.add_argument("--out", default="out")
    b.set_defaults(func=cmd_build)

    w = sub.add_parser("weather", help="获取天气和空气质量")
    w.add_argument("--lat", type=float, default=BEIJING[0])
    w.add_argument("--lon", type=float, default=BEIJING[1])
    w.add_argument("--tz", default="Asia/Shanghai")
    w.add_argument("--out", default="weather.json")
    w.set_defaults(func=cmd_weather)

    c = sub.add_parser("collect", help="解码 Google Drive 连接器下载的文件")
    c.add_argument("--out", default="data")
    c.add_argument("--match", default=r"HealthAutoExport|history-|手动记录|\.json$|\.csv$|export\.zip$|导出",
                   help="只要标题匹配这个正则的文件")
    c.add_argument("--hours", type=float, default=6, help="只看最近几小时的下载")
    c.set_defaults(func=cmd_collect)

    s = sub.add_parser("sample", help="生成示例数据")
    s.add_argument("--out", default="demo")
    s.add_argument("--end", help="最后一天 YYYY-MM-DD")
    s.add_argument("--days", type=int, default=60)
    s.add_argument("--scenario", choices=["normal", "illness", "shortsleep"], default="normal")
    s.set_defaults(func=cmd_sample)

    a = ap.parse_args(argv)
    return a.func(a)
