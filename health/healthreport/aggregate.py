"""把各种来源的原始样本整理成“每天每个指标一个数”。

Health Auto Export（按天汇总或原始样本）和苹果原生 export.xml 都先转成这里的
add_* 调用，再由 finish() 统一汇总成 DayData，这样两种来源的算法完全一致。
"""

from collections import defaultdict
from datetime import timedelta

from .catalog import METRICS
from .store import DayData, SleepNight, Workout

# 睡眠阶段的统一名称
ASLEEP_STAGES = {"core", "deep", "rem", "asleep"}
STAGE_ALIASES = {
    "core": "core", "asleepcore": "core", "light": "core",
    "deep": "deep", "asleepdeep": "deep",
    "rem": "rem", "asleeprem": "rem",
    "asleep": "asleep", "asleepunspecified": "asleep", "unspecified": "asleep",
    "awake": "awake",
    "inbed": "inbed",
    # iPhone 设成中文时 Health Auto Export 可能输出本地化的阶段名
    "核心": "core", "核心睡眠": "core", "浅睡": "core", "浅度睡眠": "core",
    "深度": "deep", "深度睡眠": "deep", "深睡": "deep",
    "快速动眼": "rem", "快速动眼期": "rem", "快速动眼睡眠": "rem", "快速眼动": "rem", "快速眼动期": "rem",
    "快速眼动睡眠": "rem",
    "睡眠": "asleep", "睡眠时长": "asleep", "已入睡": "asleep", "入睡": "asleep", "未指定": "asleep",
    "睡着": "asleep",
    "清醒": "awake", "醒着": "awake", "醒来": "awake",
    "卧床": "inbed", "在床上": "inbed", "躺在床上": "inbed",
}
SESSION_GAP = timedelta(minutes=90)   # 两段睡眠间隔超过 90 分钟算两觉


def stage_name(v):
    s = str(v or "").strip().lower()
    s = s.replace("hkcategoryvaluesleepanalysis", "").replace("_", "").replace(" ", "")
    return STAGE_ALIASES.get(s)


class Aggregator:
    def __init__(self, source_name=""):
        # key -> day -> list[(timestamp, value, source)]
        self.q = defaultdict(lambda: defaultdict(list))
        self.sleep_segments = []   # (start, end, stage, source)
        self.sleep_summaries = []  # SleepNight（来源已经汇总好的）
        self.workouts = []
        self.latest = None
        self.source_name = source_name
        self.warnings = []

    def _seen(self, dt):
        if dt is not None and (self.latest is None or dt > self.latest):
            self.latest = dt

    PLAUSIBLE = {"wrist_temp": (30, 40), "body_temp": (34, 43), "spo2": (50, 100), "rhr": (25, 200),
                 "hrv": (1, 400), "resp_rate": (4, 60)}

    def add(self, key, day, value, source="", ts=None):
        if value is None or day is None:
            return
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        lo_hi = self.PLAUSIBLE.get(key)
        if lo_hi and not lo_hi[0] <= value <= lo_hi[1]:
            return   # 明显不可能的读数（传感器异常、单位错误）直接丢掉
        self.q[key][day].append((ts, value, source or ""))
        self._seen(ts)

    def add_sleep_segment(self, start, end, stage, source=""):
        if start is None or end is None or end <= start or stage is None:
            return
        self.sleep_segments.append((start, end, stage, source or ""))
        self._seen(end)

    def add_sleep_summary(self, night: SleepNight):
        self.sleep_summaries.append(night)
        self._seen(night.end)

    def add_workout(self, w: Workout):
        self.workouts.append(w)
        self._seen(w.end or w.start)

    # ---- 汇总 ----
    @staticmethod
    def _sum(entries):
        """累加型指标（步数、能量…）。

        同一时间戳来自多个来源（手机 + 手表都记了步数）时取较大的那个，避免重复计数；
        原始样本时间戳对不上时，按来源分别求和再取最大来源，近似苹果健康的去重结果。
        """
        simple_sources = {s for _, _, s in entries if s and "|" not in s}
        timestamps = [t for t, _, _ in entries]
        raw = len(set(timestamps)) > 1 and len(simple_sources) > 1
        if raw:
            per_src = defaultdict(float)
            for _, v, s in entries:
                per_src[s] += v
            return max(per_src.values())
        by_ts = {}
        for t, v, _ in entries:
            by_ts[t] = max(by_ts.get(t, v), v)
        return sum(by_ts.values())

    def finish(self):
        dd = DayData(source_name=self.source_name, latest=self.latest, warnings=self.warnings)
        for key, days in self.q.items():
            m = METRICS.get(key)
            agg = m.agg if m else "mean"
            for day, entries in days.items():
                vals = [v for _, v, _ in entries]
                if agg == "sum":
                    v = self._sum(entries)
                elif agg == "min":
                    v = min(vals)
                elif agg == "max":
                    v = max(vals)
                elif agg == "last":
                    v = max(entries, key=lambda e: (e[0] is not None, e[0] or 0))[1] \
                        if any(e[0] for e in entries) else vals[-1]
                else:
                    v = sum(vals) / len(vals)
                dd.values[day][key] = v
        for night in self._nights_from_segments() + self.sleep_summaries:
            prev = dd.sleep.get(night.day)
            if prev is None or _better_night(night, prev):
                dd.sleep[night.day] = night
        self._night_metrics(dd)
        dd.workouts = self.workouts
        return dd

    NIGHT_KEYS = {"hrv": "hrv_night", "resp_rate": "resp_night", "spo2": "spo2_night"}

    def _night_metrics(self, dd):
        """有逐条或逐小时样本时，只用主睡眠时段内的数据算“夜间 HRV / 呼吸频率 / 血氧”，记在醒来那天。

        夜间数值不受白天活动干扰，也不会被午夜切成两天，比全天均值稳定得多。
        按天汇总的数据（每天只有一条 00:00:00）没法区分昼夜，这时跳过。
        """
        for key, night_key in self.NIGHT_KEYS.items():
            samples = [(t, v) for day in self.q.get(key, {}).values() for t, v, _ in day if t is not None]
            per_day = defaultdict(int)
            for t, _ in samples:
                per_day[t.date()] += 1
            intraday = any((t.hour, t.minute, t.second) != (0, 0, 0) for t, _ in samples) or \
                any(n > 1 for n in per_day.values())
            if not intraday:
                continue
            for night in dd.sleep.values():
                if not (night.start and night.end):
                    continue
                vals = [v for t, v in samples if night.start <= t <= night.end]
                if len(vals) >= 2:
                    dd.values[night.day][night_key] = sum(vals) / len(vals)

    def _nights_from_segments(self):
        """原始睡眠片段 → 每晚汇总。每个来源分开拼接，最后每天挑最好的一晚。"""
        by_src = defaultdict(list)
        for seg in self.sleep_segments:
            by_src[seg[3]].append(seg)
        nights = []
        for src, segs in by_src.items():
            segs.sort()
            sessions, cur, cur_end = [], [], None
            for seg in segs:
                if cur and seg[0] - cur_end > SESSION_GAP:
                    sessions.append(cur)
                    cur, cur_end = [], None
                cur.append(seg)
                cur_end = seg[1] if cur_end is None else max(cur_end, seg[1])
            if cur:
                sessions.append(cur)
            for sess in sessions:
                n = _night_from_session(sess, src)
                if n:
                    nights.append(n)
        return nights


def _hours(segs):
    """片段总时长（小时），重叠部分只算一次。"""
    ivs = sorted((s, e) for s, e in segs)
    total, cur_s, cur_e = 0.0, None, None
    for s, e in ivs:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += (cur_e - cur_s).total_seconds()
    return total / 3600


def _night_from_session(sess, src):
    by_stage = defaultdict(list)
    for s, e, st, _ in sess:
        by_stage[st].append((s, e))
    asleep = [iv for st in ASLEEP_STAGES for iv in by_stage.get(st, [])]
    if not asleep:
        return None
    start = min(s for s, _ in asleep)
    end = max(e for _, e in asleep)
    total = _hours(asleep)
    if total < 0.25:
        return None
    inbed_ivs = by_stage.get("inbed", [])
    inbed = _hours(inbed_ivs) if inbed_ivs else None
    return SleepNight(
        day=end.date(), total_h=total,
        deep_h=_hours(by_stage["deep"]) if by_stage.get("deep") else None,
        rem_h=_hours(by_stage["rem"]) if by_stage.get("rem") else None,
        core_h=_hours(by_stage["core"]) if by_stage.get("core") else None,
        awake_h=_hours(by_stage["awake"]) if by_stage.get("awake") else (0.0 if by_stage.get("core") else None),
        inbed_h=inbed, start=start, end=end, source=src)


def _better_night(a, b):
    """同一天有多段睡眠（午睡、不同 App）时，挑主睡眠：有分期的优先，其次时长更长。"""
    return (a.has_stages(), a.total_h or 0) > (b.has_stages(), b.total_h or 0)
