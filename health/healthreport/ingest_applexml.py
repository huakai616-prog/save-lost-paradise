"""苹果「健康」App 原生导出（导出所有健康数据 → export.zip / export.xml）。

适合一次性导入很长的历史数据来建立基线。文件可能有几百 MB，这里用流式解析，
只取最近 N 天（默认 120 天）的数据，内存占用很小。
"""

import os
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import timedelta

from .aggregate import Aggregator, stage_name
from .ingest_hae import convert, workout_name_cn
from .store import Workout
from .timeutil import local_date, parse_dt

QUANTITY = {
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_kcal",
    "HKQuantityTypeIdentifierBasalEnergyBurned": "basal_kcal",
    "HKQuantityTypeIdentifierAppleExerciseTime": "exercise_min",
    "HKQuantityTypeIdentifierAppleStandTime": "stand_min",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance_km",
    "HKQuantityTypeIdentifierFlightsClimbed": "flights",
    "HKQuantityTypeIdentifierTimeInDaylight": "daylight_min",
    "HKQuantityTypeIdentifierPhysicalEffort": "physical_effort",
    "HKQuantityTypeIdentifierRestingHeartRate": "rhr",
    "HKQuantityTypeIdentifierWalkingHeartRateAverage": "walking_hr",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv",
    "HKQuantityTypeIdentifierRespiratoryRate": "resp_rate",
    "HKQuantityTypeIdentifierOxygenSaturation": "spo2",
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": "wrist_temp",
    "HKQuantityTypeIdentifierBodyTemperature": "body_temp",
    "HKQuantityTypeIdentifierVO2Max": "vo2max",
    "HKQuantityTypeIdentifierHeartRateRecoveryOneMinute": "cardio_recovery",
    "HKQuantityTypeIdentifierBodyMass": "weight_kg",
    "HKQuantityTypeIdentifierBodyMassIndex": "bmi",
    "HKQuantityTypeIdentifierBodyFatPercentage": "body_fat",
    "HKQuantityTypeIdentifierBloodPressureSystolic": "bp_sys",
    "HKQuantityTypeIdentifierBloodPressureDiastolic": "bp_dia",
    "HKQuantityTypeIdentifierBloodGlucose": "glucose",
    "HKQuantityTypeIdentifierHeadphoneAudioExposure": "headphone_db",
    "HKQuantityTypeIdentifierEnvironmentalAudioExposure": "env_db",
    "HKQuantityTypeIdentifierDietaryWater": "water_ml",
    "HKQuantityTypeIdentifierAppleSleepingBreathingDisturbances": "breathing_dist",
}


def _open(path):
    if path.lower().endswith(".zip"):
        z = zipfile.ZipFile(path)
        xmls = [n for n in z.namelist() if n.lower().endswith(".xml") and not n.lower().endswith("_cda.xml")]
        if not xmls:
            raise ValueError("压缩包里没有 export.xml")
        name = max(xmls, key=lambda n: z.getinfo(n).file_size)
        return z.open(name)
    return open(path, "rb")


def _strip_doctype(stream):
    """去掉内部 DTD（部分 iOS 版本的 DTD 本身有语法错误），逐块产出字节。"""
    head = stream.read(1 << 20)
    head = re.sub(rb"<!DOCTYPE.*?\]>", b"", head, count=1, flags=re.S)
    yield head
    while True:
        chunk = stream.read(1 << 20)
        if not chunk:
            break
        yield chunk


def parse(path, tz, days=120, today=None):
    agg = Aggregator(os.path.basename(path))
    parser = ET.XMLPullParser(events=("start", "end"))
    depth = 0
    root = None
    cutoff = None
    if today is not None:
        cutoff = today - timedelta(days=days)
    stand_hours = {}
    with _open(path) as f:
        for chunk in _strip_doctype(f):
            # iOS 16.0/16.1 的已知问题：WorkoutStatistics 里 startDate 写了两次
            if b"<WorkoutStatistics" in chunk:
                chunk = re.sub(rb'(<WorkoutStatistics[^>]*?startDate="[^"]*")([^>]*?)startDate=',
                               rb"\1\2endDate=", chunk)
            parser.feed(chunk)
            for ev, el in parser.read_events():
                if ev == "start":
                    if root is None:
                        root = el
                    depth += 1
                    continue
                depth -= 1
                if depth != 1:   # 只处理 HealthData 的直接子元素
                    continue
                try:
                    _handle(el, agg, tz, cutoff, stand_hours)
                except Exception as e:
                    if len(agg.warnings) < 20:
                        agg.warnings.append(f"{agg.source_name}: 跳过一条记录（{e}）")
                root.clear()   # 处理完就丢掉，保持内存占用恒定
    for day, hours in stand_hours.items():
        agg.add("stand_hours", day, len(hours), "Apple Watch")
    return agg.finish()


def _handle(el, agg, tz, cutoff, stand_hours):
    tag = el.tag
    if tag == "Record":
        typ = el.get("type", "")
        start_s = el.get("startDate")
        day = local_date(start_s, tz)
        if day is None or (cutoff and day < cutoff):
            return
        src = el.get("sourceName", "")
        if typ == "HKCategoryTypeIdentifierSleepAnalysis":
            agg.add_sleep_segment(parse_dt(start_s, tz), parse_dt(el.get("endDate"), tz),
                                  stage_name(el.get("value")), src)
        elif typ == "HKQuantityTypeIdentifierHeartRate":
            ts = parse_dt(start_s, tz)
            v = float(el.get("value"))
            agg.add("hr_min", day, v, src, ts)
            agg.add("hr_avg", day, v, src, ts)
            agg.add("hr_max", day, v, src, ts)
        elif typ == "HKCategoryTypeIdentifierAppleStandHour":
            if el.get("value", "").endswith("Stood"):
                stand_hours.setdefault(day, set()).add(start_s[:13])
        elif typ == "HKCategoryTypeIdentifierMindfulSession":
            s, e = parse_dt(start_s, tz), parse_dt(el.get("endDate"), tz)
            if s and e:
                agg.add("mindful_min", day, (e - s).total_seconds() / 60, src, s)
        elif typ in QUANTITY:
            key = QUANTITY[typ]
            v = el.get("value")
            if v is None:
                return
            v = float(v)
            if key == "spo2" and v == 0:
                return
            agg.add(key, day, convert(key, v, el.get("unit")), src, parse_dt(start_s, tz))
    elif tag == "Workout":
        start = parse_dt(el.get("startDate"), tz)
        if start is None or (cutoff and start.date() < cutoff):
            return
        end = parse_dt(el.get("endDate"), tz)
        dur = float(el.get("duration") or 0)
        unit = (el.get("durationUnit") or "min").lower()
        dur_min = dur * 60 if unit.startswith("h") else dur / 60 if unit.startswith("s") else dur
        kcal = el.get("totalEnergyBurned")
        kcal = convert("active_kcal", float(kcal), el.get("totalEnergyBurnedUnit")) if kcal else None
        dist = el.get("totalDistance")
        dist = convert("distance_km", float(dist), el.get("totalDistanceUnit")) if dist else None
        avg_hr = max_hr = None
        for st in el.findall("WorkoutStatistics"):
            t = st.get("type", "")
            if t.endswith("HeartRate"):
                avg_hr = float(st.get("average")) if st.get("average") else None
                max_hr = float(st.get("maximum")) if st.get("maximum") else None
            elif t.endswith("ActiveEnergyBurned") and kcal is None and st.get("sum"):
                kcal = convert("active_kcal", float(st.get("sum")), st.get("unit"))
            elif t.endswith("DistanceWalkingRunning") and dist is None and st.get("sum"):
                dist = convert("distance_km", float(st.get("sum")), st.get("unit"))
        name = el.get("workoutActivityType", "").replace("HKWorkoutActivityType", "")
        name = re.sub(r"(?<!^)(?=[A-Z])", " ", name)
        agg.add_workout(Workout(day=start.date(), name=workout_name_cn(name), start=start, end=end,
                                duration_min=dur_min, kcal=kcal, distance_km=dist, avg_hr=avg_hr, max_hr=max_hr))
