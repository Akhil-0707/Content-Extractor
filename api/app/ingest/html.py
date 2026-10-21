"""Parser for ordinary web pages and saved HTML lessons.

Databricks exports are handled by their own parser; this covers everything else. Script,
style and navigation elements are dropped so only readable content survives.
"""

from __future__ import annotations

from app.ingest.base import Block, BlockKind, ParsedDocument, ParseError

DROP_TAGS = ("script", "style", "noscript", "nav", "footer", "header", "form", "svg", "iframe")
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
CONTENT_TAGS = (*HEADING_TAGS, "p", "li", "pre", "td", "th", "blockquote")


def parse(raw: bytes) -> ParsedDocument:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover - installed in the image
        raise ParseError("HTML support requires beautifulsoup4") from exc

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(list(DROP_TAGS)):
        tag.decompose()

    blocks: list[Block] = []
    seen: set[tuple[str, str]] = set()

    for index, element in enumerate(soup.find_all(CONTENT_TAGS)):
        text = " ".join(element.get_text(" ", strip=True).split())
        if not text:
            continue
        name = element.name
        # Nested elements (a <li> inside a <td>) would otherwise be emitted twice
        key = (name, text)
        if key in seen:
            continue
        seen.add(key)

        level = None
        if name in HEADING_TAGS:
            kind = BlockKind.HEADING
            level = int(name[1])
        elif name == "pre":
            kind = BlockKind.CODE
        elif name in ("td", "th"):
            kind = BlockKind.TABLE
        else:
            kind = BlockKind.TEXT
        blocks.append(Block(kind, text, {"element": index}, level=level))

    title = (soup.title.get_text(strip=True) if soup.title else "") or None
    if not title:
        title = next((b.text for b in blocks if b.kind is BlockKind.HEADING), None)

    return ParsedDocument(blocks=blocks, title=title, meta={"source": "html", "elements": len(blocks)})
