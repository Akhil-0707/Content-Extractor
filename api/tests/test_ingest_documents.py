"""PDF, Office and HTML parser tests.

Fixtures are built in-memory by the same libraries that read them, so no real course
material is committed (rule 5).
"""

import io

import pytest

from app.ingest import html, office, pdf
from app.ingest.base import BlockKind, ParseError
from app.ingest.ocr import OcrUnavailable, drop_noise

fitz = pytest.importorskip("fitz")
docx_lib = pytest.importorskip("docx")
pptx_lib = pytest.importorskip("pptx")


def pdf_with_text(pages: list[str], title: str = "") -> bytes:
    """Build a PDF whose pages carry a real text layer.

    Each page gets enough text to clear MIN_CHARS_PER_PAGE, as a real page would —
    below that the parser correctly decides the page needs OCR instead.
    """
    document = fitz.open()
    for body in pages:
        page = document.new_page()
        padded = f"{body}\n" + "Supporting sentence for this page. " * 3
        page.insert_text((72, 100), padded, fontsize=11)
    if title:
        document.set_metadata({"title": title})
    raw = document.tobytes()
    document.close()
    return raw


def pdf_image_only(page_count: int = 2) -> bytes:
    """A deck exported as pictures: no text layer at all, like 14 decks in the corpus."""
    source = fitz.open()
    for index in range(page_count):
        page = source.new_page(width=400, height=300)
        page.insert_text((40, 80), f"Slide {index} heading", fontsize=24)
    pixmaps = [page.get_pixmap(dpi=96) for page in source]
    source.close()

    document = fitz.open()
    for pixmap in pixmaps:
        page = document.new_page(width=pixmap.width, height=pixmap.height)
        page.insert_image(page.rect, pixmap=pixmap)
    raw = document.tobytes()
    document.close()
    return raw


# ---------- pdf ----------


def test_pdf_reads_the_text_layer_with_page_refs():
    doc = pdf.parse(pdf_with_text(["First page body.", "Second page body."]), allow_ocr=False)

    assert doc.meta["pages"] == 2
    assert doc.meta["text_pages"] == 2
    assert doc.meta["ocr_pages"] == 0
    assert {b.source_ref["page"] for b in doc.blocks} == {1, 2}


def test_pdf_uses_metadata_title_when_present():
    assert pdf.parse(pdf_with_text(["Body text here."], title="Course Deck")).title == "Course Deck"


def test_pdf_joins_words_split_across_lines():
    doc = pdf.parse(pdf_with_text(["proba-\nbilistic design"]), allow_ocr=False)
    assert "probabilistic" in " ".join(b.text for b in doc.blocks)


def test_pdf_without_ocr_records_pages_it_could_not_read():
    """Nothing vanishes silently: the trainer sees which pages produced nothing."""
    doc = pdf.parse(pdf_image_only(2), allow_ocr=False)

    assert doc.blocks == []
    assert doc.meta["unreadable_pages"] == [1, 2]
    assert doc.meta["text_pages"] == 0


def test_pdf_rejects_damaged_files():
    with pytest.raises(ParseError, match="readable PDF"):
        pdf.parse(b"%PDF-1.4 truncated nonsense")


def test_pdf_rejects_absurd_page_counts(monkeypatch):
    monkeypatch.setattr(pdf, "MAX_PAGES", 1)
    with pytest.raises(ParseError, match=r"too many pages \(2 > 1\)"):
        pdf.parse(pdf_with_text(["one", "two"]), allow_ocr=False)


def test_pdf_page_below_the_text_threshold_is_treated_as_needing_ocr():
    """A nearly blank page has no usable text layer, so it routes to OCR."""
    document = fitz.open()
    document.new_page().insert_text((72, 100), "Hi", fontsize=11)
    raw = document.tobytes()
    document.close()

    doc = pdf.parse(raw, allow_ocr=False)
    assert doc.meta["text_pages"] == 0
    assert doc.meta["unreadable_pages"] == [1]


def test_pdf_reports_when_no_ocr_engine_is_installed(monkeypatch):
    monkeypatch.setattr(pdf, "ocr_image", lambda _: (_ for _ in ()).throw(OcrUnavailable("none")))
    with pytest.raises(OcrUnavailable):
        pdf.parse(pdf_image_only(1), allow_ocr=True)


def test_pdf_survives_a_failing_ocr_page(monkeypatch):
    """One bad page must not lose the rest of the deck."""
    monkeypatch.setattr(pdf, "ocr_image", lambda _: (_ for _ in ()).throw(RuntimeError("engine died")))
    doc = pdf.parse(pdf_image_only(2), allow_ocr=True)

    assert doc.meta["ocr_failures"] == 2
    assert doc.blocks == []


def test_pdf_ocr_recovers_text_from_an_image_only_page(monkeypatch):
    monkeypatch.setattr(pdf, "ocr_image", lambda _: "Slide 0 heading")
    doc = pdf.parse(pdf_image_only(1), allow_ocr=True)

    assert doc.meta["ocr_pages"] == 1
    assert doc.meta["ocr_page_numbers"] == [1]
    assert doc.blocks[0].kind is BlockKind.OCR_TEXT
    assert "Slide 0" in doc.blocks[0].text


def test_ocr_noise_filter_keeps_text_and_drops_diagram_debris():
    """Slides put text over line art; OCR reports the drawing's edges as fragments."""
    raw = "\n".join(
        [
            "The AI Engineering",       # real title
            "Blueprint",                # short but a real word
            "Part 2",                   # short heading must survive
            "sys.mode = PROBABILISTIC", # code annotation
            "=e ' Ss eR i",             # debris
            "ie ~",                     # debris
            "D",                        # debris
            "|",                        # debris
        ]
    )
    assert drop_noise(raw).splitlines() == [
        "The AI Engineering",
        "Blueprint",
        "Part 2",
        "sys.mode = PROBABILISTIC",
    ]


# ---------- docx ----------


def build_docx(items: list[tuple[str, str]], table: list[list[str]] | None = None) -> bytes:
    document = docx_lib.Document()
    for style, text in items:
        document.add_paragraph(text, style=style) if style else document.add_paragraph(text)
    if table:
        word_table = document.add_table(rows=len(table), cols=len(table[0]))
        for row_index, row in enumerate(table):
            for cell_index, value in enumerate(row):
                word_table.cell(row_index, cell_index).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_docx_distinguishes_headings_from_prose():
    doc = office.parse_docx(
        build_docx([("Heading 1", "Lab Guide"), ("", "Follow these steps."), ("Heading 2", "Setup")])
    )

    kinds = [(b.kind, b.text, b.level) for b in doc.blocks]
    assert (BlockKind.HEADING, "Lab Guide", 1) in kinds
    assert (BlockKind.HEADING, "Setup", 2) in kinds
    assert any(k is BlockKind.TEXT for k, _, _ in kinds)


def test_docx_renders_tables():
    doc = office.parse_docx(build_docx([("", "intro")], table=[["Name", "Role"], ["Ana", "Trainer"]]))
    tables = [b for b in doc.blocks if b.kind is BlockKind.TABLE]

    assert len(tables) == 1
    assert "Name | Role" in tables[0].text
    assert "Ana | Trainer" in tables[0].text


def test_docx_rejects_non_word_files():
    with pytest.raises(ParseError, match="readable Word"):
        office.parse_docx(b"PK\x03\x04 not really a docx")


# ---------- pptx ----------


def build_pptx(slides: list[tuple[str, str, str]]) -> bytes:
    presentation = pptx_lib.Presentation()
    layout = presentation.slide_layouts[1]
    for title, body, notes in slides:
        slide = presentation.slides.add_slide(layout)
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def test_pptx_reads_titles_body_and_speaker_notes():
    """Speaker notes often hold the trainer's real explanation."""
    doc = office.parse_pptx(build_pptx([("Vectors", "What embeddings are", "Mention cosine distance")]))

    assert doc.title == "Vectors"
    assert doc.meta["slides"] == 1
    assert any(b.kind is BlockKind.HEADING and b.level == 1 for b in doc.blocks)
    notes = [b for b in doc.blocks if b.source_ref.get("notes")]
    assert notes and "cosine" in notes[0].text


def test_pptx_numbers_slides_from_one():
    doc = office.parse_pptx(build_pptx([("A", "a", ""), ("B", "b", "")]))
    assert sorted({b.source_ref["slide"] for b in doc.blocks}) == [1, 2]


# ---------- html ----------


def test_html_keeps_content_and_drops_chrome():
    raw = b"""
    <html><head><title>Lesson</title><style>p{color:red}</style></head>
    <body>
      <nav>Home About</nav>
      <h1>Chunking</h1><p>Split text into passages.</p>
      <pre>chunk(text)</pre>
      <script>tracker()</script>
      <footer>copyright</footer>
    </body></html>
    """
    doc = html.parse(raw)
    combined = " ".join(b.text for b in doc.blocks)

    assert doc.title == "Lesson"
    assert "Split text into passages." in combined
    assert "tracker" not in combined and "Home About" not in combined and "copyright" not in combined
    assert any(b.kind is BlockKind.CODE for b in doc.blocks)
    assert [b.level for b in doc.blocks if b.kind is BlockKind.HEADING] == [1]


def test_html_does_not_emit_nested_text_twice():
    doc = html.parse(b"<html><body><td><li>Only once</li></td></body></html>")
    assert sum("Only once" in b.text for b in doc.blocks) == 1


def test_html_falls_back_to_first_heading_when_untitled():
    assert html.parse(b"<html><body><h2>Fallback</h2></body></html>").title == "Fallback"
