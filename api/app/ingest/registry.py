"""Routes a file to the right parser.

Dispatch is by extension, then corrected by content: a `.html` file may be a Databricks
notebook export rather than a web page, and that is only knowable by looking inside. File
names come from trainers' uploads and are not trusted to be accurate.

ZIP archives are expanded and their members parsed individually, which is how the
Databricks course arrives.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.ingest import archive, databricks, html, notebook, office, pdf, tabular
from app.ingest.base import ParsedDocument, ParseError, UnsupportedFile

logger = logging.getLogger(__name__)

# Magic numbers: the first bytes of a file identify its real type
PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK\x03\x04"

EXTENSIONS = {
    ".pdf": "pdf",
    ".ipynb": "notebook",
    ".html": "html",
    ".htm": "html",
    ".docx": "docx",
    ".pptx": "pptx",
    ".csv": "csv",
    ".tsv": "csv",
    ".zip": "zip",
}

# Formats we deliberately do not handle yet, with a reason the trainer can read
KNOWN_UNSUPPORTED = {
    ".rar": "RAR archives are not supported; please upload a ZIP instead",
    ".7z": "7-Zip archives are not supported; please upload a ZIP instead",
    ".doc": "Old .doc files are not supported; please save as .docx",
    ".ppt": "Old .ppt files are not supported; please save as .pptx",
    ".mp4": "Video is not supported yet",
    ".mov": "Video is not supported yet",
    ".mp3": "Audio is not supported yet",
    ".wav": "Audio is not supported yet",
}


@dataclass(slots=True)
class ParsedFile:
    """One parsed file. `path` is the name within an archive, if it came from one."""

    path: str
    document: ParsedDocument


@dataclass(slots=True)
class ParseReport:
    """Everything recovered from one upload, plus what was skipped and why."""

    files: list[ParsedFile] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def block_count(self) -> int:
        return sum(len(f.document.blocks) for f in self.files)

    @property
    def text_length(self) -> int:
        return sum(f.document.text_length for f in self.files)


def detect(filename: str, raw: bytes) -> str:
    """Return a parser name. Raises UnsupportedFile with a readable reason."""
    suffix = PurePosixPath(filename).suffix.lower()

    if raw.startswith(PDF_MAGIC):
        return "pdf"
    if raw.startswith(ZIP_MAGIC) and suffix in (".docx", ".pptx", ".zip"):
        # All three are ZIP containers; trust the extension to tell them apart
        return EXTENSIONS[suffix]

    kind = EXTENSIONS.get(suffix)
    if kind == "html" and databricks.looks_like_databricks(raw):
        return "databricks"
    if kind:
        return kind

    if suffix in KNOWN_UNSUPPORTED:
        raise UnsupportedFile(KNOWN_UNSUPPORTED[suffix])
    raise UnsupportedFile(f"No parser for '{suffix or filename}'")


def parse_file(filename: str, raw: bytes, *, allow_ocr: bool = True) -> ParsedDocument:
    """Parse a single non-archive file."""
    kind = detect(filename, raw)
    if kind == "zip":
        raise ParseError("Use parse_upload() for archives")

    if kind == "pdf":
        return pdf.parse(raw, allow_ocr=allow_ocr)
    if kind == "notebook":
        return notebook.parse(raw)
    if kind == "databricks":
        return databricks.parse(raw)
    if kind == "html":
        return html.parse(raw)
    if kind == "docx":
        return office.parse_docx(raw)
    if kind == "pptx":
        return office.parse_pptx(raw)
    if kind == "csv":
        return tabular.parse(raw, filename=PurePosixPath(filename).name)
    raise UnsupportedFile(f"No parser for '{kind}'")


def parse_upload(filename: str, raw: bytes, *, allow_ocr: bool = True) -> ParseReport:
    """Parse an upload, expanding it first if it is an archive.

    One unreadable member never fails the whole upload: it is recorded in `skipped` so
    the trainer can see exactly what was left out.
    """
    report = ParseReport()

    try:
        kind = detect(filename, raw)
    except UnsupportedFile as exc:
        report.skipped.append((filename, str(exc)))
        return report

    if kind != "zip":
        try:
            report.files.append(ParsedFile(filename, parse_file(filename, raw, allow_ocr=allow_ocr)))
        except (ParseError, UnsupportedFile) as exc:
            report.skipped.append((filename, str(exc)))
        return report

    contents = archive.expand(raw)
    report.skipped.extend(contents.skipped)
    for member in contents.members:
        try:
            document = parse_file(member.name, member.data, allow_ocr=allow_ocr)
        except (ParseError, UnsupportedFile) as exc:
            report.skipped.append((member.name, str(exc)))
            continue
        except Exception:
            logger.exception("Unexpected failure parsing %s", member.name)
            report.skipped.append((member.name, "Unreadable file"))
            continue
        if document.blocks:
            report.files.append(ParsedFile(member.name, document))

    return report
