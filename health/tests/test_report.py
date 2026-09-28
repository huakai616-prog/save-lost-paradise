import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from healthreport import ingest_hae, render, weather  # noqa: E402
from healthreport.analysis import Analyzer  # noqa: E402
from healthreport.sample import generate  # noqa: E402
from healthreport.store import HealthStore  # noqa: E402
from healthreport.timeutil import get_tz  # noqa: E402

TZ = get_tz("Asia/Shanghai")
TODAY = date(2026, 9, 29)
HEALTH_DIR = os.path.join(os.path.dirname(__file__), "..")


def store_for(scenario="normal", days=60):
    s = HealthStore()
    s.merge(ingest_hae.parse(generate(TODAY, days, scenario), TZ))
    return s


def run(store, **kw):
    return Analyzer(store, TODAY, TZ, **kw).run()


def titles(r, level=None, cat=None):
    return [f["title"] for f in r["findings"]
            if (level is None or f["level"] == level) and (cat is None or f["cat"] == cat)]


class ScenarioTests(unittest.TestCase):
    def test_normal_has_no_urgent_items(self):
        r = run(store_for("normal"))
        self.assertEqual(r["counts"]["red"], 0)
        self.assertEqual(r["counts"]["orange"], 0)
        self.assertGreaterEqual(r["readiness"]["score"], 70)
        self.assertEqual(r["data"]["state"], "ok")

    def test_illness_onset_triggers_combined_recovery_alert(self):
        r = run(store_for("illness"))
        rec = [f for f in r["findings"] if f["cat"] == "恢复"]
        self.assertEqual(len(rec), 1)             # 合并成一条，不重复
        self.assertEqual(rec[0]["level"], "orange")
        self.assertGreaterEqual(len(r["vitals"]["signals"]), 3)
        self.assertLessEqual(r["readiness"]["score"], 60)
        self.assertIn("恢复为主", r["plan"]["exercise"])
        for banned in ("确诊", "患有", "诊断为"):
            self.assertNotIn(banned, json.dumps(r["findings"], ensure_ascii=False))

    def test_short_sleep_debt(self):
        r = run(store_for("shortsleep"))
        self.assertTrue(any("睡眠债" in t for t in titles(r, "orange", "睡眠")))

    def test_no_data(self):
        r = run(HealthStore())
        self.assertEqual(r["data"]["state"], "none")
        self.assertIsNone(r["readiness"])
        self.assertIn("还没有收到手表数据", titles(r, "info"))
        html = render.build_html(r)
        self.assertIn("还没有收到手表数据", html)

    def test_stale_data(self):
        s = HealthStore()
        s.merge(ingest_hae.parse(generate(TODAY - timedelta(days=4), 30), TZ))
        r = run(s)
        self.assertEqual(r["data"]["state"], "stale")

    def test_new_user_gets_baseline_notice_and_no_relative_alerts(self):
        r = run(store_for("illness", days=4))
        self.assertTrue(any("正在建立你的个人基线" in t for t in titles(r, "info")))
        self.assertFalse(titles(r, cat="恢复"))


class AbsoluteRuleTests(unittest.TestCase):
    def test_rhr_over_100_three_days_is_red(self):
        s = store_for()
        for i in range(1, 4):
            s.put(TODAY - timedelta(days=i), "rhr", 104)
        r = run(s)
        self.assertTrue(any("连续 3 天" in t for t in titles(r, "red", "心率")))

    def test_rhr_over_100_once_is_orange(self):
        s = store_for()
        s.put(TODAY - timedelta(days=1), "rhr", 104)
        r = run(s)
        self.assertTrue(titles(r, "orange", "心率"))
        self.assertFalse(titles(r, "red", "心率"))

    def test_spo2(self):
        s = store_for()
        s.put(TODAY, "spo2", 93.2)
        r = run(s)
        self.assertTrue(titles(r, "yellow", "血氧"))
        s.put(TODAY - timedelta(days=1), "spo2", 90.5)
        s.put(TODAY, "spo2", 91.0)
        r = run(s)
        self.assertTrue(titles(r, "red", "血氧"))

    def test_blood_pressure_categories(self):
        s = store_for()
        s.put(TODAY, "bp_sys", 185)
        s.put(TODAY, "bp_dia", 100)
        self.assertTrue(titles(run(s), "red", "血压"))
        s = store_for()
        for i in range(3):
            s.put(TODAY - timedelta(days=i), "bp_sys", 138)
            s.put(TODAY - timedelta(days=i), "bp_dia", 86)
        self.assertTrue(any("135/85" in f["detail"] for f in run(s)["findings"] if f["cat"] == "血压"))
        s = store_for()
        for i in range(3):
            s.put(TODAY - timedelta(days=i), "bp_sys", 125)
            s.put(TODAY - timedelta(days=i), "bp_dia", 78)
        self.assertTrue(any("正常高值" in t for t in titles(run(s), "yellow", "血压")))

    def test_fever(self):
        s = store_for()
        s.put(TODAY, "body_temp", 38.0)
        self.assertTrue(titles(run(s), "orange", "体温"))


class ReviewRegressionTests(unittest.TestCase):
    """评审发现的问题，逐条固定下来。"""

    def test_red_finding_blocks_hard_training(self):
        s = store_for()
        s.put(TODAY, "bp_sys", 186)
        s.put(TODAY, "bp_dia", 114)
        r = run(s)
        self.assertTrue(titles(r, "red", "血压"))
        self.assertEqual(r["plan"]["level"], "none")
        self.assertLessEqual(r["readiness"]["score"], 40)

    def test_urgent_symptom_words(self):
        s = store_for()
        s.manual[TODAY - timedelta(days=1)] = {"symptoms": "早上有点胸痛"}
        r = run(s)
        self.assertTrue(titles(r, "red", "记录"))
        self.assertEqual(r["plan"]["level"], "none")
        s.manual[TODAY - timedelta(days=1)] = {"symptoms": "发烧 37.8"}
        r = run(s)
        self.assertTrue(titles(r, "orange", "记录"))
        self.assertEqual(r["plan"]["level"], "recovery")

    def test_short_sleep_never_gets_hard_plan(self):
        s = store_for()
        n = s.sleep[TODAY]
        n.total_h = 5.6
        s.put(TODAY, "sleep_h", 5.6)
        self.assertNotEqual(run(s)["plan"]["level"], "hard")

    def test_lazy_weekend_is_not_illness(self):
        s = store_for()
        s.sleep[TODAY].total_h = 9.5
        s.put(TODAY, "sleep_h", 9.5)
        s.put(TODAY - timedelta(days=1), "steps", 1500)
        r = run(s)
        self.assertFalse(titles(r, "orange", "恢复"))

    def test_under_3h_night_is_not_an_outlier(self):
        s = store_for()
        s.sleep[TODAY].total_h = 1.4
        s.values[TODAY].pop("sleep_h", None)
        s.put(TODAY - timedelta(days=1), "steps", 1500)
        r = run(s)
        self.assertFalse(titles(r, "orange", "恢复"))
        self.assertTrue(any("只记录到" in t for t in titles(r, "info")))

    def test_multi_outlier_plus_absolute_flag_is_red(self):
        s = store_for("illness")
        s.put(TODAY - timedelta(days=1), "rhr", 106)
        r = run(s)
        self.assertTrue(titles(r, "red", "恢复"))

    def test_yellow_titles_have_the_right_direction(self):
        s = store_for()
        base = [s.get(TODAY - timedelta(days=i), "rhr") for i in range(3, 30)]
        s.put(TODAY - timedelta(days=1), "rhr", sorted(base)[len(base) // 2] + 6)
        r = run(s)
        rec = [f for f in r["findings"] if f["cat"] == "恢复"]
        self.assertTrue(rec)
        self.assertNotIn("略高于平常", rec[0]["title"])
        self.assertIn("静息心率", rec[0]["title"])

    def test_wrist_temp_stamped_before_midnight_onset(self):
        s = store_for()
        n = s.sleep[TODAY]
        n.start = n.start.replace(hour=0, minute=40) + timedelta(days=1) if n.start.hour >= 12 else n.start.replace(hour=0, minute=40)
        # 时段开始于前一天 23:50，样本记在前一天（入睡当天没有样本）
        s.values[TODAY].pop("wrist_temp", None)
        s.put(TODAY - timedelta(days=1), "wrist_temp", 36.6)
        r = run(s)
        self.assertIsNotNone(r["vitals"]["wrist_temp"])
        self.assertEqual(r["vitals"]["wrist_temp"]["day"], (TODAY - timedelta(days=1)).isoformat())

    def test_wrist_temp_prefers_onset_day_when_present(self):
        s = store_for()
        n = s.sleep[TODAY]
        n.start = n.start.replace(hour=0, minute=56) + timedelta(days=1) if n.start.hour >= 12 else n.start.replace(hour=0, minute=56)
        s.put(TODAY, "wrist_temp", 35.3)          # 入睡当天的样本就是昨晚的
        s.put(TODAY - timedelta(days=1), "wrist_temp", 35.1)
        self.assertEqual(run(s)["vitals"]["wrist_temp"]["day"], TODAY.isoformat())

    def test_negated_symptoms_do_not_alert(self):
        for text in ("无", "无胸闷胸痛", "没有发烧", "不发热"):
            s = store_for()
            s.manual[TODAY - timedelta(days=1)] = {"symptoms": text}
            r = run(s)
            self.assertFalse(titles(r, "red", "记录"), text)
            self.assertFalse(titles(r, "orange", "记录"), text)
        for text in ("咳嗽不止，胸痛", "非常胸闷", "不明原因胸痛", "没有胸痛但是胸闷", "头晕无力，呼吸困难"):
            s = store_for()
            s.manual[TODAY - timedelta(days=1)] = {"symptoms": text}
            self.assertTrue(titles(run(s), "red", "记录"), text)
        for text in ("无明显不适", "没什么不舒服", "否认胸痛"):
            s = store_for()
            s.manual[TODAY - timedelta(days=1)] = {"symptoms": text}
            self.assertFalse([f for f in run(s)["findings"] if f["cat"] == "记录" and "不适" in f["title"]], text)

    def test_logged_period_relaxes_wrist_temp(self):
        s = store_for()
        base = s.get(TODAY - timedelta(days=1), "wrist_temp") or 35.2
        n = s.sleep[TODAY]
        s.put(n.start.date(), "wrist_temp", 35.2 + 0.6)
        s.manual[TODAY - timedelta(days=3)] = {"period": "是"}
        r = run(s)
        self.assertNotIn("wrist_temp", " ".join(r["vitals"]["signals"]))

    def test_low_rhr_even_for_athletes_when_far_below_usual(self):
        s = store_for()
        for i in range(1, 60):
            s.put(TODAY - timedelta(days=i), "rhr", 44)
        s.put(TODAY - timedelta(days=1), "rhr", 33)
        self.assertTrue(titles(run(s), "orange", "心率"))

    def test_old_bp_reading_not_reported_as_current(self):
        s = store_for()
        s.put(TODAY - timedelta(days=6), "bp_sys", 182)
        s.put(TODAY - timedelta(days=6), "bp_dia", 112)
        s.put(TODAY, "bp_sys", 118)
        r = run(s)
        self.assertFalse(titles(r, "red", "血压"))

    def test_glucose_low_reading_not_hidden_by_mean(self):
        from healthreport.aggregate import Aggregator
        agg = Aggregator()
        for v in (5.4, 3.1, 6.2):
            agg.add("glucose", TODAY - timedelta(days=1), v)
            agg.add("glucose_min", TODAY - timedelta(days=1), v)
            agg.add("glucose_max", TODAY - timedelta(days=1), v)
        s = store_for()
        s.merge(agg.finish())
        self.assertTrue(any("偏低" in t for t in titles(run(s), "orange", "血糖")))

    def test_spo2_night_uses_median(self):
        from healthreport.aggregate import Aggregator
        agg = Aggregator()
        for v in (94, 90, 90, 88, 94, 93, 93, 93, 90, 93):
            agg.add("spo2", TODAY, v)
        self.assertEqual(agg.finish().values[TODAY]["spo2"], 93)

    def test_calendar_rule_ignores_previous_night(self):
        s = store_for()
        del s.sleep[TODAY]
        s.values[TODAY].pop("sleep_h", None)
        s.sleep[TODAY - timedelta(days=1)].total_h = 5.4
        cal = {"count": 1, "busy_hours": 1, "longest_block_hours": 1, "first_start": "08:00",
               "first_start_dt": datetime(2026, 9, 29, 8, 0, tzinfo=TZ), "last_end": "09:00",
               "last_end_dt": datetime(2026, 9, 29, 9, 0, tzinfo=TZ), "events": [], "all_day": [],
               "exercise_slot": None}
        r = run(s, calendar=cal)
        self.assertFalse(any("昨晚睡得不多" in t for t in titles(r)))

    def test_plan_moves_indoors_on_light_pollution(self):
        r = run(store_for(), weather={"reliable": True, "aqi": 118, "aqi_level": "轻度污染", "aqi_advice": ""})
        self.assertIn("室内", r["plan"]["exercise"])


class WeatherTests(unittest.TestCase):
    def test_iaqi_hj633_2026(self):
        self.assertEqual(weather.iaqi("pm2_5_24h", 45), 70)      # 标准里的算例
        self.assertEqual(weather.iaqi("pm2_5_24h", 60), 100)
        self.assertEqual(weather.iaqi("pm2_5_24h", 61), 101)     # 向上取整
        self.assertEqual(weather.iaqi("pm10_24h", 120), 100)
        self.assertEqual(weather.iaqi("o3_8h", 900), 300)
        aqi, primary = weather.china_aqi({"pm2_5_24h": 60, "pm10_24h": 120, "o3_8h": 50})
        self.assertEqual((aqi, sorted(primary)), (100, ["PM10", "PM2.5"]))
        self.assertEqual(weather.china_aqi({"pm2_5_24h": 10})[1], [])

    def test_normalize_open_meteo(self):
        hours = [f"2026-09-{d}T{h:02d}:00" for d in (28, 29, 30) for h in range(24)]
        n = len(hours)
        raw = {
            "forecast": {"daily": {"time": ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"],
                                   "weather_code": [0, 61, 2, 3], "temperature_2m_max": [30, 36, 36, 37],
                                   "temperature_2m_min": [20, 22, 23, 24], "apparent_temperature_max": [31, 38, 37, 38],
                                   "uv_index_max": [5, 9, 7, 6], "precipitation_probability_max": [0, 70, 10, 0],
                                   "sunrise": ["x", "2026-09-29T06:05", "x", "x"],
                                   "sunset": ["x", "2026-09-29T18:02", "x", "x"]},
                         "current": {"temperature_2m": 25}},
            "air": {"hourly": {"time": hours, "pm2_5": [80.0] * n, "pm10": [100.0] * n,
                               "carbon_monoxide": [800.0] * n, "ozone": [60.0] * n,
                               "nitrogen_dioxide": [30.0] * n, "sulphur_dioxide": [5.0] * n}},
        }
        w = weather.normalize_open_meteo(raw, TODAY)
        self.assertEqual(w["desc"], "小雨")
        self.assertEqual(w["temp_max"], 36)
        self.assertEqual(w["sunrise"], "06:05")
        self.assertEqual(w["tmax_next3"], [36, 36, 37])
        self.assertEqual(w["aqi"], weather.iaqi("pm2_5_24h", 80))
        self.assertEqual(w["aqi_level"], "轻度污染")
        r = run(store_for(), weather=w)
        wf = [f for f in r["findings"] if f["cat"] == "天气"][0]
        self.assertEqual(wf["level"], "orange")
        self.assertIn("高温", wf["title"])
        self.assertIn("室内", r["plan"]["exercise"])

    def test_websearch_weather_never_alerts(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"source": "网络搜索", "date": TODAY.isoformat(), "temp_max": 39, "aqi": 250}, f,
                      ensure_ascii=False)
        try:
            w = weather.load(f.name, TODAY)
            self.assertFalse(w["reliable"])
            self.assertFalse(titles(run(store_for(), weather=w), cat="天气"))
            self.assertIsNone(weather.load(f.name, TODAY + timedelta(days=1)))   # 日期不对就不用
        finally:
            os.unlink(f.name)


class RenderTests(unittest.TestCase):
    def test_html_is_email_safe(self):
        r = run(store_for("illness"))
        html = render.build_html(r, "今天多休息。", {"sheet": "https://example.com/s", "folder": None})
        self.assertNotIn("<script", html)
        self.assertNotIn("<svg", html)
        self.assertLess(len(html.encode()), 40_000)
        for s in ("今天需要注意", "昨晚睡眠", "恢复指标", "昨日活动", "今天多休息。", "打开手动记录表", "120"):
            self.assertIn(s, html)
        md = render.build_markdown(r)
        self.assertIn("## 今天需要注意", md)
        subj = render.subject(r)
        self.assertTrue(subj.startswith("身体日报 9/29"))
        json.loads(render.build_brief(r))

    def test_body_style_attribute_is_intact(self):
        from html.parser import HTMLParser
        attrs = {}

        class P(HTMLParser):
            def handle_starttag(self, tag, a):
                if tag in ("body", "table") and tag not in attrs:
                    attrs[tag] = dict(a)
        P().feed(render.build_html(run(store_for())))
        self.assertEqual(set(attrs["body"]), {"style"})
        self.assertIn("PingFang SC", attrs["body"]["style"])

    def test_partial_weather_and_all_day_calendar(self):
        r = run(store_for(), weather={"source": "网络搜索", "reliable": False, "desc": "晴", "temp_max": 24,
                                      "temp_min": None, "aqi": 85, "aqi_level": "良"},
                calendar={"count": 0, "busy_hours": 0, "longest_block_hours": 0, "first_start": None,
                          "last_end": None, "events": [], "all_day": ["国庆节"], "exercise_slot": None})
        md = render.build_markdown(r)
        self.assertIn("最高 24°C", md)
        self.assertIn("全天：国庆节", md)
        html = render.build_html(r)
        self.assertNotIn("0 项安排", html)
        self.assertEqual(html.count("网络搜索"), 1)

    def test_subject_wording(self):
        subj = render.subject(run(store_for("illness")))
        self.assertIn("1 项需留意", subj)
        self.assertIn("条小提醒", subj)
        s = HealthStore()
        s.merge(ingest_hae.parse(generate(TODAY - timedelta(days=4), 30), TZ))
        self.assertIn("手表数据未更新", render.subject(run(s)))

    def test_brief_carries_advice_for_urgent_items(self):
        s = store_for()
        s.put(TODAY, "bp_sys", 185)
        s.put(TODAY, "bp_dia", 100)
        brief = json.loads(render.build_brief(run(s)))
        red = [f for f in brief["findings"] if f["level"] == "red"][0]
        self.assertIn("复测", red["advice"])

    def test_trimming(self):
        fs = [{"level": "yellow", "cat": "x", "title": f"t{i}", "detail": "", "advice": ""} for i in range(9)]
        fs.insert(0, {"level": "orange", "cat": "x", "title": "o", "detail": "", "advice": ""})
        main, extra, infos, goods = render.split_findings(fs)
        self.assertEqual(len(main), 6)
        self.assertEqual(len(extra), 4)
        fs.append({"level": "info", "cat": "数据", "title": "i", "detail": "", "advice": ""})
        main, extra, infos, goods = render.split_findings(fs)
        self.assertEqual(len(main) + len(infos), 6)


class MergeTests(unittest.TestCase):
    def test_cross_midnight_rows_do_not_overwrite_full_day(self):
        from healthreport.cli import primary_days
        self.assertEqual(primary_days("x/HealthAutoExport-2026-09-26__abc.json"), {date(2026, 9, 26)})
        self.assertEqual(len(primary_days("HealthAutoExport-2026-09-01-2026-09-10.json")), 10)
        day26 = ingest_hae.parse({"data": {"metrics": [{"name": "headphone_audio_exposure", "units": "dBASPL", "data": [
            {"date": "2026-09-26 00:00:00 +0800", "qty": 84}]}]}}, TZ)
        day26.primary_days = {date(2026, 9, 26)}
        day27 = ingest_hae.parse({"data": {"metrics": [{"name": "headphone_audio_exposure", "units": "dBASPL", "data": [
            {"date": "2026-09-26 23:50:00 +0800", "qty": 60}, {"date": "2026-09-27 10:00:00 +0800", "qty": 70}]}]}}, TZ)
        day27.primary_days = {date(2026, 9, 27)}
        s = HealthStore()
        s.merge(day26)
        s.merge(day27)
        self.assertEqual(s.get(date(2026, 9, 26), "headphone_db"), 84)
        self.assertEqual(s.get(date(2026, 9, 27), "headphone_db"), 70)

    def test_zip_of_json_exports(self):
        import zipfile
        from healthreport.cli import load_store
        with tempfile.TemporaryDirectory() as d:
            with zipfile.ZipFile(os.path.join(d, "HealthAutoExport_20260928101010.zip"), "w") as z:
                z.writestr("HealthAutoExport_20260928101010/HealthAutoExport-2026-08-01-2026-09-29.json",
                           json.dumps(generate(TODAY, 60)))
            store, _ = load_store([d], TZ, TODAY, log=lambda *a: None)
        self.assertGreaterEqual(len(store.watch_days()), 59)


class CliTests(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, PYTHONPATH=HEALTH_DIR)
            subprocess.run([sys.executable, "-m", "healthreport", "sample", "--out", d, "--end", "2026-09-29",
                            "--scenario", "illness"], check=True, env=env, capture_output=True)
            out = os.path.join(d, "out")
            # 数据目录里混着日程/天气 JSON 和手动记录 CSV，也要能正确识别
            p = subprocess.run([sys.executable, "-m", "healthreport", "build", "--data", d,
                                "--calendar", os.path.join(d, "calendar.json"),
                                "--weather", os.path.join(d, "weather.json"),
                                "--date", "2026-09-29", "--out", out], env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            for f in ("report.html", "report.md", "brief.json", "subject.txt", "summary.json",
                      "history-2026-09-29.csv"):
                self.assertTrue(os.path.exists(os.path.join(out, f)), f)
            self.assertIn("手动记录", p.stdout)
            # 第二天：只有历史存档 + 一个新的日文件，基线照样可用
            day2 = os.path.join(d, "day2")
            os.makedirs(day2)
            os.rename(os.path.join(out, "history-2026-09-29.csv"), os.path.join(day2, "history-2026-09-29.csv"))
            with open(os.path.join(day2, "HealthAutoExport-2026-09-30.json"), "w") as f:
                json.dump(generate(date(2026, 9, 30), 2), f)
            p = subprocess.run([sys.executable, "-m", "healthreport", "build", "--data", day2, "--date",
                                "2026-09-30", "--out", os.path.join(d, "out2")], env=env, capture_output=True,
                               text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            with open(os.path.join(d, "out2", "summary.json"), encoding="utf-8") as f:
                r = json.load(f)
            self.assertGreaterEqual(r["data"]["days_available"], 55)
            self.assertIsNotNone(r["vitals"]["rhr"]["baseline"])


if __name__ == "__main__":
    unittest.main()
