# 每日身体报告

每天早上 7:45（北京时间），根据 Apple Watch / iPhone 的健康数据，结合当天的日程、天气空气质量和你的手动记录，
生成一份中文的「身体日报」：今天状态怎么样、需要注意什么、适合什么强度的运动。报告会发到你的 Gmail，
同时存一份到 Google Drive。

> 本工具只做健康管理参考，不能替代医生的诊断。身体不适请及时就医，紧急情况请拨打 120。

## 工作原理

```
Apple Watch ──同步──▶ iPhone「健康」
                         │  Health Auto Export（每小时自动导出，需解锁手机）
                         ▼
               Google Drive / Health Auto Export / metrics、workouts
                         │
每天 07:45  Claude 定时任务 ──读取──▶ 手表数据 + 历史存档 + 手动记录表 + Google 日历 + 天气
                         │  python3 -m healthreport build（本目录的代码，纯 Python 标准库）
                         ▼
               Gmail 邮件  +  Google Drive「健康日报/每日报告」
```

报告里的判断都是和**你自己过去几周的平常水平**比较（个人基线），而不是只和人群标准比；
单个指标偶尔波动很常见，多项一起偏离、或者连续几天偏离才会提醒你认真对待。

## 一次性设置（iPhone，约 10 分钟）

### 1. 安装并授权 Health Auto Export

1. App Store 搜索 **Health Auto Export - JSON+CSV** 并安装。
2. 自动导出到 Google Drive 需要它的 **Premium**（订阅或买断，有 7 天免费试用）。
3. 第一次打开时允许读取健康数据（全部打开即可）。

### 2. 建两个自动导出

在 App 底部 **Automations（自动化）→ 右上角 +**：

**自动化一：健康指标**

| 设置 | 选择 |
|---|---|
| 类型 | Google Drive（登录 huakai616@gmail.com，允许它创建文件） |
| 文件夹名 | `metrics`（会出现在 Drive 的 `Health Auto Export/metrics/`） |
| Data Type | Health Metrics |
| Export Format | JSON，Export Version 选 **Version 2** |
| Summarize Data | **打开** |
| Time Grouping | **Hours（小时）**。这样才能只取睡眠时段算夜间 HRV、呼吸频率和血氧；如果 App 在后台经常失败，可以退而选 Days（天），报告照样能用，只是夜间指标会退化成全天均值 |
| Date Range | **Default（默认）**，不要选 Since Last Sync（会漏掉静息心率和昨晚的睡眠） |
| 文件周期 | Day（每天一个文件） |
| Sync Cadence | 每 1 小时 |
| 指标 | 只勾下面这些（全选会让 App 在后台崩溃）：步数、活动能量、静息能量、锻炼分钟数、站立小时、步行+跑步距离、已爬楼层、日光下时间、心率、静息心率、步行平均心率、心率变异性、呼吸频率、血氧饱和度、睡眠时手腕温度、睡眠分析、最大摄氧量、体重、体脂率、身体质量指数、血压、体温、血糖、耳机音频暴露、心率恢复、呼吸紊乱 |

**自动化二：体能训练**

| 设置 | 选择 |
|---|---|
| 类型 | Google Drive，文件夹名 `workouts` |
| Data Type | Workouts，JSON，Version 2 |
| Summarize Data | **关闭**（打开会报错） |
| 路线 Route | 关闭（文件会小很多） |
| Date Range | Default |

### 3. 手机和手表设置

- 设置 → 通用 → 后台 App 刷新：打开，并允许 Health Auto Export。
- 尽量别开低电量模式；设置 → 通用 → 日期与时间 → **24 小时制** 打开。
- 「健康」App → 睡眠：设置睡眠计划并打开“用 Apple Watch 追踪睡眠”（睡眠分期、手腕温度、夜间呼吸都靠它）。
- **每天起床后解锁一下手机、打开一次 Health Auto Export**。iOS 锁屏时不允许读取健康数据，
  手表也要在你醒来后一段时间才把昨晚的睡眠交给手机。7:45 生成报告时如果昨晚的数据还没同步，报告会注明。

### 4. 一次性补历史（强烈建议）

个人基线需要至少 7 天、最好 14 天以上的数据。与其等两周，不如马上手动导出一次：

Health Auto Export → **Export（手动导出）** → Health Metrics → 日期范围选**最近 60 天** → JSON、Summarize 打开、
Time Grouping 选 Hours（文件太大导不出来就选 Days）→ 导出后用“存储到文件 / Google Drive”存到 Drive 里任意位置（文件名保持 `HealthAutoExport` 开头）。
第二天的报告就会用上这些历史数据。

## 手动记录表

Google Drive「健康日报」文件夹里有一张表格 **健康手动记录**，每天一行，想填什么填什么，空着也没关系：

| 日期 | 体重(kg) | 收缩压 | 舒张压 | 心情(1-5) | 压力(1-5) | 精力(1-5) | 饮酒(杯) | 咖啡因(杯) | 症状 | 用药 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|---|

- 血压也可以写在一列里，如 `120/80`；日期写 `2026-09-29` 或 `2026/9/29` 都行。
- 记录了饮酒、症状、压力，报告在解释心率和 HRV 的变化时会一起考虑。
- 列的顺序可以改，也可以加一列“经期”（是/否），手腕温度升高时会一并参考。

## 天气与空气质量

天气来自 [Open-Meteo](https://open-meteo.com/)（免费、无需密钥），空气质量按国标
**HJ 633—2026**（2026 年 3 月 1 日起实施）由污染物浓度换算成中国 AQI。

定时任务运行的云端环境默认拦截了这两个域名，需要在环境设置里放行一次：
Claude Code 会话标题栏的云端环境菜单 → Edit → Network access → 允许的域名里加上
`api.open-meteo.com` 和 `air-quality-api.open-meteo.com`（或者选更宽的访问级别）。
没放行时，任务会用网页搜索兜底，这种天气只显示、不触发提醒。

## 报告里有什么

- **今日状态分（0–100）**：睡眠 40%、HRV 25%、静息心率 25%、夜间呼吸/手腕温度/血氧 10%，启发式估算，仅供参考。
- **今天需要注意**：按严重程度排序，最多展开 6 条，其余折叠。
  - 🔴 **建议就医**：比如血压 ≥180/110、静息心率连续 3 天 >100、近 7 天有 2 晚血氧 <92%、睡眠呼吸频率连续 2 晚 >24。
  - 🟠 **需要留意**：比如 ≥2 项夜间指标同时偏离你的基线（静息心率、HRV、呼吸频率、手腕温度、血氧、睡眠时长）、
    静息心率连续 2 天比平时高 ≥4、近 7 晚睡眠欠债、空气中度污染或高温。
  - 🟡 **小提醒**：睡眠不足 7 小时、午夜后入睡、作息不规律、一周锻炼不到 150 分钟、日均步数不到 6000 等。
  - 🟢 **做得好** / ℹ️ **提示**（比如数据没同步）。
- **今日运动建议**：按状态分、天气和日程里的空档给出强度和时段。
- 昨晚睡眠（分期、入睡和醒来时间、近 14 晚走势）、恢复指标表、昨日活动、身体数据、今天的日程、天气与空气、你的记录。
- 每份报告开头还有一段 Claude 根据当天数据写的简短点评（只用报告里的事实，不做诊断）。

所有阈值和出处都在 [`healthreport/thresholds.py`](healthreport/thresholds.py)，想让提醒更灵敏或更安静，改那里就行。

## 隐私

- 健康数据只存在你自己的 Google Drive 和 Gmail 里。这个仓库是公开的，**只放代码**，
  `health/.gitignore` 会挡住任何数据文件；定时任务也被要求不修改仓库。
- 每天的定时任务在一个临时的云端会话里读取数据、生成报告，会话结束后容器会被回收。
- Drive「健康日报/数据存档」里每天会多一个约 10 KB 的 `history-日期.csv`（最近 60 天的每日汇总），
  用来算基线，旧的可以随时删掉，只保留最新的即可。

## 在本地运行

```bash
cd health
python3 -m healthreport sample --out demo --scenario illness      # 生成示例数据（normal / illness / shortsleep）
python3 -m healthreport build --data demo --calendar demo/calendar.json --weather demo/weather.json --out out
open out/report.html
python3 -m unittest discover -s tests                              # 运行测试
```

`--data` 可以是 Health Auto Export 的 JSON、苹果「健康」App 的原生导出 `export.zip`，
也可以是包含它们、历史存档 `history-*.csv` 和手动记录 CSV 的目录。每天自动任务的完整步骤见 [ROUTINE.md](ROUTINE.md)。

## 参考依据

- 睡眠：AASM/SRS 成人睡眠时长共识（2015）；全国爱卫办《睡眠健康核心信息及释义》（2025）；
  Huang 等 2020 *JACC*（作息规律性与心血管风险）；Nikbakhtian 等 2021 *Eur Heart J Digit Health*（入睡时间）；
  Ohayon 等 2017（睡眠效率）。
- 可穿戴设备早期预警：Mishra 等 2020 *Nat Biomed Eng*；Quer 等 2021 *Nat Med*（DETECT）；
  Alavi 等 2022 *Nat Med*（NightSignal）；Natarajan 等 2020 *npj Digit Med*；Miller 等 2020 *PLOS One*；
  Mason 等 2022 *Sci Rep*（体温）；Apple「生命体征」App 说明。
- HRV：Plews & Buchheit 2013；HRV4Training（Altini）的 7 天均值与正常范围方法。
- 血压：《中国高血压防治指南（2024 年修订版）》；AHA/ACC 2025 高血压指南。
- 身体活动：WHO 2020 身体活动指南；《中国居民膳食指南（2022）》；Paluch 等 2022 *Lancet Public Health*（步数）。
- 体重：WS/T 428-2013《成人体重判定》。
- 听力：WHO-ITU H.870 安全聆听标准。
- 空气质量：HJ 633—2026《环境空气质量指数（AQI）技术规定》；气象部门高温、寒潮预警信号标准。
- 数据格式：Health Auto Export 官方文档与示例；Apple HealthKit 文档。
