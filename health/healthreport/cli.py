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
import re
import sys
import traceback
import zipfile
from datetime import date, datetime, timedelta

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


def _zip_jsons(path):
    try:
        with zipfile.ZipFile(path) as z:
            return [n for n in z.namelist() if n.lower().endswith(".json") and not n.startswith("__MACOSX")]
    except zipfile.BadZipFile:
        return []


def _parse_zip_jsons(path, tz, today):
    out = []
    with zipfile.ZipFile(path) as z:
        for n in _zip_jsons(path):
            with z.open(n) as f:
                obj = json.load(f)
            if ingest_hae.looks_like_hae(obj):
                dd = ingest_hae.parse(obj, tz, os.path.basename(n), last_day=today)
                dd.primary_days = primary_days(n)
                out.append(dd)
    return out


_NAME_DAYS = re.compile(r"HealthAutoExport-(\d{4}-\d{2}-\d{2})(?:-(\d{4}-\d{2}-\d{2}))?")


def primary_days(path):
    """文件名里写明的日期范围（每日文件只有一天）。跨午夜的样本会出现在相邻日期里，
    那些“非本文件日期”的值只用来补空，不覆盖别的文件里完整的一天。"""
    m = _NAME_DAYS.search(os.path.basename(path))
    if not m:
        return None
    try:
        a = date.fromisoformat(m.group(1))
        b = date.fromisoformat(m.group(2)) if m.group(2) else a
    except ValueError:
        return None
    return {a + timedelta(days=i) for i in range((b - a).days + 1)} if b >= a else None


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
            elif p.lower().endswith(".zip") and _zip_jsons(p):
                # Health Auto Export 手动导出的压缩包：里面是 JSON
                for dd in _parse_zip_jsons(p, tz, today):
                    parsed.append(dd)
                    log(f"  读取 {name}/{dd.source_name}：{len(dd.values)} 天，{len(dd.sleep)} 晚睡眠")
                continue
            elif p.lower().endswith((".zip", ".xml")):
                dd = ingest_applexml.parse(p, tz, today=today)
            else:
                dd = ingest_hae.load(p, tz, last_day=today)
                if dd is None:
                    log(f"  跳过 {name}（不是 Health Auto Export 的 JSON）")
                    continue
                dd.primary_days = primary_days(p)
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
    store.files_tried = sum(1 for p in files if not p.lower().endswith(".csv"))
    return store, manual_files


def cmd_build(a):
    tz = get_tz(a.tz)
    today = date.fromisoformat(a.date) if a.date else datetime.now(tz).date()
    print(f"生成 {today} 的报告")
    store, manual_files = load_store(a.data, tz, today)
    if a.manual:
        manual_files = [a.manual] if os.path.exists(a.manual) else []
    for mf in manual_files[-1:]:
        entries = manual.load(mf, today, store.warnings)
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
    os.makedirs(a.out, exist_ok=True)
    try:
        r = Analyzer(store, today, tz, weather=wx, calendar=cal).run()
    except Exception:
        # 分析出错也要给用户一份说明，而不是什么都不发
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        _write(a.out, "subject.txt", f"身体日报 {today.month}/{today.day} · 今天的报告生成失败")
        _write(a.out, "report.html", render.error_html(today, err.strip().splitlines()[-1]))
        _write(a.out, "brief.json", json.dumps({"date": today.isoformat(), "error": err[-2000:]}, ensure_ascii=False))
        return 1
    narrative = None
    if a.narrative and os.path.exists(a.narrative):
        with open(a.narrative, encoding="utf-8") as f:
            narrative = f.read().strip() or None
    links = {"sheet": a.sheet_url, "folder": a.folder_url, "guide": a.guide_url}
    # 邮件正文和标题最重要，先写；其余输出各自出错也不影响发送
    html = render.build_html(r, narrative, links)
    _write(a.out, "report.html", html)
    _write(a.out, "subject.txt", render.subject(r))
    status = 0
    extras = {
        "report.md": lambda: render.build_markdown(r, narrative),
        "brief.json": lambda: render.build_brief(r),
        "summary.json": lambda: json.dumps(r, ensure_ascii=False, indent=1, default=str),
    }
    if store.latest_day():
        extras[f"history-{today.isoformat()}.csv"] = lambda: history.dump(store, today)
    for name, make in extras.items():
        try:
            _write(a.out, name, make())
        except Exception as e:
            print(f"  ! 生成 {name} 失败：{e}", file=sys.stderr)
            status = 1
    print(f"  标题：{render.subject(r)}")
    print(f"  提醒：" + "，".join(f"{k} {v}" for k, v in r["counts"].items() if v))
    for w in store.warnings[:10]:
        print(f"  ! {w}")
    print(f"  已写入 {a.out}/report.html（{len(html) // 1024} KB）")
    return status


def _write(out_dir, name, content):
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
        f.write(content)


def cmd_weather(a):
    raw = weather.fetch_open_meteo(a.lat, a.lon, a.tz)
    if raw["errors"]:
        print("获取失败：" + "；".join(raw["errors"]), file=sys.stderr)
    ok = raw["forecast"] is not None or raw["air"] is not None
    if not ok:
        print("没有拿到天气数据（没有写文件）")
        return 2
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
    print("已写入 " + a.out)
    return 0


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
    b.add_argument("--guide-url", help="使用说明文档的链接")
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
