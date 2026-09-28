"""个人基线：用你自己过去几周的数据描述“平时的样子”。

- 用中位数和 MAD（中位数绝对偏差）而不是均值和标准差，几天生病或熬夜的异常值不会把基线带偏；
- 默认用第 t-29 到 t-2 天（跳过最近 2 天），这样正在发生的变化不会“污染”基线；
- 每个指标有标准差下限，数据特别平稳时一点小波动不会被当成异常；
- HRV 在对数尺度上比较（ln SDNN），用 60 天窗口，并看 7 天滚动均值（参考 HRV4Training 的做法）。
"""

import math
from dataclasses import dataclass
from datetime import timedelta
from statistics import mean, median, pstdev

from .catalog import METRICS

WINDOW_DAYS = 28
GAP_DAYS = 2          # 跳过最近几天
FULL_BASELINE_DAYS = 14


@dataclass
class Baseline:
    key: str
    median: float
    sd: float
    n: int

    @property
    def provisional(self):
        return self.n < FULL_BASELINE_DAYS

    def z(self, value):
        return None if value is None else (value - self.median) / self.sd

    def delta(self, value):
        return None if value is None else value - self.median


def robust_sd(values, center):
    return 1.4826 * median(abs(v - center) for v in values)


def compute(store, key, day, window=WINDOW_DAYS, gap=GAP_DAYS):
    """day 的基线：取 [day-gap-window+1, day-gap] 这些天的数据；不够时返回 None。"""
    m = METRICS[key]
    end = day - timedelta(days=gap)
    vals = store.values_between(key, end - timedelta(days=window - 1), end)
    if len(vals) < m.min_days:
        return None
    med = median(vals)
    return Baseline(key, med, max(robust_sd(vals, med), m.sd_floor), len(vals))


def rolling_mean(store, key, end_day, n):
    vals = store.values_between(key, end_day - timedelta(days=n - 1), end_day)
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)


# ---- HRV：对数尺度 ----
LN_SD_FLOOR = 0.08


@dataclass
class HrvStatus:
    today_ms: float
    today_z: float          # 当天 ln 值相对 60 天基线
    week_ms: float          # 近 7 天 ln 均值换回毫秒
    week_z: float
    base_ms: float          # 60 天 ln 均值换回毫秒
    lo_ms: float            # 正常范围（均值 ± 0.5 SD）
    hi_ms: float
    n: int
    below_days: int         # 最近 3 天里，7 天均值低于 “均值 − 1 SD” 的天数


def hrv_status(store, key, day):
    """key 为 hrv 或 hrv_night。数据不足（60 天里少于 14 天）返回 None。"""
    def ln_vals(a, b):
        return [math.log(v) for v in store.values_between(key, a, b) if v and v > 0]

    base = ln_vals(day - timedelta(days=60), day - timedelta(days=1))
    today = store.get(day, key)
    if len(base) < FULL_BASELINE_DAYS or not today:
        return None
    mu, sd = mean(base), max(pstdev(base), LN_SD_FLOOR)

    def week_mean(d):
        w = ln_vals(d - timedelta(days=6), d)
        return mean(w) if len(w) >= 4 else None

    wk = week_mean(day)
    below = sum(1 for i in range(3)
                if (m := week_mean(day - timedelta(days=i))) is not None and m < mu - sd)
    lt = math.log(today)
    return HrvStatus(today_ms=today, today_z=(lt - mu) / sd,
                     week_ms=math.exp(wk) if wk is not None else None,
                     week_z=(wk - mu) / sd if wk is not None else None,
                     base_ms=math.exp(mu), lo_ms=math.exp(mu - 0.5 * sd), hi_ms=math.exp(mu + 0.5 * sd),
                     n=len(base), below_days=below)
