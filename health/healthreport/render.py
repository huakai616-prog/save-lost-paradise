"""把分析结果渲染成 HTML 邮件、Markdown 和给 Claude 写点评用的简报。

HTML 按邮件客户端的限制来写：表格布局、行内样式、不用 SVG 和脚本（Gmail 会过滤掉），
同一份 HTML 上传到 Google Drive 时也会被转成 Google 文档。
"""

import html
import json
from datetime import date, datetime

from .catalog import fmt

# ---- 颜色（dataviz 参考调色板）----
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
SURFACE, PAGE, GRID, BORDER = "#fcfcfb", "#f9f9f7", "#e1e0d9", "#e6e5e0"
SERIES, SERIES_LIGHT, TRACK = "#2a78d6", "#86b6ef", "#cde2fb"
GOOD_TEXT = "#006300"
LEVELS = {  # 状态色 + 图标 + 文字，颜色从不单独表达含义
    "red": ("#d03b3b", "🔴", "建议就医"),
    "orange": ("#ec835a", "🟠", "需要留意"),
    "yellow": ("#fab219", "🟡", "小提醒"),
    "info": ("#898781", "ℹ️", "提示"),
    "green": ("#0ca30c", "🟢", "做得好"),
}
STAGES = [("deep_h", "深睡", "#4a3aa7"), ("core_h", "核心", "#2a78d6"),
          ("rem_h", "REM", "#1baf7a"), ("awake_h", "清醒", "#eb6834")]
AQI_COLORS = {"优": "#00e400", "良": "#ffff00", "轻度污染": "#ff7e00", "中度污染": "#ff0000",
              "重度污染": "#99004c", "严重污染": "#7e0023"}
FONT = ('-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",'
        '"Helvetica Neue",Arial,sans-serif')

e = html.escape


def _h(title):
    return (f'<tr><td style="padding:22px 24px 8px"><div style="font-size:17px;font-weight:700;color:{INK}">'
            f'{e(title)}</div></td></tr>')


def _row(inner, pad="4px 24px 12px"):
    return f'<tr><td style="padding:{pad}">{inner}</td></tr>'


def _tiles(items):
    """数据块：[(标签, 数值, 小字)]。超过 3 个时两两一行，手机上也不会挤得换行。"""
    rows = [items] if len(items) <= 3 else [items[i:i + 2] for i in range(0, len(items), 2)]
    out = []
    for row in rows:
        cells = []
        for label, value, sub in row:
            cells.append(
                f'<td valign="top" style="padding:8px 10px 8px 0;width:{100 // max(1, len(row))}%">'
                f'<div style="font-size:12px;color:{INK2}">{e(label)}</div>'
                f'<div style="font-size:20px;font-weight:600;color:{INK};line-height:1.3;white-space:nowrap">{e(value)}</div>'
                f'<div style="font-size:12px;color:{MUTED}">{e(sub or "")}</div></td>')
        out.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{"".join(cells)}</tr></table>')
    return "".join(out)


def _bars(points, key, title):
    """14 天迷你柱状图：单一序列，旧的日子浅色，最新一天强调色，只标注最新值。"""
    vals = [p["value"] for p in points]
    have = [v for v in vals if v is not None]
    if len(have) < 3:
        return ""
    top = max(have) or 1
    cols = []
    for i, v in enumerate(vals):
        if v is None:
            cols.append(f'<td valign="bottom" style="padding:0 1px"><div style="height:2px;background:{GRID}"></div></td>')
            continue
        color = SERIES if i == len(vals) - 1 else SERIES_LIGHT
        cols.append(f'<td valign="bottom" style="padding:0 1px"><div style="height:{max(3, round(v / top * 44))}px;'
                    f'background:{color};border-radius:4px 4px 0 0"></div></td>')
    first_day = points[0]["day"][5:].replace("-", "/")
    return (f'<div style="font-size:12px;color:{INK2};margin:10px 0 4px">{e(title)}'
            f'<span style="color:{MUTED}"> · 最新 {e(fmt(key, have[-1]))}</span></div>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="height:46px;border-bottom:1px solid {BORDER}"><tr>{"".join(cols)}</tr></table>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="font-size:11px;color:{MUTED}">{e(first_day)}</td>'
            f'<td align="right" style="font-size:11px;color:{MUTED}">{e(points[-1]["day"][5:].replace("-", "/"))}</td>'
            f'</tr></table>')


def _finding_html(f):
    color, icon, label = LEVELS[f["level"]]
    detail = f'<div style="font-size:13px;color:{INK2};margin-top:3px">{e(f["detail"])}</div>' if f["detail"] else ""
    advice = (f'<div style="font-size:13px;color:{INK};margin-top:4px">👉 {e(f["advice"])}</div>'
              if f["advice"] else "")
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 10px">'
            f'<tr><td width="4" style="background:{color};border-radius:2px"></td>'
            f'<td style="padding:6px 0 6px 12px">'
            f'<div style="font-size:12px;color:{INK2}">{icon} {e(label)} · {e(f["cat"])}</div>'
            f'<div style="font-size:15px;font-weight:600;color:{INK};margin-top:2px">{e(f["title"])}</div>'
            f'{detail}{advice}</td></tr></table>')


def _delta_str(v):
    if not v or v.get("delta") is None:
        return "—"
    d = v["delta"]
    key = v["key"]
    if key in ("wrist_temp",):
        return f"{d:+.2f}°C"
    if key in ("resp_rate", "spo2", "vo2max"):
        return f"{d:+.1f}"
    return f"{d:+.0f}"


def _vital_status(v):
    """根据 z 分数给出简短的文字状态（文字 + 箭头，不只靠颜色）。"""
    if not v or v.get("z") is None:
        return "建立基线中" if v else "—"
    z, key = v["z"], v["key"]
    good_up = key in ("hrv", "hrv_night", "spo2", "spo2_night", "vo2max")
    bad_up = key in ("rhr", "resp_rate", "resp_night", "wrist_temp", "walking_hr", "breathing_dist")
    if abs(z) < 1:
        return "正常"
    if (z > 0 and good_up) or (z < 0 and bad_up):
        return "↑ 更好" if z > 0 else "↓ 更好"
    word = "偏高" if z > 0 else "偏低"
    return f'{"↑" if z > 0 else "↓"} {"明显" if abs(z) >= 2 else ""}{word}'


def build_html(r, narrative=None, links=None):
    links = links or {}
    parts = []
    rd = r.get("readiness")
    counts = r["counts"]
    # ---- 头部 ----
    if rd:
        tone = LEVELS["green" if rd["tone"] == "green" else ("yellow" if rd["tone"] == "yellow" else "orange")]
        hero = (f'<div style="font-size:13px;color:{INK2}">今日状态</div>'
                f'<div style="line-height:1.1"><span style="font-size:52px;font-weight:700;color:{INK}">{rd["score"]}</span>'
                f'<span style="font-size:18px;color:{INK2}"> / 100</span>'
                f'<span style="display:inline-block;margin-left:12px;font-size:15px;font-weight:600;color:{INK}">'
                f'{tone[1]} {e(rd["label"])}</span></div>'
                f'<div style="font-size:12px;color:{MUTED};margin-top:2px">根据睡眠、HRV、静息心率和夜间体征估算'
                f'{"（部分数据缺失）" if rd["partial"] else ""}</div>')
    else:
        hero = (f'<div style="font-size:15px;color:{INK2}">今天还算不出状态分'
                f'（需要睡眠和心率数据，并积累一段时间的基线）。</div>')
    summary_bits = []
    for lv in ("red", "orange", "yellow"):
        if counts.get(lv):
            summary_bits.append(f'{LEVELS[lv][1]} {LEVELS[lv][2]} {counts[lv]} 项')
    parts.append(
        f'<tr><td style="padding:24px 24px 6px">'
        f'<div style="font-size:13px;color:{MUTED}">身体日报 · {e(r["date_cn"])}</div>'
        f'<div style="margin-top:12px">{hero}</div>'
        + (f'<div style="font-size:13px;color:{INK2};margin-top:8px">{" · ".join(summary_bits)}</div>' if summary_bits else "")
        + '</td></tr>')
    if narrative:
        paras = "".join(f'<p style="margin:0 0 8px">{e(p)}</p>' for p in narrative.strip().split("\n") if p.strip())
        parts.append(_row(f'<div style="font-size:15px;line-height:1.7;color:{INK};background:{PAGE};'
                          f'border-radius:8px;padding:12px 14px">{paras}</div>', "10px 24px 4px"))

    # ---- 需要注意 ----
    main, extra, infos, goods = split_findings(r["findings"])
    parts.append(_h("今天需要注意"))
    if main or infos:
        parts.append(_row("".join(_finding_html(f) for f in main + infos)))
    else:
        parts.append(_row(f'<div style="font-size:14px;color:{INK2}">没有需要特别注意的地方，继续保持。</div>'))
    if extra:
        items = "；".join(e(f["title"]) for f in extra)
        parts.append(_row(f'<div style="font-size:13px;color:{INK2}">🟡 其他小提醒：{items}</div>', "0 24px 8px"))
    if goods:
        items = "".join(f'<div style="font-size:13px;color:{INK};margin:3px 0">🟢 {e(g["title"])}</div>' for g in goods)
        parts.append(_row(f'<div style="font-size:12px;color:{INK2};margin-bottom:2px">做得好</div>{items}', "0 24px 8px"))
    plan = r.get("plan") or {}
    if plan.get("exercise"):
        parts.append(_row(f'<div style="font-size:14px;color:{INK};border:1px solid {BORDER};border-radius:8px;'
                          f'padding:10px 12px"><b>🏃 今日运动建议</b><br>{e(plan["exercise"])}</div>', "4px 24px 8px"))

    # ---- 睡眠 ----
    sl = r["sleep"]
    if sl.get("total_h"):
        parts.append(_h("昨晚睡眠" if sl["which"] == "last_night" else "最近一次睡眠"))
        base = f'平时 {sl["baseline_h"]:.1f} 小时' if sl.get("baseline_h") else ""
        tiles = [("睡着", f'{sl["total_h"]:.1f} 小时', base),
                 ("入睡–醒来", f'{sl.get("start") or "—"}–{sl.get("end") or "—"}', ""),
                 ("近 7 晚平均", f'{sl["avg7_h"]:.1f} 小时' if sl.get("avg7_h") else "—",
                  f'{sl["short_nights7"]} 晚不足 6 小时' if sl.get("short_nights7") else "")]
        parts.append(_row(_tiles(tiles), "0 24px 4px"))
        stages = [(lab, sl.get(k), c) for k, lab, c in STAGES if sl.get(k)]
        if stages:
            tot = sum(v for _, v, _ in stages)
            segs = "".join(
                f'<td style="background:{c};height:14px;width:{v / tot * 100:.1f}%;'
                f'{"border-radius:4px 0 0 4px;" if i == 0 else ""}'
                f'{"border-radius:0 4px 4px 0;" if i == len(stages) - 1 else ""}'
                f'border-right:{"2px solid " + SURFACE if i < len(stages) - 1 else "0"}"></td>'
                for i, (_, v, c) in enumerate(stages))
            legend = " ".join(
                f'<span style="white-space:nowrap;margin-right:10px">'
                f'<span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:{c}"></span> '
                f'{e(lab)} {v * 60:.0f}分 ({v / tot:.0%})</span>' for lab, v, c in stages)
            parts.append(_row(
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{segs}</tr></table>'
                f'<div style="font-size:12px;color:{INK2};margin-top:6px;line-height:1.8">{legend}</div>'
                f'<div style="font-size:11px;color:{MUTED}">手表的睡眠分期是估算值，看长期趋势比看单晚更有意义。</div>',
                "4px 24px 4px"))
        parts.append(_row(_bars(r["trends"]["sleep_h"], "sleep_h", "近 14 晚睡眠时长"), "0 24px 8px"))

    # ---- 恢复指标 ----
    v = r["vitals"]
    rows = []
    for key in ("rhr", "hrv", "resp_rate", "wrist_temp", "spo2", "breathing_dist", "walking_hr", "vo2max"):
        x = v.get(key)
        if not x:
            continue
        val = x["value_str"] if key != "wrist_temp" else (
            f'{x["delta"]:+.2f}°C' if x.get("delta") is not None else x["value_str"])
        base = x["baseline_str"] or "—"
        if key == "wrist_temp":
            base = "±0.00°C"
        rows.append(
            f'<tr><td style="padding:7px 0;border-bottom:1px solid {GRID};font-size:14px;color:{INK}">{e(x["name"])}</td>'
            f'<td align="right" style="padding:7px 6px;border-bottom:1px solid {GRID};font-size:14px;color:{INK};'
            f'font-variant-numeric:tabular-nums">{e(val)}</td>'
            f'<td align="right" style="padding:7px 6px;border-bottom:1px solid {GRID};font-size:13px;color:{INK2};'
            f'font-variant-numeric:tabular-nums;white-space:nowrap">{e(base)}</td>'
            f'<td align="right" style="padding:7px 0;border-bottom:1px solid {GRID};font-size:13px;color:{INK2};white-space:nowrap">'
            f'{e(_vital_status(x))}</td></tr>')
    if rows:
        parts.append(_h("恢复指标"))
        head = (f'<tr><td style="font-size:12px;color:{MUTED};padding-bottom:4px">指标</td>'
                f'<td align="right" style="font-size:12px;color:{MUTED}">最新</td>'
                f'<td align="right" style="font-size:12px;color:{MUTED}">平时</td>'
                f'<td align="right" style="font-size:12px;color:{MUTED}">状态</td></tr>')
        parts.append(_row(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{head}{"".join(rows)}</table>'))
        parts.append(_row(_bars(r["trends"]["hrv"], "hrv", "近 14 天 HRV（每日均值）"), "0 24px 8px"))

    # ---- 活动 ----
    a = r["activity"]
    if any(a.get(k) is not None for k in ("steps", "active_kcal", "exercise_min")) or a.get("workouts"):
        parts.append(_h("昨日活动"))
        parts.append(_row(_tiles([
            ("步数", fmt("steps", a.get("steps"), False), f'近 7 天日均 {a["steps7_avg"]:,.0f}' if a.get("steps7_avg") else ""),
            ("活动消耗", fmt("active_kcal", a.get("active_kcal")), ""),
            ("锻炼", fmt("exercise_min", a.get("exercise_min")), ""),
            ("站立", fmt("stand_hours", a.get("stand_hours")), ""),
        ]), "0 24px 4px"))
        if a.get("exercise7") is not None:
            pct = min(1.0, a["exercise7"] / 150)
            parts.append(_row(
                f'<div style="font-size:12px;color:{INK2};margin-bottom:4px">近 7 天锻炼 {a["exercise7"]:.0f} / 150 分钟</div>'
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
                f'<td style="background:{SERIES};height:8px;width:{pct * 100:.0f}%;border-radius:4px 0 0 4px"></td>'
                f'<td style="background:{TRACK};height:8px;border-radius:0 4px 4px 0"></td></tr></table>',
                "4px 24px 4px") if pct < 1 else _row(
                f'<div style="font-size:12px;color:{GOOD_TEXT}">✓ 近 7 天锻炼 {a["exercise7"]:.0f} 分钟，已达到每周 150 分钟</div>',
                "4px 24px 4px"))
        ws = a.get("workouts") or []
        if ws:
            lines = []
            for w in ws:
                bits = [f'{w["duration_min"]:.0f} 分钟' if w.get("duration_min") else None,
                        f'{w["distance_km"]:.2f} 公里' if w.get("distance_km") else None,
                        f'{w["kcal"]:.0f} 千卡' if w.get("kcal") else None,
                        f'平均心率 {w["avg_hr"]:.0f}' if w.get("avg_hr") else None]
                t = w["start"].strftime("%H:%M") if isinstance(w.get("start"), datetime) else ""
                lines.append(f'<div style="font-size:14px;color:{INK};margin:3px 0">🏋️ {e(t)} {e(w["name"])}'
                             f'<span style="color:{INK2}"> · {e(" · ".join(b for b in bits if b))}</span></div>')
            parts.append(_row("".join(lines), "4px 24px 4px"))
        parts.append(_row(_bars(r["trends"]["steps"], "steps", "近 14 天步数"), "0 24px 8px"))

    # ---- 身体数据 ----
    b = r["body"]
    body_items = []
    if b.get("weight_kg"):
        chg = b.get("weight_change_7d")
        body_items.append(("体重", fmt("weight_kg", b["weight_kg"]["value"]),
                           f"一周 {chg:+.1f} kg" if chg is not None else _mmdd(b["weight_kg"]["day"])))
    if b.get("bp_sys") and b.get("bp_dia"):
        body_items.append(("血压", f'{b["bp_sys"]["value"]:.0f}/{b["bp_dia"]["value"]:.0f}', _mmdd(b["bp_sys"]["day"])))
    if b.get("body_fat"):
        body_items.append(("体脂率", fmt("body_fat", b["body_fat"]["value"]), _mmdd(b["body_fat"]["day"])))
    if b.get("glucose"):
        body_items.append(("血糖", fmt("glucose", b["glucose"]["value"]), _mmdd(b["glucose"]["day"])))
    if body_items:
        parts.append(_h("身体数据"))
        parts.append(_row(_tiles(body_items[:4]), "0 24px 8px"))

    # ---- 日程 ----
    c = r.get("calendar")
    if c is not None:
        parts.append(_h("今天的日程"))
        if not c.get("count") and not c.get("all_day"):
            parts.append(_row(f'<div style="font-size:14px;color:{INK2}">日历里今天没有安排。</div>'))
        else:
            head = (f'<div style="font-size:13px;color:{INK2};margin-bottom:6px">{c["count"]} 项安排，'
                    f'约 {c["busy_hours"]:.1f} 小时'
                    + (f'，{c["first_start"]} 开始，{c["last_end"]} 结束' if c.get("first_start") else "")
                    + "</div>")
            evs = "".join(f'<div style="font-size:14px;color:{INK};margin:2px 0">'
                          f'<span style="color:{INK2};font-variant-numeric:tabular-nums">{e(x["time"])}</span> '
                          f'{e(x["title"])}</div>' for x in c["events"][:10])
            more = f'<div style="font-size:12px;color:{MUTED}">……还有 {len(c["events"]) - 10} 项</div>' \
                if len(c["events"]) > 10 else ""
            ad = "".join(f'<div style="font-size:14px;color:{INK};margin:2px 0">📌 全天：{e(t)}</div>'
                         for t in c.get("all_day") or [])
            slot = (f'<div style="font-size:13px;color:{INK2};margin-top:6px">空档 {e(c["exercise_slot"])} '
                    f'适合安排运动或散步。</div>') if c.get("exercise_slot") else ""
            parts.append(_row(head + ad + evs + more + slot))

    # ---- 天气 ----
    w = r.get("weather")
    if w:
        parts.append(_h("天气与空气"))
        t = []
        if w.get("temp_min") is not None and w.get("temp_max") is not None:
            t.append(("气温", f'{w["temp_min"]:.0f}~{w["temp_max"]:.0f}°C', w.get("desc") or ""))
        if w.get("aqi") is not None:
            t.append(("空气质量", f'{w["aqi"]:.0f} {w.get("aqi_level", "")}',
                      f'首要污染物 {w["aqi_primary"]}' if w.get("aqi_primary") else ""))
        if w.get("uv_max") is not None:
            t.append(("紫外线", f'{w["uv_max"]:.0f}', _uv_word(w["uv_max"])))
        if w.get("precip_prob") is not None:
            t.append(("降水概率", f'{w["precip_prob"]:.0f}%', ""))
        parts.append(_row(_tiles(t[:4]), "0 24px 4px"))
        if w.get("aqi") is not None and w.get("aqi_level") in AQI_COLORS:
            parts.append(_row(
                f'<div style="font-size:13px;color:{INK2}"><span style="display:inline-block;width:10px;height:10px;'
                f'border-radius:5px;background:{AQI_COLORS[w["aqi_level"]]};border:1px solid {BORDER}"></span> '
                f'空气{e(w["aqi_level"])}：{e(w.get("aqi_advice", ""))}</div>', "0 24px 8px"))
        src = "来源：" + e(w.get("source") or "")
        if not w.get("reliable", True):
            src += "（网络搜索，仅供参考）"
        if w.get("sunrise") and w.get("sunset"):
            src += f' · 日出 {e(w["sunrise"])} 日落 {e(w["sunset"])}'
        if w.get("aqi_note"):
            src += f'<br>空气质量按国标 HJ 633—2026 由污染物浓度换算，{e(w["aqi_note"])}'
        parts.append(_row(f'<div style="font-size:11px;color:{MUTED}">{src}</div>', "0 24px 8px"))

    # ---- 手动记录 ----
    m = r.get("manual") or {}
    if m:
        parts.append(_h("你的记录"))
        lines = []
        for d in sorted(m):
            rec = m[d]
            bits = []
            for k, lab, suf in (("mood", "心情", "/5"), ("stress", "压力", "/5"), ("energy", "精力", "/5"),
                                ("alcohol", "饮酒", " 杯"), ("caffeine", "咖啡因", " 杯"),
                                ("weight", "体重", " kg")):
                if rec.get(k) is not None:
                    bits.append(f"{lab} {rec[k]:g}{suf}")
            if rec.get("bp_sys") and rec.get("bp_dia"):
                bits.append(f'血压 {rec["bp_sys"]:.0f}/{rec["bp_dia"]:.0f}')
            for k, lab in (("symptoms", "症状"), ("meds", "用药"), ("period", "经期"), ("notes", "备注")):
                if rec.get(k):
                    bits.append(f"{lab}：{rec[k]}")
            lines.append(f'<div style="font-size:14px;color:{INK};margin:3px 0"><span style="color:{INK2}">'
                         f'{e(_mmdd(d))}</span> {e("；".join(bits))}</div>')
        parts.append(_row("".join(lines)))

    # ---- 页脚 ----
    ds = r["data"]
    foot = []
    if ds.get("latest_day"):
        foot.append(f'手表数据截至 {_mmdd(ds["latest_day"])}，共 {ds["days_available"]} 天。')
    if links.get("sheet"):
        foot.append(f'<a href="{e(links["sheet"])}" style="color:{SERIES}">打开手动记录表</a>')
    if links.get("folder"):
        foot.append(f'<a href="{e(links["folder"])}" style="color:{SERIES}">历史报告</a>')
    parts.append(
        f'<tr><td style="padding:18px 24px 22px;border-top:1px solid {GRID}">'
        f'<div style="font-size:12px;color:{MUTED};line-height:1.7">{" · ".join(foot)}<br>'
        '“平时”指你自己过去约 4 周的中位数（HRV 用 60 天）。' + FOOTER + '</div></td></tr>')

    body = "".join(parts)
    return _entities(f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>身体日报 {e(r["date"])}</title></head>'
            f'<body style="margin:0;padding:0;background:{PAGE};font-family:{FONT};color:{INK}">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE}">'
            f'<tr><td align="center" style="padding:16px 8px">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="max-width:640px;background:{SURFACE};border:1px solid {BORDER};border-radius:12px;font-family:{FONT}">'
            f'{body}</table></td></tr></table></body></html>')


def _entities(html_text):
    """把 emoji 等 BMP 以外的字符写成 &#x...; 实体。

    Google Drive 把 HTML 转成 Google 文档时会把 4 字节的 UTF-8 字符（emoji）解码成乱码，
    写成实体后邮件和文档都能正常显示。
    """
    return "".join(c if ord(c) < 0x10000 else f"&#x{ord(c):X};" for c in html_text)


FOOTER = ("本报告基于可穿戴设备数据自动生成，仅供健康参考，不能替代医生诊断；设备测量存在误差。"
          "如有不适请及时就医，紧急情况请拨打 120。")


def split_findings(findings, limit=None):
    """红、橙全部显示；黄色补足到 limit 条，其余折叠成一行。返回 (主要, 折叠, 提示, 做得好)。"""
    from .thresholds import MAX_MAIN_ITEMS
    limit = limit or MAX_MAIN_ITEMS
    urgent = [f for f in findings if f["level"] in ("red", "orange")]
    yellows = [f for f in findings if f["level"] == "yellow"]
    room = max(0, limit - len(urgent))
    return (urgent + yellows[:room], yellows[room:],
            [f for f in findings if f["level"] == "info"],
            [f for f in findings if f["level"] == "green"][:3])


def _mmdd(d):
    if isinstance(d, date):
        return f"{d.month}月{d.day}日"
    if isinstance(d, str) and len(d) >= 10:
        return f"{int(d[5:7])}月{int(d[8:10])}日"
    return str(d or "")


def _uv_word(uv):
    return "低" if uv < 3 else "中等" if uv < 6 else "高" if uv < 8 else "很高" if uv < 11 else "极高"


# ---------------------------------------------------------------------------
def build_markdown(r, narrative=None):
    L = [f"# 身体日报 · {r['date_cn']}", ""]
    rd = r.get("readiness")
    if rd:
        L.append(f"**今日状态 {rd['score']}/100 · {rd['label']}**" + ("（部分数据缺失）" if rd["partial"] else ""))
        L.append("")
    if narrative:
        L += [narrative.strip(), ""]
    L.append("## 今天需要注意")
    main, extra, infos, goods = split_findings(r["findings"])
    main = main + infos
    for f in main:
        _, icon, label = LEVELS[f["level"]]
        L.append(f"- {icon} **{f['title']}**（{label}）")
        if f["detail"]:
            L.append(f"  {f['detail']}")
        if f["advice"]:
            L.append(f"  👉 {f['advice']}")
    if not main:
        L.append("- 没有需要特别注意的地方。")
    if extra:
        L.append("- 🟡 其他小提醒：" + "；".join(f["title"] for f in extra))
    if goods:
        L += ["", "**做得好：** " + "；".join(g["title"] for g in goods)]
    if (r.get("plan") or {}).get("exercise"):
        L += ["", f"**今日运动建议：** {r['plan']['exercise']}"]
    sl = r["sleep"]
    if sl.get("total_h"):
        L += ["", "## 睡眠", f"- 睡着 {sl['total_h']:.1f} 小时（{sl.get('start') or '?'} → {sl.get('end') or '?'}）"]
        st = [f"{lab} {sl[k] * 60:.0f} 分" for k, lab, _ in STAGES if sl.get(k)]
        if st:
            L.append("- " + " · ".join(st))
        if sl.get("avg7_h"):
            L.append(f"- 近 7 晚平均 {sl['avg7_h']:.1f} 小时")
    v = r["vitals"]
    rows = [(v[k]["name"], v[k]["value_str"], v[k]["baseline_str"] or "—", _vital_status(v[k]))
            for k in ("rhr", "hrv", "resp_rate", "wrist_temp", "spo2", "walking_hr", "vo2max") if v.get(k)]
    if rows:
        L += ["", "## 恢复指标", "| 指标 | 最新 | 平时 | 状态 |", "|---|---|---|---|"]
        L += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
    a = r["activity"]
    if a.get("steps") is not None or a.get("workouts"):
        L += ["", "## 昨日活动",
              f"- 步数 {fmt('steps', a.get('steps'))} · 活动消耗 {fmt('active_kcal', a.get('active_kcal'))} · "
              f"锻炼 {fmt('exercise_min', a.get('exercise_min'))} · 站立 {fmt('stand_hours', a.get('stand_hours'))}"]
        for w in a.get("workouts") or []:
            L.append(f"- {w['name']} {w['duration_min']:.0f} 分钟" if w.get("duration_min") else f"- {w['name']}")
    c = r.get("calendar")
    if c and c.get("count"):
        L += ["", "## 今天的日程", f"- {c['count']} 项，约 {c['busy_hours']:.1f} 小时"]
        L += [f"- {x['time']} {x['title']}" for x in c["events"][:10]]
    w = r.get("weather")
    if w:
        L += ["", "## 天气与空气"]
        if w.get("temp_max") is not None:
            L.append(f"- {w.get('desc') or ''} {w.get('temp_min', 0):.0f}~{w['temp_max']:.0f}°C")
        if w.get("aqi") is not None:
            L.append(f"- AQI {w['aqi']:.0f} {w.get('aqi_level', '')}")
    L += ["", "---", FOOTER]
    return "\n".join(L)


# ---------------------------------------------------------------------------
def build_brief(r):
    """给 Claude 写“今日点评”用的精简事实清单（不含原始数据）。"""
    out = {
        "date": r["date"],
        "readiness": r.get("readiness"),
        "sleep": {k: r["sleep"].get(k) for k in ("which", "total_h", "start", "end", "deep_h", "rem_h",
                                                  "awake_h", "avg7_h", "short_nights7", "baseline_h")},
        "vitals": {k: {kk: (round(x[kk], 2) if isinstance(x.get(kk), float) else x.get(kk))
                       for kk in ("value", "baseline", "delta", "z", "day")}
                   for k, x in r["vitals"].items() if isinstance(x, dict) and "baseline" in x},
        "signals": r["vitals"].get("signals"),
        "activity": {k: r["activity"].get(k) for k in ("steps", "active_kcal", "exercise_min", "exercise7",
                                                        "stand_hours", "acwr")},
        "workouts": [w["name"] for w in r["activity"].get("workouts") or []],
        "calendar": {k: (r.get("calendar") or {}).get(k) for k in ("count", "busy_hours", "first_start",
                                                                  "last_end", "exercise_slot")},
        "weather": {k: (r.get("weather") or {}).get(k) for k in ("desc", "temp_min", "temp_max", "aqi",
                                                                 "aqi_level", "uv_max")},
        "manual": r.get("manual"),
        "findings": [{"level": f["level"], "title": f["title"]} for f in r["findings"]],
        "plan": r.get("plan"),
        "data_state": r["data"].get("state"),
    }
    return json.dumps(out, ensure_ascii=False, indent=1, default=str)


def subject(r):
    rd = r.get("readiness")
    bits = [f"身体日报 {int(r['date'][5:7])}/{int(r['date'][8:10])}"]
    if rd:
        bits.append(f"状态 {rd['score']} {rd['label']}")
    c = r["counts"]
    if c.get("red"):
        bits.append(f"🔴 {c['red']} 项建议就医")
    n = c.get("orange", 0) + c.get("yellow", 0)
    if n:
        bits.append(f"{n} 项需留意")
    if r["data"].get("state") == "none":
        bits.append("等待手表数据")
    return " · ".join(bits)
