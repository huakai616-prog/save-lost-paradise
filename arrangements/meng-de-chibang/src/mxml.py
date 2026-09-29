# -*- coding: utf-8 -*-
"""事件模型 → MusicXML 4.0（供 Sibelius「文件 → 打开」导入，版式与 PDF 一致）。"""
from fractions import Fraction as F
from xml.sax.saxutils import escape

import model
import score_data as SD

DIV = 4                      # 每四分音符 4 个 division（最小十六分音符）
MM_PER_STAFF = 6.7           # 19pt 谱表高度
TENTHS = 40
PAGE_W_MM, PAGE_H_MM = 210, 297


def t(mm):
    return round(mm / MM_PER_STAFF * TENTHS, 1)


PAGE_W, PAGE_H = t(PAGE_W_MM), t(PAGE_H_MM)
MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = t(17), t(14), t(12), t(11)

TYPE_NAME = {1: "whole", 2: "half", 4: "quarter", 8: "eighth", 16: "16th", 32: "32nd"}
STEP_NAME = {"c": "C", "d": "D", "e": "E", "f": "F", "g": "G", "a": "A", "b": "B"}
KEY_ALTER = {"f": 1}          # E 小调 / G 大调：F#
DYN_SOUND = {"ppp": 25, "pp": 36, "p": 54, "mp": 71, "mf": 89, "f": 106, "ff": 124}
CLEF = {"treble": ("G", 2), "alto": ("C", 3), "bass": ("F", 4)}
LATIN, LATIN_IT, CJK = "EB Garamond", "EB Garamond", "Noto Serif CJK SC"


def x(s):
    return escape(str(s))


def compute_beams(events, group=1):
    """符杠分组（与 LilyPond 一致）：人声按拍（group=1），弦乐按半小节（group=2）。"""
    beams = {}
    groups, cur, cur_beat = [], [], None
    for e in events:
        beamable = e.kind == "note" and e.base >= 8
        beat = int(e.onset // group) * group
        if beamable and (cur_beat == beat) and cur and e.onset < beat + group:
            cur.append(e)
        else:
            if len(cur) >= 2:
                groups.append(cur)
            cur, cur_beat = ([e], beat) if beamable else ([], None)
    if len(cur) >= 2:
        groups.append(cur)
    for g in groups:
        for i, e in enumerate(g):
            lv = ["begin" if i == 0 else "end" if i == len(g) - 1 else "continue"]
            beams[id(e)] = lv
        # 第二层（十六分）
        i = 0
        while i < len(g):
            if g[i].base >= 16:
                j = i
                while j + 1 < len(g) and g[j + 1].base >= 16:
                    j += 1
                if j > i:
                    for k in range(i, j + 1):
                        beams[id(g[k])].append("begin" if k == i else "end" if k == j else "continue")
                else:
                    beams[id(g[i])].append("backward hook" if i > 0 else "forward hook")
                i = j + 1
            else:
                i += 1
    return beams


def direction(inner, placement, sound=None, offset=None, system=None):
    sys_attr = f' system="{system}"' if system else ""
    s = f'      <direction placement="{placement}"{sys_attr}>\n{inner}'
    if sound:
        s += f"        {sound}\n"
    s += "      </direction>\n"
    return s


def words(text, placement, italic=True, bold=False, size=None, family=LATIN, system=None):
    attrs = f' font-family="{family}"'
    if italic:
        attrs += ' font-style="italic"'
    if bold:
        attrs += ' font-weight="bold"'
    if size:
        attrs += f' font-size="{size}"'
    return direction(f"        <direction-type><words{attrs}>{x(text)}</words></direction-type>\n", placement,
                     system=system)


def note_xml(e, part, beams, acc_state, first_in_chord=True):
    out = []
    dur = int(e.dur * DIV)
    if e.kind == "mrest":
        ferm = '        <notations>\n          <fermata type="upright"/>\n        </notations>\n' if e.fermata else ""
        return [f'      <note>\n        <rest measure="yes"/>\n        <duration>{DIV * 4}</duration>\n'
                f'        <voice>1</voice>\n{ferm}      </note>\n']
    if e.kind == "rest":
        s = (f"      <note>\n        <rest/>\n        <duration>{dur}</duration>\n        <voice>1</voice>\n"
             f"        <type>{TYPE_NAME[e.base]}</type>\n" + "        <dot/>\n" * e.dots
             + ('        <notations>\n          <fermata type="upright"/>\n        </notations>\n' if e.fermata else "")
             + "      </note>\n")
        return [s]
    for pi, p in enumerate(e.pitches):
        s = "      <note>\n"
        if pi > 0:
            s += "        <chord/>\n"
        s += f"        <pitch>\n          <step>{STEP_NAME[p.step]}</step>\n"
        if p.alter:
            s += f"          <alter>{p.alter}</alter>\n"
        s += f"          <octave>{p.octave}</octave>\n        </pitch>\n"
        s += f"        <duration>{dur}</duration>\n"
        if e.tie_stop:
            s += '        <tie type="stop"/>\n'
        if e.tie_start:
            s += '        <tie type="start"/>\n'
        s += "        <voice>1</voice>\n"
        s += f"        <type>{TYPE_NAME[e.base]}</type>\n"
        s += "        <dot/>\n" * e.dots
        # 临时记号
        key = (p.step, p.octave)
        cur = acc_state.get(key, KEY_ALTER.get(p.step, 0))
        if p.alter != cur and not e.tie_stop:
            s += "        <accidental>{}</accidental>\n".format(
                {1: "sharp", -1: "flat", 0: "natural", 2: "double-sharp", -2: "flat-flat"}[p.alter])
        acc_state[key] = p.alter
        if pi == 0 and id(e) in beams:
            for lvl, b in enumerate(beams[id(e)], start=1):
                s += f'        <beam number="{lvl}">{b}</beam>\n'
        nots = []
        if e.tie_stop:
            nots.append('<tied type="stop"/>')
        if e.tie_start:
            nots.append('<tied type="start"/>')
        if pi == 0:
            for _ in range(e.slur_stop):
                nots.append('<slur type="stop" number="1"/>')
            for _ in range(e.slur_start):
                nots.append('<slur type="start" number="1"/>')
            if e.fermata:
                nots.append('<fermata type="upright"/>')
            arts = []
            for a in e.artic:
                arts.append({"--": "<tenuto/>", "-.": "<staccato/>", "->": "<accent/>"}[a])
            if arts:
                nots.append("<articulations>" + "".join(arts) + "</articulations>")
        if nots:
            s += "        <notations>\n" + "".join(f"          {n}\n" for n in nots) + "        </notations>\n"
        if pi == 0 and e.lyric:
            s += (f'        <lyric number="1" default-y="-94">\n          <syllabic>single</syllabic>\n'
                  f"          <text>{x(e.lyric)}</text>\n        </lyric>\n")
        s += "      </note>\n"
        out.append(s)
    return out


def credit(page, text, xx, yy, size, justify="center", valign="top", bold=False, italic=False,
           family=CJK, ctype=None, spacing=None):
    s = f'  <credit page="{page}">\n'
    if ctype:
        s += f"    <credit-type>{ctype}</credit-type>\n"
    attrs = (f'default-x="{xx}" default-y="{yy}" justify="{justify}" valign="{valign}" '
             f'font-family="{family}" font-size="{size}"')
    if bold:
        attrs += ' font-weight="bold"'
    if italic:
        attrs += ' font-style="italic"'
    if spacing:
        attrs += f' letter-spacing="{spacing}"'
    s += f"    <credit-words {attrs}>{x(text)}</credit-words>\n  </credit>\n"
    return s


def build(parts, date="2026-09-28"):
    cx = round(PAGE_W / 2, 1)
    right = round(PAGE_W - MARGIN_R, 1)
    top = PAGE_H - MARGIN_T
    n_pages = len(SD.PAGE_STARTS)

    head = f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <work>
    <work-title>{x(SD.TITLE)}</work-title>
  </work>
  <movement-title>{x(SD.TITLE)}</movement-title>
  <identification>
    <creator type="composer">{x(SD.COMPOSER)}</creator>
    <creator type="lyricist">{x(SD.LYRICIST)}</creator>
    <creator type="arranger">{x(SD.ARRANGER)}</creator>
    <rights>编配 · 制谱：{x(SD.ARRANGER)}　｜　原唱 · 词曲：{x(SD.SINGER)}</rights>
    <encoding>
      <encoder>{x(SD.ENGRAVER)}</encoder>
      <encoding-date>{date}</encoding-date>
      <software>LilyPond 2.24 / Python（同源生成）</software>
      <supports element="accidental" type="yes"/>
      <supports element="beam" type="yes"/>
      <supports element="stem" type="no"/>
      <supports attribute="new-system" element="print" type="yes" value="yes"/>
      <supports attribute="new-page" element="print" type="yes" value="yes"/>
    </encoding>
    <miscellaneous>
      <miscellaneous-field name="engraver">{x(SD.ENGRAVER)}</miscellaneous-field>
      <miscellaneous-field name="singer">{x(SD.SINGER)}</miscellaneous-field>
    </miscellaneous>
  </identification>
  <defaults>
    <scaling>
      <millimeters>{MM_PER_STAFF}</millimeters>
      <tenths>{TENTHS}</tenths>
    </scaling>
    <page-layout>
      <page-height>{PAGE_H}</page-height>
      <page-width>{PAGE_W}</page-width>
      <page-margins type="both">
        <left-margin>{MARGIN_L}</left-margin>
        <right-margin>{MARGIN_R}</right-margin>
        <top-margin>{MARGIN_T}</top-margin>
        <bottom-margin>{MARGIN_B}</bottom-margin>
      </page-margins>
    </page-layout>
    <system-layout>
      <system-margins>
        <left-margin>{t(11)}</left-margin>
        <right-margin>0</right-margin>
      </system-margins>
      <system-distance>{t(30)}</system-distance>
      <top-system-distance>{t(14)}</top-system-distance>
      <system-dividers>
        <left-divider print-object="yes" halign="left" valign="bottom"/>
        <right-divider print-object="no"/>
      </system-dividers>
    </system-layout>
    <staff-layout>
      <staff-distance>{t(11)}</staff-distance>
    </staff-layout>
    <word-font font-family="{LATIN}" font-size="10"/>
    <lyric-font font-family="{CJK}" font-size="11"/>
  </defaults>
'''
    cr = ""
    cr += credit(1, "F U L L    S C O R E", cx, top, 8.5, family=LATIN)
    cr += credit(1, " ".join(SD.TITLE), cx, round(top - t(8), 1), 25, bold=True, ctype="title")
    cr += credit(1, SD.SUBTITLE_EN, cx, round(top - t(21), 1), 12.5, italic=True, family=LATIN, ctype="subtitle")
    cr += credit(1, SD.SUBTITLE_ZH, cx, round(top - t(27), 1), 10, ctype="subtitle")
    cr += credit(1, f"原唱　{SD.SINGER}", MARGIN_L, round(top - t(38), 1), 10.5, justify="left")
    cr += credit(1, f"词曲　{SD.LYRICIST}", right, round(top - t(38), 1), 10.5, justify="right", ctype="composer")
    cr += credit(1, f"编配　{SD.ARRANGER}", right, round(top - t(44), 1), 11.5, justify="right", bold=True, ctype="arranger")
    cr += credit(1, f"制谱　{SD.ENGRAVER}", right, round(top - t(50), 1), 11.5, justify="right", bold=True)
    for pg in range(1, n_pages + 1):
        cr += credit(pg, f"原唱 · 词曲　{SD.SINGER}　　｜　　编配 · 制谱　{SD.ARRANGER}",
                     cx, round(t(11), 1), 8, valign="bottom", ctype="rights" if pg == 1 else None)
        if pg > 1:
            cr += credit(pg, f"{SD.TITLE}   ·   Full Score", cx, top, 8.5, family=CJK)

    pl = "  <part-list>\n"
    for i, p in enumerate(parts):
        if p["key"] == "vn1":
            pl += ('    <part-group type="start" number="1">\n      <group-symbol>bracket</group-symbol>\n'
                   '      <group-barline>yes</group-barline>\n    </part-group>\n')
        pan = round((p["pan"] - 64) / 64 * 90)
        pl += f'''    <score-part id="{p["id"]}">
      <part-name>{x(p["name"])}</part-name>
      <part-abbreviation>{x(p["abbr"])}</part-abbreviation>
      <score-instrument id="{p["id"]}-I1">
        <instrument-name>{x(p["name"])}</instrument-name>
        <instrument-sound>{p["sound"]}</instrument-sound>
      </score-instrument>
      <midi-instrument id="{p["id"]}-I1">
        <midi-channel>{p["channel"] + 1}</midi-channel>
        <midi-program>{p["program"] + 1}</midi-program>
        <volume>80</volume>
        <pan>{pan}</pan>
      </midi-instrument>
    </score-part>
'''
    pl += '    <part-group type="stop" number="1"/>\n  </part-list>\n'

    body = ""
    for p in parts:
        body += f'  <part id="{p["id"]}">\n'
        is_top = p["key"] == "voice"
        dyn_place = "above" if is_top else "below"
        open_wedge = False
        for b in range(1, SD.N_BARS + 1):
            evs = model.display_bar([e for e in p["events"] if e.bar == b])
            body += f'    <measure number="{b}">\n'
            # 分行 / 分页
            if b == 1 or b in SD.SYSTEM_STARTS:
                attr = ""
                if b in SD.PAGE_STARTS and b > 1:
                    attr = ' new-page="yes"'
                elif b > 1:
                    attr = ' new-system="yes"'
                pr = f"      <print{attr}>\n"
                if is_top:
                    left = t(24) if b == 1 else t(11)
                    pr += (f"        <system-layout>\n          <system-margins>\n"
                           f"            <left-margin>{left}</left-margin>\n"
                           f"            <right-margin>0</right-margin>\n          </system-margins>\n")
                    if b == 1:
                        pr += f"          <top-system-distance>{t(68)}</top-system-distance>\n"
                    elif b in SD.PAGE_STARTS:
                        pr += f"          <top-system-distance>{t(14)}</top-system-distance>\n"
                    else:
                        pr += f"          <system-distance>{t(30)}</system-distance>\n"
                    pr += "        </system-layout>\n"
                else:
                    dist = t(19) if p["key"] == "vn1" else t(11)
                    pr += (f"        <staff-layout>\n          <staff-distance>{dist}</staff-distance>\n"
                           f"        </staff-layout>\n")
                pr += "      </print>\n"
                body += pr
            if b == 1:
                cs, cl = CLEF[p["clef"]]
                body += (f"      <attributes>\n        <divisions>{DIV}</divisions>\n"
                         f"        <key>\n          <fifths>1</fifths>\n          <mode>minor</mode>\n        </key>\n"
                         f"        <time>\n          <beats>4</beats>\n          <beat-type>4</beat-type>\n        </time>\n"
                         f"        <clef>\n          <sign>{cs}</sign>\n          <line>{cl}</line>\n        </clef>\n"
                         f"      </attributes>\n")
            if is_top and b == 1:
                body += direction(
                    f'        <direction-type><words font-family="{LATIN}" font-weight="bold" font-size="12">'
                    f"{x(SD.TEMPO_TEXT)}</words></direction-type>\n"
                    f'        <direction-type><metronome parentheses="yes"><beat-unit>quarter</beat-unit>'
                    f"<per-minute>{SD.BPM}</per-minute></metronome></direction-type>\n",
                    "above", sound=f'<sound tempo="{SD.BPM}"/>', system="only-top")
            if is_top and b in SD.REHEARSAL:
                body += direction(
                    f'        <direction-type><rehearsal enclosure="square" font-weight="bold" font-size="14">'
                    f"{SD.REHEARSAL[b]}</rehearsal></direction-type>\n", "above", system="only-top")
            if is_top and b in SD.TEXT_MARKS:
                body += words(SD.TEXT_MARKS[b], "above", size=11, system="only-top")
            beams = compute_beams(evs, 1 if is_top else 2)
            acc_state = {}
            for e in evs:
                if (e.hairpin_end or e.dyn or e.hairpin) and open_wedge:
                    body += direction('        <direction-type><wedge type="stop" number="1"/></direction-type>\n',
                                      dyn_place)
                    open_wedge = False
                if e.dyn:
                    body += direction(
                        f"        <direction-type><dynamics><{e.dyn}/></dynamics></direction-type>\n",
                        dyn_place, sound=f'<sound dynamics="{DYN_SOUND[e.dyn]}"/>')
                if e.hairpin:
                    wt = "crescendo" if e.hairpin == "<" else "diminuendo"
                    body += direction(f'        <direction-type><wedge type="{wt}" number="1"/></direction-type>\n',
                                      dyn_place)
                    open_wedge = True
                for pl_, txt in e.texts:
                    body += words(txt, "above" if pl_ == "^" else "below")
                for s in note_xml(e, p, beams, acc_state):
                    body += s
            # 下一小节第一拍有新力度/发夹/\! 时，发夹收在本小节线（= LilyPond Hairpin.to-barline）
            nxt = next((e for e in p["events"] if e.bar == b + 1), None)
            if open_wedge and nxt is not None and (nxt.dyn or nxt.hairpin or nxt.hairpin_end):
                body += direction('        <direction-type><wedge type="stop" number="1"/></direction-type>\n',
                                  dyn_place)
                open_wedge = False
            if b in SD.DOUBLE_BAR_AFTER:
                body += '      <barline location="right">\n        <bar-style>light-light</bar-style>\n      </barline>\n'
            if b == SD.N_BARS:
                body += '      <barline location="right">\n        <bar-style>light-heavy</bar-style>\n      </barline>\n'
            body += "    </measure>\n"
        assert not open_wedge, f"{p['name']}: hairpin never closed"
        body += "  </part>\n"
    return head + cr + pl + body + "</score-partwise>\n"
