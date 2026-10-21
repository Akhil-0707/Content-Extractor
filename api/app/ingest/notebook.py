"""Parser for Jupyter notebooks (.ipynb).

Markdown cells are the teaching text; code cells are worked examples. Outputs are
skipped: in this corpus they are mostly base64 images and long logs (one notebook is
33 MB, nearly all of it output), which would swamp the real content.
"""

from __future__ import annotations

import json
from typing import Any

from app.ingest.base import Block, BlockKind, ParsedDocument, ParseError, split_markdown

# Skip giant pasted blobs (minified data, base64) that aren't teachable content
MAX_CODE_CHARS = 20_000


def _source_to_text(source: Any) -> str:
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    return str(source or "")


def parse(raw: bytes) -> ParsedDocument:
    try:
        document = json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        raise ParseError(f"Not a readable notebook: {exc}") from exc

    cells = document.get("cells")
    if not isinstance(cells, list):
        raise ParseError("Notebook has no cells")

    language = (
        document.get("metadata", {}).get("language_info", {}).get("name")
        or document.get("metadata", {}).get("kernelspec", {}).get("language")
        or "python"
    ).lower()

    blocks: list[Block] = []
    code_cells = text_cells = skipped = 0

    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            continue
        text = _source_to_text(cell.get("source"))
        if not text.strip():
            continue
        ref = {"cell": index}
        kind = cell.get("cell_type")

        if kind == "markdown":
            text_cells += 1
            blocks.extend(split_markdown(text, ref))
        elif kind == "code":
            if len(text) > MAX_CODE_CHARS:
                skipped += 1
                continue
            code_cells += 1
            blocks.append(Block(BlockKind.CODE, text, ref, language=language))

    blocks = [b for b in blocks if b.text]
    meta = {
        "source": "jupyter",
        "cells": len(cells),
        "text_cells": text_cells,
        "code_cells": code_cells,
        "language": language,
    }
    if skipped:
        meta["skipped_oversized_cells"] = skipped

    # Notebooks rarely set a title; fall back to the first heading
    title = next((b.text for b in blocks if b.kind is BlockKind.HEADING), None)
    return ParsedDocument(blocks=blocks, title=title, meta=meta)
