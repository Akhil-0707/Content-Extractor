"""Shared types for document parsers.

Every parser turns one file into an ordered list of `Block`s. A block is the smallest
piece of content worth citing: a heading, a paragraph, a code sample, a table, or the
text recovered from an image. `source_ref` records where it came from so a quiz
question can point back at the exact page, slide, cell or timestamp.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

HEADING_RE = re.compile(r"^(#{1,6})\s+\S")


class BlockKind(StrEnum):
    HEADING = "heading"
    TEXT = "text"
    CODE = "code"
    TABLE = "table"
    # Text recovered by OCR; lower confidence than a real text layer
    OCR_TEXT = "ocr_text"


@dataclass(slots=True)
class Block:
    kind: BlockKind
    text: str
    # Where this came from, e.g. {"page": 4} / {"cell": 7} / {"start_s": 812.4}
    source_ref: dict = field(default_factory=dict)
    # Code blocks only: "python", "sql", …
    language: str | None = None

    def __post_init__(self) -> None:
        self.text = self.text.strip()


@dataclass(slots=True)
class ParsedDocument:
    """The result of parsing one file."""

    blocks: list[Block]
    # Free-form notes for the trainer: page counts, OCR usage, skipped parts
    meta: dict = field(default_factory=dict)
    title: str | None = None

    @property
    def text_length(self) -> int:
        return sum(len(b.text) for b in self.blocks)

    def teaching_text(self) -> str:
        """Prose only — what the quiz and content-document agents read."""
        return "\n\n".join(b.text for b in self.blocks if b.kind is not BlockKind.CODE)


def split_markdown(body: str, source_ref: dict) -> list[Block]:
    """Split markdown into heading and paragraph blocks.

    Headings are kept separate because they anchor topic boundaries for the
    Structuring agent. Every block gets its own copy of `source_ref`.
    """
    blocks: list[Block] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            block = Block(BlockKind.TEXT, "\n".join(buffer), dict(source_ref))
            if block.text:
                blocks.append(block)
            buffer.clear()

    for line in body.splitlines():
        if HEADING_RE.match(line):
            flush()
            blocks.append(Block(BlockKind.HEADING, line.lstrip("# ").strip(), dict(source_ref)))
        else:
            buffer.append(line)
    flush()
    return blocks


class UnsupportedFile(Exception):
    """Raised when no parser handles this file type."""


class ParseError(Exception):
    """Raised when a parser recognises the type but the file is damaged."""
