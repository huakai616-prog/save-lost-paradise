# -*- coding: utf-8 -*-
"""编配自检：音域、声部间平行五/八度、人声与弦乐的小二度摩擦、气口数量。"""
from fractions import Fraction as F
from itertools import combinations

import model

RANGES = {  # 实用音域（MIDI）
    "voice": (57, 74),   # A3–D5（女中音舒适区）
    "vn1": (55, 91), "vn2": (55, 91), "va": (48, 81), "vc": (36, 67),
}
NAMES = "C C# D D# E F F# G G# A A# B".split()


def nm(m):
    return f"{NAMES[m % 12]}{m // 12 - 1}"


def sounding(events, t):
    """t 时刻正在发声的音（取最高音，只看单音线）。"""
    for e in events:
        if e.kind == "note" and e.start <= t < e.end:
            return max(p.midi for p in e.pitches)
    return None


def onsets(events):
    return sorted({e.start for e in events if e.kind == "note" and not e.tie_stop})


def main():
    parts = model.load()
    by = {p["key"]: p for p in parts}
    problems = []

    for p in parts:
        lo, hi = RANGES[p["key"]]
        for e in p["events"]:
            for q in e.pitches:
                if not lo <= q.midi <= hi:
                    problems.append(f"音域  {p['name']} 第{e.bar}小节 {nm(q.midi)}")

    strings = ["vn1", "vn2", "va", "vc"]
    pairs = list(combinations(strings, 2)) + [("voice", k) for k in strings]
    for a, b in pairs:
        ea, eb = by[a]["events"], by[b]["events"]
        times = sorted(set(onsets(ea)) | set(onsets(eb)))
        prev = None
        for t in times:
            x, y = sounding(ea, t), sounding(eb, t)
            if x is None or y is None:
                prev = None
                continue
            if prev:
                px, py = prev
                if px != x and py != y:
                    iv0, iv1 = abs(px - py) % 12, abs(x - y) % 12
                    same_dir = (x - px) * (y - py) > 0
                    # 允许：小提琴 I 在高八度加厚人声旋律（流行弦乐常规写法）
                    doubling = a == "voice" and b == "vn1" and iv0 == 0
                    if same_dir and iv0 == iv1 and iv0 in (0, 7) and not doubling:
                        bar = int(t // 4) + 1
                        beat = t % 4 + 1
                        kind = "八度" if iv0 == 0 else "五度"
                        problems.append(
                            f"平行{kind} {by[a]['name']}/{by[b]['name']} 第{bar}小节第{float(beat):g}拍 "
                            f"{nm(px)}-{nm(py)} → {nm(x)}-{nm(y)}")
            prev = (x, y)

    # 外声部（小提琴 I 最高音 / 大提琴）隐伏八度：同向进入八度且高声部跳进
    ea, eb = by["vn1"]["events"], by["vc"]["events"]
    times = sorted(set(onsets(ea)) | set(onsets(eb)))
    prev = None
    for t in times:
        x, y = sounding(ea, t), sounding(eb, t)
        if x is None or y is None:
            prev = None
            continue
        if prev:
            px, py = prev
            if px != x and py != y and (x - px) * (y - py) > 0 and abs(x - y) % 12 == 0 \
                    and abs(px - py) % 12 != 0 and abs(x - px) > 2:
                problems.append(f"隐伏八度 外声部 第{int(t // 4) + 1}小节 {nm(px)}-{nm(py)} → {nm(x)}-{nm(y)}")
        prev = (x, y)

    # 人声与弦乐：同时持续 ≥ 一拍的小二度 / 小九度
    ve = by["voice"]["events"]
    for v in ve:
        if v.kind != "note":
            continue
        vm = v.pitches[0].midi
        for k in strings:
            for e in by[k]["events"]:
                if e.kind != "note":
                    continue
                ov = min(v.end, e.end) - max(v.start, e.start)
                if ov >= 1:
                    for q in e.pitches:
                        d = abs(q.midi - vm)
                        if d in (1, 13):
                            problems.append(
                                f"摩擦  人声 {nm(vm)} 与 {by[k]['name']} {nm(q.midi)} "
                                f"第{v.bar}小节（重叠 {float(ov):g} 拍）")

    brs = sum(1 for e in ve if e.br)
    print(f"人声气口 br：{brs} 处")
    print(f"歌词：{sum(1 for e in ve if e.lyric)} 字")
    if problems:
        print("\n".join(problems))
    else:
        print("无平行五八度、无越界、无人声摩擦。")
    return problems


if __name__ == "__main__":
    main()
