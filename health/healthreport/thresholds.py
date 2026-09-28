"""所有提醒用到的阈值和出处。改这里就能调整提醒的灵敏度。

ENG 表示工程上的取舍，不是指南原文里的数字。出处全文见 health/README.md 的“参考依据”。
"""

# ---- 睡眠：AASM/SRS 2015 成人共识（每晚 ≥7 小时）；全国爱卫办《睡眠健康核心信息》2025 ----
SLEEP_TARGET_H = 7.0
SLEEP_SHORT_H = 6.0
SLEEP_VERY_SHORT_H = 5.0
SLEEP_MIN_TRACKED_H = 3.0          # 少于 3 小时多半是没戴表或没记录全
SLEEP_SHORT_NIGHTS_7 = 3           # 近 7 晚 ≥3 晚 <6 小时 → 睡眠欠债
SLEEP_AVG7_LOW_H = 6.5
SLEEP_AVG7_LONG_H = 9.5
LATE_ONSET_AFTER_MIN = 0           # 午夜后入睡（Nikbakhtian 2021：心血管风险约高 25%）
ONSET_SD_YELLOW_MIN = 60           # 近 7 晚入睡时间标准差（Huang 2020 JACC；60 为 ENG）
ONSET_SD_ORANGE_MIN = 90
DURATION_SD_ORANGE_MIN = 120
SLEEP_EFFICIENCY_LOW = 0.85        # Ohayon 2017（NSF）
WASO_LONG_MIN = 50                 # 夜间清醒 >50 分钟…
WASO_LONG_NIGHTS = 3               # …近 7 晚里有 ≥3 晚

# ---- 恢复：和个人基线比（Apple“生命体征”、NightSignal/Alavi 2022、Natarajan 2020、Miller 2020）----
RHR_DELTA = 5              # 静息心率比基线高 ≥5 次/分（或 z ≥ 2）算异常
RHR_Z = 2.0
RHR_PERSIST_DELTA = 4      # 连续 2 天比基线高 ≥4 次/分（NightSignal 红色预警）
HRV_Z_OUTLIER = -1.5       # 当天 ln(SDNN) 低于 60 天基线 1.5 SD：只算一项异常，不单独提醒
HRV_WEEK_BAND = 0.5        # 7 天均值低于 “均值 − 0.5 SD”：恢复不足（HRV4Training 正常范围）
HRV_WEEK_LOW = 1.0         # 连续 ≥3 天低于 “均值 − 1 SD”：明显
RESP_DELTA = 1.5
RESP_Z = 2.0
RESP_PERSIST_DELTA = 2.0   # 连续 2 晚高 ≥2 次/分
RESP_HIGH = 24             # 绝对值：睡眠呼吸频率 >24（NEWS2）
TEMP_DELTA = 0.5           # 手腕温度 ≥ +0.5°C（Apple 生命体征）
TEMP_DELTA_HIGH = 1.0
SPO2_DROP = 2.0            # 比基线低 ≥2 个百分点，或低于 93%
SPO2_OUTLIER_ABS = 93
SLEEP_DEV_H = 2.0          # 睡眠时长偏离基线 ≥2 小时
STEPS_DROP_RATIO = 0.5     # 步数不到基线一半
VITALS_OUTLIERS_FOR_ALERT = 2   # 同时 ≥2 项异常才发橙色提醒（同 Apple 生命体征）

# ---- 绝对值 ----
RHR_HIGH = 100             # AHA：成人静息心率 60–100
RHR_HIGH_DAYS_RED = 3      # 连续 3 天 >100 → 建议就医
RHR_LOW = 40
RHR_LOW_NEW = 50           # 平时 ≥60，突然 <50
SPO2_LOW = 95              # 手表血氧 92–94%：留意；误差约 ±2–3 个百分点
SPO2_LOW_RED = 92          # ≥2 晚 <92% → 建议就医（睡眠呼吸问题）
FEVER = 37.3
FEVER_HIGH = 39.0

# ---- 血压：《中国高血压防治指南（2024 年修订版）》----
BP_NORMAL_HIGH_SYS, BP_NORMAL_HIGH_DIA = 120, 80     # 正常高值 120–139/80–89
BP_HOME_HIGH_SYS, BP_HOME_HIGH_DIA = 135, 85         # 家庭血压诊断界值
BP_GRADE2_SYS, BP_GRADE2_DIA = 160, 100
BP_GRADE3_SYS, BP_GRADE3_DIA = 180, 110              # 3 级

# ---- 血糖（mmol/L）----
GLUCOSE_LOW = 3.9
GLUCOSE_HIGH = 11.1

# ---- 活动：WHO 2020；《中国居民膳食指南（2022）》；Paluch 2022 ----
STEPS_AVG7_LOW = 6000
EXERCISE_WEEK_MIN = 150
ACWR_HIGH = 1.5            # 只在过去 4 周平均每周锻炼 ≥90 分钟时计算
ACWR_MIN_CHRONIC_WEEK = 90
STAND_HOURS_LOW = 8
DAYLIGHT_AVG7_LOW_MIN = 30   # ENG
HEADPHONE_DB = 80            # WHO-ITU H.870：80 dB 每周 40 小时

# ---- 体重：WS/T 428-2013 ----
WEIGHT_WEEK_CHANGE_KG = 2.0
WEIGHT_LOSS_PCT = 5.0

# ---- 手动记录 ----
ALCOHOL_DRINKS = 2
STRESS_HIGH = 4
MOOD_LOW = 2
CAFFEINE_CUPS = 4

# ---- 天气 ----
HEAT_ORANGE = 35
HEAT_YELLOW = 32
COLD = -10
TEMP_SWING = 12
UV_HIGH = 8
RAIN_PROB = 60

# ---- 日程 ----
BUSY_HOURS = 6
LONG_BLOCK_HOURS = 3

# ---- 报告长度 ----
MAX_MAIN_ITEMS = 6         # 红、橙全部显示；黄色补足到 6 条，其余折叠
