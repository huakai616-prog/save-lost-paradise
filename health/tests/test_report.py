import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta

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

    def test_trimming(self):
        fs = [{"level": "yellow", "cat": "x", "title": f"t{i}", "detail": "", "advice": ""} for i in range(9)]
        fs.insert(0, {"level": "orange", "cat": "x", "title": "o", "detail": "", "advice": ""})
        main, extra, infos, goods = render.split_findings(fs)
        self.assertEqual(len(main), 6)
        self.assertEqual(len(extra), 4)


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
