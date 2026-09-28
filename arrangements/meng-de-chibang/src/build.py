# -*- coding: utf-8 -*-
"""一键生成全部交付物：

  ../梦的翅膀受了伤_总谱.pdf            封面 + 说明页 + LilyPond 总谱
  ../梦的翅膀受了伤_Sibelius.musicxml   Sibelius「文件 → 打开」
  ../梦的翅膀受了伤_弦乐.mid            弦乐四重奏总 MIDI（四轨）
  ../梦的翅膀受了伤_人声_带歌词.mid     人声 MIDI（歌词 + br 气口块）

用法：cd src && python3 build.py
"""
import os
import subprocess
import sys
import tempfile

import pypdf

import checks
import cover
import lily
import midi_out
import model
import mxml
import score_data as SD

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
NAME = SD.TITLE


def main():
    problems = checks.main()
    if problems:
        sys.exit("自检未通过，停止生成。")
    parts = model.load()
    work = tempfile.mkdtemp(prefix="score-build-")

    # 1) LilyPond 总谱
    ly_path = os.path.join(HERE, "score.ly")
    with open(ly_path, "w", encoding="utf-8") as f:
        f.write(lily.build(parts, SD.LYRICS))
    subprocess.run(["lilypond", "-dno-point-and-click", "-o", os.path.join(work, "score"), ly_path],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2) 封面、说明页
    for nm, html in (("cover", cover.cover_html()), ("notes", cover.notes_html())):
        hp = os.path.join(work, nm + ".html")
        with open(hp, "w", encoding="utf-8") as f:
            f.write(html)
        cover.print_pdf(hp, os.path.join(work, nm + ".pdf"))

    # 3) 合并 PDF
    w = pypdf.PdfWriter()
    for nm in ("cover", "notes", "score"):
        for pg in pypdf.PdfReader(os.path.join(work, nm + ".pdf")).pages:
            w.add_page(pg)
    w.add_metadata({
        "/Title": f"{NAME} — 人声与弦乐四重奏 总谱",
        "/Author": f"编配、制谱：{SD.ARRANGER}",
        "/Subject": f"原唱：{SD.SINGER}；词曲：{SD.LYRICIST}",
        "/Keywords": "String Quartet, Voice, Full Score",
        "/Creator": "LilyPond 2.24",
    })
    try:
        w.set_page_label(0, 1, style="/r")
        w.set_page_label(2, len(w.pages) - 1, style="/D", start=1)
    except Exception:
        pass
    pdf_path = os.path.join(OUT, f"{NAME}_总谱.pdf")
    with open(pdf_path, "wb") as f:
        w.write(f)

    # 4) MusicXML
    xml_path = os.path.join(OUT, f"{NAME}_Sibelius.musicxml")
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(mxml.build(parts))

    # 5) MIDI
    midi_out.write_strings(parts, os.path.join(OUT, f"{NAME}_弦乐.mid"))
    voice = next(p for p in parts if p["key"] == "voice")
    midi_out.write_vocal(voice, os.path.join(OUT, f"{NAME}_人声_带歌词.mid"))

    for fn in sorted(os.listdir(OUT)):
        fp = os.path.join(OUT, fn)
        if os.path.isfile(fp):
            print(f"{os.path.getsize(fp):>9,d}  {fn}")


if __name__ == "__main__":
    main()
