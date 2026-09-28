import base64
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from healthreport import calendar_ctx, collect, history, ingest_applexml, ingest_hae, manual  # noqa: E402
from healthreport.aggregate import stage_name  # noqa: E402
from healthreport.store import HealthStore  # noqa: E402
from healthreport.timeutil import get_tz, local_date, parse_dt  # noqa: E402

TZ = get_tz("Asia/Shanghai")


def metric(name, units, data):
    return {"name": name, "units": units, "data": data}


class TimeTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_dt("2026-02-06 00:00:00 -0800", TZ).utcoffset(), timedelta(hours=-8))
        self.assertEqual(parse_dt("2026-02-06 1:05:00 PM +0800", TZ).hour, 13)
        self.assertEqual(parse_dt("2026-02-06 23:10:00.123 +0800", TZ).minute, 10)
        self.assertEqual(parse_dt("2026-09-29T10:00:00+08:00", TZ).hour, 10)
        self.assertEqual(parse_dt("2026-09-29", TZ).tzinfo, TZ)
        self.assertIsNone(parse_dt("not a date", TZ))

    def test_local_date_keeps_phone_date(self):
        # 按天汇总的数据：取字面日期，不做时区换算
        self.assertEqual(local_date("2026-02-06 00:00:00 -0800", TZ), date(2026, 2, 6))
        # UTC 的 Z 时间换算到本地
        self.assertEqual(local_date("2026-09-28T20:00:00Z", TZ), date(2026, 9, 29))


class HaeTests(unittest.TestCase):
    def parse(self, metrics=(), workouts=()):
        return ingest_hae.parse({"data": {"metrics": list(metrics), "workouts": list(workouts)}}, TZ)

    def test_units_and_shapes(self):
        dd = self.parse([
            metric("active_energy", "kJ", [{"date": "2026-09-28 00:00:00 +0800", "qty": 1255.2}]),
            metric("blood_oxygen_saturation", "%", [{"date": "2026-09-28 00:00:00 +0800", "qty": 0.97},
                                                     {"date": "2026-09-27 00:00:00 +0800", "qty": 0}]),
            metric("heart_rate", "count/min", [{"date": "2026-09-28 00:00:00 +0800", "Min": 50, "Avg": 70, "Max": 150}]),
            metric("apple_sleeping_wrist_temperature", "degF", [{"date": "2026-09-28 00:00:00 +0800", "qty": 95.9}]),
            metric("walking_heart_rate", "count/min", [{"date": "2026-09-28 00:00:00 +0800", "qty": 95}]),
            metric("weight_body_mass", "lb", [{"date": "2026-09-28 07:00:00 +0800", "qty": 150}]),
            metric("unknown_metric", "x", [{"date": "2026-09-28 00:00:00 +0800", "qty": 1}]),
        ])
        v = dd.values[date(2026, 9, 28)]
        self.assertAlmostEqual(v["active_kcal"], 300.0, places=0)
        self.assertAlmostEqual(v["spo2"], 97.0)
        self.assertNotIn(date(2026, 9, 27), dd.values)   # qty 0 = 没测到
        self.assertEqual((v["hr_min"], v["hr_avg"], v["hr_max"]), (50, 70, 150))
        self.assertAlmostEqual(v["wrist_temp"], 35.5, places=1)
        self.assertEqual(v["walking_hr"], 95)
        self.assertAlmostEqual(v["weight_kg"], 68.04, places=1)

    def test_sleep_summary_uses_wake_day_and_stages(self):
        dd = self.parse([metric("sleep_analysis", "hr", [{
            "date": "2026-09-29 00:00:00 +0800", "totalSleep": 7.4, "asleep": 0.4, "core": 4.0, "deep": 1.0,
            "rem": 2.0, "awake": 0.3, "inBed": 0, "sleepStart": "2026-09-28 23:10:00 +0800",
            "sleepEnd": "2026-09-29 06:40:00 +0800", "source": "我的Apple Watch"}])])
        n = dd.sleep[date(2026, 9, 29)]
        self.assertAlmostEqual(n.total_h, 7.0)   # 有分期时只算 core+deep+rem，未分期部分算小睡
        self.assertAlmostEqual(n.nap_h, 0.4)
        self.assertEqual(n.start.hour, 23)

    def test_sleep_span_including_naps_is_ignored(self):
        dd = self.parse([metric("sleep_analysis", "hr", [{
            "date": "2026-09-29 00:00:00 +0800", "totalSleep": 7.0, "core": 5, "deep": 1, "rem": 1, "awake": 0.2,
            "sleepStart": "2026-09-28 17:31:00 +0800", "sleepEnd": "2026-09-29 13:55:00 +0800"}])])
        n = dd.sleep[date(2026, 9, 29)]
        self.assertIsNone(n.start)
        self.assertIsNone(n.end)

    def test_raw_sleep_segments_chinese(self):
        segs = []
        t = datetime(2026, 9, 28, 23, 0, tzinfo=TZ)
        for stage, mins in [("核心", 90), ("深度", 60), ("快速动眼期", 45), ("清醒", 10), ("核心", 120)]:
            segs.append({"startDate": t.strftime("%Y-%m-%d %H:%M:%S +0800"),
                         "endDate": (t + timedelta(minutes=mins)).strftime("%Y-%m-%d %H:%M:%S +0800"),
                         "qty": mins / 60, "value": stage, "source": "Watch"})
            t += timedelta(minutes=mins)
        dd = self.parse([metric("sleep_analysis", "hr", segs)])
        n = dd.sleep[date(2026, 9, 29)]
        self.assertAlmostEqual(n.total_h, (90 + 60 + 45 + 120) / 60, places=2)
        self.assertAlmostEqual(n.deep_h, 1.0)
        self.assertAlmostEqual(n.awake_h * 60, 10, places=0)

    def test_stage_names(self):
        self.assertEqual(stage_name("HKCategoryValueSleepAnalysisAsleepCore"), "core")
        self.assertEqual(stage_name("In Bed"), "inbed")
        self.assertEqual(stage_name("快速动眼期"), "rem")
        self.assertEqual(stage_name("睡眠时长"), "asleep")

    def test_workout_v2(self):
        dd = self.parse(workouts=[{
            "name": "户外 步行", "start": "2026-09-28 18:51:59 +0800", "end": "2026-09-28 19:34:32 +0800",
            "duration": 2553, "activeEnergyBurned": {"qty": 536.2, "units": "kJ"},
            "heartRate": {"avg": {"qty": 95.5, "units": "bpm"}, "max": {"qty": 125, "units": "bpm"}},
            "walkingAndRunningDistance": [{"qty": 1.0, "units": "km"}, {"qty": 1.2, "units": "km"}]}])
        w = dd.workouts[0]
        self.assertEqual(w.name, "户外 步行")
        self.assertAlmostEqual(w.duration_min, 42.55, places=1)
        self.assertAlmostEqual(w.kcal, 128.2, places=0)
        self.assertAlmostEqual(w.distance_km, 2.2)
        self.assertEqual(w.avg_hr, 95.5)

    def test_server_shape_and_non_hae(self):
        obj = {"data": {"healthMetrics": {"metrics": [metric("step_count", "count",
                                                             [{"date": "2026-09-28 00:00:00 +0800", "qty": 5000}])]},
                        "workouts": {"workouts": []}}}
        self.assertTrue(ingest_hae.looks_like_hae(obj))
        self.assertEqual(ingest_hae.parse(obj, TZ).values[date(2026, 9, 28)]["steps"], 5000)
        self.assertFalse(ingest_hae.looks_like_hae([{"summary": "日程"}]))
        self.assertFalse(ingest_hae.looks_like_hae({"forecast": {}}))

    def test_raw_steps_from_two_sources_not_double_counted(self):
        data = []
        for h in range(8, 20):
            data.append({"date": f"2026-09-28 {h:02d}:05:00 +0800", "qty": 500, "source": "iPhone"})
            data.append({"date": f"2026-09-28 {h:02d}:07:00 +0800", "qty": 520, "source": "Apple Watch"})
        dd = self.parse([metric("step_count", "count", data)])
        self.assertEqual(dd.values[date(2026, 9, 28)]["steps"], 520 * 12)

    def test_night_metrics_from_hourly_buckets(self):
        def hourly(name, units, val):
            return metric(name, units, [{"date": f"2026-09-{d} {h:02d}:00:00 +0800", "qty": val(d, h)}
                                        for d, hs in ((28, range(12, 24)), (29, range(0, 12))) for h in hs])
        sleep = [{"date": "2026-09-29 00:00:00 +0800", "totalSleep": 7, "core": 5, "deep": 1, "rem": 1,
                  "sleepStart": "2026-09-28 23:30:00 +0800", "sleepEnd": "2026-09-29 06:30:00 +0800"}]
        night = lambda d, h: d == 29 and h <= 6
        dd = self.parse([
            hourly("respiratory_rate", "count/min", lambda d, h: 15 if night(d, h) else 30),
            hourly("blood_oxygen_saturation", "%", lambda d, h: 96 if night(d, h) else 80),
            hourly("heart_rate_variability", "ms", lambda d, h: 60 if night(d, h) else 20),
            metric("sleep_analysis", "hr", sleep)])
        v = dd.values[date(2026, 9, 29)]
        self.assertEqual((v["resp_night"], v["spo2_night"], v["hrv_night"]), (15, 96, 60))   # 含 00:00 这一小时

    def test_daily_values_do_not_make_night_metrics(self):
        dd = self.parse([
            metric("heart_rate_variability", "ms", [{"date": "2026-09-29 00:00:00 +0800", "qty": 50}]),
            metric("sleep_analysis", "hr", [{"date": "2026-09-29 00:00:00 +0800", "totalSleep": 7, "core": 7,
                                             "sleepStart": "2026-09-28 23:30:00 +0800",
                                             "sleepEnd": "2026-09-29 06:30:00 +0800"}])])
        self.assertNotIn("hrv_night", dd.values[date(2026, 9, 29)])

    def test_implausible_values_dropped(self):
        dd = self.parse([metric("apple_sleeping_wrist_temperature", "degC",
                                [{"date": "2026-09-28 00:00:00 +0800", "qty": 12.0}])])
        self.assertNotIn(date(2026, 9, 28), dd.values)

    def test_hourly_buckets_with_single_source_labels_are_summed(self):
        rows = [("07", 800, "X的iPhone"), ("08", 3000, "X的Apple Watch|X的iPhone"),
                ("12", 2000, "X的Apple Watch|X的iPhone"), ("18", 4000, "X的Apple Watch")]
        dd = self.parse([metric("step_count", "count", [{"date": f"2026-09-28 {h}:00:00 +0800", "qty": q, "source": src}
                                                        for h, q, src in rows])])
        self.assertEqual(dd.values[date(2026, 9, 28)]["steps"], 9800)

    def test_utc_timestamps_use_local_day(self):
        dd = self.parse([metric("sleep_analysis", "hr", [{
            "date": "2026-09-28T00:00:00Z", "totalSleep": 7, "core": 5, "deep": 1, "rem": 1,
            "sleepStart": "2026-09-27T15:20:00Z", "sleepEnd": "2026-09-27T22:45:00Z"}])])
        n = dd.sleep[date(2026, 9, 28)]
        self.assertEqual(n.start.strftime("%H:%M"), "23:20")

    def test_night_hrv_from_samples(self):
        hrv = [{"date": "2026-09-28 15:00:00 +0800", "qty": 20},
               {"date": "2026-09-29 01:00:00 +0800", "qty": 50},
               {"date": "2026-09-29 04:00:00 +0800", "qty": 60}]
        sleep = [{"date": "2026-09-29 00:00:00 +0800", "totalSleep": 7, "core": 5, "deep": 1, "rem": 1,
                  "sleepStart": "2026-09-28 23:30:00 +0800", "sleepEnd": "2026-09-29 07:00:00 +0800"}]
        dd = self.parse([metric("heart_rate_variability", "ms", hrv), metric("sleep_analysis", "hr", sleep)])
        self.assertAlmostEqual(dd.values[date(2026, 9, 29)]["hrv_night"], 55)


class AppleXmlTests(unittest.TestCase):
    def test_export_zip(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE HealthData [
<!ELEMENT HealthData (ExportDate,Me,(Record|Workout)*)>
]>
<HealthData locale="zh_CN">
 <ExportDate value="2026-09-29 07:00:00 +0800"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="我的iPhone" unit="count" startDate="2026-09-28 09:00:00 +0800" endDate="2026-09-28 09:10:00 +0800" value="1000"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="我的Apple Watch" unit="count" startDate="2026-09-28 09:01:00 +0800" endDate="2026-09-28 09:11:00 +0800" value="1100"/>
 <Record type="HKQuantityTypeIdentifierOxygenSaturation" sourceName="我的Apple Watch" unit="%" startDate="2026-09-28 03:00:00 +0800" endDate="2026-09-28 03:00:00 +0800" value="0.96"/>
 <Record type="HKQuantityTypeIdentifierRestingHeartRate" sourceName="我的Apple Watch" unit="count/min" startDate="2026-09-28 00:01:00 +0800" endDate="2026-09-28 23:59:00 +0800" value="58"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="我的Apple Watch" startDate="2026-09-27 23:30:00 +0800" endDate="2026-09-28 03:30:00 +0800" value="HKCategoryValueSleepAnalysisAsleepCore"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="我的Apple Watch" startDate="2026-09-28 03:30:00 +0800" endDate="2026-09-28 04:30:00 +0800" value="HKCategoryValueSleepAnalysisAsleepDeep"/>
 <Record type="HKCategoryTypeIdentifierAppleStandHour" sourceName="我的Apple Watch" startDate="2026-09-28 10:00:00 +0800" endDate="2026-09-28 11:00:00 +0800" value="HKCategoryValueAppleStandHourStood"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30" durationUnit="min" sourceName="我的Apple Watch" startDate="2026-09-28 18:00:00 +0800" endDate="2026-09-28 18:30:00 +0800">
  <WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" startDate="2026-09-28 18:00:00 +0800" endDate="2026-09-28 18:30:00 +0800" sum="300" unit="kcal"/>
  <WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" startDate="2026-09-28 18:00:00 +0800" endDate="2026-09-28 18:30:00 +0800" average="150" minimum="100" maximum="170" unit="count/min"/>
 </Workout>
</HealthData>"""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "export.zip")
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("apple_health_export/export.xml", xml)
                z.writestr("apple_health_export/export_cda.xml", "<x/>")
            dd = ingest_applexml.parse(p, TZ, today=date(2026, 9, 29))
        v = dd.values[date(2026, 9, 28)]
        self.assertEqual(v["steps"], 1100)
        self.assertAlmostEqual(v["spo2"], 96)
        self.assertEqual(v["rhr"], 58)
        self.assertEqual(v["stand_hours"], 1)
        self.assertAlmostEqual(dd.sleep[date(2026, 9, 28)].total_h, 5.0)
        w = dd.workouts[0]
        self.assertEqual((w.name, w.kcal, w.avg_hr, w.duration_min), ("跑步", 300, 150, 30))


class ManualTests(unittest.TestCase):
    def test_parse_headers_and_values(self):
        text = ("健康手动记录（每天一行）\n"
                "日期,体重(kg),血压,心情(1-5),压力(1-5),饮酒(杯),症状,备注\n"
                "2026/9/27,68.5,120/80,4,2,0,,\n"
                "2026年9月28日,68.2kg,,3,4,2,嗓子疼,加班\n"
                ",,,,,,,\n")
        e = manual.parse(text)
        self.assertEqual(e[date(2026, 9, 27)]["bp_sys"], 120)
        self.assertEqual(e[date(2026, 9, 28)]["weight"], 68.2)
        self.assertEqual(e[date(2026, 9, 28)]["symptoms"], "嗓子疼")
        store = HealthStore()
        manual.merge_into(store, e)
        self.assertEqual(store.get(date(2026, 9, 27), "bp_dia"), 80)
        self.assertEqual(store.watch_days(), [])   # 手动补的值不算手表数据

    def test_note_row_mentioning_date_is_not_header(self):
        e = manual.parse("每天一行。日期写 2026-09-29 或 2026/9/29 都行,,,\n日期,体重(kg),收缩压,舒张压\n2026-09-28,68.6,150,96\n")
        self.assertEqual(e[date(2026, 9, 28)]["bp_sys"], 150)

    def test_month_day_dates_and_none_words(self):
        w = []
        e = manual.parse("日期,体重,症状\n9月27日,70.1,无\n9/28,70.0,咳嗽\n昨天,69,\n", ref=date(2026, 9, 29), warnings=w)
        self.assertEqual(e[date(2026, 9, 27)], {"weight": 70.1})
        self.assertEqual(e[date(2026, 9, 28)]["symptoms"], "咳嗽")
        self.assertTrue(w)   # “昨天”看不懂，要提示
        e = manual.parse("日期,体重\n12月31日,70\n", ref=date(2026, 1, 2))
        self.assertIn(date(2025, 12, 31), e)

    def test_english_headers(self):
        e = manual.parse("date,weight,systolic,diastolic,mood\n2026-09-28,70,130,85,2\n")
        self.assertEqual(e[date(2026, 9, 28)]["bp_dia"], 85)


class CalendarTests(unittest.TestCase):
    def test_analyze(self):
        evs = [
            {"summary": "A", "start": {"dateTime": "2026-09-29T09:00:00+08:00"}, "end": {"dateTime": "2026-09-29T10:00:00+08:00"}},
            {"summary": "B", "start": "2026-09-29T09:30:00+08:00", "end": "2026-09-29T11:00:00+08:00"},
            {"summary": "C", "start": "2026-09-29T14:00:00+08:00", "end": "2026-09-29T15:00:00+08:00"},
            {"summary": "取消", "status": "cancelled", "start": "2026-09-29T16:00:00+08:00", "end": "2026-09-29T17:00:00+08:00"},
            {"summary": "假期", "start": {"date": "2026-09-29"}, "end": {"date": "2026-10-02"}},
            {"summary": "明天", "start": "2026-09-30T09:00:00+08:00", "end": "2026-09-30T10:00:00+08:00"},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"events": evs}, f, ensure_ascii=False)
        try:
            c = calendar_ctx.load(f.name, date(2026, 9, 29), TZ)
        finally:
            os.unlink(f.name)
        self.assertEqual(c["count"], 3)
        self.assertEqual(c["busy_hours"], 3.0)   # 9:00–11:00 合并 + 14:00–15:00
        self.assertEqual(c["all_day"], ["假期"])
        self.assertEqual(c["first_start"], "09:00")
        self.assertEqual(c["exercise_slot"], "11:00–14:00")


class CalendarEdgeTests(unittest.TestCase):
    def test_multi_day_timed_event_is_all_day_context(self):
        evs = [{"summary": "休假（不在办公室）", "start": "2026-09-27T09:00:00+08:00", "end": "2026-10-08T09:00:00+08:00"},
               {"summary": "夜班", "start": "2026-09-28T22:00:00+08:00", "end": "2026-09-29T06:00:00+08:00"}]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(evs, f, ensure_ascii=False)
        try:
            c = calendar_ctx.load(f.name, date(2026, 9, 29), TZ)
        finally:
            os.unlink(f.name)
        self.assertEqual(c["all_day"], ["休假（不在办公室）"])
        self.assertEqual(c["count"], 1)
        self.assertEqual(c["first_start"], "00:00")      # 夜班只算今天的部分
        self.assertEqual(c["busy_hours"], 6.0)


class HistoryTests(unittest.TestCase):
    def test_roundtrip(self):
        from healthreport.sample import generate
        dd = ingest_hae.parse(generate(date(2026, 9, 29), 30), TZ)
        store = HealthStore()
        store.merge(dd)
        text = history.dump(store, date(2026, 9, 29))
        self.assertLess(len(text), 20000)
        back = history.parse(text, TZ)
        d = date(2026, 9, 20)
        self.assertAlmostEqual(back.values[d]["rhr"], store.get(d, "rhr"), places=0)
        self.assertAlmostEqual(back.sleep[d].total_h, store.sleep[d].total_h, places=2)
        self.assertEqual(back.sleep[d].start.strftime("%H:%M"), store.sleep[d].start.strftime("%H:%M"))
        self.assertIsNone(back.latest)
        self.assertEqual(history.pick_latest(["a/history-2026-09-27__x.csv", "history-2026-09-28__y.csv", "m.csv"]),
                         "history-2026-09-28__y.csv")


class CollectTests(unittest.TestCase):
    def test_scan_tool_results_and_transcript(self):
        payload = {"data": {"metrics": []}}
        b64 = base64.b64encode(json.dumps(payload).encode()).decode()
        with tempfile.TemporaryDirectory() as root:
            proj = os.path.join(root, "proj")
            os.makedirs(os.path.join(proj, "sess", "tool-results"))
            # 大结果：独立文件
            with open(os.path.join(proj, "sess", "tool-results", "mcp-Google_Drive-download_file_content-1.txt"), "w") as f:
                json.dump({"content": b64, "id": "AAA111", "mimeType": "application/json",
                           "title": "HealthAutoExport-2026-09-28.json"}, f)
            # 小结果：对话记录里的 tool_result（结果本身是 JSON 字符串）
            inner = json.dumps({"content": b64, "id": "BBB222", "mimeType": "application/json",
                                "title": "HealthAutoExport-2026-09-28.json"})
            call = {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "toolu_1", "name": "mcp__Google_Drive__download_file_content"}]}}
            line = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_1",
                                                             "content": inner}]}, "toolUseResult": inner}
            # 长得一样、但来自 Bash 的输出，不能当成下载结果
            fake = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_bash",
                                                             "content": inner.replace("BBB222", "FAKE00")}]}}
            old_line = dict(line, timestamp="2020-01-01T00:00:00.000Z",
                            toolUseResult=json.dumps({"content": b64, "id": "OLD999", "mimeType": "application/json",
                                                      "title": "HealthAutoExport-2020-01-01.json"}))
            old_line["message"] = {"content": []}
            old_line["message"] = {"content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": ""}]}
            with open(os.path.join(proj, "sess.jsonl"), "w") as f:
                for x in ({"type": "other"}, call, old_line, line, fake):
                    f.write(json.dumps(x) + "\n")
            csv_b64 = base64.b64encode("日期,体重\n2026-09-28,70\n".encode()).decode()
            csv_inner = json.dumps({"content": csv_b64, "id": "CCC333", "mimeType": "text/csv", "title": "健康手动记录"})
            with open(os.path.join(proj, "sess2.jsonl"), "w") as f:
                f.write(json.dumps({"message": {"content": [{"type": "tool_use", "id": "t2",
                                                             "name": "mcp__Google_Drive__download_file_content"}]}}) + "\n")
                f.write(json.dumps({"message": {"content": [{"type": "tool_result", "tool_use_id": "t2",
                                                             "content": [{"type": "text", "text": csv_inner}]}]}}) + "\n")
            # 子代理的记录不看
            os.makedirs(os.path.join(proj, "sess", "subagents"))
            with open(os.path.join(proj, "sess", "subagents", "agent-x.jsonl"), "w") as f:
                f.write(json.dumps(call) + "\n" + json.dumps(line).replace("BBB222", "SUB000") + "\n")
            found = collect.scan(roots=[root], title_filter=r"HealthAutoExport|手动记录")
            self.assertEqual(set(found), {"AAA111", "BBB222", "CCC333"})
            out = os.path.join(root, "out")
            written = sorted(os.path.basename(p) for p, _ in collect.write(found, out))
            self.assertEqual(written, ["HealthAutoExport-2026-09-28__AAA111.json",
                                       "HealthAutoExport-2026-09-28__BBB222.json", "健康手动记录__CCC333.csv"])


if __name__ == "__main__":
    unittest.main()
