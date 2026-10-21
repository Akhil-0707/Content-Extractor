"""Archive, CSV and routing tests.

Archives come from trainers and are untrusted, so the guards matter as much as the
parsing. Fixtures are synthetic: the real corpus is confidential.
"""

import io
import zipfile

import pytest

from app.ingest import archive, registry, tabular
from app.ingest.base import ParseError, UnsupportedFile
from tests.test_ingest import databricks_html, ipynb


def make_zip(entries: dict[str, bytes], *, compress: bool = True) -> bytes:
    buffer = io.BytesIO()
    mode = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(buffer, "w", mode) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buffer.getvalue()


# ---------- archive safety ----------


def test_expand_returns_members():
    contents = archive.expand(make_zip({"a.txt": b"one", "dir/b.txt": b"two"}))
    assert {m.name: m.data for m in contents.members} == {"a.txt": b"one", "dir/b.txt": b"two"}
    assert contents.skipped == []


@pytest.mark.parametrize("name", ["../escape.txt", "../../etc/passwd", "/absolute.txt", "dir/../../out.txt"])
def test_path_traversal_is_rejected(name):
    with pytest.raises(ParseError, match="Unsafe path"):
        archive.expand(make_zip({name: b"x"}))


def test_zip_bomb_ratio_is_rejected():
    # Highly compressible payload: ~10 MB of zeros shrinks to a few KB
    with pytest.raises(ParseError, match="compression ratio"):
        archive.expand(make_zip({"bomb.bin": b"\0" * (10 * 1024 * 1024)}))


def test_oversized_entry_is_rejected(monkeypatch):
    monkeypatch.setattr(archive, "MAX_ENTRY_BYTES", 100)
    monkeypatch.setattr(archive, "MAX_COMPRESSION_RATIO", 10**9)
    with pytest.raises(ParseError, match="too large"):
        archive.expand(make_zip({"big.txt": b"x" * 5_000}))


def test_total_size_cap(monkeypatch):
    monkeypatch.setattr(archive, "MAX_TOTAL_BYTES", 100)
    monkeypatch.setattr(archive, "MAX_COMPRESSION_RATIO", 10**9)
    with pytest.raises(ParseError, match="total size"):
        archive.expand(make_zip({f"f{i}.txt": b"y" * 60 for i in range(5)}))


def test_too_many_entries(monkeypatch):
    monkeypatch.setattr(archive, "MAX_ENTRIES", 3)
    with pytest.raises(ParseError, match="too many entries"):
        archive.expand(make_zip({f"f{i}.txt": b"z" for i in range(5)}))


def test_nested_archives_are_skipped_but_reported():
    """Nothing vanishes silently: the trainer is told why a member produced nothing."""
    inner = make_zip({"deep.txt": b"hidden"})
    contents = archive.expand(make_zip({"outer.txt": b"ok", "inner.zip": inner}))

    assert [m.name for m in contents.members] == ["outer.txt"]
    assert [name for name, _ in contents.skipped] == ["inner.zip"]
    assert "separately" in contents.skipped[0][1]


def test_corrupt_archive_raises():
    with pytest.raises(ParseError, match="readable zip"):
        archive.expand(b"not a zip at all")


# ---------- csv ----------


def test_csv_describes_shape_not_whole_file():
    raw = b"name,score,joined\n" + b"".join(
        f"user{i},{i * 3},2026-01-{i % 28 + 1:02d}\n".encode() for i in range(500)
    )
    doc = tabular.parse(raw, filename="scores.csv")

    schema = doc.blocks[0].text
    assert "500 rows" in schema and "3 columns" in schema
    assert "score — number" in schema
    assert "joined — date" in schema
    # A preview, not the whole dataset
    assert doc.blocks[1].text.count("\n") == tabular.SAMPLE_ROWS
    assert doc.meta["rows"] == 500


def test_csv_detects_categories_and_handles_semicolons():
    raw = b"region;status\n" + b"".join(
        f"r{i};{'open' if i % 2 else 'closed'}\n".encode() for i in range(40)
    )
    schema = tabular.parse(raw).blocks[0].text
    assert "category (2 values)" in schema


def test_empty_csv_raises():
    with pytest.raises(ParseError, match="empty"):
        tabular.parse(b"")


# ---------- routing ----------


@pytest.mark.parametrize(
    ("filename", "raw", "expected"),
    [
        ("slides.pdf", b"%PDF-1.7\n...", "pdf"),
        ("lesson.ipynb", ipynb([]), "notebook"),
        ("data.csv", b"a,b\n1,2", "csv"),
        ("page.html", b"<html><body>hi</body></html>", "html"),
        ("export.html", databricks_html([]), "databricks"),
        ("bundle.zip", make_zip({"a.txt": b"x"}), "zip"),
    ],
)
def test_detect_routes_by_content_then_extension(filename, raw, expected):
    assert registry.detect(filename, raw) == expected


def test_detect_trusts_content_over_a_wrong_extension():
    """Trainers rename files; a PDF called .csv is still a PDF."""
    assert registry.detect("report.csv", b"%PDF-1.4 ...") == "pdf"


@pytest.mark.parametrize(
    ("filename", "message"),
    [("archive.rar", "RAR"), ("talk.mp4", "Video"), ("old.doc", ".docx"), ("thing.xyz", "No parser")],
)
def test_unsupported_types_explain_themselves(filename, message):
    with pytest.raises(UnsupportedFile, match=message):
        registry.detect(filename, b"\x00\x01")


def test_parse_upload_expands_archives_and_reports_skips():
    raw = make_zip(
        {
            "course/lesson.ipynb": ipynb([{"cell_type": "markdown", "source": "# Topic\nBody text."}]),
            "course/export.html": databricks_html([{"command": "%md\n# DB\ncontent", "position": 0}]),
            "course/notes.rar": b"\x00binary",
            "course/empty.csv": b"",
        }
    )
    report = registry.parse_upload("course.zip", raw)

    assert sorted(f.path for f in report.files) == ["course/export.html", "course/lesson.ipynb"]
    assert {name for name, _ in report.skipped} == {"course/notes.rar", "course/empty.csv"}
    assert report.block_count == 4
    assert report.text_length > 0


def test_parse_upload_of_a_single_file():
    report = registry.parse_upload("lesson.ipynb", ipynb([{"cell_type": "markdown", "source": "# A"}]))
    assert len(report.files) == 1 and not report.skipped


def test_parse_upload_records_unsupported_upload_rather_than_raising():
    report = registry.parse_upload("movie.mp4", b"\x00\x00")
    assert report.files == []
    assert report.skipped == [("movie.mp4", registry.KNOWN_UNSUPPORTED[".mp4"])]
