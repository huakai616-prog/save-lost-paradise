# -*- coding: utf-8 -*-
"""事件模型 → 两个 MIDI：弦乐总 MIDI（四轨）与带歌词的人声 MIDI（含 br 气口块）。"""
from fractions import Fraction as F

import mido

import model
import score_data as SD

TPQ = 480
LEVEL = model.DYN_LEVEL

# 速度图（单位：四分音符, BPM）。第 34 小节 rit.，34 小节末拍与 35 小节为延长记号。
TEMPO_MAP = [
    (F(0), SD.BPM),
    (F(27 * 4), 78), (F(27 * 4 + 2), 75), (F(28 * 4), 72),      # 28–29：poco allarg.（最后一句）
    (F(29 * 4), SD.BPM),                                        # 30：a tempo
    (F(33 * 4) + 0, 76), (F(33 * 4) + 1, 72), (F(33 * 4) + 2, 66), (F(33 * 4) + 3, 44),
    (F(34 * 4), 50),
]
MARKERS = [(1, "Intro"), (10, "A - Chorus"), (18, "B"), (26, "C - Climax"), (30, "D - Coda")]


def tick(q):
    return int(round(q * TPQ))


def conductor_track(name):
    tr = mido.MidiTrack()
    ev = [(0, mido.MetaMessage("track_name", name=name)),
          (0, mido.MetaMessage("time_signature", numerator=4, denominator=4,
                               clocks_per_click=24, notated_32nd_notes_per_beat=8)),
          (0, mido.MetaMessage("key_signature", key="Em"))]
    for q, bpm in TEMPO_MAP:
        ev.append((tick(q), mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm))))
    for b, txt in MARKERS:
        ev.append((tick((b - 1) * 4), mido.MetaMessage("marker", text=txt)))
    end = tick(SD.N_BARS * 4)
    ev.append((end, mido.MetaMessage("end_of_track")))
    return to_track(ev, tr)


def to_track(abs_events, tr=None):
    tr = tr if tr is not None else mido.MidiTrack()
    # 同一时刻：meta/控制在前，note_off 先于 note_on
    def order(item):
        t, m = item
        if m.is_meta:
            k = {"end_of_track": 9, "lyrics": 2.5}.get(m.type, 0)   # 歌词紧贴自己的 note_on
        elif m.type == "control_change" or m.type == "program_change":
            k = 1
        elif m.type == "note_off" or (m.type == "note_on" and m.velocity == 0):
            k = 2
        else:
            k = 3
        return (t, k)
    abs_events = sorted(abs_events, key=order)
    now = 0
    for t, m in abs_events:
        tr.append(m.copy(time=t - now))
        now = t
    return tr


def dynamic_curve(events):
    """返回 [(t, level)] 折线：力度记号为节点，渐强/渐弱线性过渡。"""
    pts = []
    level = 2.0
    open_hp = None  # (start_t, start_level, dir)
    for e in events:
        if (e.dyn or e.hairpin_end or e.hairpin) and open_hp:
            st, sl, d = open_hp
            target = LEVEL[e.dyn] if e.dyn else sl + (1 if d == "<" else -1)
            pts.append((st, sl))
            pts.append((e.start, float(target)))
            level = float(target)
            open_hp = None
            if e.dyn:                             # 力度记号即渐变终点，不再重复加阶梯
                pts.append((e.start, level))
                if e.hairpin:
                    open_hp = (e.start, level, e.hairpin)
                continue
        if e.dyn:
            pts.append((e.start, level))          # 阶梯：记号之前保持原力度
            level = float(LEVEL[e.dyn])
            pts.append((e.start, level))
        if e.hairpin:
            open_hp = (e.start, level, e.hairpin)
    return pts


def level_at(pts, t):
    if not pts:
        return 3.0
    if t < pts[0][0]:
        return pts[0][1]
    for (t0, l0), (t1, l1) in zip(pts, pts[1:]):
        if t0 <= t < t1:
            if t1 == t0:
                return l1
            return l0 + (l1 - l0) * float((t - t0) / (t1 - t0))
    return pts[-1][1]


def merged_notes(events):
    """合并连音线；标记圆滑线内位置。返回 dict 列表。"""
    out = []
    in_slur = False
    for e in events:
        if e.kind != "note":
            if e.kind in ("rest", "mrest"):
                out.append(dict(rest=True, ev=e, start=e.start, dur=e.dur))
            continue
        starts_slur = e.slur_start > 0
        if e.tie_stop and out and not out[-1].get("rest"):
            prev = out[-1]
            prev["dur"] += e.dur
            prev["tail"] = e
            prev["fermata"] = prev["fermata"] or e.fermata
            if e.slur_stop:
                prev["slur_end"] = True
                in_slur = False
            continue
        n = dict(rest=False, ev=e, tail=e, start=e.start, dur=e.dur,
                 pitches=[p.midi for p in e.pitches], in_slur=in_slur or starts_slur,
                 slur_end=bool(e.slur_stop), fermata=e.fermata)
        out.append(n)
        if starts_slur:
            in_slur = True
        if e.slur_stop:
            in_slur = False
    return out


def string_track(part):
    evs = part["events"]
    ch = part["channel"]
    pts = dynamic_curve(evs)
    notes = [n for n in merged_notes(evs) if not n["rest"]]
    ab = [(0, mido.MetaMessage("track_name", name=part["name"])),
          (0, mido.MetaMessage("instrument_name", name=part["name"])),
          (0, mido.Message("program_change", channel=ch, program=part["program"])),
          (0, mido.Message("control_change", channel=ch, control=7, value=100)),
          (0, mido.Message("control_change", channel=ch, control=10, value=part["pan"])),
          (0, mido.Message("control_change", channel=ch, control=91, value=48)),
          (0, mido.Message("control_change", channel=ch, control=93, value=0))]
    # CC11 表情：每八分音符取样一次，变化时输出
    last = None
    end_q = F(SD.N_BARS * 4)
    q = F(0)
    while q < end_q:
        lv = level_at(pts, q)
        if q >= F(34 * 4):                         # 最后一小节 morendo → niente
            frac = float((q - F(34 * 4)) / 4)
            lv = lv - 4.0 * frac ** 1.5
        val = max(20, min(127, round(62 + lv * 10)))
        if val != last:
            ab.append((tick(q), mido.Message("control_change", channel=ch, control=11, value=val)))
            last = val
        q += F(1, 4) if q >= F(34 * 4) else F(1, 2)
    for i, n in enumerate(notes):
        st = tick(n["start"])
        full = tick(n["dur"])
        legato = n["in_slur"] and not n["slur_end"]
        nxt = notes[i + 1] if i + 1 < len(notes) else None
        joined = nxt is not None and tick(nxt["start"]) == st + full
        if legato and joined:
            ln = full + (10 if nxt["pitches"] != n["pitches"] else -10)
        elif n["fermata"] or n["start"] + n["dur"] >= end_q:
            ln = full
        elif joined:                               # 分弓后紧接下一音：只留换弓空隙
            ln = full - (20 if full >= TPQ else 30)
        else:                                      # 后面是休止：自然收弓
            ln = max(full - max(30, full // 12), full // 2)
        lv = level_at(pts, n["start"])
        vel = 38 + lv * 11
        if not n["in_slur"]:
            vel += 3                               # 分弓：清楚的起音
        elif n["ev"].slur_start:
            vel += 4                               # 圆滑线首音
        elif n["slur_end"] and full >= TPQ:
            vel -= 8                               # 长的圆滑线尾音：叹息
        else:
            vel -= 4                               # 圆滑线内部
        vel = max(1, min(127, round(vel)))
        for pch in n["pitches"]:
            ab.append((st, mido.Message("note_on", channel=ch, note=pch, velocity=vel)))
            ab.append((st + ln, mido.Message("note_off", channel=ch, note=pch, velocity=0)))
    ab.append((tick(end_q) + TPQ * 2, mido.MetaMessage("end_of_track")))
    return to_track(ab)


def write_strings(parts, path):
    mf = mido.MidiFile(type=1, ticks_per_beat=TPQ, charset="utf-8")
    mf.tracks.append(conductor_track("Meng De Chi Bang Shou Le Shang - String Quartet"))
    for p in parts:
        if p["key"] != "voice":
            mf.tracks.append(string_track(p))
    mf.save(path)
    return mf


def vocal_notes(part):
    """返回人声 MIDI 音符列表 [(start_q, dur_q, pitch, lyric, vel)]，含 br 气口块。"""
    evs = part["events"]
    pts = dynamic_curve(evs)
    items = merged_notes(evs)
    sung = [it for it in items if not it["rest"]]
    out = []
    for idx, it in enumerate(items):
        e = it["ev"]
        if it["rest"]:
            if e.br:
                nxt = next(s for s in items[idx + 1:] if not s["rest"])
                blen = min(F(1, 2), it["dur"])
                out.append([it["start"] + it["dur"] - blen, blen, nxt["pitches"][0], "br", 52])
            continue
        lyric = e.lyric if e.lyric else "-"
        start, dur = it["start"], it["dur"]
        vel = max(1, min(127, round(40 + level_at(pts, start) * 10)))
        br_after = it["tail"].br
        if br_after:
            carve = F(1, 2) if dur >= F(3, 2) else F(1, 4)
            dur -= carve
            nxt = next(s for s in items[idx + 1:] if not s["rest"])
            out.append([start, dur, it["pitches"][0], lyric, vel])
            out.append([start + dur, carve, nxt["pitches"][0], "br", 52])
        else:
            out.append([start, dur, it["pitches"][0], lyric, vel])
    out.sort(key=lambda n: n[0])
    # 自检：不重叠
    for a, b in zip(out, out[1:]):
        assert a[0] + a[1] <= b[0], f"overlap at {a} / {b}"
    return out


def write_vocal(part, path):
    mf = mido.MidiFile(type=1, ticks_per_beat=TPQ, charset="utf-8")
    mf.tracks.append(conductor_track("Meng De Chi Bang Shou Le Shang - Vocal"))
    ch = part["channel"]
    ab = [(0, mido.MetaMessage("track_name", name="Voice")),
          (0, mido.MetaMessage("instrument_name", name="Voice")),
          (0, mido.Message("program_change", channel=ch, program=part["program"])),
          (0, mido.Message("control_change", channel=ch, control=7, value=100))]
    notes = vocal_notes(part)
    for st, du, pch, lyr, vel in notes:
        t0, t1 = tick(st), tick(st + du)
        ab.append((t0, mido.MetaMessage("lyrics", text=lyr)))
        ab.append((t0, mido.Message("note_on", channel=ch, note=pch, velocity=vel)))
        ab.append((t1, mido.Message("note_off", channel=ch, note=pch, velocity=0)))
    ab.append((tick(F(SD.N_BARS * 4)) + TPQ * 2, mido.MetaMessage("end_of_track")))
    mf.tracks.append(to_track(ab))
    mf.save(path)
    return notes
