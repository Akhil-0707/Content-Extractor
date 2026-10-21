"""Parser for CSV and TSV lab datasets.

A dataset is not teaching prose, so the whole file is never ingested — a 100 MB CSV
would bury the course material and teach the model nothing. What matters for quizzes is
the *shape*: what columns exist, what type they hold, and what a row looks like. So the
parser emits a compact description plus a few sample rows.
"""

from __future__ import annotations

import csv
import io
import re

from app.ingest.base import Block, BlockKind, ParsedDocument, ParseError

SAMPLE_ROWS = 5
MAX_SCAN_ROWS = 2_000
MAX_CELL_CHARS = 200

NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _column_type(values: list[str]) -> str:
    filled = [v for v in values if v.strip()]
    if not filled:
        return "empty"
    if all(NUMBER_RE.match(v.strip()) for v in filled):
        return "number"
    if all(DATE_RE.match(v.strip()) for v in filled):
        return "date"
    distinct = {v.strip() for v in filled}
    if len(distinct) <= max(2, len(filled) // 10):
        return f"category ({len(distinct)} values)"
    return "text"


def parse(raw: bytes, *, filename: str = "") -> ParsedDocument:
    text = raw.decode("utf-8-sig", "replace")
    sample = text[:64_000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    try:
        header = next(reader)
    except StopIteration:
        raise ParseError("The file is empty") from None

    rows: list[list[str]] = []
    total = 0
    for row in reader:
        total += 1
        if len(rows) < MAX_SCAN_ROWS:
            rows.append(row)

    columns = []
    for index, name in enumerate(header):
        values = [row[index] for row in rows if index < len(row)]
        columns.append(f"{name.strip() or f'column {index + 1}'} — {_column_type(values)}")

    blocks = [
        Block(
            BlockKind.TEXT,
            f"Dataset with {total} rows and {len(header)} columns.\nColumns:\n"
            + "\n".join(f"- {c}" for c in columns),
            {"part": "schema"},
        )
    ]

    preview = [header, *rows[:SAMPLE_ROWS]]
    rendered = "\n".join(
        " | ".join(cell.strip()[:MAX_CELL_CHARS] for cell in row) for row in preview
    )
    if rendered.strip():
        blocks.append(Block(BlockKind.TABLE, rendered, {"part": "sample_rows"}))

    return ParsedDocument(
        blocks=blocks,
        title=filename or None,
        meta={"source": "csv", "rows": total, "columns": len(header), "truncated": total > MAX_SCAN_ROWS},
    )
