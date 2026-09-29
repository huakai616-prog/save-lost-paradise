# -*- coding: utf-8 -*-
"""封面 + 说明页（HTML → Chromium 打印 PDF）。"""
import math
import os
import subprocess

import score_data as SD

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

INK = "#1b2130"
GOLD = "#9a7a43"
GOLD_SOFT = "#b99a62"
PAPER = "#f6f1e7"
MUTED = "#5d6270"


def feather_svg():
    """细线羽毛：主羽轴 + 羽枝，右侧羽片有两处裂口（受了伤的翅膀）。"""
    L = 118.0                      # 羽毛长度（mm，坐标单位）
    parts = []

    def shaft(t):                  # t ∈ [0,1]，0 = 羽根，1 = 羽尖
        y = -L * t
        xx = 5.5 * math.sin(math.pi * t * 0.9) * (1 - 0.35 * t)
        return xx, y

    def half_width(t):             # 羽片半宽：中段最宽，尖端收拢
        if t < 0.16:
            return 0.0
        u = (t - 0.16) / 0.84
        return 17.0 * math.sin(math.pi * min(1.0, u * 1.05) ** 0.85) * (1 - 0.25 * u)

    # 主羽轴
    pts = [shaft(i / 120) for i in range(121)]
    d = "M " + " L ".join(f"{a:.2f},{b:.2f}" for a, b in pts)
    parts.append(f'<path d="{d}" stroke="{GOLD}" stroke-width="0.55" fill="none" stroke-linecap="round"/>')
    # 羽根下端的空心羽管
    parts.append(f'<path d="M 0,0 L -0.6,9" stroke="{GOLD}" stroke-width="0.9" fill="none" stroke-linecap="round"/>')

    # 羽枝
    wounds_right = [(0.47, 0.515), (0.64, 0.665)]   # 裂口区间
    n = 92
    for side in (-1, 1):
        for i in range(n):
            t = 0.17 + 0.8 * i / n
            w = half_width(t)
            if w <= 0.4:
                continue
            sx, sy = shaft(t)
            ang = math.radians(58 if side < 0 else 54)
            reach = w
            # 裂口：羽枝向外张开并留出空隙
            skip = False
            spread = 0.0
            if side > 0:
                for a, b in wounds_right:
                    if a <= t <= b:
                        skip = (t - a) < (b - a) * 0.55
                        spread = 7.0
            if skip:
                continue
            ang2 = ang + math.radians(spread)
            ex = sx + side * reach * math.sin(ang2)
            ey = sy - reach * math.cos(ang2)
            # 稍带弧度
            cx_ = sx + side * reach * 0.55 * math.sin(ang2 - 0.18)
            cy_ = sy - reach * 0.55 * math.cos(ang2 - 0.18) - 0.6
            op = 0.55 + 0.35 * math.sin(math.pi * (i / n))
            parts.append(
                f'<path d="M {sx:.2f},{sy:.2f} Q {cx_:.2f},{cy_:.2f} {ex:.2f},{ey:.2f}" '
                f'stroke="{GOLD_SOFT}" stroke-width="0.22" fill="none" opacity="{op:.2f}" stroke-linecap="round"/>')
    # 羽根处的绒羽（细、短、柔）
    for k in range(6):
        t = 0.06 + 0.014 * k
        sx, sy = shaft(t)
        for side in (-1, 1):
            ln = 2.0 + 1.4 * math.sin(math.pi * k / 6)
            ex = sx + side * ln * 0.92
            ey = sy - ln * 0.55
            parts.append(
                f'<path d="M {sx:.2f},{sy:.2f} Q {sx + side * ln * 0.35:.2f},{sy - 0.2:.2f} {ex:.2f},{ey:.2f}" '
                f'stroke="{GOLD_SOFT}" stroke-width="0.16" fill="none" opacity="0.30" stroke-linecap="round"/>')
    body = "\n".join(parts)
    return (f'<svg viewBox="-40 -128 80 140" width="70mm" height="122.5mm" xmlns="http://www.w3.org/2000/svg">'
            f'<g transform="rotate(-24 0 -60)">{body}</g></svg>')


def _face(file, weight, style):
    return (f'@font-face {{ font-family: "EB Garamond"; src: url("file://{FONT_DIR}/{file}"); '
            f'font-weight: {weight}; font-style: {style}; }}')


FACES = "\n".join([_face("EBGaramond-Regular.ttf", 400, "normal"), _face("EBGaramond-Italic.ttf", 400, "italic"),
                   _face("EBGaramond-SemiBold.ttf", 600, "normal"), _face("EBGaramond-Bold.ttf", 700, "normal"),
                   _face("EBGaramond-SemiBoldItalic.ttf", 600, "italic")])

BASE_CSS = FACES + f"""
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 210mm; height: 297mm; }}
body {{ font-family: "EB Garamond", "Noto Serif CJK SC", serif; color: {INK};
       font-variant-numeric: lining-nums;
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.cjk {{ font-family: "EB Garamond", "Noto Serif CJK SC", serif; }}
"""


def cover_html():
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>{SD.TITLE}</title>
<style>
{BASE_CSS}
body {{ background: {PAPER}; }}
.page {{ position: relative; width: 210mm; height: 297mm; overflow: hidden; }}
.frame {{ position: absolute; inset: 11mm; border: 0.35mm solid {GOLD}; }}
.frame::after {{ content: ""; position: absolute; inset: 1.6mm; border: 0.15mm solid {GOLD_SOFT}; }}
.corner {{ position: absolute; width: 5mm; height: 5mm; border-color: {GOLD}; border-style: solid; }}
.top {{ position: absolute; top: 27mm; width: 100%; text-align: center; }}
.eyebrow {{ font-size: 9.5pt; letter-spacing: 0.55em; color: {GOLD}; padding-left: 0.55em; }}
.eyebrow-zh {{ margin-top: 2.2mm; font-size: 9pt; letter-spacing: 1.2em; color: {GOLD}; padding-left: 1.2em; }}
.feather {{ position: absolute; top: 44mm; left: 0; width: 100%; display: flex; justify-content: center; }}
.titleblock {{ position: absolute; top: 170mm; width: 100%; text-align: center; }}
h1 {{ font-family: "Noto Serif CJK SC", serif; font-weight: 700; font-size: 38pt;
      letter-spacing: 0.2em; padding-left: 0.2em; line-height: 1.1; color: {INK}; }}
.sub-en {{ margin-top: 7mm; font-style: italic; font-size: 15pt; letter-spacing: 0.02em; }}
.sub-zh {{ margin-top: 2mm; font-size: 10.5pt; letter-spacing: 0.35em; padding-left: 0.35em; color: {MUTED}; }}
.rule {{ margin: 9mm auto 0; width: 64mm; display: flex; align-items: center; gap: 3mm; }}
.rule span {{ flex: 1; height: 0.25mm; background: {GOLD}; }}
.rule i {{ width: 2.2mm; height: 2.2mm; transform: rotate(45deg); border: 0.3mm solid {GOLD}; }}
.credits {{ position: absolute; top: 224mm; width: 100%; text-align: center; }}
.orig {{ font-size: 10.5pt; color: {MUTED}; letter-spacing: 0.12em; }}
.orig b {{ font-weight: 400; color: {INK}; }}
.dot {{ color: {GOLD}; margin: 0 3.2mm; }}
.arr {{ margin-top: 8mm; display: inline-grid; grid-template-columns: auto auto; column-gap: 7mm; row-gap: 3.6mm;
        align-items: center; }}
.arr .k {{ font-size: 11pt; color: {GOLD}; letter-spacing: 0.5em; text-align: right; }}
.arr .v {{ font-family: "Noto Serif CJK SC", serif; font-weight: 700; font-size: 19pt; letter-spacing: 0.3em;
           text-align: left; }}
.arr .k .zh {{ margin-right: -0.5em; }}
.arr .k .en {{ display: block; font-family: "EB Garamond", serif; font-style: italic; font-size: 8.5pt;
               letter-spacing: 0.06em; color: {MUTED}; margin-top: 0.8mm; }}
.foot {{ position: absolute; bottom: 21mm; width: 100%; text-align: center; font-size: 9.5pt; font-style: italic;
         color: {MUTED}; letter-spacing: 0.05em; }}
</style></head><body><div class="page">
  <div class="frame"></div>
  <div class="top">
    <div class="eyebrow">FULL SCORE</div>
    <div class="eyebrow-zh cjk">总谱</div>
  </div>
  <div class="feather">{feather_svg()}</div>
  <div class="titleblock">
    <h1>{SD.TITLE}</h1>
    <div class="sub-en">{SD.SUBTITLE_EN}</div>
    <div class="sub-zh cjk">{SD.SUBTITLE_ZH}</div>
    <div class="rule"><span></span><i></i><span></span></div>
  </div>
  <div class="credits">
    <div class="orig cjk">原唱　<b>{SD.SINGER}</b><span class="dot">·</span>词曲　<b>{SD.LYRICIST}</b></div>
    <div class="arr cjk">
      <div class="k"><span class="zh">编配</span><span class="en">Arranged by</span></div><div class="v">{SD.ARRANGER}</div>
      <div class="k"><span class="zh">制谱</span><span class="en">Engraved by</span></div><div class="v">{SD.ENGRAVER}</div>
    </div>
  </div>
  <div class="foot">{SD.TEMPO_TEXT} &nbsp;·&nbsp; ♩ = {SD.BPM} &nbsp;·&nbsp; ca. 1′50″</div>
</div></body></html>"""


def notes_html():
    rows = [
        ("人声（女声）", "Voice (female)"),
        ("第一小提琴", "Violin I"),
        ("第二小提琴", "Violin II"),
        ("中提琴", "Viola"),
        ("大提琴", "Violoncello"),
    ]
    inst = "".join(f'<tr><td class="cjk">{a}</td><td class="en">{b}</td></tr>' for a, b in rows)
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>{SD.TITLE} — Notes</title>
<style>
{BASE_CSS}
body {{ background: #ffffff; }}
.page {{ position: relative; width: 210mm; height: 297mm; padding: 24mm 28mm 20mm; }}
.head {{ text-align: center; }}
.head .t {{ font-family: "Noto Serif CJK SC", serif; font-weight: 700; font-size: 17pt; letter-spacing: 0.2em;
            padding-left: 0.2em; }}
.head .s {{ margin-top: 2mm; font-style: italic; font-size: 11pt; color: {MUTED}; }}
.rule {{ margin: 6mm auto 6mm; width: 40mm; display: flex; align-items: center; gap: 2.5mm; }}
.rule span {{ flex: 1; height: 0.2mm; background: {GOLD}; }}
.rule i {{ width: 1.6mm; height: 1.6mm; transform: rotate(45deg); border: 0.25mm solid {GOLD}; }}
h2 {{ font-weight: 400; font-size: 9pt; letter-spacing: 0.4em; color: {GOLD}; margin: 7.5mm 0 3mm;
      display: flex; gap: 3mm; align-items: baseline; }}
h2 .zh {{ font-family: "Noto Serif CJK SC", serif; letter-spacing: 0.3em; color: {INK}; font-size: 10.5pt; }}
table {{ border-collapse: collapse; width: 100%; font-size: 11pt; }}
td {{ padding: 1.3mm 0; border-bottom: 0.15mm solid #e4dccb; }}
td.en {{ text-align: right; font-style: italic; }}
.grid {{ display: grid; grid-template-columns: 30mm 1fr; row-gap: 2.6mm; font-size: 10.5pt; line-height: 1.55; }}
.grid .k {{ color: {MUTED}; }}
ul {{ list-style: none; font-size: 10pt; line-height: 1.6; }}
li {{ padding-left: 5mm; position: relative; margin-bottom: 1.6mm; }}
li::before {{ content: ""; position: absolute; left: 0; top: 2.6mm; width: 1.4mm; height: 1.4mm;
              transform: rotate(45deg); background: {GOLD_SOFT}; }}
li .en {{ display: block; font-family: "EB Garamond", serif; font-style: italic; color: {MUTED}; font-size: 10.5pt;
          line-height: 1.4; }}
ul, .grid {{ text-wrap: pretty; }}
.nw {{ white-space: nowrap; }}
.credits {{ position: absolute; bottom: 16mm; left: 28mm; right: 28mm; border-top: 0.2mm solid {GOLD};
            padding-top: 5mm; display: flex; justify-content: space-between; font-size: 10pt; }}
.credits b {{ font-family: "Noto Serif CJK SC", serif; font-weight: 700; letter-spacing: 0.15em; }}
.credits .muted {{ color: {MUTED}; }}
</style></head><body><div class="page">
  <div class="head">
    <div class="t">{SD.TITLE}</div>
    <div class="s">{SD.SUBTITLE_EN}</div>
  </div>
  <div class="rule"><span></span><i></i><span></span></div>

  <h2>INSTRUMENTATION <span class="zh">编制</span></h2>
  <table>{inst}</table>

  <h2>AT A GLANCE <span class="zh">概要</span></h2>
  <div class="grid cjk">
    <div class="k">速度</div><div><i style="font-family:'EB Garamond'">{SD.TEMPO_TEXT}</i>，♩ = {SD.BPM}</div>
    <div class="k">调性</div><div>e 小调（原曲简谱 1 = G）</div>
    <div class="k">人声音域</div><div>B3 – B4（女声实际音高，do = G3；主要音区 E4 – A4）</div>
    <div class="k">时长</div><div>约 1 分 50 秒</div>
    <div class="k">结构</div><div>前奏（<span class="nw">第 1–9 小节</span>）→ 副歌 A · B · C（<span class="nw">第 10–29 小节</span>）<span class="nw">→ 尾奏 D（第 30–35 小节）</span></div>
  </div>

  <h2>PERFORMANCE NOTES <span class="zh">演奏提示</span></h2>
  <ul class="cjk">
    <li>总谱为实际音高（Score in C），人声按女声实际音高记谱。
      <span class="en">Score in C. The voice is notated at sounding pitch.</span></li>
    <li>前奏与尾奏取自原曲引子主题：前奏先由大提琴、再由第一小提琴奏出，尾奏则反之。
      <span class="en">The intro and coda quote the song’s original hook — cello then Violin I in the intro, the reverse in the coda.</span></li>
    <li>弦乐始终以连贯、歌唱的线条为主，力度宁弱勿强，把空间留给人声；C 段高潮亦勿过响。
      <span class="en">Sempre cantabile; keep the strings beneath the voice. Even the climax at C should never cover the singer.</span></li>
    <li>中提琴的八分音符分解和弦请连贯演奏，像呼吸一样起伏。
      <span class="en">Viola arpeggios: legato, breathing with the phrase.</span></li>
    <li>前奏铺底以 sul tasto 奏出，第 6 小节回到 ord.；第 28 小节 poco allarg.，<span class="nw">第 30 小节 a tempo。</span>
      <span class="en">Intro pad sul tasto, ord. from bar 6; poco allarg. for the last vocal line (bar 28), a tempo at bar 30.</span></li>
    <li>第 34 小节渐慢，末小节 morendo，渐弱至无声。
      <span class="en">Rit. in bar 34; the final chord dies away (morendo) to nothing.</span></li>
  </ul>

  <div class="credits cjk">
    <div class="muted">原唱 · 词曲　{SD.SINGER}</div>
    <div>编配 · 制谱　<b>{SD.ARRANGER}</b></div>
  </div>
</div></body></html>"""


def print_pdf(html_path, pdf_path):
    subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    "--run-all-compositor-stages-before-draw", "--virtual-time-budget=4000",
                    f"--print-to-pdf={pdf_path}", f"file://{html_path}"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
