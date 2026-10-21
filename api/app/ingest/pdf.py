"""PDF parser with an OCR fallback for slide decks exported as images.

Most PDFs carry a text layer that extracts cleanly. But in the first corpus, 14 of 38
decks are full-page JPEG screenshots of slides with no text at all — every title and
bullet exists only as pixels. Those pages are invisible to text extraction, so each
page is measured and routed:

    enough text        -> use the text layer (fast, exact)
    little or no text  -> render the page and OCR it (slow, approximate)

OCR runs on the CPU and is the slowest step in ingestion, so it is used per page rather
than per document: a deck with a text layer and three scanned pages only OCRs those three.
"""

from __future__ import annotations

import logging
import re

from app.ingest.base import Block, BlockKind, ParsedDocument, ParseError, split_markdown
from app.ingest.ocr import OcrUnavailable, ocr_image

logger = logging.getLogger(__name__)

# Below this many characters, a page is treated as having no usable text layer.
# Image-only slides score 0; a sparse real page still clears it comfortably.
MIN_CHARS_PER_PAGE = 40

# Rendering above the page's natural size helps OCR on slide text. Measured on real
# decks: 3x recovers display titles that 2x breaks into fragments.
OCR_RENDER_SCALE = 3.0

MAX_PAGES = 2_000

BULLET_RE = re.compile(r"^\s*[•●▪‣\-\*]\s+", re.M)


def _clean(text: str) -> str:
    text = text.replace(" ", " ")
    text = BULLET_RE.sub("", text)
    # Join hyphenated line breaks: "proba-\nbilistic" -> "probabilistic"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    return re.sub(r"[ \t]+", " ", text)


def parse(raw: bytes, *, allow_ocr: bool = True) -> ParsedDocument:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - dependency is installed in the image
        raise ParseError("PDF support requires PyMuPDF") from exc

    try:
        document = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:
        raise ParseError(f"Not a readable PDF: {exc}") from exc

    page_count = document.page_count
    if page_count > MAX_PAGES:
        document.close()
        raise ParseError(f"PDF has too many pages ({page_count} > {MAX_PAGES})")

    blocks: list[Block] = []
    ocr_pages: list[int] = []
    text_pages = 0
    failed_ocr = 0
    unreadable: list[int] = []

    with document:
        for number, page in enumerate(document, start=1):
            ref = {"page": number}
            text = _clean(page.get_text("text"))

            if len(text.strip()) >= MIN_CHARS_PER_PAGE:
                text_pages += 1
                blocks.extend(split_markdown(text, ref))
                continue

            if not allow_ocr:
                unreadable.append(number)
                continue
            try:
                recovered = _clean(ocr_image(_render(page)))
            except OcrUnavailable:
                raise
            except Exception:
                logger.warning("OCR failed on page %s", number, exc_info=True)
                failed_ocr += 1
                continue

            if recovered.strip():
                ocr_pages.append(number)
                blocks.append(Block(BlockKind.OCR_TEXT, recovered, ref))
            else:
                unreadable.append(number)

        title = (document.metadata or {}).get("title") or None

    meta = {
        "source": "pdf",
        "pages": page_count,
        "text_pages": text_pages,
        "ocr_pages": len(ocr_pages),
    }
    if failed_ocr:
        meta["ocr_failures"] = failed_ocr
    if ocr_pages:
        # Flag for the trainer: OCR text is less reliable and worth a skim
        meta["ocr_page_numbers"] = ocr_pages
    if unreadable:
        # Pages that yielded nothing at all, so a trainer can see what was lost
        meta["unreadable_pages"] = unreadable

    if not title:
        title = next((b.text for b in blocks if b.kind is BlockKind.HEADING), None)
    return ParsedDocument(blocks=[b for b in blocks if b.text], title=title, meta=meta)


def _render(page) -> bytes:
    """Render a page to PNG bytes for OCR."""
    import fitz

    matrix = fitz.Matrix(OCR_RENDER_SCALE, OCR_RENDER_SCALE)
    return page.get_pixmap(matrix=matrix).tobytes("png")
