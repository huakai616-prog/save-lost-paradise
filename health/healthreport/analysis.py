"""核心分析：把一天的数据变成“今天的身体状态 + 需要注意什么”。

原则（阈值和出处见 thresholds.py 与 README）：
- 和“你自己的平常水平”比，而不是只和人群标准比；
- 单个指标偶尔波动很常见，多项一起偏离、或连续几天偏离才值得认真对待
  （思路同 Apple 手表“生命体征”App 和 NightSignal 研究）；
- 只提示、不诊断：先列出常见的无害原因，再说什么情况下该就医；
- 真正的危险信号（极端血压、连续多天静息心率 >100、夜间血氧反复 <92% 等）才用红色。

日期约定（报告日 T，一般在早上生成）：
- 睡眠：醒来日期为 T 的那一觉（“昨晚”）；
- 静息心率、全天 HRV、活动：T-1（昨天完整的一天）；
- 睡眠呼吸频率、血氧：优先 T（午夜后那部分夜间数据），没有再用 T-1；
- 手腕温度：Health Auto Export 记在入睡那天，按昨晚的入睡日期找。
"""

from datetime import datetime, time, timedelta
from statistics import mean, median, pstdev

from . import baseline as bl
from . import thresholds as T
from .catalog import METRICS, fmt
from .timeutil import cn_date

LEVEL_ORDER = {"red": 0, "orange": 1, "yellow": 2, "info": 3, "green": 4}
PHYSIO = ("rhr", "hrv", "resp_rate", "wrist_temp", "spo2")
SHORT_TITLE = {"rhr": "静息心率比平时高", "hrv": "HRV 比平时低", "resp_rate": "睡眠呼吸频率比平时高",
               "wrist_temp": "夜间手腕温度比平时高", "spo2": "血氧比平时低"}
# 记录里出现这些词时，不管手表数据如何都要提醒及时就医
URGENT_SYMPTOMS = ("胸痛", "胸闷", "呼吸困难", "气短", "喘不上气", "憋气", "晕厥", "昏厥", "晕倒", "意识",
                   "口唇发紫", "嘴唇发紫", "言语不清", "说话不清", "口齿不清", "肢体无力", "半身", "口角歪斜",
                   "剧烈头痛", "咳血", "便血", "黑便")
FEVER_WORDS = ("发烧", "发热", "高烧", "低烧")
MEDICAL_CATS = ("体温", "心率", "呼吸", "血氧", "血压", "血糖")


def finding(level, cat, title, detail="", advice=""):
    return {"level": level, "cat": cat, "title": title, "detail": detail, "advice": advice}


def _pick(store, key, days):
    """按顺序在 days 里找第一个有值的日期，返回 (day, value)。"""
    for d in days:
        v = store.get(d, key)
        if v is not None:
            return d, v
    return None, None


def _minutes_since_18(dt):
    """距离前一天 18:00 的分钟数，跨午夜也连续（23:30 → 330，01:00 → 420）。"""
    anchor = datetime.combine(dt.date(), time(18, 0), dt.tzinfo)
    if dt < anchor:
        anchor -= timedelta(days=1)
    return (dt - anchor).total_seconds() / 60


class Analyzer:
    def __init__(self, store, today, tz, weather=None, calendar=None):
        self.s = store
        self.today = today
        self.yday = today - timedelta(days=1)
        self.tz = tz
        self.weather = weather
        self.cal = calendar
        self.findings = []

    def add(self, *a, **k):
        self.findings.append(finding(*a, **k))

    # ==================================================================
    def run(self):
        r = {"date": self.today.isoformat(), "date_cn": cn_date(self.today)}
        r["data"] = self._data_status()
        r["sleep"] = self._sleep()
        r["vitals"] = self._vitals()
        r["activity"] = self._activity(r["vitals"])
        r["body"] = self._body()
        r["manual"] = self._manual()
        r["calendar"] = self.cal
        r["weather"] = self.weather
        self._weather_rules()
        self._calendar_rules(r)
        r["readiness"] = self._readiness(r)
        r["plan"] = self._plan(r)
        r["trends"] = self._trends()
        self.findings.sort(key=lambda f: LEVEL_ORDER[f["level"]])
        r["findings"] = self.findings
        r["counts"] = {lv: sum(1 for f in self.findings if f["level"] == lv) for lv in LEVEL_ORDER}
        return r

    # ==================================================================
    def _data_status(self):
        latest = self.s.latest_day()
        days = len(self.s.watch_days())
        st = {"latest_day": latest.isoformat() if latest else None, "days_available": days,
              "sources": self.s.sources, "warnings": list(self.s.warnings)}
        if latest is None:
            st["state"] = "none"
            self.add("info", "数据", "还没有收到手表数据",
                     "Google Drive 里没有找到 Health Auto Export 导出的文件。",
                     "按 Google Drive「健康日报」文件夹里的「使用说明」在 iPhone 上设置 Health Auto Export 自动导出，"
                     "之后的报告就会包含睡眠、心率、HRV 和活动数据。")
        elif latest < self.yday:
            st["state"] = "stale"
            self.add("info", "数据", f"手表数据已经 {(self.today - latest).days} 天没有更新",
                     f"最新数据停在 {latest.month}月{latest.day}日。",
                     "解锁 iPhone 并打开一次 Health Auto Export；检查自动导出是否开着、后台 App 刷新是否打开。")
        else:
            st["state"] = "ok"
        st["baseline_ready"] = days >= bl.FULL_BASELINE_DAYS
        if latest and days < 7:
            self.add("info", "数据", f"正在建立你的个人基线（第 {days}/7 天）",
                     "现在只能按通用标准提醒；满 7 天后开始和你自己的平常水平对比，满 14 天后更准。",
                     "在 Health Auto Export 里手动导出一次最近 60 天的数据放进 Google Drive，基线马上就能建好。")
        return st

    # ==================================================================
    def _sleep(self):
        s = self.s
        night = s.sleep.get(self.today)
        which = "last_night" if night else None
        if night is None and s.latest_day() and s.latest_day() >= self.yday and self.yday in s.sleep:
            # 早上生成报告时，昨晚的睡眠可能还没从手表同步到手机
            night, which = s.sleep[self.yday], "previous"
        out = {"which": which}
        days7 = [self.today - timedelta(days=i) for i in range(7)]
        last7 = [s.sleep[d] for d in days7
                 if d in s.sleep and (s.sleep[d].total_h or 0) >= T.SLEEP_MIN_TRACKED_H]
        totals7 = [n.total_h for n in last7]
        out.update(avg7_h=mean(totals7) if totals7 else None, nights7=len(totals7),
                   short_nights7=sum(1 for t in totals7 if t < T.SLEEP_SHORT_H))
        onsets = [_minutes_since_18(n.start) for n in last7 if n.start]
        out["onset_sd_min"] = pstdev(onsets) if len(onsets) >= 4 else None
        out["duration_sd_min"] = pstdev(totals7) * 60 if len(totals7) >= 4 else None

        if night is None:
            if s.latest_day():
                self.add("info", "睡眠", "还没有昨晚的睡眠数据",
                         "可能是睡觉没戴表、手表没电，或者起床后手机还没同步。",
                         "起床后解锁手机、打开一下 Health Auto Export，数据会更及时。")
            self._sleep_week_rules(out)
            return out

        tot = round(night.total_h, 1)
        out.update({
            "day": night.day.isoformat(), "total_h": night.total_h, "deep_h": night.deep_h,
            "rem_h": night.rem_h, "core_h": night.core_h, "awake_h": night.awake_h, "inbed_h": night.inbed_h,
            "nap_h": night.nap_h, "source": night.source,
            "start": night.start.strftime("%H:%M") if night.start else None,
            "end": night.end.strftime("%H:%M") if night.end else None,
        })
        b = bl.compute(s, "sleep_h", night.day)
        out["baseline_h"] = b.median if b else None
        eff = night.total_h / night.inbed_h if night.inbed_h and night.inbed_h >= night.total_h else None
        out["efficiency"] = eff
        label = "昨晚" if which == "last_night" else "前一晚（昨晚的还没同步）"

        if tot < T.SLEEP_MIN_TRACKED_H:
            self.add("info", "睡眠", f"{label}只记录到 {tot} 小时睡眠",
                     "可能是中途摘了表或手表没电，数据不完整时不做判断。")
        elif tot < T.SLEEP_VERY_SHORT_H:
            self.add("orange", "睡眠", f"{label}只睡了 {tot} 小时",
                     "明显少于成年人每晚至少 7 小时的建议，会影响注意力、情绪和免疫力。",
                     "今天避免疲劳驾驶和高强度运动；午后可以小睡 20 分钟以内；今晚提前上床。")
        elif tot < T.SLEEP_SHORT_H:
            self.add("yellow", "睡眠", f"{label}只睡了 {tot} 小时",
                     "少于 6 小时会影响注意力和免疫力。", "今天避免疲劳驾驶和高强度训练，今晚争取早睡 30–60 分钟。")
        elif tot < T.SLEEP_TARGET_H:
            gap = round((T.SLEEP_TARGET_H - night.total_h) * 6) * 10
            self.add("yellow", "睡眠", f"{label}睡了 {tot} 小时，少于建议的 7 小时", "",
                     f"今晚争取提前 {max(gap, 10):.0f} 分钟上床。")
        else:
            self.add("green", "睡眠", f"{label}睡了 {tot} 小时")

        if night.start and tot >= T.SLEEP_MIN_TRACKED_H:
            m = night.start.hour * 60 + night.start.minute
            if T.LATE_ONSET_AFTER_MIN <= m < 6 * 60:
                self.add("yellow", "睡眠", f"{label} {night.start:%H:%M} 才入睡",
                         "建议成年人晚上 10–11 点入睡；研究发现午夜后入睡的人心血管疾病风险更高。",
                         "今晚试着提前半小时上床，睡前 1 小时调暗灯光、放下手机。")
        if eff is not None and eff < T.SLEEP_EFFICIENCY_LOW and night.inbed_h - night.total_h >= 0.5:
            self.add("yellow", "睡眠", f"躺在床上没睡着的时间偏多（睡眠效率 {eff:.0%}）",
                     "睡眠效率指在床时间里真正睡着的比例，建议 85% 以上。",
                     "睡不着时别在床上刷手机，起来做点安静的事，困了再回床。")
        self._sleep_week_rules(out)
        return out

    def _sleep_week_rules(self, out):
        s = self.s
        if out["nights7"] >= 4 and (out["short_nights7"] >= T.SLEEP_SHORT_NIGHTS_7
                                    or out["avg7_h"] < T.SLEEP_AVG7_LOW_H):
            self.add("orange", "睡眠", f"近 7 晚平均只睡 {out['avg7_h']:.1f} 小时，已经欠下睡眠债",
                     (f"其中 {out['short_nights7']} 晚不足 6 小时。" if out["short_nights7"] else "")
                     + "连续缺觉的影响会累积，一两晚补觉补不回来。",
                     "这周固定上床和起床时间；如果长期入睡困难或早醒，可以咨询睡眠门诊。")
        elif out["nights7"] >= 4 and out["avg7_h"] > T.SLEEP_AVG7_LONG_H:
            self.add("yellow", "睡眠", f"近 7 晚平均睡 {out['avg7_h']:.1f} 小时，偏长", "",
                     "如果睡很久仍然乏力、白天犯困，建议咨询医生。")
        sd, dsd = out.get("onset_sd_min"), out.get("duration_sd_min")
        onset_bad = sd is not None and sd > T.ONSET_SD_YELLOW_MIN
        dur_bad = dsd is not None and dsd > T.DURATION_SD_ORANGE_MIN
        if onset_bad or dur_bad:
            level = "orange" if (sd or 0) > T.ONSET_SD_ORANGE_MIN or dur_bad else "yellow"
            detail = []
            if onset_bad:
                detail.append(f"入睡时间前后相差约 ±{sd:.0f} 分钟")
            if dur_bad:
                detail.append(f"睡眠时长相差约 ±{dsd:.0f} 分钟")
            self.add(level, "睡眠", "最近一周作息不太规律",
                     "近 7 晚" + "，".join(detail) + "。作息不规律与心血管风险升高有关。",
                     "每天固定起床时间是让作息稳定下来最有效的办法，周末也尽量别差超过 1 小时。")
        wasos = [s.sleep[d].awake_h * 60 for d in (self.today - timedelta(days=i) for i in range(7))
                 if d in s.sleep and s.sleep[d].awake_h is not None]
        long_n = sum(1 for w in wasos if w > T.WASO_LONG_MIN)
        if long_n >= T.WASO_LONG_NIGHTS:
            self.add("yellow", "睡眠", f"近 7 晚有 {long_n} 晚夜里醒着超过 50 分钟", "",
                     "留意睡前饮酒、咖啡因、室温和噪音；如果经常夜醒、打鼾憋醒或白天很困，可以找医生聊聊。")

    # ==================================================================
    def _eval(self, key, day):
        """某天某指标和基线比较。"""
        v = self.s.get(day, key) if day else None
        if v is None:
            return None
        b = bl.compute(self.s, key, day)
        return {"key": key, "name": METRICS[key].name, "day": day.isoformat(), "value": v,
                "value_str": fmt(key, v), "baseline": b.median if b else None,
                "baseline_str": fmt(key, b.median) if b else None,
                "delta": b.delta(v) if b else None, "z": b.z(v) if b else None,
                "baseline_n": b.n if b else 0, "provisional": b.provisional if b else True}

    def _anchor(self, key, candidates):
        return _pick(self.s, key, candidates)[0]

    def _night_days(self):
        """各指标“昨晚/昨天”用哪个数据项、哪一天：{指标: (数据项, 日期)}。前一晚就是日期减一天。

        有逐小时数据时，呼吸频率、血氧、HRV 用只取睡眠时段的“夜间”版本（记在醒来那天）。
        """
        today, yday = self.today, self.yday
        night = self.s.sleep.get(today)
        # 苹果把夜间手腕温度记在“睡眠时段开始”那天，时段开始常比真正入睡早（入睡 00:40，时段 23:50）
        wt_days = [(night.start - timedelta(hours=3)).date(), night.start.date()] if night and night.start else [yday]

        def choose(base, night_key, fallback_days):
            if self.s.get(today, night_key) is not None and bl.compute(self.s, night_key, today):
                return night_key, today
            return base, self._anchor(base, fallback_days)

        if bl.hrv_status(self.s, "hrv_night", today):
            hrv = ("hrv_night", today)
        else:
            hrv = ("hrv", self._anchor("hrv", [yday]))
        return {
            "rhr": ("rhr", self._anchor("rhr", [yday])),
            "hrv": hrv,
            "resp_rate": choose("resp_rate", "resp_night", [today, yday]),
            "spo2": choose("spo2", "spo2_night", [today, yday]),
            "wrist_temp": ("wrist_temp", self._anchor("wrist_temp", wt_days)),
            "sleep_h": ("sleep_h", today if today in self.s.sleep else None),
            "steps": ("steps", yday),
        }

    def _ev(self, a, name, n=0):
        """a 里某个指标往前推 n 天的比较结果。"""
        key, day = a[name]
        return self._eval(key, self._shift(day, n))

    @staticmethod
    def _shift(day, n):
        return day - timedelta(days=n) if day else None

    def _outliers(self, a, n):
        """n=0 看昨晚，n=1 看前一晚。返回 {指标: 描述}，只统计往“不好”方向的偏离。"""
        out = {}
        x = self._ev(a, "rhr", n)
        if x and x["delta"] is not None and (x["delta"] >= T.RHR_DELTA or x["z"] >= T.RHR_Z):
            out["rhr"] = f"静息心率 {x['value']:.0f}，比平时（{x['baseline']:.0f}）高 {x['delta']:.0f} 次/分"
        hk, hd = a["hrv"]
        hs = bl.hrv_status(self.s, hk, self._shift(hd, n)) if hd else None
        if hs and hs.today_z <= T.HRV_Z_OUTLIER:
            out["hrv"] = f"HRV {hs.today_ms:.0f} 毫秒，明显低于平时（约 {hs.base_ms:.0f}）"
        x = self._ev(a, "resp_rate", n)
        if x and x["delta"] is not None and (x["delta"] >= T.RESP_DELTA or x["z"] >= T.RESP_Z):
            out["resp_rate"] = f"睡眠呼吸频率 {x['value']:.1f}，比平时（{x['baseline']:.1f}）高 {x['delta']:.1f} 次/分"
        x = self._ev(a, "wrist_temp", n)
        if x and x["delta"] is not None and x["delta"] >= T.TEMP_DELTA:
            out["wrist_temp"] = f"夜间手腕温度比平时高 {x['delta']:.1f}°C"
        x = self._ev(a, "spo2", n)
        if x and x["delta"] is not None and (x["delta"] <= -T.SPO2_DROP or x["value"] < T.SPO2_OUTLIER_ABS):
            out["spo2"] = f"血氧 {x['value']:.1f}%，低于平时（{x['baseline']:.1f}%）"
        # 行为类指标（睡得少、走得少）只在已经有生理指标异常时才一起算，睡得多不算异常
        if any(k in out for k in PHYSIO):
            x = self._ev(a, "sleep_h", n)
            if x and x["delta"] is not None and x["delta"] <= -T.SLEEP_DEV_H:
                out["sleep_h"] = f"睡眠 {x['value']:.1f} 小时，比平时（{x['baseline']:.1f}）少 {abs(x['delta']):.1f} 小时"
            if n == 0:
                x = self._ev(a, "steps")
                if x and x["baseline"] and x["value"] < x["baseline"] * T.STEPS_DROP_RATIO:
                    out["steps"] = f"昨天步数 {x['value']:,.0f}，不到平时的一半"
        return out

    def _vitals(self):
        a = self._night_days()
        v = {k: self._ev(a, k) for k in ("rhr", "resp_rate", "spo2", "wrist_temp")}
        v["walking_hr"] = self._eval("walking_hr", self.yday)
        v["vo2max"] = self._eval("vo2max", self._anchor("vo2max", [self.yday - timedelta(days=i) for i in range(21)]))
        v["breathing_dist"] = self._eval("breathing_dist", self._anchor("breathing_dist", [self.today, self.yday]))
        # HRV：优先夜间（需要逐小时数据），否则用昨天全天均值；在对数尺度上和 60 天基线比
        hrv_key, hrv_day = a["hrv"]
        v["hrv"] = self._eval(hrv_key, hrv_day)
        hs = bl.hrv_status(self.s, hrv_key, hrv_day) if hrv_day else None
        if v["hrv"] and hs:
            v["hrv"].update(baseline=hs.base_ms, baseline_str=f"{hs.lo_ms:.0f}–{hs.hi_ms:.0f}",
                            z=hs.today_z, delta=hs.today_ms - hs.base_ms, provisional=False)
        v["hrv_week"] = hs.__dict__ if hs else None

        now, prev = self._outliers(a, 0), self._outliers(a, 1)
        v["signals"], v["signals_prev"] = list(now.values()), list(prev.values())
        v["recovery_level"] = self._recovery_rules(v, a, now, prev, hs)
        self._absolute_vitals(v, a)
        return v

    def _absolute_flags(self, a):
        """昨晚/昨天是否有不依赖基线的危险值，用于和多项偏离一起升级为红色。"""
        flags = []
        rk, rd = a["rhr"]
        x = self.s.get(rd, rk) if rd else None
        if x is not None and x > T.RHR_HIGH:
            flags.append(f"静息心率 {x:.0f} 次/分")
        rk, rd = a["resp_rate"]
        x = self.s.get(rd, rk) if rd else None
        if x is not None and x > T.RESP_HIGH:
            flags.append(f"睡眠呼吸频率 {x:.1f} 次/分")
        rk, rd = a["spo2"]
        x = self.s.get(rd, rk) if rd else None
        if x is not None and x < T.SPO2_LOW_RED:
            flags.append(f"血氧 {x:.1f}%")
        return flags

    def _recovery_rules(self, v, a, now, prev, hs):
        """所有“恢复/可能在生病”的信号合并成一条提醒，避免同一件事说好几遍。

        多项偏离里必须至少有一项是生理指标（静息心率、HRV、呼吸、手腕温度、血氧）；
        只是睡得少、走得少不会被当成“可能在生病”。
        """
        notes, level = [], None

        def bump(lv):
            nonlocal level
            if level is None or LEVEL_ORDER[lv] < LEVEL_ORDER[level]:
                level = lv

        physio0 = [k for k in now if k in PHYSIO]
        n0, n1 = len(now), len(prev)
        if n0 >= 2 and physio0:
            bump("orange")
            if n1 >= 2:
                notes.append("而且前一晚也是这样")
        elif len(physio0) == 1 and physio0[0] in ("rhr", "resp_rate", "wrist_temp"):
            bump("yellow")

        def persist(name, thr):
            x0, x1 = self._ev(a, name), self._ev(a, name, 1)
            return (x0 and x1 and x0["delta"] is not None and x1["delta"] is not None
                    and x0["delta"] >= thr and x1["delta"] >= thr)

        if persist("rhr", T.RHR_PERSIST_DELTA):
            bump("orange")
            notes.append("静息心率已连续 2 天高于平时，研究发现这种持续升高常出现在感冒等感染症状出现前几天")
        if persist("resp_rate", T.RESP_PERSIST_DELTA):
            bump("orange")
            notes.append("睡眠呼吸频率连续 2 晚偏高，健康时它通常很稳定")
        t0 = self._ev(a, "wrist_temp")
        if (t0 and t0["delta"] is not None and t0["delta"] >= T.TEMP_DELTA_HIGH) or persist("wrist_temp", T.TEMP_DELTA):
            bump("orange")
            notes.append("夜间手腕温度明显或连续偏高（室温、被子太厚、饮酒、月经周期也会影响；"
                         "手腕温度不等于体温，不舒服时用体温计量一下）")
        hrv_band = False
        if hs and hs.week_z is not None:
            if hs.below_days >= 3:
                bump("orange")
                hrv_band = True
                notes.append(f"HRV 近 7 天均值 {hs.week_ms:.0f} 毫秒，已连续几天低于你的正常范围"
                             f"（{hs.lo_ms:.0f}–{hs.hi_ms:.0f}）")
            elif hs.week_z < -T.HRV_WEEK_BAND:
                bump("orange" if "rhr" in now else "yellow")
                hrv_band = True
                notes.append(f"HRV 近 7 天均值 {hs.week_ms:.0f} 毫秒，低于你的正常范围（{hs.lo_ms:.0f}–{hs.hi_ms:.0f}），"
                             "恢复可能不足")

        flags = self._absolute_flags(a)
        if len(physio0) + ("sleep_h" in now) + ("steps" in now) >= 3 and flags:
            bump("red")

        if level is None:
            rhr, hrv = v.get("rhr"), v.get("hrv")
            if rhr and hrv and rhr["z"] is not None and hrv["z"] is not None and rhr["z"] <= 0 and hrv["z"] >= 0:
                self.add("green", "恢复", "静息心率和 HRV 都在平常或更好的水平，恢复不错")
            return None

        symptoms = self._recent_manual("symptoms")
        drinks = self._recent_manual("alcohol")
        detail = ("；".join(now.values()) + "。") if now else ""
        detail += "".join(f"{n}。" for n in notes)
        slept_little = "sleep_h" in now or ((self.s.sleep.get(self.today) and
                                             (self.s.sleep[self.today].total_h or 9) < T.SLEEP_SHORT_H))
        causes = ["睡眠不足"] if slept_little else []
        causes.append(f"饮酒（你记录了 {drinks:g} 杯）" if drinks else "饮酒")
        causes += ["晚饭太晚", "压力大", "训练过量"]
        cause_txt = "常见原因有" + "、".join(causes) + "，也可能是身体正在对抗感染。"
        if level == "red":
            self.add("red", "恢复", "多项身体指标同时异常，而且" + "、".join(flags) + "超出正常范围",
                     detail + "这不是诊断，但这种组合值得尽快让医生看看。",
                     "建议今天联系医生或去医院；如伴有胸痛、呼吸困难、意识模糊或口唇发紫，请立即拨打 120。")
        elif level == "orange":
            if symptoms:
                title = f"你记录了不适（{symptoms}），身体指标也有变化"
            elif n0 >= 2 and physio0:
                title = f"{n0} 项身体指标同时偏离平常水平"
            else:
                title = "恢复指标持续偏离平常水平"
            strong = n0 >= 3 or n1 >= 2 or bool(symptoms)
            advice = ("今天以恢复为主：运动降到轻松强度或休息一天，多喝水，今晚早睡。留意发热、咽痛、咳嗽、乏力；"
                      + ("如果出现发热等症状，可以考虑就医或检测。" if strong else "如果 2–3 天还不恢复，建议就医。"))
            self.add("orange", "恢复", title, detail + cause_txt, advice)
        else:
            if hrv_band and not physio0:
                title = "HRV 近一周低于你的正常范围"
            else:
                title = SHORT_TITLE.get(physio0[0], "恢复指标略偏离平常") if physio0 else "恢复指标略偏离平常"
            self.add("yellow", "恢复", title, detail + "单项指标偶尔波动很常见。", "今天运动别太猛，明天再看是否恢复。")
        return level

    def _absolute_vitals(self, v, a):
        s = self.s
        rk, rd = a["rhr"]
        if rd:
            vals = [s.get(rd - timedelta(days=i), rk) for i in range(T.RHR_HIGH_DAYS_RED)]
            if all(x is not None and x > T.RHR_HIGH for x in vals):
                self.add("red", "心率", f"静息心率已连续 {T.RHR_HIGH_DAYS_RED} 天高于 100 次/分",
                         "安静时心率持续超过 100 次/分需要查明原因（这不是诊断）。",
                         "建议近期到心内科或全科就诊。如伴有胸痛、心慌、头晕、气短，请立即就医或拨打 120。")
            elif vals[0] is not None and vals[0] > T.RHR_HIGH:
                self.add("orange", "心率", f"昨天静息心率 {vals[0]:.0f} 次/分，高于成人正常上限 100",
                         "发热、脱水、饮酒、咖啡因、焦虑、睡眠不足都可能引起。",
                         "注意休息补水；若持续 3 天以上或伴心慌、胸闷、气短、头晕，建议就医。")
        rhr = v.get("rhr")
        if rhr:
            val, base = rhr["value"], rhr["baseline"]
            near_usual = base is not None and base - val <= 5          # 平时就这么低（常运动的人）
            if val < T.RHR_VERY_LOW or (val < T.RHR_LOW and not near_usual) or \
                    (val < T.RHR_LOW_NEW and base is not None and base >= 60) or \
                    (base is not None and base - val >= T.RHR_DROP and val < 50):
                self.add("orange", "心率", f"静息心率 {val:.0f} 次/分，明显偏低",
                         (f"你平时约 {base:.0f}。" if base else "") + "常锻炼的人心率偏低可能正常。",
                         "如出现头晕、乏力、眼前发黑或晕厥，请及时就医。")
        rk, rd = a["resp_rate"]
        if rd:
            rr = [s.get(rd - timedelta(days=i), rk) for i in range(2)]
            if all(x is not None and x > T.RESP_HIGH for x in rr):
                self.add("red", "呼吸", f"睡眠呼吸频率连续 2 晚超过 {T.RESP_HIGH} 次/分",
                         "明显高于成人 12–20 次/分的正常范围。",
                         "建议尽快就医评估；若出现呼吸困难、胸痛、口唇发紫，请立即拨打 120。")
        sk, sd = a["spo2"]
        if sd:
            last7 = [s.get(sd - timedelta(days=i), sk) for i in range(7)]
            last7 = [x for x in last7 if x is not None]
            very_low = sum(1 for x in last7 if x < T.SPO2_LOW_RED)
            low = sum(1 for x in last7 if x < T.SPO2_LOW)
            sp = v.get("spo2")
            if very_low >= 2:
                self.add("red", "血氧", f"近 7 天有 {very_low} 天平均血氧低于 {T.SPO2_LOW_RED}%",
                         "手表血氧有误差，但反复偏低可能与睡眠呼吸问题有关（这不是诊断）。",
                         "建议近期到呼吸科或睡眠门诊评估。若出现气短、胸闷、口唇发紫，请立即就医。")
            elif sp and sp["value"] < T.SPO2_LOW:
                # 连续多天偏低、而且比你自己的平常水平还低，才升级为橙色
                worse = sp["baseline"] is not None and sp["value"] <= sp["baseline"] - T.SPO2_DROP
                self.add("orange" if (low >= 3 and worse) else "yellow", "血氧",
                         f"血氧 {sp['value']:.1f}%，低于常见的 95% 以上" + (f"（近 7 天有 {low} 天）" if low >= 3 else ""),
                         "手表血氧误差约 ±2–3 个百分点，表带松、手冷、压着手臂睡都会让读数偏低。",
                         "睡前把表带稍微系紧一点继续观察；如果常打鼾、夜里憋醒、白天明显犯困，建议到睡眠门诊看看。")
        _, bt = _pick(s, "body_temp", [self.today, self.yday])
        if bt is not None:
            if bt >= T.FEVER_HIGH:
                self.add("red", "体温", f"体温 {bt:.1f}°C，属于高热", "",
                         "多喝水、注意休息，建议就医；如伴有意识改变、呼吸困难、剧烈头痛，请立即拨打 120。")
            elif bt >= T.FEVER:
                self.add("orange", "体温", f"体温 {bt:.1f}°C，有发热", "",
                         "多休息多喝水，每隔几小时复测；超过 38.5°C 持续不退或持续 3 天以上请就医。")

    # ==================================================================
    def _activity(self, vitals):
        s, d = self.s, self.yday
        out = {"day": d.isoformat()}
        for k in ("steps", "active_kcal", "exercise_min", "stand_hours", "distance_km", "flights",
                  "daylight_min", "headphone_db"):
            out[k] = s.get(d, k)
        out["workouts"] = [w.__dict__ for w in s.workouts_on(d)]
        last7 = lambda k: s.values_between(k, d - timedelta(days=6), d)
        ex7, steps7, day7, hp7 = last7("exercise_min"), last7("steps"), last7("daylight_min"), last7("headphone_db")
        out.update(exercise7=sum(ex7) if ex7 else None, exercise7_days=len(ex7),
                   steps7_avg=mean(steps7) if steps7 else None, daylight7_avg=mean(day7) if day7 else None)
        ex28 = s.values_between("exercise_min", d - timedelta(days=27), d)
        chronic_week = sum(ex28) / 4 if len(ex28) >= 21 else None
        out["acwr"] = (sum(ex7) / chronic_week) if (chronic_week and chronic_week >= T.ACWR_MIN_CHRONIC_WEEK
                                                    and len(ex7) >= 5) else None

        if out["exercise7"] is not None and out["exercise7_days"] >= 5:
            if out["exercise7"] >= T.EXERCISE_WEEK_MIN:
                self.add("green", "活动", f"近 7 天锻炼 {out['exercise7']:.0f} 分钟，达到每周 150 分钟的建议")
            else:
                gap = T.EXERCISE_WEEK_MIN - out["exercise7"]
                self.add("yellow", "活动", f"近 7 天锻炼 {out['exercise7']:.0f} 分钟，离每周 150 分钟还差 {gap:.0f} 分钟",
                         "世界卫生组织和《中国居民膳食指南》都建议每周至少 150 分钟中等强度运动。",
                         "快走、骑车、游泳都算；每周再加 2 次力量训练更好。")
        if out["steps7_avg"] is not None and len(steps7) >= 5 and out["steps7_avg"] < T.STEPS_AVG7_LOW:
            self.add("yellow", "活动", f"近 7 天日均 {out['steps7_avg']:,.0f} 步，偏少",
                     "《中国居民膳食指南》建议每天主动身体活动 6000 步。",
                     "饭后散步 15 分钟、走楼梯、提前一站下车，都能轻松多走两三千步。")
        if out["acwr"] is not None and out["acwr"] > T.ACWR_HIGH:
            poor = vitals.get("recovery_level") is not None
            self.add("orange" if poor else "yellow", "活动",
                     f"这周锻炼量约为过去 4 周平均的 {out['acwr']:.1f} 倍"
                     + ("，而恢复指标也在变差" if poor else ""),
                     "运动量增加太快，受伤和过度疲劳的风险会上升。",
                     "安排 1–2 天休息或低强度活动；之后循序渐进，每周增量最好别超过 10%。")
        if out["stand_hours"] and out["stand_hours"] < T.STAND_HOURS_LOW and (out["steps"] or 0) > 1000:
            self.add("yellow", "活动", f"昨天只有 {out['stand_hours']:.0f} 个小时起身活动过", "久坐本身就是健康风险。",
                     "每坐 1 小时起来走动 2–3 分钟，可以打开手表的站立提醒。")
        if out["daylight7_avg"] is not None and len(day7) >= 5 and out["daylight7_avg"] < T.DAYLIGHT_AVG7_LOW_MIN:
            self.add("yellow", "活动", f"近 7 天平均每天在户外日光下 {out['daylight7_avg']:.0f} 分钟", "",
                     "白天尤其上午多到户外走走，晚上睡前 3 小时调暗灯光，有助于稳定作息和睡眠。")
        if len(hp7) >= 3 and mean(hp7) >= T.HEADPHONE_DB:
            self.add("yellow", "听力", f"近 7 天耳机平均音量 {mean(hp7):.0f} dB，偏大",
                     "世界卫生组织建议成人 80 分贝每周累计不超过 40 小时。",
                     "把音量调到最大值的 60% 以下，嘈杂环境用降噪耳机，每听 1 小时让耳朵休息一下。")
        return out

    # ==================================================================
    def _body(self):
        s = self.s
        out = {}
        for k in ("weight_kg", "bmi", "body_fat", "bp_sys", "bp_dia", "glucose"):
            d, v = _pick(s, k, [self.today - timedelta(days=i) for i in range(30)])
            out[k] = {"value": v, "day": d.isoformat()} if d else None
        w_now = s.values_between("weight_kg", self.today - timedelta(days=6), self.today)
        w_prev = s.values_between("weight_kg", self.today - timedelta(days=13), self.today - timedelta(days=7))
        if len(w_now) >= 2 and len(w_prev) >= 2:   # 至少各称两次、用中位数，避免早晚一次称重的正常波动
            chg = median(w_now) - median(w_prev)
            out["weight_change_7d"] = chg
            if abs(chg) >= T.WEIGHT_WEEK_CHANGE_KG:
                self.add("orange", "身体", f"体重一周内变化 {chg:+.1f} kg", "短期波动多与水分、饮食有关。",
                         "如果不是在刻意减重或增重，或者伴有水肿、气短、乏力，请就医。")
        w_old = s.values_between("weight_kg", self.today - timedelta(days=59), self.today - timedelta(days=30))
        if len(w_now) >= 2 and len(w_old) >= 2:
            pct = (median(w_now) - median(w_old)) / median(w_old) * 100
            out["weight_change_pct_long"] = pct
            if pct <= -T.WEIGHT_LOSS_PCT:
                self.add("orange", "身体", f"最近一两个月体重下降了 {abs(pct):.0f}%", "",
                         "如果不是有意减重，医学上建议就医查明原因。")
        if out.get("bmi"):
            b = out["bmi"]["value"]
            out["bmi_cat"] = "偏瘦" if b < 18.5 else "正常" if b < 24 else "超重" if b < 28 else "肥胖"
        self._bp_rules(out)
        for d in (self.today, self.yday):
            lo = s.get(d, "glucose_min") if s.get(d, "glucose_min") is not None else s.get(d, "glucose")
            hi = s.get(d, "glucose_max") if s.get(d, "glucose_max") is not None else s.get(d, "glucose")
            if lo is None:
                continue
            when = "今天" if d == self.today else "昨天"
            if lo < T.GLUCOSE_LOW:
                self.add("orange", "血糖", f"{when}测到血糖偏低（{lo:.1f} mmol/L）", "",
                         ("马上吃点含糖食物；" if d == self.today else "如果再次出现心慌、出汗、手抖，马上吃点含糖食物；")
                         + "反复出现低血糖请就医。")
            elif hi is not None and hi >= T.GLUCOSE_HIGH:
                self.add("orange", "血糖", f"{when}测到血糖偏高（{hi:.1f} mmol/L）", "",
                         "如果不是餐后不久测的，建议就医检查空腹血糖和糖化血红蛋白。")
            break
        return out

    def _bp_rules(self, out):
        s = self.s
        days = [self.today - timedelta(days=i) for i in range(7)]
        pairs = [(d, s.get(d, "bp_sys"), s.get(d, "bp_dia")) for d in days]
        pairs = [(d, a, b) for d, a, b in pairs if a is not None and b is not None]
        if not pairs:
            return
        latest_day, latest_sys, latest_dia = pairs[0]
        avg_sys, avg_dia = mean(p[1] for p in pairs), mean(p[2] for p in pairs)
        out["bp_avg7"] = {"sys": avg_sys, "dia": avg_dia, "days": len(pairs)}
        recent = latest_day >= self.today - timedelta(days=2)
        when = "今天" if latest_day == self.today else "昨天" if latest_day == self.yday else \
            f"{latest_day.month}月{latest_day.day}日"
        txt = f"{latest_sys:.0f}/{latest_dia:.0f} mmHg（{when}）"
        protocol = "规范自测：连续 7 天，每天早晚各测一次，每次测 2–3 遍、间隔 1 分钟，取后 6 天的平均值。"
        if recent and (latest_sys >= T.BP_GRADE3_SYS or latest_dia >= T.BP_GRADE3_DIA):
            self.add("red", "血压", f"血压 {txt}，达到 3 级高血压水平", "这个读数需要马上处理（这不是诊断）。",
                     "静坐休息 5 分钟后复测；若仍 ≥180/110 请尽快就医；若伴胸痛、呼吸困难、剧烈头痛、视物模糊、"
                     "言语不清或肢体无力，请立即拨打 120。")
            return
        grade2 = sum(1 for _, a, b in pairs if a >= T.BP_GRADE2_SYS or b >= T.BP_GRADE2_DIA)
        if grade2 >= 2:
            self.add("red", "血压", f"近 7 天有 {grade2} 天血压 ≥160/100", "",
                     "建议这几天内到心内科或全科就诊，请勿自行用药。")
        elif len(pairs) >= 3 and (avg_sys >= T.BP_HOME_HIGH_SYS or avg_dia >= T.BP_HOME_HIGH_DIA):
            self.add("red", "血压", f"近 7 天家庭血压平均 {avg_sys:.0f}/{avg_dia:.0f} mmHg",
                     "达到《中国高血压防治指南（2024）》里家庭血压的高血压界值（≥135/85）。",
                     "建议到心内科或全科就诊确认，请勿自行用药。")
        elif recent and (latest_sys >= T.BP_HOME_HIGH_SYS or latest_dia >= T.BP_HOME_HIGH_DIA):
            self.add("orange", "血压", f"血压 {txt}，偏高", "单次读数说明不了太多，需要规范测量。", protocol)
        elif len(pairs) >= 3 and (avg_sys >= T.BP_NORMAL_HIGH_SYS or avg_dia >= T.BP_NORMAL_HIGH_DIA):
            self.add("yellow", "血压", f"近 7 天血压平均 {avg_sys:.0f}/{avg_dia:.0f}，处于正常高值",
                     "还不算高血压，但值得通过生活方式干预。", "少盐（每天不超过 5 克）、控制体重、规律运动、限酒。")

    # ==================================================================
    def _recent_manual(self, field):
        for d in (self.today, self.yday):
            v = self.s.manual.get(d, {}).get(field)
            if v:
                return v
        return None

    def _manual(self):
        entries = {d.isoformat(): rec for d, rec in self.s.manual.items() if d >= self.yday}
        sym = self._recent_manual("symptoms")
        urgent = [w for w in URGENT_SYMPTOMS if sym and w in sym]
        if urgent:
            self.add("red", "记录", f"你记录的症状里有「{'、'.join(urgent)}」",
                     f"原话：{sym}。这类症状可能需要尽快处理（这不是诊断）。",
                     "如果现在仍有这些症状，请立即就医或拨打 120；已经缓解，也建议尽快找医生看看。")
        elif sym and any(w in sym for w in FEVER_WORDS):
            self.add("orange", "记录", f"你记录了发热：{sym}", "",
                     "今天别运动，多喝水、多休息，量一下体温；超过 38.5°C 持续不退或持续 3 天以上请就医。")
        elif sym and not any(f["title"].startswith("你记录了不适") for f in self.findings):
            self.add("yellow", "记录", f"你记录了不适：{sym}", "", "多休息、多喝水，留意变化；症状加重或持续请就医。")
        drinks = self._recent_manual("alcohol")
        if drinks and drinks >= T.ALCOHOL_DRINKS:
            self.add("yellow", "记录", f"昨天喝了 {drinks:g} 杯酒",
                     "酒精会让深睡变少、静息心率升高、HRV 下降，常常要一两天才恢复。", "今天多喝水，别安排高强度训练。")
        stress = self._recent_manual("stress")
        if stress and stress >= T.STRESS_HIGH:
            self.add("yellow", "记录", f"压力自评 {stress:g}/5，偏高", "",
                     "试试 5 分钟的缓慢呼吸（吸气 4 秒、呼气 6 秒），或者饭后散步一圈。")
        mood = self._recent_manual("mood")
        if mood and mood <= T.MOOD_LOW:
            self.add("yellow", "记录", f"心情自评 {mood:g}/5", "",
                     "对自己好一点：晒晒太阳、动一动、和信任的人聊聊。如果情绪低落持续两周以上，可以寻求专业帮助。")
        caf = self._recent_manual("caffeine")
        if caf and caf >= T.CAFFEINE_CUPS:
            self.add("yellow", "记录", f"昨天喝了 {caf:g} 杯含咖啡因饮品", "", "下午 2 点以后尽量不喝咖啡和浓茶，以免影响睡眠。")
        return entries

    # ==================================================================
    def _weather_rules(self):
        """天气相关的提醒合并成一条，免得天气把真正的身体提醒挤下去。

        网页搜索来的天气（reliable=False）只显示、不提醒。高温和寒潮按气象部门的预警标准做“参考”，
        不等于官方预警。
        """
        w = self.weather
        if not w or not w.get("reliable", True):
            return
        items = []   # (级别, 短标题, 建议)
        aqi = w.get("aqi")
        o3 = "O₃" in (w.get("aqi_primary") or "")
        if aqi is not None:
            if aqi > 200:
                items.append(("orange", f"空气{w.get('aqi_level')}（AQI {aqi:.0f}）",
                              "停止户外运动，关窗开空气净化器；外出戴 KN95/N95 口罩"))
            elif aqi > 150:
                items.append(("orange", f"空气中度污染（AQI {aqi:.0f}）", "户外运动改到室内，外出戴口罩"))
            elif aqi > 100:
                items.append(("yellow", f"空气轻度污染（AQI {aqi:.0f}）",
                              "经常户外运动的人也属于敏感人群，长时间或高强度的运动改到室内"
                              + ("；臭氧下午最高，要出门就选早上" if o3 else "")))
        tmax3 = [t for t in (w.get("tmax_next3") or []) if t is not None]
        fmax = w.get("feels_max") if w.get("feels_max") is not None else w.get("temp_max")
        fmin = w.get("feels_min") if w.get("feels_min") is not None else w.get("temp_min")
        if tmax3 and max(tmax3) >= 37 or (len(tmax3) == 3 and min(tmax3) >= 35):
            lv = "红色" if max(tmax3) >= 40 else "橙色" if max(tmax3) >= 37 else "黄色"
            items.append(("orange", f"未来几天高温（达到高温{lv}预警标准，仅供参考）",
                          "午后尽量减少户外活动，多补水，老人和有慢性病的人尤其注意防暑"))
        elif fmax is not None and fmax >= T.HEAT_ORANGE:
            items.append(("orange", f"很热（体感最高 {fmax:.0f}°C）",
                          "停止午后户外高强度运动，运动前中后都补水，头晕恶心要马上到阴凉处休息"))
        elif fmax is not None and fmax >= T.HEAT_YELLOW:
            items.append(("yellow", f"较热（体感最高 {fmax:.0f}°C）", "户外运动安排在早晚，注意补水"))
        tmin, tmin_prev = w.get("temp_min"), w.get("tmin_prev")
        if tmin is not None and tmin_prev is not None and tmin_prev - tmin >= 8 and tmin <= 4:
            items.append(("yellow", f"明显降温（最低气温从 {tmin_prev:.0f}°C 降到 {tmin:.0f}°C）",
                          "及时加衣；骤然降温时心脑血管负担加重，有高血压的人注意监测"))
        if fmin is not None and fmin <= T.COLD:
            items.append(("yellow", f"很冷（体感最低 {fmin:.0f}°C）", "注意保暖防冻，户外运动前充分热身"))
        tmax = w.get("temp_max")
        if tmax is not None and tmin is not None and tmax - tmin >= T.TEMP_SWING:
            items.append(("yellow", f"温差大（{tmin:.0f}–{tmax:.0f}°C）", "早晚加件外套"))
        uv = w.get("uv_max")
        if uv is not None and uv >= T.UV_HIGH:
            items.append(("yellow", f"紫外线很强（UV {uv:.0f}）", "避免中午外出；出门遮阳、戴帽子、涂 SPF30+ 防晒霜"))
        pp = w.get("precip_prob")
        if pp is not None and pp >= T.RAIN_PROB:
            items.append(("info", f"降水概率 {pp:.0f}%", "出门带伞"))
        if not items:
            return
        level = min((lv for lv, _, _ in items), key=lambda lv: LEVEL_ORDER[lv])
        self.add(level, "天气", "今天" + "、".join(t for _, t, _ in items),
                 w.get("aqi_advice", "") if aqi is not None and aqi > 100 else "",
                 "；".join(a for _, _, a in items) + "。")

    # ==================================================================
    def _calendar_rules(self, r):
        c = self.cal
        if not c or not c.get("count"):
            return
        if c["busy_hours"] >= T.BUSY_HOURS or c["longest_block_hours"] >= T.LONG_BLOCK_HOURS:
            self.add("yellow", "日程", f"今天日程很满（{c['count']} 项，约 {c['busy_hours']:.1f} 小时）",
                     f"最长连续 {c['longest_block_hours']:.1f} 小时。",
                     "每 60–90 分钟起身活动一下、喝口水；把最费脑的事放在精力最好的时段。")
        sl = r.get("sleep") or {}
        sleep_h = sl.get("total_h") if sl.get("which") == "last_night" else None
        if sleep_h is not None and sleep_h < T.SLEEP_MIN_TRACKED_H:
            sleep_h = None
        if c.get("first_start_dt") and sleep_h and sleep_h < T.SLEEP_TARGET_H \
                and c["first_start_dt"].time() <= time(8, 30):
            self.add("yellow", "日程", f"今天 {c['first_start']} 就有安排，而昨晚睡得不多", "",
                     "早餐吃好，上午少喝含糖饮料；午间争取小睡一会儿。")
        if c.get("last_end_dt") and c["last_end_dt"].time() >= time(21, 0):
            self.add("yellow", "日程", f"今晚的安排到 {c['last_end']} 才结束", "",
                     "结束后别再看工作消息，给自己留 1 小时放松再睡。")

    # ==================================================================
    def _readiness(self, r):
        """0–100 的“今日状态”分。启发式，仅供参考：睡眠 40%、HRV 25%、静息心率 25%、其他夜间体征 10%。"""
        parts = []
        sl = r["sleep"]
        if sl.get("total_h") and sl.get("which") == "last_night" and sl["total_h"] >= T.SLEEP_MIN_TRACKED_H:
            t = sl["total_h"]
            sc = 100 if t >= 8 else (100 - (8 - t) * 15 if t >= 6 else max(10, 70 - (6 - t) * 25))
            if sl.get("short_nights7", 0) >= T.SLEEP_SHORT_NIGHTS_7:
                sc -= 10
            parts.append(("睡眠", max(0, min(100, sc)), 0.40))
        v = r["vitals"]
        hw = v.get("hrv_week")
        if hw:
            z = hw["today_z"] if hw["week_z"] is None else (hw["today_z"] + hw["week_z"]) / 2
            parts.append(("HRV", _interp(z, [(-3, 20), (-2, 45), (-1, 75), (0, 95), (1, 100)]), 0.25))
        if v.get("rhr") and v["rhr"]["z"] is not None:
            parts.append(("静息心率", _interp(v["rhr"]["z"], [(-1, 100), (0, 95), (1, 80), (2, 55), (3, 30)]), 0.25))
        other, have_other = 100, False
        for k, bad in (("resp_rate", lambda x: x["delta"] >= T.RESP_DELTA),
                       ("wrist_temp", lambda x: x["delta"] >= T.TEMP_DELTA),
                       ("spo2", lambda x: x["delta"] <= -T.SPO2_DROP)):
            x = v.get(k)
            if x and x["delta"] is not None:
                have_other = True
                other -= 35 if bad(x) else 0
        if have_other:
            parts.append(("其他体征", max(0, other), 0.10))
        core = [p for p in parts if p[0] in ("睡眠", "HRV", "静息心率")]
        if not core:
            return None
        score = round(sum(p[1] * p[2] for p in parts) / sum(p[2] for p in parts))
        if v.get("recovery_level") == "orange":
            score = min(score, 60)
        # 有需要就医的提醒时，“状态分”不能还显示充沛
        if any(f["level"] == "red" for f in self.findings):
            score = min(score, 40)
        elif any(f["level"] == "orange" and f["cat"] in MEDICAL_CATS for f in self.findings):
            score = min(score, 55)
        for lo, label, tone in ((85, "充沛", "green"), (70, "良好", "green"), (55, "一般", "yellow"),
                                (0, "需要恢复", "orange")):
            if score >= lo:
                break
        return {"score": score, "label": label, "tone": tone,
                "parts": [{"name": n, "score": round(sc), "weight": w} for n, sc, w in parts],
                "partial": len(core) < 3}

    def _plan(self, r):
        """今日运动建议。先看有没有需要处理的健康问题，再看恢复状态、睡眠和天气。"""
        rd = r.get("readiness")
        w = self.weather or {}
        if not w.get("reliable", True):
            w = {}
        feels = w.get("feels_max") if w.get("feels_max") is not None else w.get("temp_max")
        aqi = w.get("aqi")
        outdoor_ok = (aqi is None or aqi <= 150) and (feels is None or feels < T.HEAT_ORANGE)
        slot = (self.cal or {}).get("exercise_slot")
        sl = r["sleep"]
        last = sl.get("total_h") if sl.get("which") == "last_night" and \
            (sl.get("total_h") or 0) >= T.SLEEP_MIN_TRACKED_H else None
        reds = [f for f in self.findings if f["level"] == "red"]
        medical = [f for f in self.findings if f["level"] == "orange" and f["cat"] in MEDICAL_CATS]
        symptoms = self._recent_manual("symptoms")

        if reds:
            return {"exercise": "今天先别安排运动，把上面红色提醒里的事处理好；身体允许的话，散散步就好。", "level": "none"}
        if medical or symptoms or r["vitals"].get("recovery_level") == "orange" \
                or (rd and rd["score"] < 55) or (last is not None and last < T.SLEEP_VERY_SHORT_H):
            ex, lvl = "今天以恢复为主：散步、拉伸、瑜伽，或者干脆休息一天。", "recovery"
        elif rd is None:
            ex, lvl = "保持日常活动，今天目标 30 分钟快走或同等强度的运动。", "moderate"
        elif rd["score"] >= 80 and (last is None or last >= T.SLEEP_SHORT_H):
            ex, lvl = "状态不错，可以安排一次有强度的训练（跑步、力量训练、间歇训练都可以）。", "hard"
        else:
            ex, lvl = "适合中等强度：快走、慢跑、骑车或游泳 30–45 分钟，别冲极限。", "moderate"
        if not outdoor_ok:
            ex += "今天天气不适合户外，建议在室内进行。"
        elif aqi is not None and aqi > 100 and lvl != "recovery":
            ex += "空气轻度污染，长时间或高强度的运动放到室内。"
        if slot and lvl != "recovery":
            ex += f"日程里 {slot} 比较空，可以安排在这个时段。"
        return {"exercise": ex, "level": lvl}

    # ==================================================================
    def _trends(self):
        """近 14 天走势，用于报告里的小柱状图。"""
        out = {}
        for k, end in (("sleep_h", self.today), ("steps", self.yday), ("rhr", self.yday),
                       ("hrv", self.yday), ("exercise_min", self.yday)):
            days = [end - timedelta(days=i) for i in range(13, -1, -1)]
            out[k] = [{"day": d.isoformat(), "value": self.s.get(d, k)} for d in days]
        return out


def _interp(x, pts):
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]
