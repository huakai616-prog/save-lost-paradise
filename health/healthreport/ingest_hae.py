"""Health Auto Export（iOS App）导出的 JSON。

结构：{"data": {"metrics": [{"name", "units", "data": [...]}, ...], "workouts": [...]}}
推荐在 App 里把“时间分组”设成“天”（按天汇总），这样文件小、苹果已经帮忙去重；
原始样本（不汇总）也能读，只是步数这类累加值要靠启发式去重。
"""

import json
import os

from .aggregate import Aggregator, stage_name
from .store import SleepNight, Workout
from .timeutil import local_date, parse_dt

# Health Auto Export 指标名 → (我们的指标, 取值字段)
SIMPLE = {
    "step_count": "steps",
    "active_energy": "active_kcal",
    "basal_energy_burned": "basal_kcal",
    "apple_exercise_time": "exercise_min",
    "apple_stand_hour": "stand_hours",
    "apple_stand_time": "stand_min",
    "walking_running_distance": "distance_km",
    "flights_climbed": "flights",
    "time_in_daylight": "daylight_min",
    "mindful_minutes": "mindful_min",
    "physical_effort": "physical_effort",
    "resting_heart_rate": "rhr",
    "walking_heart_rate_average": "walking_hr",
    "walking_heart_rate": "walking_hr",
    "heart_rate_variability": "hrv",
    "respiratory_rate": "resp_rate",
    "blood_oxygen_saturation": "spo2",
    "oxygen_saturation": "spo2",
    "apple_sleeping_wrist_temperature": "wrist_temp",
    "body_temperature": "body_temp",
    "vo2_max": "vo2max",
    "vo2max": "vo2max",
    "breathing_disturbances": "breathing_dist",
    "apple_sleeping_breathing_disturbances": "breathing_dist",
    "cardio_recovery": "cardio_recovery",
    "weight_body_mass": "weight_kg",
    "body_mass_index": "bmi",
    "body_fat_percentage": "body_fat",
    "blood_glucose": "glucose",
    "headphone_audio_exposure": "headphone_db",
    "headphone_audio": "headphone_db",
    "environmental_audio_exposure": "env_db",
    "environmental_audio": "env_db",
    "dietary_water": "water_ml",
}


# ---- 单位换算 ----
def _unit(u):
    return (u or "").strip().lower().replace(" ", "")


def convert(key, value, units):
    """把数值换算到目录里约定的单位。"""
    if value is None:
        return None
    u = _unit(units)
    v = float(value)
    if key in ("active_kcal", "basal_kcal"):
        if u in ("kj", "kilojoules"):
            return v / 4.184
        return v   # kcal / Cal
    if key == "distance_km":
        if u in ("mi", "mile", "miles"):
            return v * 1.609344
        if u in ("m", "meter", "meters"):
            return v / 1000
        return v
    if key in ("wrist_temp", "body_temp"):
        if u in ("degf", "°f", "f", "fahrenheit"):
            return (v - 32) * 5 / 9
        return v
    if key == "weight_kg":
        if u in ("lb", "lbs", "pound", "pounds"):
            return v * 0.45359237
        if u in ("g",):
            return v / 1000
        return v
    if key in ("spo2", "body_fat"):
        return v * 100 if v <= 1.0 else v   # 有的版本给 0–1 的小数
    if key == "glucose":
        if "mg" in u:
            return v / 18.016
        return v
    if key == "water_ml":
        if u in ("l", "liter", "litre"):
            return v * 1000
        if "oz" in u:
            return v * 29.5735
        return v
    if key in ("exercise_min", "stand_min", "daylight_min", "mindful_min"):
        if u in ("s", "sec", "seconds"):
            return v / 60
        if u in ("hr", "h", "hours"):
            return v * 60
        return v
    return v


def _qty(entry):
    for f in ("qty", "Avg", "avg", "value"):
        if isinstance(entry.get(f), (int, float)):
            return entry[f]
    return None


def _src(entry):
    return str(entry.get("source") or "")


def _parse_metric(agg, metric, tz):
    name = (metric.get("name") or "").strip()
    units = metric.get("units")
    data = metric.get("data") or []
    if name == "sleep_analysis":
        _parse_sleep(agg, data, tz)
        return
    if name == "heart_rate":
        for e in data:
            ts = parse_dt(e.get("date"), tz)
            day = local_date(e.get("date"), tz)
            src = _src(e)
            mn = e.get("Min", e.get("min"))
            av = e.get("Avg", e.get("avg", e.get("qty")))
            mx = e.get("Max", e.get("max"))
            agg.add("hr_min", day, mn if mn is not None else av, src, ts)
            agg.add("hr_avg", day, av, src, ts)
            agg.add("hr_max", day, mx if mx is not None else av, src, ts)
        return
    if name == "blood_pressure":
        for e in data:
            ts = parse_dt(e.get("date"), tz)
            day = local_date(e.get("date"), tz)
            agg.add("bp_sys", day, e.get("systolic"), _src(e), ts)
            agg.add("bp_dia", day, e.get("diastolic"), _src(e), ts)
        return
    key = SIMPLE.get(name)
    if key is None:
        return
    for e in data:
        ts = parse_dt(e.get("date"), tz)
        day = local_date(e.get("date"), tz)
        q = _qty(e)
        if key == "spo2" and not q:
            continue   # 0 表示没测到
        agg.add(key, day, convert(key, q, units), _src(e), ts)
        if key == "spo2":
            lo = e.get("Min", e.get("min"))
            agg.add("spo2_min", day, convert("spo2", lo if lo is not None else q, units), _src(e), ts)
        elif key == "glucose":   # 低血糖看当天最低值，高血糖看最高值，不能被均值掩盖
            agg.add("glucose_min", day, convert(key, q, units), _src(e), ts)
            agg.add("glucose_max", day, convert(key, q, units), _src(e), ts)


def _hours_field(e, *names):
    for n in names:
        v = e.get(n)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _parse_sleep(agg, data, tz):
    for e in data:
        if ("startDate" in e or "start" in e) and ("value" in e or "stage" in e):
            # 原始片段：{"startDate"/"start","endDate"/"end","value":"Core","qty":0.5,"source"}
            st = stage_name(e.get("value") or e.get("stage"))
            agg.add_sleep_segment(parse_dt(e.get("startDate") or e.get("start"), tz),
                                  parse_dt(e.get("endDate") or e.get("end"), tz), st, _src(e))
            continue
        # 按天汇总：{"date"(醒来那天),"totalSleep","core","deep","rem","awake","asleep","inBed","sleepStart","sleepEnd",...}
        start = parse_dt(e.get("sleepStart") or e.get("inBedStart"), tz)
        end = parse_dt(e.get("sleepEnd") or e.get("inBedEnd"), tz)
        core = _hours_field(e, "core") or 0
        deep = _hours_field(e, "deep") or 0
        rem = _hours_field(e, "rem") or 0
        asleep = _hours_field(e, "asleep") or 0     # 未分期的睡眠，Apple Watch 上多半是白天小睡
        inbed = _hours_field(e, "inBed") or 0
        awake = _hours_field(e, "awake")
        staged = core + deep + rem
        nap = None
        if staged > 0:
            total = staged
            nap = asleep if asleep >= 0.1 else None
        else:
            total = _hours_field(e, "totalSleep") or asleep or inbed   # 第三方 App 可能只有“睡眠/卧床”
        if not total:
            continue
        # 醒来那天：优先按 sleepEnd（date 字段在部分版本里带着任意时刻），没有再用 date 的日期部分
        day = end.date() if end else (local_date(e.get("date"), tz) if e.get("date") else None)
        if day is None:
            continue
        # sleepStart–sleepEnd 覆盖当天所有片段（含小睡），跨度明显大于睡眠时间时起止时刻不可信
        if start and end and (end - start).total_seconds() / 3600 > total + (awake or 0) + (nap or 0) + 3:
            start = end = None
        agg.add_sleep_summary(SleepNight(
            day=day, total_h=total, deep_h=deep or None, rem_h=rem or None, core_h=core or None,
            awake_h=awake, inbed_h=inbed or None, start=start, end=end, source=_src(e), nap_h=nap))


# ---- 体能训练 ----
WORKOUT_CN = {
    "outdoor run": "户外跑步", "indoor run": "室内跑步", "running": "跑步",
    "outdoor walk": "户外步行", "indoor walk": "室内步行", "walking": "步行",
    "outdoor cycling": "户外骑行", "indoor cycling": "室内骑行", "cycling": "骑行",
    "traditional strength training": "传统力量训练", "functional strength training": "功能性力量训练",
    "strength training": "力量训练", "high intensity interval training": "高强度间歇训练",
    "hiit": "高强度间歇训练", "core training": "核心训练", "yoga": "瑜伽", "pilates": "普拉提",
    "pool swim": "泳池游泳", "open water swim": "开放水域游泳", "swimming": "游泳",
    "hiking": "徒步", "elliptical": "椭圆机", "rower": "划船机", "rowing": "划船",
    "stair stepper": "踏步机", "stairs": "爬楼梯", "dance": "舞蹈", "cooldown": "整理放松",
    "mixed cardio": "混合有氧", "tai chi": "太极", "mind and body": "身心训练",
    "flexibility": "柔韧训练", "badminton": "羽毛球", "basketball": "篮球", "soccer": "足球",
    "tennis": "网球", "table tennis": "乒乓球", "jump rope": "跳绳", "climbing": "攀岩",
    "skiing": "滑雪", "golf": "高尔夫", "other": "其他运动",
}


def workout_name_cn(name):
    n = (name or "").strip()
    return WORKOUT_CN.get(n.lower(), n or "运动")


def _qty_units(obj):
    """{"qty": 1.2, "units": "km"} / 数字 / [{"qty":..}, ...]（逐分钟样本，求和）。"""
    if obj is None:
        return None, None
    if isinstance(obj, (int, float)):
        return float(obj), None
    if isinstance(obj, dict):
        q = obj.get("qty", obj.get("avg", obj.get("Avg")))
        return (float(q) if isinstance(q, (int, float)) else None), obj.get("units")
    if isinstance(obj, list):
        qs = [x.get("qty") for x in obj if isinstance(x, dict) and isinstance(x.get("qty"), (int, float))]
        units = next((x.get("units") for x in obj if isinstance(x, dict) and x.get("units")), None)
        return (sum(qs) if qs else None), units
    return None, None


def _parse_workout(agg, w, tz):
    start = parse_dt(w.get("start"), tz)
    end = parse_dt(w.get("end"), tz)
    if start is None:
        return
    if end and end > start:
        dur = (end - start).total_seconds() / 60
    else:
        d = w.get("duration")
        dur = float(d) / 60 if isinstance(d, (int, float)) else None   # Health Auto Export 给的是秒
    kcal, ku = _qty_units(w.get("activeEnergyBurned") or w.get("activeEnergy"))
    kcal = convert("active_kcal", kcal, ku) if kcal is not None else None
    dist, du = _qty_units(w.get("distance") or w.get("walkingAndRunningDistance"))
    dist = convert("distance_km", dist, du) if dist is not None else None
    hr = w.get("heartRate") if isinstance(w.get("heartRate"), dict) else {}
    avg_hr, _ = _qty_units(w.get("avgHeartRate") or hr.get("avg"))
    max_hr, _ = _qty_units(w.get("maxHeartRate") or hr.get("max"))
    if avg_hr is None and isinstance(w.get("heartRateData"), list):
        vals = [x.get("Avg") or x.get("qty") for x in w["heartRateData"] if isinstance(x, dict)]
        vals = [v for v in vals if isinstance(v, (int, float))]
        if vals:
            avg_hr = sum(vals) / len(vals)
            maxes = [x.get("Max") for x in w["heartRateData"] if isinstance(x, dict)
                     and isinstance(x.get("Max"), (int, float))]
            max_hr = max_hr or (max(maxes) if maxes else max(vals))
    agg.add_workout(Workout(day=start.date(), name=workout_name_cn(w.get("name")), start=start, end=end,
                            duration_min=dur, kcal=kcal, distance_km=dist, avg_hr=avg_hr, max_hr=max_hr))


def parse(obj, tz, source_name="Health Auto Export", last_day=None):
    """已经 json.load 的对象 → DayData。last_day 之后的数据会被丢弃。"""
    agg = Aggregator(source_name)
    metrics, workouts = _sections(obj)
    if not metrics and not workouts:
        agg.warnings.append(f"{source_name}: 没有找到 metrics / workouts，可能不是 Health Auto Export 的 JSON")
    for m in metrics:
        try:
            _parse_metric(agg, m, tz)
        except Exception as e:  # 单个指标格式异常不影响其他指标
            agg.warnings.append(f"{source_name}: 解析 {m.get('name')} 失败：{e}")
    for w in workouts:
        try:
            _parse_workout(agg, w, tz)
        except Exception as e:
            agg.warnings.append(f"{source_name}: 解析体能训练失败：{e}")
    if last_day is not None:
        agg.drop_future(last_day)
    return agg.finish()


def _sections(obj):
    """返回 (metrics, workouts)。也兼容 Health Auto Export 服务器版的 {"data":{"healthMetrics":{"metrics":..}}}。"""
    root = obj.get("data", obj) if isinstance(obj, dict) else {}
    if not isinstance(root, dict):
        return [], []
    metrics = root.get("metrics")
    workouts = root.get("workouts")
    if metrics is None and isinstance(root.get("healthMetrics"), dict):
        metrics = root["healthMetrics"].get("metrics")
    if isinstance(workouts, dict):
        workouts = workouts.get("workouts")
    metrics = [m for m in metrics or [] if isinstance(m, dict)]
    workouts = [w for w in workouts or [] if isinstance(w, dict)]
    return metrics, workouts


def looks_like_hae(obj):
    root = obj.get("data") if isinstance(obj, dict) else None
    return isinstance(root, dict) and any(k in root for k in ("metrics", "workouts", "healthMetrics"))


def load(path, tz, last_day=None):
    """读一个 JSON 文件；不是 Health Auto Export 格式时返回 None。"""
    with open(path, encoding="utf-8-sig") as f:
        obj = json.load(f)
    if not looks_like_hae(obj):
        return None
    return parse(obj, tz, os.path.basename(path), last_day)
