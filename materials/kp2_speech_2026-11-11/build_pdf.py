"""Build the original Russian three-minute speech; no source document is embedded."""
from __future__ import annotations

import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = json.loads((HERE / "speech.json").read_text(encoding="utf-8"))
OUT = ROOT / "output" / "pdf" / "KP2_speech_3_minutes_ru.pdf"
NAVY = colors.HexColor("#183047")
TEAL = colors.HexColor("#11756C")
GRAY = colors.HexColor("#52616D")
PALE = colors.HexColor("#EAF4F1")
WIDTH, HEIGHT = A4
LEFT = 43
RIGHT = WIDTH - 43


def register_fonts() -> None:
    fonts = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("SpeechArial", str(fonts / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("SpeechArialBold", str(fonts / "arialbd.ttf")))
    pdfmetrics.registerFontFamily("SpeechArial", normal="SpeechArial", bold="SpeechArialBold")


def paragraph(c, text, x, top, width, style):
    p = Paragraph(text, style)
    _, h = p.wrap(width, HEIGHT)
    p.drawOn(c, x, top - h)
    return top - h


def build():
    register_fonts()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=A4, pageCompression=1, invariant=1)
    c.setTitle("Текст выступления КП2 на 3 минуты")
    c.setAuthor("Учебный проект")
    c.setSubject(DATA["title"])
    body = ParagraphStyle("body", fontName="SpeechArial", fontSize=12.2, leading=17.1,
                          textColor=NAVY, alignment=TA_LEFT, splitLongWords=False)
    heading = ParagraphStyle("heading", fontName="SpeechArialBold", fontSize=12.4,
                             leading=16.2, textColor=NAVY)
    title = ParagraphStyle("title", fontName="SpeechArialBold", fontSize=19,
                           leading=23.5, textColor=NAVY)
    layout = []
    for page, slides in enumerate((DATA["slides"][:5], DATA["slides"][5:]), 1):
        c.setFillColor(TEAL)
        c.rect(0, HEIGHT - 9, WIDTH, 9, fill=1, stroke=0)
        c.setFillColor(TEAL)
        c.setFont("SpeechArialBold", 10)
        c.drawString(LEFT, HEIGHT - 38, "КП2 / ТЕКСТ ВЫСТУПЛЕНИЯ")
        if page == 1:
            top = paragraph(c, escape(DATA["title"]), LEFT, HEIGHT - 53, RIGHT - LEFT, title)
            c.setFillColor(GRAY)
            c.setFont("SpeechArial", 10.4)
            c.drawString(LEFT, top - 20, "9 слайдов   /   5 выступающих   /   около 3 минут")
            top -= 47
        else:
            top = paragraph(c, "Результаты, проверка и итоги", LEFT, HEIGHT - 57, RIGHT - LEFT, title)
            top -= 23
        for slide in slides:
            start = top
            c.setFillColor(PALE)
            c.roundRect(LEFT, top - 23, 26, 25, 5, fill=1, stroke=0)
            c.setFillColor(TEAL)
            c.setFont("SpeechArialBold", 11)
            c.drawCentredString(LEFT + 13, top - 15, str(slide["number"]))
            top = paragraph(c, escape(slide["title"]), LEFT + 37, top,
                            RIGHT - LEFT - 37, heading)
            c.setFillColor(TEAL)
            c.setFont("SpeechArialBold", 10)
            c.drawString(LEFT + 37, top - 14, slide["speaker"])
            top -= 27
            top = paragraph(c, escape(slide["text"]), LEFT + 37, top,
                            RIGHT - LEFT - 37, body)
            layout.append({"slide": slide["number"], "page": page,
                           "top": round(start, 2), "bottom": round(top, 2)})
            top -= 17
        if top < 56:
            raise RuntimeError(f"Page {page} overflows: bottom={top}")
        c.setStrokeColor(colors.HexColor("#DCE4E8"))
        c.line(LEFT, 45, RIGHT, 45)
        c.setFillColor(GRAY)
        c.setFont("SpeechArial", 8.5)
        c.drawString(LEFT, 29, "Заголовки и имена не зачитываются. Время ориентировочное.")
        c.drawRightString(RIGHT, 29, f"{page} / 2")
        c.showPage()
    c.save()

    md = [f"# {DATA['title']}", "", "Готовый текст по девяти слайдам. Около трёх минут с короткими паузами.",
          "Заголовки и имена не зачитываются.", ""]
    for slide in DATA["slides"]:
        md.extend([f"## Слайд {slide['number']}. {slide['title']}", "", f"Выступает: {slide['speaker']}",
                   "", slide["text"], ""])
    (HERE / "speech.md").write_text("\n".join(md), encoding="utf-8", newline="\n")
    (HERE / "KP2_speech_3_minutes_ru.pdf").write_bytes(OUT.read_bytes())
    spoken = " ".join(s["text"] for s in DATA["slides"])
    summary = {"pdf": str(OUT), "pages": 2,
               "words_by_whitespace": len(spoken.split()),
               "words_by_pattern": len(re.findall(r"[\w]+(?:[-:]\w+)*", spoken)),
               "duration": "Approximate 3 minutes; no recorded rehearsal",
               "layout": layout}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
