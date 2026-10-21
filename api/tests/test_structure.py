"""Structuring agent tests.

Fixtures are synthetic: the real corpus is confidential.
"""

import pytest

from app.ingest.base import Block, BlockKind, ParsedDocument
from app.ingest.structure import (
    MAX_CHUNK_CHARS,
    MIN_TOPIC_CHARS,
    TARGET_CHUNK_CHARS,
    Chunk,
    structure,
)


def heading(text: str, level: int, **ref) -> Block:
    return Block(BlockKind.HEADING, text, ref, level=level)


def text(body: str, **ref) -> Block:
    return Block(BlockKind.TEXT, body, ref)


def code(body: str, **ref) -> Block:
    return Block(BlockKind.CODE, body, ref, language="python")


def prose(chars: int, word: str = "word") -> str:
    """Filler long enough to clear the minimum-topic threshold."""
    return " ".join([word] * (chars // (len(word) + 1) + 1))


def titles(result) -> list[str]:
    return [t.title for t in result.all_topics()]


# ---------- topic tree ----------


def test_headings_build_a_nested_tree():
    doc = ParsedDocument(
        blocks=[
            heading("Retrieval", 1),
            text(prose(200)),
            heading("Embeddings", 2),
            text(prose(200)),
            heading("Chunking", 2),
            text(prose(200)),
            heading("Agents", 1),
            text(prose(200)),
        ]
    )
    result = structure(doc)

    assert [t.title for t in result.topics] == ["Retrieval", "Agents"]
    assert [c.title for c in result.topics[0].children] == ["Embeddings", "Chunking"]
    assert result.meta["strategy"] == "headings"


def test_deeper_heading_nests_and_shallower_closes():
    doc = ParsedDocument(
        blocks=[
            heading("A", 1),
            text(prose(200)),
            heading("A.1", 3),  # jumps two levels: still a child of A
            text(prose(200)),
            heading("B", 1),
            text(prose(200)),
        ]
    )
    result = structure(doc)

    assert [t.title for t in result.topics] == ["A", "B"]
    assert [c.title for c in result.topics[0].children] == ["A.1"]


def test_content_before_the_first_heading_becomes_a_preamble():
    doc = ParsedDocument(
        blocks=[text(prose(200)), heading("Later", 1), text(prose(200))],
        title="Course Intro",
    )
    result = structure(doc)
    assert [t.title for t in result.topics] == ["Course Intro", "Later"]


def test_divider_headings_without_content_are_dropped():
    """A section-divider slide carries only its own title and teaches nothing."""
    doc = ParsedDocument(
        blocks=[heading("Part One", 1), heading("Real Topic", 2), text(prose(300))]
    )
    result = structure(doc)

    # "Part One" is empty but keeps its child, so it stays as a parent
    assert titles(result) == ["Part One", "Real Topic"]

    # With no child to keep, it disappears entirely
    doc = ParsedDocument(blocks=[heading("Empty", 1), heading("Real", 1), text(prose(300))])
    assert titles(structure(doc)) == ["Real"]


def test_topics_are_numbered_in_reading_order():
    doc = ParsedDocument(
        blocks=[
            heading("One", 1),
            text(prose(200)),
            heading("One.A", 2),
            text(prose(200)),
            heading("Two", 1),
            text(prose(200)),
        ]
    )
    result = structure(doc)
    assert [(t.title, t.position) for t in result.all_topics()] == [
        ("One", 0),
        ("One.A", 1),
        ("Two", 2),
    ]


# ---------- fallbacks for material with no headings ----------


def test_pages_become_topics_when_there_are_no_headings():
    """OCR'd slide decks arrive this way: one page is one slide."""
    doc = ParsedDocument(
        blocks=[
            Block(BlockKind.OCR_TEXT, prose(200), {"page": 1}),
            Block(BlockKind.OCR_TEXT, prose(200), {"page": 2}),
        ],
        title="Deck",
    )
    result = structure(doc)

    assert titles(result) == ["Deck — page 1", "Deck — page 2"]
    assert result.meta["strategy"] == "pages"


def test_unpaginated_text_is_split_by_size():
    doc = ParsedDocument(blocks=[text(prose(2_500)) for _ in range(3)], title="Notes")
    result = structure(doc)

    assert result.meta["strategy"] == "size"
    assert len(titles(result)) > 1
    assert titles(result)[0] == "Notes"


def test_empty_document():
    result = structure(ParsedDocument(blocks=[]))
    assert result.topics == [] and result.chunks == []
    assert result.meta["strategy"] == "empty"


def test_whitespace_only_blocks_are_ignored():
    result = structure(ParsedDocument(blocks=[Block(BlockKind.TEXT, "   ", {})]))
    assert result.meta["strategy"] == "empty"


# ---------- chunking ----------


def test_chunks_stay_near_the_target_size():
    doc = ParsedDocument(blocks=[heading("T", 1), *[text(prose(300)) for _ in range(10)]])
    result = structure(doc)

    assert len(result.chunks) > 1
    assert all(len(c.text) <= TARGET_CHUNK_CHARS * 2 for c in result.chunks)


def test_chunks_carry_topic_path_and_source_refs():
    doc = ParsedDocument(
        blocks=[
            heading("Parent", 1),
            heading("Child", 2),
            text(prose(200), page=7),
            text(prose(200), page=8),
        ]
    )
    chunk = structure(doc).chunks[0]

    assert chunk.topic_path == ["Parent", "Child"]
    assert chunk.source_refs == [{"page": 7}, {"page": 8}]


def test_chunks_are_numbered_consecutively():
    doc = ParsedDocument(blocks=[heading("T", 1), *[text(prose(400)) for _ in range(8)]])
    chunks = structure(doc).chunks
    assert [c.position for c in chunks] == list(range(len(chunks)))


def test_code_is_never_merged_with_prose():
    """A quiz written from a chunk must not mistake a code sample for an explanation."""
    doc = ParsedDocument(
        blocks=[heading("T", 1), text(prose(200)), code("import numpy as np"), text(prose(200))]
    )
    chunks = structure(doc).chunks

    code_chunks = [c for c in chunks if "import numpy" in c.text]
    assert len(code_chunks) == 1
    assert code_chunks[0].text == "import numpy as np"
    assert "word" not in code_chunks[0].text


def test_consecutive_code_cells_merge_into_one_example():
    """A run of small cells is one worked example; alone each is too small to retrieve."""
    doc = ParsedDocument(
        blocks=[
            heading("Demo", 1),
            code("import numpy as np"),
            code("data = np.arange(10)"),
            code("print(data.mean())"),
        ]
    )
    chunks = structure(doc).chunks

    assert len(chunks) == 1
    assert chunks[0].text.splitlines() == [
        "import numpy as np",
        "data = np.arange(10)",
        "print(data.mean())",
    ]


def test_merged_code_still_respects_the_size_target():
    doc = ParsedDocument(blocks=[heading("T", 1), *[code(prose(400, "x=1;")) for _ in range(8)]])
    chunks = structure(doc).chunks

    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)


def test_code_chunks_do_not_repeat_lines_across_a_split():
    """Prose overlaps for context, but a repeated code line would read as running it twice."""
    doc = ParsedDocument(blocks=[heading("T", 1), *[code(f"step_{i}()" + " " * 300) for i in range(10)]])
    chunks = structure(doc).chunks

    calls = [line for c in chunks for line in c.text.splitlines() if line.strip().startswith("step_")]
    assert len(calls) == len(set(calls))


def test_oversized_block_is_split_on_sentence_boundaries():
    sentences = " ".join(f"Sentence number {i} explains a concept." for i in range(200))
    doc = ParsedDocument(blocks=[heading("T", 1), text(sentences)])
    chunks = structure(doc).chunks

    assert len(chunks) > 1
    # No sentence should be cut in half
    assert all(c.text.strip().endswith(".") for c in chunks[:-1])


def test_a_single_unbroken_run_is_still_split():
    doc = ParsedDocument(blocks=[heading("T", 1), text("x" * 9_000)])
    chunks = structure(doc).chunks

    assert len(chunks) > 1
    assert sum(len(c.text) for c in chunks) >= 9_000 - len(chunks)


@pytest.mark.parametrize("title", ["", "   ", None])
def test_missing_titles_fall_back(title):
    doc = ParsedDocument(blocks=[text(prose(200))], title=title)
    assert titles(structure(doc))[0] in ("Untitled", "Untitled".title())


def test_long_titles_are_trimmed():
    doc = ParsedDocument(blocks=[heading("T" * 500, 1), text(prose(200))])
    assert len(titles(structure(doc))[0]) <= 200


def test_short_prose_topics_below_the_threshold_are_dropped():
    doc = ParsedDocument(
        blocks=[heading("Tiny", 1), text("x" * (MIN_TOPIC_CHARS - 10)), heading("Real", 1), text(prose(300))]
    )
    assert titles(structure(doc)) == ["Real"]


def test_short_code_topics_are_kept():
    """Code is terse; a few short cells are still a complete worked example."""
    doc = ParsedDocument(blocks=[heading("Demo", 1), code("x = 1"), heading("Real", 1), text(prose(300))])
    assert titles(structure(doc)) == ["Demo", "Real"]


def test_meta_counts_match_the_result():
    doc = ParsedDocument(blocks=[heading("A", 1), text(prose(2_000)), heading("B", 1), text(prose(2_000))])
    result = structure(doc)

    assert result.meta["topics"] == len(result.all_topics())
    assert result.meta["chunks"] == len(result.chunks)
    assert isinstance(result.chunks[0], Chunk)
