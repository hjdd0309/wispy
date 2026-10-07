# -*- coding: utf-8 -*-
"""submission/*.docx → PDF(Word) 변환 후 페이지 수 확인, 페이지별 PNG 렌더링."""
import pathlib, sys, fitz, win32com.client

here = pathlib.Path(__file__).resolve().parent
out = here.parent / "submission"
docx = next(out.glob("*.docx")); pdf = docx.with_suffix(".pdf")
w = win32com.client.DispatchEx("Word.Application"); w.Visible = False
try:
    d = w.Documents.Open(str(docx), ReadOnly=True)
    d.ExportAsFixedFormat(str(pdf), 17)
    d.Close(False)
finally:
    w.Quit()
doc = fitz.open(str(pdf)); print("pages:", len(doc))
dpi = int(sys.argv[1]) if len(sys.argv) > 1 else 110
for i, pg in enumerate(doc):
    pg.get_pixmap(dpi=dpi).save(str(here / f"page{i+1}.png"))
    blocks = pg.get_text("blocks")
    print(i + 1, "last y:", round(max(b[3] for b in blocks)), "/", round(pg.rect.height))
