"""指标目录：每个日度指标的中文名、单位、汇总方式、好坏方向和基线参数。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    key: str
    name: str          # 中文名
    unit: str          # 显示单位
    agg: str           # 同一天多条样本时怎么合并：sum / mean / median / min / max / last
    better: str        # 数值越高越好 "up"，越低越好 "down"，无所谓 "none"
    decimals: int = 0
    sd_floor: float = 0.0   # 基线标准差下限，防止基线过于平稳时小波动就报警
    min_days: int = 7       # 建立基线至少需要多少天数据


METRICS = {m.key: m for m in [
    # 活动
    Metric("steps", "步数", "步", "sum", "up", 0, 800),
    Metric("active_kcal", "活动消耗", "千卡", "sum", "up", 0, 40),
    Metric("basal_kcal", "静息消耗", "千卡", "sum", "none", 0, 30),
    Metric("exercise_min", "锻炼时间", "分钟", "sum", "up", 0, 5),
    Metric("stand_hours", "站立小时", "小时", "sum", "up", 0, 1),
    Metric("stand_min", "站立时间", "分钟", "sum", "up", 0, 10),
    Metric("distance_km", "步行跑步距离", "公里", "sum", "up", 1, 0.5),
    Metric("flights", "爬楼", "层", "sum", "up", 0, 2),
    Metric("daylight_min", "日光下时间", "分钟", "sum", "up", 0, 10),
    Metric("mindful_min", "正念", "分钟", "sum", "up", 0, 2),
    Metric("physical_effort", "体能消耗强度", "kcal/hr·kg", "mean", "none", 1, 0.2),
    # 心血管与恢复
    Metric("rhr", "静息心率", "次/分", "last", "down", 0, 1.5),   # 苹果会用更准的估计替换当天的值
    Metric("hr_min", "最低心率", "次/分", "min", "none", 0, 2),
    Metric("hr_avg", "平均心率", "次/分", "mean", "none", 0, 2),
    Metric("hr_max", "最高心率", "次/分", "max", "none", 0, 5),
    Metric("walking_hr", "步行平均心率", "次/分", "mean", "down", 0, 2),
    Metric("hrv", "心率变异性 HRV", "毫秒", "mean", "up", 0, 4),
    Metric("hrv_night", "夜间 HRV", "毫秒", "mean", "up", 0, 4),
    Metric("resp_rate", "睡眠呼吸频率", "次/分", "mean", "none", 1, 0.5),
    Metric("resp_night", "夜间呼吸频率", "次/分", "mean", "none", 1, 0.5),
    Metric("spo2", "血氧", "%", "median", "up", 1, 1.0),
    Metric("spo2_night", "夜间血氧", "%", "median", "up", 1, 1.0),
    Metric("spo2_min", "最低血氧", "%", "min", "up", 0, 1.0),
    Metric("wrist_temp", "睡眠手腕温度", "°C", "mean", "none", 2, 0.15, 5),
    Metric("body_temp", "体温", "°C", "max", "none", 1, 0.2),
    Metric("vo2max", "心肺耐力 VO₂max", "", "last", "up", 1, 0.5, 3),   # 每周只测几次
    Metric("cardio_recovery", "心率恢复", "次/分", "mean", "up", 0, 2),
    Metric("breathing_dist", "呼吸紊乱", "次/小时", "mean", "down", 1, 0.5),
    # 身体
    Metric("weight_kg", "体重", "kg", "last", "none", 1, 0.3),
    Metric("bmi", "BMI", "", "last", "none", 1, 0.1),
    Metric("body_fat", "体脂率", "%", "last", "none", 1, 0.3),
    Metric("bp_sys", "收缩压", "mmHg", "mean", "down", 0, 4),
    Metric("bp_dia", "舒张压", "mmHg", "mean", "down", 0, 3),
    Metric("glucose", "血糖", "mmol/L", "mean", "none", 1, 0.3),
    Metric("glucose_min", "最低血糖", "mmol/L", "min", "none", 1, 0.3),
    Metric("glucose_max", "最高血糖", "mmol/L", "max", "none", 1, 0.3),
    # 环境与习惯
    Metric("headphone_db", "耳机音量", "dB", "mean", "down", 0, 2),
    Metric("env_db", "环境噪音", "dB", "mean", "down", 0, 2),
    Metric("water_ml", "饮水", "毫升", "sum", "up", 0, 100),
    # 睡眠（按“醒来那天”记）
    Metric("sleep_h", "睡眠时长", "小时", "sum", "up", 1, 0.3),
    Metric("sleep_deep_h", "深睡", "小时", "sum", "none", 1, 0.1),
    Metric("sleep_rem_h", "快速眼动 REM", "小时", "sum", "none", 1, 0.1),
    Metric("sleep_core_h", "核心睡眠", "小时", "sum", "none", 1, 0.2),
    Metric("sleep_awake_h", "夜间清醒", "小时", "sum", "down", 1, 0.05),
    Metric("sleep_inbed_h", "卧床时长", "小时", "sum", "none", 1, 0.3),
]}


def fmt(key, value, with_unit=True):
    """按指标的小数位格式化数值。"""
    if value is None:
        return "—"
    m = METRICS.get(key)
    d = m.decimals if m else 1
    s = f"{value:,.{d}f}" if d else f"{round(value):,}"
    if with_unit and m and m.unit:
        sep = "" if m.unit in ("%", "°C") else " "
        s = f"{s}{sep}{m.unit}"
    return s
