"""按天存放的健康数据。

所有来源（Health Auto Export JSON、苹果原生 export.xml、手动记录）先各自整理成
“某一天某个指标一个数”，再合并进 HealthStore。后导入的文件覆盖先导入的同日同指标，
因为较晚导出的文件对同一天的数据更完整。
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

MIN_TRACKED_SLEEP_H = 3.0   # 与 thresholds.SLEEP_MIN_TRACKED_H 一致


@dataclass
class SleepNight:
    day: date                       # 醒来的那天
    total_h: Optional[float] = None  # 实际睡着的时长
    deep_h: Optional[float] = None
    rem_h: Optional[float] = None
    core_h: Optional[float] = None
    awake_h: Optional[float] = None
    inbed_h: Optional[float] = None
    start: Optional[datetime] = None  # 入睡
    end: Optional[datetime] = None    # 醒来
    source: str = ""
    nap_h: Optional[float] = None     # 未分期的零散睡眠（多半是小睡）

    def has_stages(self):
        return any(v for v in (self.deep_h, self.rem_h, self.core_h))


@dataclass
class Workout:
    day: date
    name: str
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    duration_min: Optional[float] = None
    kcal: Optional[float] = None
    distance_km: Optional[float] = None
    avg_hr: Optional[float] = None
    max_hr: Optional[float] = None

    def key(self):
        return (self.start.isoformat() if self.start else "", self.name)


@dataclass
class DayData:
    """一个文件里解析出来的按天数据，合并前的中间形态。"""
    values: dict = field(default_factory=lambda: defaultdict(dict))   # day -> key -> value
    sleep: dict = field(default_factory=dict)                          # day -> SleepNight
    workouts: list = field(default_factory=list)
    latest: Optional[datetime] = None   # 文件里最晚的时间戳，用于决定合并顺序
    source_name: str = ""
    primary_days: Optional[set] = None  # 文件名写明的日期；其余日期的值只补空、不覆盖
    warnings: list = field(default_factory=list)


class HealthStore:
    def __init__(self):
        self.values = defaultdict(dict)
        self.sleep = {}
        self.workouts = {}
        self.manual = {}
        self.manual_filled = set()   # (day, key)：由手动记录补上的值
        self.sources = []
        self.warnings = []
        self.files_tried = 0

    # ---- 写入 ----
    def merge(self, data: DayData):
        own = data.primary_days
        for day, kv in data.values.items():
            for k, v in kv.items():
                if v is None:
                    continue
                if own is not None and day not in own and self.values[day].get(k) is not None:
                    continue   # 相邻日期里跨午夜的零星样本，不能覆盖那天完整的值
                self.values[day][k] = v
        for day, night in data.sleep.items():
            if own is not None and day not in own and day in self.sleep:
                continue
            self.sleep[day] = night
            self._sleep_to_values(night)
        for w in data.workouts:
            self.workouts[w.key()] = w
        self.sources.append(data.source_name)
        self.warnings.extend(data.warnings)

    def _sleep_to_values(self, n: SleepNight):
        if (n.total_h or 0) < MIN_TRACKED_SLEEP_H:
            return   # 多半是没戴表或手表没电，不当作真实睡眠参与基线和趋势
        for k, v in (("sleep_h", n.total_h), ("sleep_deep_h", n.deep_h), ("sleep_rem_h", n.rem_h),
                     ("sleep_core_h", n.core_h), ("sleep_awake_h", n.awake_h),
                     ("sleep_inbed_h", n.inbed_h)):
            if v is not None:
                self.values[n.day][k] = v

    def put(self, day, key, value):
        if value is not None:
            self.values[day][key] = value

    # ---- 读取 ----
    def get(self, day, key):
        return self.values.get(day, {}).get(key)

    def series(self, key, end_day, n):
        """[end_day-n+1, end_day] 这 n 天里有值的 (day, value)，按日期升序。"""
        out = []
        for i in range(n - 1, -1, -1):
            d = end_day - timedelta(days=i)
            v = self.get(d, key)
            if v is not None:
                out.append((d, v))
        return out

    def values_between(self, key, start_day, end_day):
        """start_day 到 end_day（都包含）之间的数值列表。"""
        n = (end_day - start_day).days + 1
        return [v for _, v in self.series(key, end_day, n)] if n > 0 else []

    def workouts_on(self, day):
        ws = [w for w in self.workouts.values() if w.day == day]
        return sorted(ws, key=lambda w: w.start or datetime.min)

    def workouts_between(self, start_day, end_day):
        return [w for w in self.workouts.values() if start_day <= w.day <= end_day]

    def watch_days(self):
        """有手表/手机数据的日期（不含手动记录补上的值）。"""
        return sorted(d for d, kv in self.values.items()
                      if any((d, k) not in self.manual_filled for k in kv))

    def latest_day(self):
        days = self.watch_days()
        return days[-1] if days else None
