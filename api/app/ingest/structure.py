"""Structuring agent (Agent 2): turns parsed blocks into topics and retrievable chunks.

Two jobs:

1. **Topic tree.** Headings carry the author's own outline, so they drive the structure
   rather than a model guessing at it. A heading opens a topic; its level decides whether
   it nests under the previous one or sits beside it. Material with no headings — most
   PDFs, and anything recovered by OCR — is split by page or by size instead, so it still
   arrives as teachable units.

2. **Chunks.** Each topic's prose is cut into pieces small enough to embed and retrieve,
   with a little overlap so a sentence spanning a boundary is still findable. Every chunk
   keeps the source references of the blocks it came from, which is what lets a generated
   quiz question cite the page or cell it was drawn from.

This stage is deliberately deterministic. The model is not asked to outline a document it
could mis-transcribe; it is handed clean units later, for writing quizzes and summaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ingest.base import Block, BlockKind, ParsedDocument

# Sized for bge-m3 retrieval: large enough to hold an idea, small enough to be specific
TARGET_CHUNK_CHARS = 1_200
MAX_CHUNK_CHARS = 2_000
CHUNK_OVERLAP_CHARS = 150

# Below this, a "topic" is a stray heading rather than real content
MIN_TOPIC_CHARS = 80

# Used when a document has no headings at all
FALLBACK_TOPIC_CHARS = 3_000

MAX_TITLE_CHARS = 200

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(slots=True)
class Chunk:
    """A retrievable passage, ready to embed."""

    text: str
    # Merged references of every block in the chunk, e.g. [{"page": 3}, {"page": 4}]
    source_refs: list[dict] = field(default_factory=list)
    # Titles from the root down to this chunk's topic, for display and citation
    topic_path: list[str] = field(default_factory=list)
    position: int = 0


@dataclass(slots=True)
class Topic:
    title: str
    level: int
    blocks: list[Block] = field(default_factory=list)
    children: list[Topic] = field(default_factory=list)
    position: int = 0

    @property
    def text_length(self) -> int:
        return sum(len(b.text) for b in self.blocks)

    def walk(self) -> list[Topic]:
        """This topic and all descendants, in reading order."""
        found = [self]
        for child in self.children:
            found.extend(child.walk())
        return found


@dataclass(slots=True)
class StructuredDocument:
    topics: list[Topic] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def all_topics(self) -> list[Topic]:
        found: list[Topic] = []
        for topic in self.topics:
            found.extend(topic.walk())
        return found


def structure(document: ParsedDocument, *, fallback_title: str = "Untitled") -> StructuredDocument:
    """Group a parsed document into topics and chunks."""
    blocks = [b for b in document.blocks if b.text]
    if not blocks:
        return StructuredDocument(meta={"topics": 0, "chunks": 0, "strategy": "empty"})

    headings = [b for b in blocks if b.kind is BlockKind.HEADING]
    if headings:
        roots = _split_by_headings(blocks, document.title or fallback_title)
        strategy = "headings"
    else:
        roots = _split_without_headings(blocks, document.title or fallback_title)
        strategy = "pages" if _has_pages(blocks) else "size"

    roots = _drop_empty(roots)
    _number(roots)

    chunks: list[Chunk] = []
    for topic in _iter_all(roots):
        chunks.extend(_chunk_topic(topic, _path_to(roots, topic)))
    for index, chunk in enumerate(chunks):
        chunk.position = index

    return StructuredDocument(
        topics=roots,
        chunks=chunks,
        meta={
            "topics": sum(1 for _ in _iter_all(roots)),
            "chunks": len(chunks),
            "strategy": strategy,
            "characters": sum(len(b.text) for b in blocks),
        },
    )


# ---------- topic building ----------


def _split_by_headings(blocks: list[Block], document_title: str) -> list[Topic]:
    """Build a tree from heading levels.

    A heading deeper than the current one nests inside it; a heading at the same or
    shallower level closes topics until it finds its parent. Content appearing before
    any heading becomes a preamble topic named after the document.
    """
    roots: list[Topic] = []
    stack: list[Topic] = []

    # Anything before the first heading is a preamble. It is a sibling of the headings
    # that follow, not their parent, so it never joins the nesting stack.
    first_heading = next(i for i, b in enumerate(blocks) if b.kind is BlockKind.HEADING)
    if first_heading:
        roots.append(Topic(_trim(document_title), level=1, blocks=list(blocks[:first_heading])))

    for block in blocks[first_heading:]:
        if block.kind is not BlockKind.HEADING:
            if stack:
                stack[-1].blocks.append(block)
            continue

        level = block.level or 1
        topic = Topic(_trim(block.text), level=level)

        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            stack[-1].children.append(topic)
        else:
            roots.append(topic)
        stack.append(topic)

    return roots


def _split_without_headings(blocks: list[Block], document_title: str) -> list[Topic]:
    """Fall back to page boundaries, or to fixed-size groups when there are none.

    Slide decks recovered by OCR land here: one page is one slide, which is already a
    sensible teaching unit.
    """
    title = _trim(document_title)
    if _has_pages(blocks):
        by_page: dict[int, Topic] = {}
        for block in blocks:
            page = block.source_ref.get("page", 0)
            topic = by_page.get(page)
            if topic is None:
                topic = by_page[page] = Topic(f"{title} — page {page}", level=1)
            topic.blocks.append(block)
        return [by_page[page] for page in sorted(by_page)]

    topics: list[Topic] = []
    current = Topic(title, level=1)
    for block in blocks:
        if current.text_length + len(block.text) > FALLBACK_TOPIC_CHARS and current.blocks:
            topics.append(current)
            current = Topic(f"{title} — part {len(topics) + 1}", level=1)
        current.blocks.append(block)
    if current.blocks:
        topics.append(current)
    return topics


def _has_pages(blocks: list[Block]) -> bool:
    return any("page" in b.source_ref for b in blocks)


def _has_substance(topic: Topic) -> bool:
    """Whether a topic is worth keeping.

    Prose has to clear a minimum length, since a stray line under a divider heading
    teaches nothing. Code and tables are kept whatever their length: three short cells
    are a complete worked example, and terseness is normal for them.
    """
    if any(b.kind in (BlockKind.CODE, BlockKind.TABLE) for b in topic.blocks):
        return True
    return topic.text_length >= MIN_TOPIC_CHARS


def _drop_empty(topics: list[Topic]) -> list[Topic]:
    """Remove headings that carry no real content, lifting their children up.

    Decks often have a section divider slide whose only content is its own title.
    """
    kept: list[Topic] = []
    for topic in topics:
        topic.children = _drop_empty(topic.children)
        if _has_substance(topic) or topic.children:
            kept.append(topic)
        else:
            kept.extend(topic.children)
    return kept


def _number(topics: list[Topic], start: int = 0) -> int:
    position = start
    for topic in topics:
        topic.position = position
        position += 1
        position = _number(topic.children, position)
    return position


def _iter_all(topics: list[Topic]):
    for topic in topics:
        yield from topic.walk()


def _path_to(roots: list[Topic], target: Topic) -> list[str]:
    """Titles from a root down to `target`."""

    def search(topics: list[Topic], trail: list[str]) -> list[str] | None:
        for topic in topics:
            here = [*trail, topic.title]
            if topic is target:
                return here
            found = search(topic.children, here)
            if found:
                return found
        return None

    return search(roots, []) or [target.title]


# ---------- chunking ----------


def _chunk_topic(topic: Topic, topic_path: list[str]) -> list[Chunk]:
    """Cut one topic's own blocks into chunks.

    Code is never merged with prose: a quiz written from a chunk should not mistake a
    code sample for an explanation. Consecutive code blocks *are* merged with each
    other, because a run of notebook cells is usually one worked example, and a chunk
    holding only `import numpy as np` is too small to retrieve meaningfully.

    Oversized blocks are split on sentence boundaries.
    """
    chunks: list[Chunk] = []
    buffer: list[Block] = []
    size = 0
    # Prose and code never share a chunk, so the buffer is flushed when the kind changes
    buffered_code = False

    def flush() -> None:
        nonlocal size
        if buffer:
            separator = "\n\n" if not buffered_code else "\n"
            chunks.append(
                Chunk(
                    text=separator.join(b.text for b in buffer),
                    source_refs=_merge_refs(buffer),
                    topic_path=list(topic_path),
                )
            )
            buffer.clear()
            size = 0

    for block in topic.blocks:
        is_code = block.kind is BlockKind.CODE

        if is_code != buffered_code:
            flush()
            buffered_code = is_code

        if len(block.text) > MAX_CHUNK_CHARS:
            flush()
            for piece in _split_long(block.text):
                chunks.append(
                    Chunk(text=piece, source_refs=[dict(block.source_ref)], topic_path=list(topic_path))
                )
            continue

        if size + len(block.text) > TARGET_CHUNK_CHARS and buffer:
            tail = buffer[-1] if len(buffer) > 1 else None
            flush()
            # Repeat the previous block when it is small, so context survives the cut.
            # Only for prose: duplicating a code line would read as running it twice.
            if not is_code and tail is not None and len(tail.text) <= CHUNK_OVERLAP_CHARS:
                buffer.append(tail)
                size = len(tail.text)

        buffer.append(block)
        size += len(block.text)

    flush()
    return chunks


def _split_long(text: str) -> list[str]:
    """Split oversized text on sentence boundaries, falling back to a hard cut."""
    sentences = SENTENCE_END.split(text)
    pieces: list[str] = []
    current = ""

    for sentence in sentences:
        while len(sentence) > MAX_CHUNK_CHARS:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:MAX_CHUNK_CHARS])
            sentence = sentence[MAX_CHUNK_CHARS:]
        if current and len(current) + len(sentence) + 1 > TARGET_CHUNK_CHARS:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()

    if current:
        pieces.append(current)
    return [p for p in pieces if p.strip()]


def _merge_refs(blocks: list[Block]) -> list[dict]:
    """Distinct source references, in order of first appearance."""
    seen: list[dict] = []
    for block in blocks:
        if block.source_ref and block.source_ref not in seen:
            seen.append(dict(block.source_ref))
    return seen


def _trim(title: str) -> str:
    title = " ".join(title.split())
    return title[:MAX_TITLE_CHARS] if title else "Untitled"
