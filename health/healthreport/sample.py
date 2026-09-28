"""生成示例数据（Health Auto Export 按天汇总格式），用来测试和演示，不含任何真实数据。

情景：
  normal   — 普通的一段时间
  illness  — 最后两天出现“生病前兆”：静息心率↑、HRV↓、呼吸频率↑、手腕温度↑
  shortsleep — 最近一周多晚睡眠不足
"""

import json
import math
import os
import random
from datetime import date, datetime, time, timedelta


def _ts(d, t=time(0, 0)):
    return datetime.combine(d, t).strftime("%Y-%m-%d %H:%M:%S") + " +0800"


def generate(end: date, days=60, scenario="normal", seed=7):
    rnd = random.Random(seed)
    metrics = {k: [] for k in (
        "step_count", "active_energy", "apple_exercise_time", "apple_stand_hour", "walking_running_distance",
        "resting_heart_rate", "heart_rate", "heart_rate_variability", "respiratory_rate",
        "blood_oxygen_saturation", "apple_sleeping_wrist_temperature", "walking_heart_rate_average",
        "time_in_daylight", "vo2_max", "weight_body_mass", "sleep_analysis", "headphone_audio_exposure")}
    workouts = []
    for i in range(days):
        d = end - timedelta(days=days - 1 - i)
        weekend = d.weekday() >= 5
        last = days - 1 - i          # 0 = end 当天
        ill = scenario == "illness" and last <= 1
        # 睡眠：醒来日期 = d
        sleep_h = rnd.gauss(7.3 if weekend else 6.9, 0.45)
        if scenario == "shortsleep" and last <= 6 and last % 2 == 0:
            sleep_h = rnd.uniform(4.8, 5.8)
        if ill:
            sleep_h = rnd.uniform(6.0, 6.6)
        bed = datetime.combine(d - timedelta(days=1), time(23, 20)) + timedelta(minutes=rnd.gauss(0, 25))
        wake = bed + timedelta(hours=sleep_h + 0.3)
        deep, rem = sleep_h * rnd.uniform(0.13, 0.19), sleep_h * rnd.uniform(0.2, 0.25)
        metrics["sleep_analysis"].append({
            "date": _ts(d), "totalSleep": round(sleep_h, 3), "asleep": 0, "core": round(sleep_h - deep - rem, 3),
            "deep": round(deep, 3), "rem": round(rem, 3), "awake": round(rnd.uniform(0.1, 0.4), 3),
            "inBed": round(sleep_h + 0.3, 3),
            "sleepStart": bed.strftime("%Y-%m-%d %H:%M:%S +0800"),
            "sleepEnd": wake.strftime("%Y-%m-%d %H:%M:%S +0800"),
            "inBedStart": bed.strftime("%Y-%m-%d %H:%M:%S +0800"),
            "inBedEnd": wake.strftime("%Y-%m-%d %H:%M:%S +0800"), "source": "Apple Watch"})
        rhr = rnd.gauss(58, 1.6) + (7 if ill else 0)
        hrv = max(15, rnd.gauss(48, 6) - (17 if ill else 0))
        metrics["resting_heart_rate"].append({"date": _ts(d), "qty": round(rhr), "source": "Apple Watch"})
        metrics["heart_rate_variability"].append({"date": _ts(d), "qty": round(hrv, 1), "source": "Apple Watch"})
        metrics["heart_rate"].append({"date": _ts(d), "Min": round(rhr - 6), "Avg": round(rhr + 16),
                                      "Max": round(rnd.uniform(120, 165)), "source": "Apple Watch"})
        metrics["respiratory_rate"].append({"date": _ts(d), "qty": round(rnd.gauss(14.6, 0.35) + (2.0 if ill else 0), 1),
                                            "source": "Apple Watch"})
        metrics["blood_oxygen_saturation"].append({"date": _ts(d), "qty": round(rnd.gauss(96.8, 0.6), 1),
                                                   "source": "Apple Watch"})
        metrics["apple_sleeping_wrist_temperature"].append(
            {"date": _ts(d), "qty": round(35.2 + rnd.gauss(0, 0.12) + (0.8 if ill else 0), 2), "source": "Apple Watch"})
        metrics["walking_heart_rate_average"].append({"date": _ts(d), "qty": round(rnd.gauss(96, 3)),
                                                      "source": "Apple Watch"})
        # 活动：end 当天只到早上，数据很少
        partial = 0.08 if last == 0 else 1.0
        steps = max(800, rnd.gauss(10500 if weekend else 7800, 2200)) * partial * (0.6 if ill else 1)
        exercise = 0
        if rnd.random() < (0.55 if not ill else 0.1) and last != 0:
            exercise = rnd.uniform(25, 55)
            start = datetime.combine(d, time(18, 40)) + timedelta(minutes=rnd.randint(-30, 60))
            kind = rnd.choice(["Outdoor Run", "Traditional Strength Training", "Outdoor Walk", "Indoor Cycling"])
            dist = exercise / 60 * (9.5 if "Run" in kind else 5.2 if "Walk" in kind else 0)
            w = {"name": kind, "start": start.strftime("%Y-%m-%d %H:%M:%S +0800"),
                 "end": (start + timedelta(minutes=exercise)).strftime("%Y-%m-%d %H:%M:%S +0800"),
                 "duration": exercise * 60,
                 "activeEnergyBurned": {"qty": round(exercise * rnd.uniform(7, 11)), "units": "kcal"},
                 "avgHeartRate": {"qty": round(rnd.uniform(118, 152)), "units": "bpm"},
                 "maxHeartRate": {"qty": round(rnd.uniform(155, 178)), "units": "bpm"}}
            if dist:
                w["distance"] = {"qty": round(dist, 2), "units": "km"}
            workouts.append(w)
        metrics["step_count"].append({"date": _ts(d), "qty": round(steps), "source": "Apple Watch|iPhone"})
        metrics["walking_running_distance"].append({"date": _ts(d), "qty": round(steps * 0.00072, 2),
                                                    "source": "Apple Watch|iPhone"})
        metrics["active_energy"].append({"date": _ts(d), "qty": round((steps * 0.035 + exercise * 8) * rnd.uniform(0.9, 1.1)),
                                         "source": "Apple Watch"})
        metrics["apple_exercise_time"].append({"date": _ts(d), "qty": round(exercise + rnd.uniform(3, 12) * partial),
                                               "source": "Apple Watch"})
        metrics["apple_stand_hour"].append({"date": _ts(d), "qty": round(rnd.uniform(7, 13) * partial),
                                            "source": "Apple Watch"})
        metrics["time_in_daylight"].append({"date": _ts(d), "qty": round(rnd.uniform(15, 90) * partial),
                                            "source": "Apple Watch"})
        metrics["headphone_audio_exposure"].append({"date": _ts(d), "qty": round(rnd.gauss(68, 5), 1),
                                                    "source": "AirPods"})
        if i % 7 == 3:
            metrics["vo2_max"].append({"date": _ts(d), "qty": round(41.5 + i * 0.02, 1), "source": "Apple Watch"})
        if rnd.random() < 0.4:
            metrics["weight_body_mass"].append({"date": _ts(d), "qty": round(68.4 + math.sin(i / 9) * 0.6 + rnd.gauss(0, 0.2), 1),
                                                "source": "Health"})
    units = {"step_count": "count", "active_energy": "kcal", "apple_exercise_time": "min",
             "apple_stand_hour": "count", "walking_running_distance": "km", "resting_heart_rate": "count/min",
             "heart_rate": "count/min", "heart_rate_variability": "ms", "respiratory_rate": "count/min",
             "blood_oxygen_saturation": "%", "apple_sleeping_wrist_temperature": "degC",
             "walking_heart_rate_average": "count/min", "time_in_daylight": "min", "vo2_max": "ml/(kg·min)",
             "weight_body_mass": "kg", "sleep_analysis": "hr", "headphone_audio_exposure": "dBASPL"}
    return {"data": {"metrics": [{"name": k, "units": units[k], "data": v} for k, v in metrics.items()],
                     "workouts": workouts}}


def write_demo(out_dir, end: date, days=60, scenario="normal"):
    os.makedirs(out_dir, exist_ok=True)
    data_dir = os.path.join(out_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    start = end - timedelta(days=days - 1)
    path = os.path.join(data_dir, f"HealthAutoExport-{start}-{end}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(generate(end, days, scenario), f, ensure_ascii=False)
    y = end - timedelta(days=1)
    with open(os.path.join(out_dir, "manual.csv"), "w", encoding="utf-8") as f:
        f.write("日期,体重(kg),收缩压,舒张压,心情(1-5),压力(1-5),饮酒(杯),咖啡因(杯),症状,用药,备注\n")
        f.write(f"{y - timedelta(days=1)},68.6,118,76,4,2,0,2,,,\n")
        f.write(f"{y},,124,79,3,4,1,3,{'有点嗓子疼' if scenario == 'illness' else ''},,加班到很晚\n")
    with open(os.path.join(out_dir, "calendar.json"), "w", encoding="utf-8") as f:
        ev = lambda h1, m1, h2, m2, t: {"summary": t, "start": f"{end}T{h1:02d}:{m1:02d}:00+08:00",
                                          "end": f"{end}T{h2:02d}:{m2:02d}:00+08:00"}
        json.dump([ev(9, 30, 10, 30, "周会"), ev(10, 30, 12, 0, "产品评审"), ev(14, 0, 15, 30, "客户电话"),
                   ev(15, 30, 17, 0, "方案讨论"), {"summary": "国庆假期", "start": str(end + timedelta(days=2)),
                                                "end": str(end + timedelta(days=9)), "allDay": True}],
                  f, ensure_ascii=False)
    with open(os.path.join(out_dir, "weather.json"), "w", encoding="utf-8") as f:
        json.dump({"source": "示例数据", "desc": "多云", "temp_min": 13, "temp_max": 25, "feels_max": 24,
                   "uv_max": 6, "precip_prob": 10, "aqi": 118, "aqi_primary": "PM2.5", "pm25": 88,
                   "sunrise": "06:09", "sunset": "18:00"}, f, ensure_ascii=False)
    return path
