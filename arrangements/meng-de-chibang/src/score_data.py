# -*- coding: utf-8 -*-
"""《梦的翅膀受了伤》人声 + 弦乐四重奏 —— 乐谱源数据（唯一真源）。

PDF（LilyPond）、MusicXML（Sibelius）、两个 MIDI 都由这一份数据生成，保证内容一致。

记法（类 LilyPond，绝对音高）：
  c = C3, c' = C4, c'' = C5, c, = C2；is = 升, es = 降。
  时值 1 2 4 8 16（可加附点 .），省略时沿用上一个音的时值。
  后缀：~ 连音线  ( ) 圆滑线  \\p \\mf …… 力度  \\< \\> \\! 渐强/渐弱/结束
        \\fermata 延长记号   ^{文字} 谱表上方表情文字   _{文字} 下方
        \\br  人声气口：只写进人声 MIDI（歌词 br），不在谱面显示。
          · 挂在音符上 = 从该音尾部切出一段做气口
          · 挂在休止符上 = 气口放在该休止的最后一个八分音符
  R1 = 整小节休止；小节用列表元素分隔（每个元素恰好 4 拍，程序会校验）。
"""

TITLE = "梦的翅膀受了伤"
SUBTITLE_ZH = "人声与弦乐四重奏版"
SUBTITLE_EN = "for Voice and String Quartet"
SINGER = "蒋雪儿"
LYRICIST = "蒋雪儿"
COMPOSER = "蒋雪儿"
ARRANGER = "花开富贵"
ENGRAVER = "花开富贵"
TEMPO_TEXT = "Andante mesto"
BPM = 80

N_BARS = 35

# 结构：前奏 1–9 ｜ A 10–17 ｜ B 18–25 ｜ C 26–29 ｜ 尾奏 D 30–35
REHEARSAL = {10: "A", 18: "B", 26: "C", 30: "D"}
DOUBLE_BAR_AFTER = [9, 29]          # 段落双纵线
SYSTEM_STARTS = [1, 5, 10, 14, 18, 22, 26, 30]
PAGE_STARTS = [1, 10, 18, 26]
TEXT_MARKS = {28: "poco allarg.", 30: "a tempo", 34: "rit."}   # 谱面顶端的速度文字

# ───────────────────────────── 人声 ─────────────────────────────
# 实际演唱音高（女声，do = G3）。副歌只唱一遍：图一 20 小节。
VOICE = [
    "R1", "R1", "R1", "R1", "R1", "R1", "R1", "R1",                    # 1–8
    r"r2. r4\br",                                                      # 9   入口前换气（谱面显示为整小节休止）
    r"e'4\mp e'8 g' fis'2\br",                                         # 10  梦的翅膀，
    r"d'8 d' a' fis' g'2\br",                                          # 11  已经受了伤，
    r"b8 d' e' g' a' a' a' d'",                                        # 12  我飞不到有你的地
    r"d'8( e'~ e'2) r4\br",                                            # 13  方。
    r"b'8 a' g' fis' fis' fis' fis' a'",                               # 14  每次想你我都会心
    r"g'2 r4\br g'8 g'",                                               # 15  痛，我的
    r"g'8 g' g' a' fis' d' a' a'",                                     # 16  思念转过寂静的天
    r"a'8( b'~ b'2) r4\br",                                            # 17  空。
    r"e'8 e' e' g' g'( a'4.\br)",                                      # 18  我的记忆里，
    r"fis'8 b fis' fis'( e') e'~ e'4\br",                              # 19  有你的痕迹，
    r"e'8 d' e' g' a' a' a' g'16( e')",                                # 20  我的爱在寂寞世界
    r"e'2 r2\br",                                                      # 21  里。
    r"b'8\mf a' g' fis' fis' fis' a' a'",                              # 22  天空飘过流浪的白
    r"g'2 r4\br g'8 fis'",                                             # 23  云，就像
    r"g'8 g' g' a' fis' d' a' a'",                                     # 24  我们已经破碎的爱
    r"a'8( b'~ b'2) r4\br",                                            # 25  情。
    r"e'4\f e'8 g' g'( a'4.\br)",                                      # 26  爱得太累，
    r"fis'4 b8 fis'( e') e'4.\br",                                     # 27  心已憔悴，
    r"e'8 d' e' g' a' a' a' d'",                                       # 28  让风吹干受伤的眼
    r"d'8( e'~\> e'2.)",                                               # 29  泪。
    r"R1\!", "R1", "R1", "R1",                                        # 30–33
    r"r2 r4 r4\fermata",                                              # 34  延长记号与弦乐第 4 拍对齐
    r"R1\fermata",                                                     # 35
]

LYRICS = (
    "梦 的 翅 膀 已 经 受 了 伤 我 飞 不 到 有 你 的 地 方 "
    "每 次 想 你 我 都 会 心 痛 我 的 思 念 转 过 寂 静 的 天 空 "
    "我 的 记 忆 里 有 你 的 痕 迹 我 的 爱 在 寂 寞 世 界 里 "
    "天 空 飘 过 流 浪 的 白 云 就 像 我 们 已 经 破 碎 的 爱 情 "
    "爱 得 太 累 心 已 憔 悴 让 风 吹 干 受 伤 的 眼 泪"
).split()

# ─────────────────────────── 小提琴 I ───────────────────────────
VIOLIN_I = [
    "R1", "R1", "R1", "R1", "R1",                                      # 1–5
    r"e''8\mp^{dolce, cantabile}( d'' e'' g'') fis''4( g''8 a'')",      # 6   前奏主题（原曲引子）
    r"b''2.\> r4\!",                                                   # 7
    r"e''8\mp( d'' e'' g'') fis''4( d'')",                              # 8
    r"e''2.\> r4\!",                                                   # 9
    "R1", "R1", "R1",                                                  # 10–12
    r"r2 r4 g''8\p^{dolce}( a''",                                      # 13  在人声空档里“长”出来
    r"b''2 a'')",                                                      # 14  高声部对位旋律
    r"g''2 a''8( g'' fis''4)",                                         # 15
    r"e''2( d'')",                                                     # 16
    r"g''2( fis''",                                                    # 17
    r"e''2)\> r2\!",                                                   # 18
    "R1", "R1",                                                        # 19–20
    r"r2 e''8\mp( d'' e'' g'')",                                       # 21  引子动机的回声
    r"fis''1\<",                                                       # 22
    r"g''4\mf( a'' b'' a''8 g'')",                                     # 23
    r"e''2\mp( fis'')",                                                # 24
    r"g''2(\< fis''4. a''8)",                                          # 25
    r"b''2\mf^{con anima} a''",                                        # 26  高潮
    r"b''2( a''4 g'')",                                                # 27
    r"c'''2 b''4( a'')",                                               # 28
    r"b''2.\>( a''4)",                                                 # 29
    r"e''8\p( d'' e'' g'') fis''4( g''8 fis'')",                        # 30  尾奏
    r"e''2.\> r4\!",                                                   # 31
    "R1", "R1",                                                        # 32–33
    r"e''8\pp( d'' e'' g'') fis''4( d''\fermata)",                      # 34
    r"e''1\fermata_{morendo}",                                         # 35
]

# ─────────────────────────── 小提琴 II ──────────────────────────
VIOLIN_II = [
    r"b'1\pp^{sul tasto}",                                             # 1
    r"b'2 d''",                                                        # 2
    r"c''2 b'",                                                        # 3
    r"c''2 d''",                                                       # 4
    r"d''1",                                                           # 5
    r"b'2\p^{ord.} d''~",                                              # 6
    r"d''2 c''~",                                                      # 7
    r"c''2 a'",                                                        # 8
    r"fis'2( g')",                                                     # 9
    r"e''2\p d''~",                                                    # 10
    r"d''2 b'",                                                        # 11
    r"c''1",                                                           # 12
    r"b'1",                                                            # 13
    r"e''2\mp( fis'')",                                                # 14
    r"e''2 b'",                                                        # 15
    r"c''2 a'",                                                        # 16
    r"e''2 dis''",                                                     # 17
    r"e''2\p d''~",                                                    # 18
    r"d''2 b'",                                                        # 19
    r"c''2 e''",                                                       # 20
    r"b'1\<",                                                          # 21
    r"e''2\mp d''",                                                    # 22
    r"b'1",                                                            # 23
    r"c''2 d''",                                                       # 24
    r"e''2\< dis''",                                                   # 25
    r"e''2\mf fis''~",                                                 # 26
    r"fis''2. e''4",                                                   # 27
    r"e''2 fis''",                                                     # 28
    r"d''1\>",                                                         # 29  Cmaj9 的九音
    r"b'2\p d''",                                                      # 30
    r"b'1",                                                            # 31
    r"c''2 d''~",                                                      # 32
    r"d''2 b'",                                                        # 33
    r"c''2\pp a'4~ a'\fermata",                                        # 34
    r"fis'2_{morendo}( g'\fermata)",                                   # 35
]

# ───────────────────────────── 中提琴 ────────────────────────────
VIOLA = [
    r"g'1\pp^{sul tasto}",                                             # 1
    r"g'2 a'",                                                         # 2
    r"g'1",                                                            # 3
    r"a'1",                                                            # 4
    r"g'2 fis'",                                                       # 5
    r"g'2\p^{ord.} a'",                                                # 6
    r"e'2 e'4( d')",                                                   # 7
    r"e'2 d'",                                                         # 8
    r"d'2 b",                                                          # 9
    r"c'2\p a",                                                        # 10
    r"a2 g",                                                           # 11
    r"g2 fis",                                                         # 12
    r"g1",                                                             # 13
    r"g4\mp( e') a( d')",                                              # 14
    r"g4( e') g( d')",                                                 # 15
    r"g4( e') a( d')",                                                 # 16
    r"c'4( e') fis( a)",                                               # 17
    r"g8\p^{legato}( e c' g) d'( a fis a)",                             # 18  分解和弦始终在人声之下
    r"a8( b fis b) e( g b g)",                                         # 19
    r"c'8( a e a) fis( b e' b)",                                       # 20
    r"g8\<( e b g) g2",                                                # 21  让引子回声独白
    r"g8\mp( c' e' c') fis( a d' a)",                                  # 22
    r"e'8( b g b) g( b d' b)",                                         # 23
    r"g8( c' e' c') a( b d' b)",                                       # 24
    r"g8( c' e' c') fis(\< a c' a)",                                   # 25
    r"g8\mf( e c' g) d'( a fis a)",                                    # 26
    r"a8( fis a fis) g( e g b)",                                       # 27
    r"g8( e c' g) d'( a fis a)",                                       # 28
    r"e8\>( g c' g) e( g c' g)",                                       # 29
    r"g'2\p a'",                                                       # 30
    r"e'1",                                                            # 31
    r"a'1",                                                            # 32
    r"g'2 d'",                                                         # 33
    r"e'2\pp a4~ a\fermata",                                           # 34
    r"b1\fermata_{morendo}",                                           # 35
]

# ───────────────────────────── 大提琴 ────────────────────────────
CELLO = [
    r"e,1\pp",                                                         # 1
    r"e8\p^{espress.}( d e g) fis4( g8 fis)",                          # 2   前奏主题
    r"e2. r4",                                                         # 3
    r"e8( d e g) fis4.( a8)",                                          # 4
    r"b2. r4",                                                         # 5
    r"e2\p d",                                                         # 6
    r"c1",                                                             # 7
    r"a,2 fis",                                                        # 8
    r"e2 d",                                                           # 9
    r"c2\p d",                                                         # 10
    r"b,2 e",                                                          # 11
    r"a,2 d",                                                          # 12
    r"e2 d",                                                           # 13
    r"c2\mp d",                                                        # 14
    r"e2 d",                                                           # 15
    r"c2 b,",                                                          # 16
    r"a,2 b,",                                                         # 17
    r"c2\p d~",                                                        # 18
    r"d2 e",                                                           # 19  Bm7/D
    r"a,2 b,",                                                         # 20
    r"e2\< d",                                                         # 21
    r"c2\mp d",                                                        # 22
    r"e2 d",                                                           # 23
    r"c2 b,",                                                          # 24
    r"a,2\< b,",                                                       # 25
    r"c,2\mf d,",                                                      # 26  高潮：低音 C–D–D#–E 半音上行
    r"dis,2 e,",                                                       # 27  B7/D#
    r"a,2 d,",                                                         # 28
    r"c,1\>",                                                          # 29
    r"e,2\p d,",                                                       # 30
    r"c,1",                                                            # 31
    r"e8\p^{espress.}( d e g) fis4.( a8)",                             # 32  主题回到大提琴
    r"b2. r4",                                                         # 33
    r"a,2\pp fis,4~ fis,\fermata",                                     # 34
    r"e,1\fermata_{morendo}",                                          # 35
]

PARTS = [
    # id, 全名, 缩写, 谱号, 数据, GM 音色(0 起), MIDI 声道, 声像(0–127)
    dict(id="P1", key="voice", name="Voice", abbr="V.", clef="treble", bars=VOICE,
         program=53, channel=4, pan=64, sound="voice.alto"),
    dict(id="P2", key="vn1", name="Violin I", abbr="Vln. I", clef="treble", bars=VIOLIN_I,
         program=40, channel=0, pan=38, sound="strings.violin"),
    dict(id="P3", key="vn2", name="Violin II", abbr="Vln. II", clef="treble", bars=VIOLIN_II,
         program=40, channel=1, pan=54, sound="strings.violin"),
    dict(id="P4", key="va", name="Viola", abbr="Vla.", clef="alto", bars=VIOLA,
         program=41, channel=2, pan=76, sound="strings.viola"),
    dict(id="P5", key="vc", name="Violoncello", abbr="Vc.", clef="bass", bars=CELLO,
         program=42, channel=3, pan=90, sound="strings.cello"),
]
