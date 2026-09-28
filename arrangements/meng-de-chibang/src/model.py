# -*- coding: utf-8 -*-
"""把 score_data 里的类 LilyPond 记法解析成统一的事件模型。"""
import re
from dataclasses import dataclass, field
from fractions import Fraction as F

import score_data as SD

STEP_SEMI = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
ALTER = {"": 0, "is": 1, "es": -1, "isis": 2, "eses": -2}
BAR_LEN = F(4)

HEAD_RE = re.compile(
    r"^(?P<head>R|r|<[^>]*>|[a-g](?:isis|eses|is|es)?[',]*)"
    r"(?P<dur>(?:16|32|1|2|4|8)\.*)?(?P<post>.*)$"
)
PITCH_RE = re.compile(r"^(?P<step>[a-g])(?P<alt>isis|eses|is|es)?(?P<oct>[',]*)$")
POST_RE = re.compile(
    r"~|\(|\)|\\<|\\>|\\!|\\fermata|\\br|"
    r"\\(?:ppp|pp|p|mp|mf|fff|ff|f|sfz|fp)(?![a-z])|"
    r"\^\{[^}]*\}|_\{[^}]*\}|--|-\.|->"
)
DYN_LEVEL = {"ppp": 0, "pp": 1, "p": 2, "mp": 3, "mf": 4, "f": 5, "ff": 6, "fff": 7}


@dataclass
class Pitch:
    step: str      # 'c'..'b'
    alter: int
    octave: int
    name: str      # 原记法（LilyPond 用）

    @property
    def midi(self):
        return (self.octave + 1) * 12 + STEP_SEMI[self.step] + self.alter


@dataclass
class Event:
    kind: str                  # note | rest | mrest
    pitches: list
    dur: F                     # 以四分音符为单位
    base: int                  # 1 2 4 8 16
    dots: int
    bar: int = 0
    onset: F = F(0)            # 小节内位置
    start: F = F(0)            # 全曲绝对位置
    tie_start: bool = False
    tie_stop: bool = False
    slur_start: int = 0
    slur_stop: int = 0
    dyn: str = None
    hairpin: str = None        # '<' | '>'
    hairpin_end: bool = False
    fermata: bool = False
    br: bool = False
    artic: list = field(default_factory=list)
    texts: list = field(default_factory=list)   # (placement '^'|'_', text)
    lyric: str = None
    melisma_cont: bool = False  # 人声：拖腔/连音线后续音（不配新字）

    @property
    def end(self):
        return self.start + self.dur

    def lily_dur(self):
        return str(self.base) + "." * self.dots


def tokenize(s):
    toks, cur, brace, angle = [], "", 0, 0
    for ch in s:
        if ch.isspace() and brace == 0 and angle == 0:
            if cur:
                toks.append(cur)
                cur = ""
            continue
        if ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
        elif ch == "<" and cur == "" and brace == 0:
            angle += 1
        elif ch == ">" and angle > 0 and brace == 0:
            angle -= 1
        cur += ch
    if cur:
        toks.append(cur)
    return toks


def parse_pitch(txt):
    m = PITCH_RE.match(txt)
    if not m:
        raise ValueError(f"bad pitch {txt!r}")
    octv = 3 + m.group("oct").count("'") - m.group("oct").count(",")
    return Pitch(m.group("step"), ALTER[m.group("alt") or ""], octv, txt)


def dur_value(base, dots):
    d = F(4, base)
    return d * (2 - F(1, 2 ** dots))


def parse_part(bars, part_name):
    events = []
    last_base, last_dots = 4, 0
    for bi, bar_src in enumerate(bars, start=1):
        pos = F(0)
        for tok in tokenize(bar_src):
            m = HEAD_RE.match(tok)
            if not m:
                raise ValueError(f"{part_name} bar {bi}: cannot parse {tok!r}")
            head, dur, post = m.group("head"), m.group("dur"), m.group("post")
            if dur:
                base = int(dur.rstrip("."))
                dots = dur.count(".")
                last_base, last_dots = base, dots
            else:
                base, dots = last_base, last_dots
            if head == "R":
                ev = Event("mrest", [], BAR_LEN, 1, 0)
            elif head == "r":
                ev = Event("rest", [], dur_value(base, dots), base, dots)
            elif head.startswith("<"):
                ps = [parse_pitch(p) for p in head[1:-1].split()]
                ev = Event("note", ps, dur_value(base, dots), base, dots)
            else:
                ev = Event("note", [parse_pitch(head)], dur_value(base, dots), base, dots)
            i = 0
            while i < len(post):
                pm = POST_RE.match(post, i)
                if not pm:
                    raise ValueError(f"{part_name} bar {bi}: bad suffix {post[i:]!r} in {tok!r}")
                a = pm.group(0)
                i = pm.end()
                if a == "~":
                    ev.tie_start = True
                elif a == "(":
                    ev.slur_start += 1
                elif a == ")":
                    ev.slur_stop += 1
                elif a == "\\<":
                    ev.hairpin = "<"
                elif a == "\\>":
                    ev.hairpin = ">"
                elif a == "\\!":
                    ev.hairpin_end = True
                elif a == "\\fermata":
                    ev.fermata = True
                elif a == "\\br":
                    ev.br = True
                elif a.startswith("\\"):
                    ev.dyn = a[1:]
                elif a[0] in "^_":
                    ev.texts.append((a[0], a[2:-1]))
                else:
                    ev.artic.append(a)
            ev.bar, ev.onset = bi, pos
            ev.start = (bi - 1) * BAR_LEN + pos
            pos += ev.dur
            events.append(ev)
        if pos != BAR_LEN:
            raise ValueError(f"{part_name} bar {bi}: length {pos} != 4  ({bar_src!r})")
    if len(bars) != SD.N_BARS:
        raise ValueError(f"{part_name}: {len(bars)} bars, expected {SD.N_BARS}")
    # 连音线终点
    notes = [e for e in events if e.kind == "note"]
    for a, b in zip(events, events[1:]):
        if a.tie_start:
            if b.kind != "note" or [p.midi for p in a.pitches] != [p.midi for p in b.pitches]:
                raise ValueError(f"{part_name} bar {a.bar}: tie to a different pitch")
            b.tie_stop = True
    # 圆滑线配对检查
    depth = 0
    for e in events:
        depth += e.slur_start
        if e.slur_start and depth > 1:
            raise ValueError(f"{part_name} bar {e.bar}: nested slur")
        depth -= e.slur_stop
        if depth < 0:
            raise ValueError(f"{part_name} bar {e.bar}: slur closed twice")
    if depth:
        raise ValueError(f"{part_name}: unclosed slur")
    return events


def assign_lyrics(events, syllables):
    """LilyPond \\lyricsto 的规则：圆滑线内后续音、连音线后续音不配新字。"""
    in_slur = False
    k = 0
    for e in events:
        if e.kind != "note":
            continue
        cont = e.tie_stop or (in_slur and not e.slur_start)
        e.melisma_cont = cont
        if not cont:
            if k >= len(syllables):
                raise ValueError(f"voice bar {e.bar}: more notes than syllables")
            e.lyric = syllables[k]
            k += 1
        if e.slur_start:
            in_slur = True
        if e.slur_stop:
            in_slur = False
    if k != len(syllables):
        raise ValueError(f"lyrics: {len(syllables)} syllables but {k} syllable notes")


def load():
    parts = []
    for p in SD.PARTS:
        evs = parse_part(p["bars"], p["name"])
        if p["key"] == "voice":
            assign_lyrics(evs, SD.LYRICS)
        parts.append(dict(p, events=evs))
    return parts


if __name__ == "__main__":
    ps = load()
    for p in ps:
        n = sum(1 for e in p["events"] if e.kind == "note")
        print(f"{p['name']:12s} {n:4d} notes  OK")
