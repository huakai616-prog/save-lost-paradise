"""今天的日程负荷。

输入是一个 JSON 列表（由每日任务从 Google 日历读出来后写入）：
    [{"summary": "周会", "start": "2026-09-29T10:00:00+08:00", "end": "2026-09-29T11:00:00+08:00"},
     {"summary": "国庆", "start": "2026-10-01", "end": "2026-10-02", "allDay": true}]
也接受 Google Calendar API 原样的 {"start": {"dateTime": ...}} 结构，或 {"events": [...]} 外层。
"""

import json
from datetime import date, datetime, time, timedelta

from .timeutil import parse_dt

DAY_START = time(7, 0)
DAY_END = time(21, 0)
MIN_GAP_FOR_EXERCISE = timedelta(minutes=45)


def _field(ev, name):
    v = ev.get(name)
    if isinstance(v, dict):
        return v.get("dateTime") or v.get("date")
    return v


def load(path, day: date, tz):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        raw = raw.get("events") or raw.get("items") or []
    events, all_day = [], []
    for ev in raw:
        title = (ev.get("summary") or ev.get("title") or "（无标题）").strip()
        if (ev.get("status") or "").lower() == "cancelled":
            continue
        s, e = _field(ev, "start"), _field(ev, "end")
        if not s:
            continue
        is_all_day = bool(ev.get("allDay")) or (isinstance(s, str) and len(s) == 10)
        if is_all_day:
            sd = date.fromisoformat(s[:10])
            ed = date.fromisoformat(e[:10]) if e else sd + timedelta(days=1)
            if sd <= day < ed:
                all_day.append(title)
            continue
        start, end = parse_dt(s, tz), parse_dt(e, tz) if e else None
        if start is None:
            continue
        if end is None or end <= start:
            end = start + timedelta(minutes=30)
        start, end = start.astimezone(tz), end.astimezone(tz)
        if not (start.date() <= day <= end.date()):
            continue
        # 休假、出差这类跨天的“不在办公室”事件，覆盖了今天整个白天或长达 20 小时以上，当全天事件看
        if (end - start) >= timedelta(hours=20) or (
                start <= datetime.combine(day, DAY_START, tz) and end >= datetime.combine(day, DAY_END, tz)):
            all_day.append(title)
            continue
        events.append({"title": title, "start": start, "end": end})
    return analyze(events, all_day, day, tz)


def _merge(intervals):
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def analyze(events, all_day, day, tz):
    day_start = datetime.combine(day, time(0, 0), tz)
    day_end = day_start + timedelta(days=1)
    # 跨午夜的事件只算今天这一段，显示的时间也用裁剪后的
    events = [dict(ev, start=max(ev["start"], day_start), end=min(ev["end"], day_end)) for ev in events]
    clipped = [(ev["start"], ev["end"]) for ev in events]
    busy = _merge(clipped)
    busy_h = sum((e - s).total_seconds() for s, e in busy) / 3600

    # 连续开会：间隔不到 10 分钟的日程算一段
    blocks = []
    for s, e in sorted(clipped):
        if blocks and s - blocks[-1][1] < timedelta(minutes=10):
            blocks[-1][1] = max(blocks[-1][1], e)
        else:
            blocks.append([s, e])
    longest_h = max(((e - s).total_seconds() / 3600 for s, e in blocks), default=0)

    # 找白天能运动的空档，优先中午和傍晚
    win_start = datetime.combine(day, DAY_START, tz)
    win_end = datetime.combine(day, DAY_END, tz)
    free, cursor = [], win_start
    for s, e in busy:
        if e <= win_start or s >= win_end:
            continue
        if s - cursor >= MIN_GAP_FOR_EXERCISE:
            free.append((cursor, min(s, win_end)))
        cursor = max(cursor, e)
    if win_end - cursor >= MIN_GAP_FOR_EXERCISE:
        free.append((cursor, win_end))

    def pref(slot):
        mid = slot[0] + (slot[1] - slot[0]) / 2
        h = mid.hour + mid.minute / 60
        return min(abs(h - 12.5), abs(h - 18.5))

    suggestion = min(free, key=pref) if (free and events) else None   # 没有日程时不用特意推荐时段
    evs = sorted(events, key=lambda x: x["start"])
    return {
        "count": len(events),
        "all_day": all_day,
        "busy_hours": round(busy_h, 1),
        "longest_block_hours": round(longest_h, 1),
        "first_start": evs[0]["start"].strftime("%H:%M") if evs else None,
        "last_end": max(ev["end"] for ev in evs).strftime("%H:%M") if evs else None,
        "first_start_dt": evs[0]["start"] if evs else None,
        "last_end_dt": max(ev["end"] for ev in evs) if evs else None,
        "events": [{"time": f'{ev["start"]:%H:%M}–{ev["end"]:%H:%M}', "title": ev["title"]} for ev in evs],
        "exercise_slot": (f"{suggestion[0]:%H:%M}–{suggestion[1]:%H:%M}" if suggestion else None),
    }
