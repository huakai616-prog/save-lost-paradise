"""时间解析与时区。"""

import re
from datetime import datetime, timedelta, timezone

_FIXED = {"Asia/Shanghai": 8, "Asia/Chongqing": 8, "Asia/Hong_Kong": 8, "Asia/Taipei": 8,
          "Asia/Tokyo": 9, "Asia/Singapore": 8, "UTC": 0}


def get_tz(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        # 没装时区库时，常见的无夏令时时区用固定偏移兜底
        if name in _FIXED:
            return timezone(timedelta(hours=_FIXED[name]), name)
        raise


_OFFSET_RE = re.compile(r"\s*([+-])(\d{2}):?(\d{2})$")


def parse_dt(s, tz=None):
    """解析 Health Auto Export / 苹果导出 / ISO 8601 的时间字符串，返回带时区的 datetime。

    "2024-02-06 00:00:00 -0800"、"2024-02-06T00:00:00+08:00"、"2024-02-06T00:00:00Z"、
    "2024-02-06 00:00"、"2024-02-06" 都可以。没有时区的按 tz 处理。
    """
    if s is None:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo or tz is None else s.replace(tzinfo=tz)
    s = str(s).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    offset = None
    m = _OFFSET_RE.search(s)
    if m and len(s) > 10:
        sign = 1 if m.group(1) == "+" else -1
        offset = timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))
        s = s[:m.start()]
    s = s.replace("T", " ").replace("\u202f", " ").replace("\u00a0", " ").strip()
    s = re.sub(r"\s+", " ", s)
    # 去掉毫秒
    s = re.sub(r"(\d{2}:\d{2}:\d{2})\.\d+", r"\1", s)
    # 12 小时制地区可能写成 “2024-02-06 1:05:00 PM”
    s = s.replace("上午", " AM ").replace("下午", " PM ")
    s = re.sub(r"\s+", " ", s).strip()
    m12 = re.match(r"^(\S+) (AM|PM) (\d{1,2}:\d{2}(?::\d{2})?)$", s)   # “2026-02-06 下午1:05:00”
    if m12:
        s = f"{m12.group(1)} {m12.group(3)} {m12.group(2)}"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d %H:%M", "%Y/%m/%d", "%Y-%m-%d %I:%M:%S %p", "%Y-%m-%d %I:%M %p",
                "%Y-%m-%d %p %I:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            break
        except ValueError:
            continue
    else:
        return None
    if offset is not None:
        return dt.replace(tzinfo=offset)
    return dt.replace(tzinfo=tz) if tz else dt


def local_date(s, tz):
    """样本所属的本地日期。

    Health Auto Export 和苹果导出的时间都写成“手机当地时间 + 时区偏移”，直接取字面上的
    日期最符合用户的感受，也不会因为换算让按天汇总的数据（当地 00:00:00）错到前一天。
    只有 UTC 的 “Z” 结尾时间才换算到 tz。
    """
    dt = parse_dt(s, tz)
    if dt is None:
        return None
    if isinstance(s, str) and s.strip().endswith("Z") and tz is not None:
        return dt.astimezone(tz).date()
    return dt.date()


WEEKDAYS = "一二三四五六日"


def cn_date(d):
    return f"{d.year}年{d.month}月{d.day}日 周{WEEKDAYS[d.weekday()]}"
