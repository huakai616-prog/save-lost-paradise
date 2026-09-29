# -*- coding: utf-8 -*-
"""事件模型 → LilyPond 源文件（出版级总谱排版）。"""
import os

import model
import score_data as SD

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

CJK = "Noto Serif CJK SC"
CJK_BOLD = "Noto Serif CJK SC Bold"
LATIN = "EB Garamond"
LATIN_IT = "EB Garamond Italic"


def spaced(s, sep=" "):
    return sep.join(s)


def ev_to_ly(e):
    if e.kind == "mrest":
        out = "R1"
    elif e.kind == "rest":
        out = "r" + e.lily_dur()
    else:
        if len(e.pitches) == 1:
            out = e.pitches[0].name + e.lily_dur()
        else:
            out = "<" + " ".join(p.name for p in e.pitches) + ">" + e.lily_dur()
    post = ""
    if e.tie_start:
        post += "~"
    post += ")" * e.slur_stop
    if e.dyn:
        post += "\\" + e.dyn
    if e.hairpin_end:
        post += "\\!"
    if e.hairpin:
        post += "\\" + e.hairpin
    for pl, t in e.texts:
        post += f'{pl}\\markup \\italic "{t}"'
    if e.fermata:
        post += "\\fermata"
    post += "(" * e.slur_start
    return out + post


def part_music(events):
    lines = []
    for evs in model.bars_of(events):
        body = " ".join(ev_to_ly(e) for e in model.display_bar(evs))
        lines.append(f"  {body} |  % {evs[0].bar}")
    return "\n".join(lines)


def marks_track():
    out = []
    for b in range(1, SD.N_BARS + 1):
        pre = []
        if b in SD.SYSTEM_STARTS and b > 1:
            pre.append("\\pageBreak" if b in SD.PAGE_STARTS else "\\break")
        if b == 1:
            pre.append(f'\\tempo \\markup {{ \\abs-fontsize #12.5 \\bold "{SD.TEMPO_TEXT}" }} 4 = {SD.BPM}')
        if b in SD.REHEARSAL:
            pre.append("\\mark \\default")
        spacer = "s1"
        if b in SD.TEXT_MARKS:
            spacer += f'^\\markup {{ \\abs-fontsize #11 \\italic "{SD.TEXT_MARKS[b]}" }}'
        post = []
        if b in SD.DOUBLE_BAR_AFTER:
            post.append('\\bar "||"')
        if b == SD.N_BARS:
            post.append('\\bar "|."')
        out.append("  " + " ".join(pre + [spacer] + post) + f"  % {b}")
    return "\n".join(out)


def title_markup():
    return rf'''
\markup {{
  \column {{
    \fill-line {{
      \override #'(font-name . "{LATIN}") \abs-fontsize #8.5 \concat {{ "F U L L    S C O R E" }}
    }}
    \vspace #0.9
    \fill-line {{
      \override #'(font-name . "{CJK_BOLD}") \abs-fontsize #25 "{spaced(SD.TITLE)}"
    }}
    \vspace #0.7
    \fill-line {{
      \override #'(font-name . "{LATIN_IT}") \abs-fontsize #12.5 "{SD.SUBTITLE_EN}"
    }}
    \vspace #0.25
    \fill-line {{
      \override #'(font-name . "{CJK}") \abs-fontsize #10 "{SD.SUBTITLE_ZH}"
    }}
    \vspace #1.6
    \fill-line {{
      \override #'(font-name . "{CJK}") \abs-fontsize #10.5
      \column {{
        \line {{ "原唱　{SD.SINGER}" }}
      }}
      \override #'(font-name . "{CJK}") \abs-fontsize #10.5
      \right-column {{
        "词曲　{SD.LYRICIST}"
        \vspace #0.1
        \override #'(font-name . "{CJK_BOLD}") \abs-fontsize #11.5 "编配　{SD.ARRANGER}"
        \vspace #0.1
        \override #'(font-name . "{CJK_BOLD}") \abs-fontsize #11.5 "制谱　{SD.ENGRAVER}"
      }}
    }}
    \vspace #0.4
  }}
}}
'''


def build(parts, lyrics):
    by = {p["key"]: p for p in parts}
    head_title = ("\\concat { \\override #'(font-name . \"" + CJK + "\") \"" + SD.TITLE + "\" "
                  "\\override #'(font-name . \"" + LATIN_IT + "\") \"   ·   Full Score\" }")
    footer = ("\\override #'(font-name . \"" + CJK + "\") \\abs-fontsize #8 "
              "\\concat { \"编配 · 制谱　\" \\override #'(font-name . \"" + CJK_BOLD + "\") \"" + SD.ARRANGER + "\" "
              "\"　　｜　　原唱 · 词曲　" + SD.SINGER + "\" }")
    ly = rf'''\version "2.24.3"
#(ly:font-config-add-directory "{FONT_DIR}")
% 《{SD.TITLE}》 人声与弦乐四重奏 —— 编配 / 制谱：{SD.ARRANGER}
% 本文件由 src/build.py 自动生成，请修改 src/score_data.py 后重新生成。

#(set-global-staff-size 19)

\paper {{
  #(set-paper-size "a4")
  top-margin = 12\mm
  bottom-margin = 11\mm
  left-margin = 17\mm
  right-margin = 14\mm
  indent = 24\mm
  short-indent = 11\mm
  #(define fonts (set-global-fonts #:roman "{LATIN}, {CJK}" #:sans "{LATIN}, {CJK}" #:factor (/ staff-height pt 20)))
  ragged-last-bottom = ##f
  ragged-bottom = ##f
  system-separator-markup = \markup \center-align \vcenter \combine \beam #2.4 #0.5 #0.34 \raise #1.25 \beam #2.4 #0.5 #0.34
  markup-system-spacing = #'((basic-distance . 10) (minimum-distance . 6) (padding . 3) (stretchability . 12))
  system-system-spacing = #'((basic-distance . 22) (minimum-distance . 16) (padding . 8) (stretchability . 25))
  top-system-spacing = #'((basic-distance . 6) (minimum-distance . 2) (padding . 2))
  last-bottom-spacing = #'((basic-distance . 6) (minimum-distance . 2) (padding . 2) (stretchability . 30))
  print-first-page-number = ##f
  oddHeaderMarkup = \markup \fill-line {{
    \null
    \unless \on-first-page \abs-fontsize #8.5 {head_title}
    \unless \on-first-page \override #'(font-name . "{LATIN}") \abs-fontsize #11 \fromproperty #'page:page-number-string
  }}
  evenHeaderMarkup = \markup \fill-line {{
    \unless \on-first-page \override #'(font-name . "{LATIN}") \abs-fontsize #11 \fromproperty #'page:page-number-string
    \unless \on-first-page \abs-fontsize #8.5 {head_title}
    \null
  }}
  oddFooterMarkup = \markup \fill-line {{ {footer} }}
  evenFooterMarkup = \markup \fill-line {{ {footer} }}
}}

\header {{
  tagline = ##f
}}

global = {{
  \key e \minor
  \numericTimeSignature
  \time 4/4
}}

marks = {{
{marks_track()}
}}

voiceMusic = {{
{part_music(by["voice"]["events"])}
}}

lyricText = \lyricmode {{
  {" ".join(lyrics)}
}}

violinOne = {{
{part_music(by["vn1"]["events"])}
}}

violinTwo = {{
{part_music(by["vn2"]["events"])}
}}

viola = {{
{part_music(by["va"]["events"])}
}}

cello = {{
{part_music(by["vc"]["events"])}
}}

{title_markup()}

\score {{
  <<
    \new Staff = "voice" \with {{
      instrumentName = "Voice"
      shortInstrumentName = "V."
    }} <<
      \marks
      \new Voice = "vox" {{
        \global
        \set Staff.beamExceptions = #'()
        \set Staff.baseMoment = #(ly:make-moment 1/4)
        \set Staff.beatStructure = 1,1,1,1
        \dynamicUp \voiceMusic
      }}
    >>
    \new Lyrics \lyricsto "vox" \lyricText
    \new StaffGroup <<
      \new Staff \with {{ instrumentName = "Violin I" shortInstrumentName = "Vln. I" }}
        {{ \global \violinOne }}
      \new Staff \with {{ instrumentName = "Violin II" shortInstrumentName = "Vln. II" }}
        {{ \global \violinTwo }}
      \new Staff \with {{ instrumentName = "Viola" shortInstrumentName = "Vla." }}
        {{ \global \clef alto \viola }}
      \new Staff \with {{ instrumentName = "Violoncello" shortInstrumentName = "Vc." }}
        {{ \global \clef bass \cello }}
    >>
  >>
  \layout {{
    \context {{
      \Score
      \override NonMusicalPaperColumn.line-break-permission = ##f
      \override NonMusicalPaperColumn.page-break-permission = ##f
      rehearsalMarkFormatter = #format-mark-box-alphabet
      \override RehearsalMark.font-size = #2.2
      \override RehearsalMark.font-series = #'bold
      \override RehearsalMark.padding = #1.2
      \override RehearsalMark.outside-staff-horizontal-padding = #1.5
      \override RehearsalMark.break-align-symbols = #'(staff-bar clef)
      \override RehearsalMark.self-alignment-X = #CENTER
      \override BarNumber.font-shape = #'italic
      \override BarNumber.font-size = #0.5
      \override BarNumber.font-features = #'("lnum")
      \override MetronomeMark.font-features = #'("lnum")
      \override MetronomeMark.font-size = #1.5
      \override BarNumber.padding = #2.5
      \override MetronomeMark.padding = #2.5
      \override SpacingSpanner.base-shortest-duration = #(ly:make-moment 1/16)
      \override TextScript.font-shape = #'italic
      \override Hairpin.minimum-length = #4
    }}
    \context {{
      \Staff
      \override InstrumentName.font-size = #1.6
      \override InstrumentName.padding = #1.2
      \override TextScript.padding = #1.0
      \override DynamicLineSpanner.padding = #1.2
    }}
    \context {{
      \Lyrics
      \override LyricText.font-name = "{CJK}"
      \override LyricText.font-size = #0.4
      \override VerticalAxisGroup.nonstaff-relatedstaff-spacing.padding = #1.4
      \override VerticalAxisGroup.nonstaff-unrelatedstaff-spacing.padding = #2.6
      \override LyricSpace.minimum-distance = #1.1
    }}
    \context {{
      \StaffGroup
      \override StaffGrouper.staff-staff-spacing = #'((basic-distance . 12) (minimum-distance . 9) (padding . 2.5) (stretchability . 40))
    }}
  }}
}}
'''
    return ly
