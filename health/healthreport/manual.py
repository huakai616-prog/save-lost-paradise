"""手动记录：Google 表格「健康手动记录」导出的 CSV。

表头认中文或英文，顺序随意，多余的列会被忽略。支持的列（括号里是可以替代的写法）：
    日期(date) 体重(weight) 收缩压(高压, systolic) 舒张压(低压, diastolic) 血压(bp, 写成 120/80)
    心情(mood, 1-5) 压力(stress, 1-5) 精力(energy, 1-5) 饮酒(alcohol, 标准杯)
    咖啡因(咖啡, caffeine, 杯) 症状(symptoms) 用药(meds) 经期(period, 是/否) 备注(notes)
"""

import csv
import io
import re
from datetime import date

ALIASES = {
    "date": ["日期", "date", "day"],
    "weight": ["体重", "weight"],
    "bp_sys": ["收缩压", "高压", "systolic", "sys"],
    "bp_dia": ["舒张压", "低压", "diastolic", "dia"],
    "bp": ["血压", "bp", "blood pressure"],
    "mood": ["心情", "mood"],
    "stress": ["压力", "stress"],
    "energy": ["精力", "energy"],
    "alcohol": ["饮酒", "酒", "alcohol"],
    "caffeine": ["咖啡因", "咖啡", "caffeine", "coffee"],
    "symptoms": ["症状", "不适", "symptoms"],
    "meds": ["用药", "药", "meds", "medication"],
    "period": ["经期", "月经", "period"],
    "notes": ["备注", "notes", "note"],
}
NUMERIC = {"weight", "bp_sys", "bp_dia", "mood", "stress", "energy", "alcohol", "caffeine"}
TEXT = {"symptoms", "meds", "notes", "period"}


NONE_WORDS = {"无", "没有", "没", "否", "不", "正常", "无症状", "none", "no", "n/a", "na", "-", "—", "/", "0"}


def _match_header(h):
    raw = (h or "").strip()
    if not raw or len(raw) > 20:          # 长句子是说明文字，不是表头
        return None
    h0 = re.sub(r"[（(].*?[）)]", "", raw).strip().lower()
    for key, names in ALIASES.items():
        for n in names:
            if h0 == n.lower():
                return key
    for key, names in ALIASES.items():   # 宽松匹配：表头里包含别名（“日期”列必须精确匹配）
        if key == "date":
            continue
        for n in names:
            if len(n) >= 2 and n.lower() in h0:
                return key
    return None


def parse_date(s, ref=None):
    """支持 2026-09-29、2026/9/29、2026年9月29日、9/29/2026，以及不带年份的 9月29日、9/29、9-29。"""
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)   # 美式 月/日/年
        if m:
            mo, d, y = map(int, m.groups())
        else:
            m = re.match(r"^(\d{1,2})[月/.-](\d{1,2})日?$", s)
            if not m:
                return None
            ref = ref or date.today()
            mo, d = map(int, m.groups())
            y = ref.year
            try:
                if date(y, mo, d) > ref:      # 不带年份时按“最近的过去”算
                    y -= 1
            except ValueError:
                return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _num(s):
    m = re.search(r"-?\d+(?:\.\d+)?", (s or "").replace(",", ""))
    return float(m.group()) if m else None


def parse(text, ref=None, warnings=None):
    """CSV 文本 → {date: {字段: 值}}。同一天多行时后面的覆盖前面的非空字段。"""
    text = text.lstrip("\ufeff")
    rows = list(csv.reader(io.StringIO(text)))
    # 表头可能不在第一行（上面有说明文字）：在前 10 行里找认出列最多、且含“日期”的那一行
    header_idx, cols, best = None, None, 1
    for i, row in enumerate(rows[:10]):
        mapped = [_match_header(c) for c in row]
        n = sum(1 for m in mapped if m)
        if "date" in mapped and n > best:
            header_idx, cols, best = i, mapped, n
    if header_idx is None:
        if warnings is not None and any(any(c.strip() for c in r) for r in rows):
            warnings.append("手动记录表没有找到“日期”列，已跳过")
        return {}
    out, bad = {}, 0
    for row in rows[header_idx + 1:]:
        if not any(c.strip() for c in row):
            continue
        rec = {}
        for key, cell in zip(cols, row):
            cell = cell.strip()
            if key is None or not cell:
                continue
            if key == "date":
                rec["date"] = parse_date(cell, ref)
            elif key == "bp":
                m = re.search(r"(\d{2,3})\s*[/／]\s*(\d{2,3})", cell)
                if m:
                    rec["bp_sys"], rec["bp_dia"] = float(m.group(1)), float(m.group(2))
            elif key in NUMERIC:
                v = _num(cell)
                if v is not None:
                    rec[key] = v
            elif cell.lower() not in NONE_WORDS:   # “无”“没有”之类等于没填
                rec[key] = cell
        d = rec.pop("date", None)
        if d and rec:
            out.setdefault(d, {}).update(rec)
        elif d is None and rec and not any("示例" in c for c in row):
            bad += 1
    if bad and warnings is not None:
        warnings.append(f"手动记录表有 {bad} 行日期看不懂，已跳过（日期写成 2026-09-29 这样最稳）")
    return out


def load(path, ref=None, warnings=None):
    with open(path, encoding="utf-8-sig") as f:
        return parse(f.read(), ref, warnings)


def merge_into(store, entries):
    """体重、血压在健康数据里没有时，用手动记录补上。"""
    store.manual.update(entries)
    for d, rec in entries.items():
        for src, key in (("weight", "weight_kg"), ("bp_sys", "bp_sys"), ("bp_dia", "bp_dia")):
            if rec.get(src) is not None and store.get(d, key) is None:
                store.put(d, key, rec[src])
                store.manual_filled.add((d, key))
