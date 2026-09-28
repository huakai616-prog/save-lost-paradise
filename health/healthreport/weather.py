"""天气与空气质量。

数据来自 Open-Meteo（免费、无需密钥）。空气质量按中国《环境空气质量指数(AQI)技术规定》
HJ 633—2026（2026-03-01 起实施，替代 HJ 633-2012）从污染物浓度换算，而不是用美标 AQI，
这样和国内天气 App 看到的级别一致。注意 Open-Meteo 的空气质量是 CAMS 全球模式估算值
（约 45 公里网格），不是监测站实测，报告里会注明。

如果运行环境访问不了 Open-Meteo，可以写一个 weather.json（字段见 normalize_manual），
来自网页搜索的数据会标记为“仅供参考”，不会触发高温、污染等提醒。
"""

import json
import math
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# ---- HJ 633—2026 表 3：IAQI 分段 ----
IAQI_STEPS = [0, 50, 100, 150, 200, 300, 400, 500]
BREAKPOINTS = {
    # 污染物: (中文名, 浓度分段)，单位 μg/m³（CO 为 mg/m³）
    "pm2_5_24h": ("PM2.5", [0, 35, 60, 115, 150, 250, 350, 500]),   # 2026 版：100 对应 60（旧版 75）
    "pm10_24h": ("PM10", [0, 50, 120, 250, 350, 420, 500, 600]),    # 2026 版：100 对应 120（旧版 150）
    "so2_24h": ("SO₂", [0, 50, 150, 475, 800, 1600, 2100, 2620]),
    "no2_24h": ("NO₂", [0, 40, 80, 180, 280, 565, 750, 940]),
    "co_24h": ("CO", [0, 2, 4, 14, 24, 36, 48, 60]),
    "o3_8h": ("O₃", [0, 100, 160, 215, 265, 800]),                  # >800 时 IAQI 按 300 计
}

AQI_LEVELS = [
    # 上限, 级别, 类别, 建议采取的措施（HJ 633—2026 表 1）
    (50, "一级", "优", "各类人群可正常活动。"),
    (100, "二级", "良", "极少数异常敏感人群应减少户外活动。"),
    (150, "三级", "轻度污染", "青少年儿童、老年人及心血管、呼吸系统疾病患者应减少长时间、高强度的户外锻炼。"),
    (200, "四级", "中度污染", "青少年儿童、老年人及心血管、呼吸系统疾病患者避免长时间、高强度的户外锻炼，一般人群适量减少户外运动。"),
    (300, "五级", "重度污染", "青少年儿童、老年人和心血管、呼吸系统疾病患者应停留在室内，停止户外运动；一般人群减少户外运动。"),
    (10_000, "六级", "严重污染", "青少年儿童、老年人和病人应当留在室内，避免体力消耗；一般人群应避免户外活动。"),
]

WMO_CODES = {
    0: "晴", 1: "晴间少云", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨", 56: "小冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "小冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "米雪",
    80: "小阵雨", 81: "中阵雨", 82: "强阵雨", 85: "小阵雪", 86: "大阵雪",
    95: "雷阵雨", 96: "雷阵雨伴小冰雹", 97: "强雷阵雨", 99: "雷阵雨伴大冰雹",
}


def iaqi(key, conc):
    """单项污染物浓度 → 空气质量分指数 IAQI（按规定向上取整）。"""
    if conc is None:
        return None
    # 浓度先修约：CO 保留 1 位小数，其余取整
    conc = round(conc, 1) if key == "co_24h" else round(conc)
    steps = BREAKPOINTS[key][1]
    if key == "o3_8h" and conc > 800:
        return 300
    if conc <= 0:
        return 0
    for i in range(1, len(steps)):
        if conc <= steps[i]:
            lo_c, hi_c = steps[i - 1], steps[i]
            lo_i, hi_i = IAQI_STEPS[i - 1], IAQI_STEPS[i]
            return math.ceil((hi_i - lo_i) / (hi_c - lo_c) * (conc - lo_c) + lo_i - 1e-9)
    return 500


def aqi_level(aqi):
    for cap, grade, name, advice in AQI_LEVELS:
        if aqi <= cap:
            return grade, name, advice
    return AQI_LEVELS[-1][1:]


def china_aqi(conc):
    """conc: {pm2_5_24h, pm10_24h, so2_24h, no2_24h, co_24h(mg/m³), o3_8h}。

    返回 (AQI, 首要污染物列表)。AQI ≤ 50 时没有首要污染物。
    """
    sub = {k: iaqi(k, conc.get(k)) for k in BREAKPOINTS if conc.get(k) is not None}
    sub = {k: v for k, v in sub.items() if v is not None}
    if not sub:
        return None, []
    aqi = max(sub.values())
    primary = [BREAKPOINTS[k][0] for k, v in sub.items() if v == aqi] if aqi > 50 else []
    return aqi, primary


# ---- 从 Open-Meteo 获取 ----
def _get_json(url, params, timeout=15):
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{q}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_open_meteo(lat, lon, tz="Asia/Shanghai"):
    """返回 {"forecast": ..., "air": ...} 原始 JSON。任一接口失败时对应值为 None 并附错误信息。"""
    out = {"source": "open-meteo", "fetched_at": datetime.now().isoformat(timespec="seconds"),
           "lat": lat, "lon": lon, "tz": tz, "forecast": None, "air": None, "errors": []}
    try:
        out["forecast"] = _get_json(FORECAST_URL, {
            "latitude": lat, "longitude": lon, "timezone": tz, "forecast_days": 3, "past_days": 1,
            "daily": ",".join([
                "weather_code", "temperature_2m_max", "temperature_2m_min",
                "apparent_temperature_max", "apparent_temperature_min",
                "precipitation_probability_max", "precipitation_sum", "uv_index_max",
                "wind_speed_10m_max", "sunrise", "sunset"]),
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code",
        })
    except Exception as e:  # 网络被拦截、超时等
        out["errors"].append(f"forecast: {e}")
    try:
        out["air"] = _get_json(AIR_URL, {
            "latitude": lat, "longitude": lon, "timezone": tz, "forecast_days": 2, "past_days": 1,
            "hourly": "pm2_5,pm10,sulphur_dioxide,nitrogen_dioxide,carbon_monoxide,ozone",
        })
    except Exception as e:
        out["errors"].append(f"air: {e}")
    return out


def _daily_value(forecast, field, day_str):
    daily = (forecast or {}).get("daily") or {}
    times = daily.get("time") or []
    vals = daily.get(field) or []
    if day_str in times:
        i = times.index(day_str)
        if i < len(vals):
            return vals[i]
    return None


def _day_concentrations(air, day: date):
    """逐小时浓度 → 当天日均值，以及 O₃ 日最大 8 小时滑动平均（窗口结束于 08:00–24:00，至少 6 个有效小时）。"""
    hourly = (air or {}).get("hourly") or {}
    times = hourly.get("time") or []
    ds = day.isoformat()
    idx = [i for i, t in enumerate(times) if t.startswith(ds)]
    if not idx:
        return {}

    def col(field):
        return hourly.get(field) or []

    def day_mean(field):
        vals = col(field)
        xs = [vals[i] for i in idx if i < len(vals) and vals[i] is not None]
        return sum(xs) / len(xs) if len(xs) >= 12 else None

    conc = {"pm2_5_24h": day_mean("pm2_5"), "pm10_24h": day_mean("pm10"),
            "so2_24h": day_mean("sulphur_dioxide"), "no2_24h": day_mean("nitrogen_dioxide")}
    co = day_mean("carbon_monoxide")
    conc["co_24h"] = co / 1000 if co is not None else None   # Open-Meteo 的 CO 单位是 μg/m³
    o3 = col("ozone")
    best = None
    for i in idx:
        hour = int(times[i][11:13])
        if hour < 7:          # 该小时结束于 hour+1 点，窗口需结束于 08:00 之后
            continue
        win = [o3[j] for j in range(i - 7, i + 1) if 0 <= j < len(o3) and o3[j] is not None]
        if len(win) >= 6:
            m = sum(win) / len(win)
            best = m if best is None else max(best, m)
    conc["o3_8h"] = best
    return conc


def normalize_open_meteo(raw, day: date):
    """Open-Meteo 原始 JSON → 报告用的扁平字典。"""
    ds = day.isoformat()
    fc = raw.get("forecast")
    w = {"source": "Open-Meteo", "date": ds, "reliable": True}
    if fc:
        code = _daily_value(fc, "weather_code", ds)
        w.update({
            "desc": WMO_CODES.get(code, "") if code is not None else "",
            "temp_max": _daily_value(fc, "temperature_2m_max", ds),
            "temp_min": _daily_value(fc, "temperature_2m_min", ds),
            "feels_max": _daily_value(fc, "apparent_temperature_max", ds),
            "feels_min": _daily_value(fc, "apparent_temperature_min", ds),
            "precip_prob": _daily_value(fc, "precipitation_probability_max", ds),
            "precip_mm": _daily_value(fc, "precipitation_sum", ds),
            "uv_max": _daily_value(fc, "uv_index_max", ds),
            "wind_max_kmh": _daily_value(fc, "wind_speed_10m_max", ds),
            # 用于“连续 3 天高温”“寒潮降温”这类参考预警
            "tmax_next3": [_daily_value(fc, "temperature_2m_max", (day + timedelta(days=i)).isoformat())
                           for i in range(3)],
            "tmin_prev": _daily_value(fc, "temperature_2m_min", (day - timedelta(days=1)).isoformat()),
        })
        for f in ("sunrise", "sunset"):
            v = _daily_value(fc, f, ds)
            w[f] = v[11:16] if isinstance(v, str) and len(v) >= 16 else None
        cur = fc.get("current") or {}
        w["temp_now"] = cur.get("temperature_2m")
    air = raw.get("air")
    if air:
        conc = _day_concentrations(air, day)
        aqi, primary = china_aqi(conc)
        if aqi is not None:
            grade, name, advice = aqi_level(aqi)
            w.update({"aqi": aqi, "aqi_level": name, "aqi_grade": grade, "aqi_advice": advice,
                      "aqi_primary": "、".join(primary) or None, "aqi_note": "模式估算，非监测站实测",
                      "pm25": round(conc["pm2_5_24h"]) if conc.get("pm2_5_24h") is not None else None})
    return w


def normalize_manual(raw, day: date):
    """手写或网页搜索得到的天气：{"desc","temp_max","temp_min","uv_max","precip_prob","aqi",...,"source"}。

    来源里带“搜索”字样（或 reliable=false）时视为不可靠：照常显示，但不触发提醒。
    """
    keys = ("desc", "temp_max", "temp_min", "feels_max", "feels_min", "precip_prob", "precip_mm", "uv_max",
            "wind_max_kmh", "sunrise", "sunset", "temp_now", "aqi", "aqi_primary", "pm25")
    w = {k: raw.get(k) for k in keys}
    for k in keys:
        if k not in ("desc", "sunrise", "sunset", "aqi_primary") and isinstance(w[k], str):
            try:
                w[k] = float(w[k])
            except ValueError:
                w[k] = None
    w["source"] = raw.get("source") or "手动填写"
    w["date"] = raw.get("date") or day.isoformat()
    w["reliable"] = bool(raw.get("reliable", "搜索" not in w["source"]))
    if w["date"] != day.isoformat():
        return None   # 不是今天的天气，宁可不用
    if w.get("aqi") is not None:
        grade, name, advice = aqi_level(float(w["aqi"]))
        w.update({"aqi_level": raw.get("aqi_level") or name, "aqi_grade": grade, "aqi_advice": advice})
    return w


def load(path, day: date):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if "forecast" in raw or "air" in raw:
        w = normalize_open_meteo(raw, day)
    else:
        w = normalize_manual(raw, day)
    if w is None:
        return None
    has_any = w.get("temp_max") is not None or w.get("aqi") is not None or bool(w.get("desc"))
    return w if has_any else None
