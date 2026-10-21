"""Parser tests.

Fixtures are synthetic by design: the real corpus is confidential and must never be
copied into committed files.
"""

import base64
import json
import urllib.parse

import pytest

from app.ingest import databricks, notebook
from app.ingest.base import Block, BlockKind, ParseError, split_markdown


def databricks_html(commands: list[dict], *, name: str = "Lesson", language: str = "python") -> bytes:
    model = {"version": "NotebookV1", "name": name, "language": language, "commands": commands}
    payload = base64.b64encode(urllib.parse.quote(json.dumps(model)).encode()).decode()
    return f"<html><script>__DATABRICKS_NOTEBOOK_MODEL = '{payload}';</script></html>".encode()


def ipynb(cells: list[dict], language: str = "python") -> bytes:
    return json.dumps(
        {"cells": cells, "metadata": {"language_info": {"name": language}}, "nbformat": 4}
    ).encode()


def md_cell(text: str, position: float = 0) -> dict:
    return {"command": f"%md\n{text}", "position": position}


# ---------- shared markdown splitting ----------


def test_split_markdown_separates_headings_from_prose():
    blocks = split_markdown("# Title\nSome prose.\nMore prose.\n## Sub\nTail.", {"cell": 1})
    assert [(b.kind, b.text) for b in blocks] == [
        (BlockKind.HEADING, "Title"),
        (BlockKind.TEXT, "Some prose.\nMore prose."),
        (BlockKind.HEADING, "Sub"),
        (BlockKind.TEXT, "Tail."),
    ]
    assert all(b.source_ref == {"cell": 1} for b in blocks)


def test_split_markdown_blocks_do_not_share_source_ref():
    ref = {"cell": 1}
    blocks = split_markdown("# A\ntext", ref)
    blocks[0].source_ref["page"] = 99
    assert ref == {"cell": 1}
    assert "page" not in blocks[1].source_ref


def test_blank_blocks_are_dropped():
    assert split_markdown("# H\n\n   \n\n", {}) == [Block(BlockKind.HEADING, "H", {}, level=1)]


@pytest.mark.parametrize(("markup", "level"), [("# A", 1), ("### A", 3), ("###### A", 6)])
def test_heading_level_is_recorded_for_nesting(markup, level):
    (block,) = split_markdown(markup, {})
    assert block.level == level


# ---------- databricks ----------


def test_databricks_decodes_the_embedded_model():
    raw = databricks_html([md_cell("# Vectors\nEmbeddings explained."), {"command": "SELECT 1", "position": 1}])
    doc = databricks.parse(raw)

    assert doc.title == "Lesson"
    assert [b.kind for b in doc.blocks] == [BlockKind.HEADING, BlockKind.TEXT, BlockKind.CODE]
    assert doc.meta["text_cells"] == 1 and doc.meta["code_cells"] == 1


def test_databricks_respects_cell_position_not_list_order():
    raw = databricks_html([md_cell("# Second", position=2), md_cell("# First", position=1)])
    assert [b.text for b in databricks.parse(raw).blocks] == ["First", "Second"]


@pytest.mark.parametrize(
    ("command", "expected_language"),
    [("%sql\nSELECT 1", "sql"), ("%scala\nval x = 1", "scala"), ("print(1)", "python")],
)
def test_databricks_magic_sets_language_and_is_stripped(command, expected_language):
    doc = databricks.parse(databricks_html([{"command": command, "position": 0}]))
    (block,) = doc.blocks
    assert block.language == expected_language
    assert not block.text.startswith("%")


def test_databricks_skips_empty_cells():
    raw = databricks_html([{"command": "   ", "position": 0}, md_cell("# Real", position=1)])
    assert [b.text for b in databricks.parse(raw).blocks] == ["Real"]


def test_databricks_detection_and_errors():
    assert databricks.looks_like_databricks(databricks_html([]))
    assert not databricks.looks_like_databricks(b"<html><body>plain page</body></html>")

    with pytest.raises(ParseError):
        databricks.parse(b"<html>no model here</html>")
    with pytest.raises(ParseError):
        databricks.parse(b"<html>__DATABRICKS_NOTEBOOK_MODEL = 'not-base64!!';</html>")


# ---------- jupyter ----------


def test_notebook_splits_markdown_and_keeps_code():
    raw = ipynb(
        [
            {"cell_type": "markdown", "source": ["# Intro\n", "Why RAG matters."]},
            {"cell_type": "code", "source": "import numpy as np"},
        ]
    )
    doc = notebook.parse(raw)

    assert doc.title == "Intro"
    assert [b.kind for b in doc.blocks] == [BlockKind.HEADING, BlockKind.TEXT, BlockKind.CODE]
    assert doc.blocks[-1].language == "python"
    assert doc.blocks[0].source_ref == {"cell": 0}


def test_notebook_ignores_outputs():
    """Stored outputs are the bulk of real notebooks and must not reach the content."""
    raw = ipynb(
        [
            {
                "cell_type": "code",
                "source": "plot()",
                "outputs": [{"data": {"image/png": "A" * 50_000}}],
            }
        ]
    )
    doc = notebook.parse(raw)
    assert doc.text_length < 100
    assert "A" * 20 not in doc.blocks[0].text


def test_notebook_skips_oversized_code_cells():
    raw = ipynb([{"cell_type": "code", "source": "x = '" + "y" * 25_000 + "'"}])
    doc = notebook.parse(raw)
    assert doc.blocks == []
    assert doc.meta["skipped_oversized_cells"] == 1


def test_notebook_teaching_text_excludes_code():
    raw = ipynb(
        [
            {"cell_type": "markdown", "source": "Prose here."},
            {"cell_type": "code", "source": "secret_code_token = 1"},
        ]
    )
    teaching = notebook.parse(raw).teaching_text()
    assert "Prose here." in teaching
    assert "secret_code_token" not in teaching


def test_notebook_rejects_broken_files():
    with pytest.raises(ParseError):
        notebook.parse(b"{not json")
    with pytest.raises(ParseError):
        notebook.parse(b'{"metadata": {}}')
