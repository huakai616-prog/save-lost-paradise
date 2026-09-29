\version "2.24.3"
#(ly:font-config-add-directory "/home/user/save-lost-paradise/arrangements/meng-de-chibang/src/fonts")
% 《梦的翅膀受了伤》 人声与弦乐四重奏 —— 编配 / 制谱：花开富贵
% 本文件由 src/build.py 自动生成，请修改 src/score_data.py 后重新生成。

#(set-global-staff-size 19)

\paper {
  #(set-paper-size "a4")
  top-margin = 12\mm
  bottom-margin = 11\mm
  left-margin = 17\mm
  right-margin = 14\mm
  indent = 24\mm
  short-indent = 11\mm
  #(define fonts (set-global-fonts #:roman "EB Garamond, Noto Serif CJK SC" #:sans "EB Garamond, Noto Serif CJK SC" #:factor (/ staff-height pt 20)))
  ragged-last-bottom = ##f
  ragged-bottom = ##f
  system-separator-markup = \markup \center-align \vcenter \combine \beam #2.4 #0.5 #0.34 \raise #1.25 \beam #2.4 #0.5 #0.34
  markup-system-spacing = #'((basic-distance . 10) (minimum-distance . 6) (padding . 3) (stretchability . 12))
  system-system-spacing = #'((basic-distance . 22) (minimum-distance . 16) (padding . 8) (stretchability . 25))
  top-system-spacing = #'((basic-distance . 6) (minimum-distance . 2) (padding . 2))
  last-bottom-spacing = #'((basic-distance . 6) (minimum-distance . 2) (padding . 2) (stretchability . 30))
  print-first-page-number = ##f
  oddHeaderMarkup = \markup \fill-line {
    \null
    \unless \on-first-page \abs-fontsize #8.5 \concat { \override #'(font-name . "Noto Serif CJK SC") "梦的翅膀受了伤" \override #'(font-name . "EB Garamond Italic") "   ·   Full Score" }
    \unless \on-first-page \override #'(font-name . "EB Garamond") \abs-fontsize #11 \fromproperty #'page:page-number-string
  }
  evenHeaderMarkup = \markup \fill-line {
    \unless \on-first-page \override #'(font-name . "EB Garamond") \abs-fontsize #11 \fromproperty #'page:page-number-string
    \unless \on-first-page \abs-fontsize #8.5 \concat { \override #'(font-name . "Noto Serif CJK SC") "梦的翅膀受了伤" \override #'(font-name . "EB Garamond Italic") "   ·   Full Score" }
    \null
  }
  oddFooterMarkup = \markup \fill-line { \override #'(font-name . "Noto Serif CJK SC") \abs-fontsize #8 \concat { "原唱 · 词曲　蒋雪儿　　｜　　编配 · 制谱　" \override #'(font-name . "Noto Serif CJK SC Bold") "花开富贵" } }
  evenFooterMarkup = \markup \fill-line { \override #'(font-name . "Noto Serif CJK SC") \abs-fontsize #8 \concat { "原唱 · 词曲　蒋雪儿　　｜　　编配 · 制谱　" \override #'(font-name . "Noto Serif CJK SC Bold") "花开富贵" } }
}

\header {
  tagline = ##f
}

global = {
  \key e \minor
  \numericTimeSignature
  \time 4/4
}

marks = {
  \tempo \markup { \abs-fontsize #12.5 \bold "Andante mesto" } 4 = 80 s1  % 1
  s1  % 2
  s1  % 3
  s1  % 4
  \break s1  % 5
  s1  % 6
  s1  % 7
  s1  % 8
  s1 \bar "||"  % 9
  \pageBreak \mark \default s1  % 10
  s1  % 11
  s1  % 12
  s1  % 13
  \break s1  % 14
  s1  % 15
  s1  % 16
  s1  % 17
  \pageBreak \mark \default s1  % 18
  s1  % 19
  s1  % 20
  s1  % 21
  \break s1  % 22
  s1  % 23
  s1  % 24
  s1  % 25
  \pageBreak \mark \default s1  % 26
  s1  % 27
  s1^\markup { \abs-fontsize #11 \italic "poco allarg." }  % 28
  s1 \bar "||"  % 29
  \break \mark \default s1^\markup { \abs-fontsize #11 \italic "a tempo" }  % 30
  s1  % 31
  s1  % 32
  s1  % 33
  s1^\markup { \abs-fontsize #11 \italic "rit." }  % 34
  s1 \bar "|."  % 35
}

voiceMusic = {
  R1 |  % 1
  R1 |  % 2
  R1 |  % 3
  R1 |  % 4
  R1 |  % 5
  R1 |  % 6
  R1 |  % 7
  R1 |  % 8
  R1 |  % 9
  e'4\mp e'8 g'8 fis'2 |  % 10
  d'8 d'8 a'8 fis'8 g'2 |  % 11
  b8 d'8 e'8 g'8 a'8 a'8 a'8 d'8 |  % 12
  d'8( e'8~ e'2) r4 |  % 13
  b'8 a'8 g'8 fis'8 fis'8 fis'8 fis'8 a'8 |  % 14
  g'2 r4 g'8 g'8 |  % 15
  g'8 g'8 g'8 a'8 fis'8 d'8 a'8 a'8 |  % 16
  a'8( b'8~ b'2) r4 |  % 17
  e'8 e'8 e'8 g'8 g'8( a'4.) |  % 18
  fis'8 b8 fis'8 fis'8( e'8) e'8~ e'4 |  % 19
  e'8 d'8 e'8 g'8 a'8 a'8 a'8 g'16( e'16) |  % 20
  e'2 r2 |  % 21
  b'8\mf a'8 g'8 fis'8 fis'8 fis'8 a'8 a'8 |  % 22
  g'2 r4 g'8 fis'8 |  % 23
  g'8 g'8 g'8 a'8 fis'8 d'8 a'8 a'8 |  % 24
  a'8( b'8~ b'2) r4 |  % 25
  e'4\f e'8 g'8 g'8( a'4.) |  % 26
  fis'4 b8 fis'8( e'8) e'4. |  % 27
  e'8 d'8 e'8 g'8 a'8 a'8 a'8 d'8 |  % 28
  d'8( e'8~\> e'2.) |  % 29
  R1\! |  % 30
  R1 |  % 31
  R1 |  % 32
  R1 |  % 33
  r2 r4 r4\fermata |  % 34
  R1\fermata |  % 35
}

lyricText = \lyricmode {
  梦 的 翅 膀 已 经 受 了 伤 我 飞 不 到 有 你 的 地 方 每 次 想 你 我 都 会 心 痛 我 的 思 念 转 过 寂 静 的 天 空 我 的 记 忆 里 有 你 的 痕 迹 我 的 爱 在 寂 寞 世 界 里 天 空 飘 过 流 浪 的 白 云 就 像 我 们 已 经 破 碎 的 爱 情 爱 得 太 累 心 已 憔 悴 让 风 吹 干 受 伤 的 眼 泪
}

violinOne = {
  R1 |  % 1
  R1 |  % 2
  R1 |  % 3
  R1 |  % 4
  R1 |  % 5
  e''8\mp^\markup \italic "dolce, cantabile"( d''8 e''8 g''8) fis''4( g''8 a''8) |  % 6
  b''2.\> r4\! |  % 7
  e''8\mp( d''8 e''8 g''8) fis''4( d''4) |  % 8
  e''2.\> r4\! |  % 9
  R1 |  % 10
  R1 |  % 11
  R1 |  % 12
  r2 r4 g''8\p^\markup \italic "dolce"( a''8 |  % 13
  b''2 a''2) |  % 14
  g''2 a''8( g''8 fis''4) |  % 15
  e''2( d''2) |  % 16
  g''2( fis''2 |  % 17
  e''2)\> r2\! |  % 18
  R1 |  % 19
  R1 |  % 20
  r2 e''8\mp( d''8 e''8 g''8) |  % 21
  fis''1\< |  % 22
  g''4\mf( a''4 b''4 a''8 g''8) |  % 23
  e''2\mp( fis''2) |  % 24
  g''2\<( fis''4. a''8) |  % 25
  b''2\mf^\markup \italic "con anima" a''2 |  % 26
  b''2( a''4 g''4) |  % 27
  c'''2 b''4( a''4) |  % 28
  b''2.\>( a''4) |  % 29
  e''8\p( d''8 e''8 g''8) fis''4( g''8 fis''8) |  % 30
  e''2.\> r4\! |  % 31
  R1 |  % 32
  R1 |  % 33
  e''8\pp( d''8 e''8 g''8) fis''4( d''4)\fermata |  % 34
  e''1_\markup \italic "morendo"\fermata |  % 35
}

violinTwo = {
  b'1\pp^\markup \italic "sul tasto" |  % 1
  b'2 d''2 |  % 2
  c''2 b'2 |  % 3
  c''2 d''2 |  % 4
  d''1 |  % 5
  b'2\p^\markup \italic "ord." d''2~ |  % 6
  d''2 c''2~ |  % 7
  c''2 a'2 |  % 8
  fis'2( g'2) |  % 9
  e''2\p d''2~ |  % 10
  d''2 b'2 |  % 11
  c''1 |  % 12
  b'1 |  % 13
  e''2\mp( fis''2) |  % 14
  e''2 b'2 |  % 15
  c''2 a'2 |  % 16
  e''2 dis''2 |  % 17
  e''2\p d''2~ |  % 18
  d''2 b'2 |  % 19
  c''2 e''2 |  % 20
  b'1\< |  % 21
  e''2\mp d''2 |  % 22
  b'1 |  % 23
  c''2 d''2 |  % 24
  e''2\< dis''2 |  % 25
  e''2\mf fis''2~ |  % 26
  fis''2. e''4 |  % 27
  e''2 fis''2 |  % 28
  d''1\> |  % 29
  b'2\p d''2 |  % 30
  b'1 |  % 31
  c''2 d''2~ |  % 32
  d''2 b'2 |  % 33
  c''2\pp a'4~ a'4\fermata |  % 34
  fis'2_\markup \italic "morendo"( g'2)\fermata |  % 35
}

viola = {
  g'1\pp^\markup \italic "sul tasto" |  % 1
  g'2 a'2 |  % 2
  g'1 |  % 3
  a'1 |  % 4
  g'2 fis'2 |  % 5
  g'2\p^\markup \italic "ord." a'2 |  % 6
  e'2 e'4( d'4) |  % 7
  e'2 d'2 |  % 8
  d'2 b2 |  % 9
  c'2\p a2 |  % 10
  a2 g2 |  % 11
  g2 fis2 |  % 12
  g1 |  % 13
  g4\mp( e'4) a4( d'4) |  % 14
  g4( e'4) g4( d'4) |  % 15
  g4( e'4) a4( d'4) |  % 16
  c'4( e'4) fis4( a4) |  % 17
  g8\p^\markup \italic "legato"( e8 c'8 g8) d'8( a8 fis8 a8) |  % 18
  a8( b8 fis8 b8) e8( g8 b8 g8) |  % 19
  c'8( a8 e8 a8) fis8( b8 e'8 b8) |  % 20
  g8\<( e8 b8 g8) g2 |  % 21
  g8\mp( c'8 e'8 c'8) fis8( a8 d'8 a8) |  % 22
  e'8( b8 g8 b8) g8( b8 d'8 b8) |  % 23
  g8( c'8 e'8 c'8) a8( b8 d'8 b8) |  % 24
  g8( c'8 e'8 c'8) fis8\<( a8 c'8 a8) |  % 25
  g8\mf( e8 c'8 g8) d'8( a8 fis8 a8) |  % 26
  a8( fis8 a8 fis8) g8( e8 g8 b8) |  % 27
  g8( e8 c'8 g8) d'8( a8 fis8 a8) |  % 28
  e8\>( g8 c'8 g8) e8( g8 c'8 g8) |  % 29
  g'2\p a'2 |  % 30
  e'1 |  % 31
  a'1 |  % 32
  g'2 d'2 |  % 33
  e'2\pp a4~ a4\fermata |  % 34
  b1_\markup \italic "morendo"\fermata |  % 35
}

cello = {
  e,1\pp |  % 1
  e8\p^\markup \italic "espress."( d8 e8 g8) fis4( g8 fis8) |  % 2
  e2. r4 |  % 3
  e8( d8 e8 g8) fis4.( a8) |  % 4
  b2. r4 |  % 5
  e2\p d2 |  % 6
  c1 |  % 7
  a,2 fis2 |  % 8
  e2 d2 |  % 9
  c2\p d2 |  % 10
  b,2 e2 |  % 11
  a,2 d2 |  % 12
  e2 d2 |  % 13
  c2\mp d2 |  % 14
  e2 d2 |  % 15
  c2 b,2 |  % 16
  a,2 b,2 |  % 17
  c2\p d2~ |  % 18
  d2 e2 |  % 19
  a,2 b,2 |  % 20
  e2\< d2 |  % 21
  c2\mp d2 |  % 22
  e2 d2 |  % 23
  c2 b,2 |  % 24
  a,2\< b,2 |  % 25
  c,2\mf d,2 |  % 26
  dis,2 e,2 |  % 27
  a,2 d,2 |  % 28
  c,1\> |  % 29
  e,2\p d,2 |  % 30
  c,1 |  % 31
  e8\p^\markup \italic "espress."( d8 e8 g8) fis4.( a8) |  % 32
  b2. r4 |  % 33
  a,2\pp fis,4~ fis,4\fermata |  % 34
  e,1_\markup \italic "morendo"\fermata |  % 35
}


\markup {
  \column {
    \fill-line {
      \override #'(font-name . "EB Garamond") \abs-fontsize #8.5 \concat { "F U L L    S C O R E" }
    }
    \vspace #0.9
    \fill-line {
      \override #'(font-name . "Noto Serif CJK SC Bold") \abs-fontsize #25 "梦 的 翅 膀 受 了 伤"
    }
    \vspace #0.7
    \fill-line {
      \override #'(font-name . "EB Garamond Italic") \abs-fontsize #12.5 "for Voice and String Quartet"
    }
    \vspace #0.25
    \fill-line {
      \override #'(font-name . "Noto Serif CJK SC") \abs-fontsize #10 "人声与弦乐四重奏版"
    }
    \vspace #1.6
    \fill-line {
      \override #'(font-name . "Noto Serif CJK SC") \abs-fontsize #10.5
      \column {
        \line { "原唱　蒋雪儿" }
      }
      \override #'(font-name . "Noto Serif CJK SC") \abs-fontsize #10.5
      \right-column {
        "词曲　蒋雪儿"
        \vspace #0.1
        \override #'(font-name . "Noto Serif CJK SC Bold") \abs-fontsize #11.5 "编配　花开富贵"
        \vspace #0.1
        \override #'(font-name . "Noto Serif CJK SC Bold") \abs-fontsize #11.5 "制谱　花开富贵"
      }
    }
    \vspace #0.4
  }
}


\score {
  <<
    \new Staff = "voice" \with {
      instrumentName = "Voice"
      shortInstrumentName = "V."
    } <<
      \marks
      \new Voice = "vox" {
        \global
        \set Staff.beamExceptions = #'()
        \set Staff.baseMoment = #(ly:make-moment 1/4)
        \set Staff.beatStructure = 1,1,1,1
        \dynamicUp \voiceMusic
      }
    >>
    \new Lyrics \lyricsto "vox" \lyricText
    \new StaffGroup <<
      \new Staff \with { instrumentName = "Violin I" shortInstrumentName = "Vln. I" }
        { \global \violinOne }
      \new Staff \with { instrumentName = "Violin II" shortInstrumentName = "Vln. II" }
        { \global \violinTwo }
      \new Staff \with { instrumentName = "Viola" shortInstrumentName = "Vla." }
        { \global \clef alto \viola }
      \new Staff \with { instrumentName = "Violoncello" shortInstrumentName = "Vc." }
        { \global \clef bass \cello }
    >>
  >>
  \layout {
    \context {
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
    }
    \context {
      \Staff
      \override InstrumentName.font-size = #1.6
      \override InstrumentName.padding = #1.2
      \override TextScript.padding = #1.0
      \override DynamicLineSpanner.padding = #1.2
    }
    \context {
      \Lyrics
      \override LyricText.font-name = "Noto Serif CJK SC"
      \override LyricText.font-size = #0.4
      \override VerticalAxisGroup.nonstaff-relatedstaff-spacing.padding = #1.4
      \override VerticalAxisGroup.nonstaff-unrelatedstaff-spacing.padding = #2.6
      \override LyricSpace.minimum-distance = #1.1
    }
    \context {
      \StaffGroup
      \override StaffGrouper.staff-staff-spacing = #'((basic-distance . 12) (minimum-distance . 9) (padding . 2.5) (stretchability . 40))
    }
  }
}
