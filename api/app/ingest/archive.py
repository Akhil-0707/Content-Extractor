"""Safe expansion of uploaded ZIP archives.

Archives arrive from trainers, so they are untrusted input. Three guards:

- **Path traversal**: entry names like `../../etc/passwd` or absolute paths are rejected,
  so nothing can be written outside the extraction root.
- **Zip bombs**: a small archive can expand to terabytes. Both the per-entry and total
  uncompressed size are capped, and entries with an absurd compression ratio are skipped.
- **Nesting**: archives inside archives are not followed.

Entries are streamed and checked while reading, because the size recorded in the archive
header is attacker-controlled and may lie.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.ingest.base import ParseError

MAX_ENTRY_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_ENTRIES = 5_000
# A legitimate document rarely compresses better than ~100x; 1000x signals a bomb
MAX_COMPRESSION_RATIO = 1_000
READ_CHUNK = 1024 * 1024

SKIP_SUFFIXES = (".zip", ".rar", ".7z", ".tar", ".gz")


@dataclass(slots=True)
class ArchiveMember:
    name: str
    data: bytes


@dataclass(slots=True)
class ArchiveContents:
    """What came out of an archive, and what did not.

    Skipped entries are reported rather than dropped, so a trainer can see why part of
    their upload produced nothing.
    """

    members: list[ArchiveMember] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def _is_safe_name(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return not (path.is_absolute() or any(part == ".." for part in path.parts))


def _read_guarded(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    """Read one entry, stopping if it exceeds the cap while decompressing."""
    chunks: list[bytes] = []
    total = 0
    with archive.open(info) as source:
        while chunk := source.read(READ_CHUNK):
            total += len(chunk)
            if total > MAX_ENTRY_BYTES:
                raise ParseError(f"Entry too large when expanded: {info.filename}")
            chunks.append(chunk)
    return b"".join(chunks)


def expand(raw: bytes, *, skip_nested_archives: bool = True) -> ArchiveContents:
    """Return the archive's file entries. Raises ParseError if the archive itself is unsafe."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ParseError(f"Not a readable zip archive: {exc}") from exc

    infos = [i for i in archive.infolist() if not i.is_dir()]
    if len(infos) > MAX_ENTRIES:
        raise ParseError(f"Archive has too many entries ({len(infos)} > {MAX_ENTRIES})")

    contents = ArchiveContents()
    total = 0
    with archive:
        for info in infos:
            if not _is_safe_name(info.filename):
                raise ParseError(f"Unsafe path in archive: {info.filename}")
            if skip_nested_archives and info.filename.lower().endswith(SKIP_SUFFIXES):
                contents.skipped.append(
                    (info.filename, "Archives inside archives are not opened; upload it separately")
                )
                continue
            if info.compress_size and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
                raise ParseError(f"Suspicious compression ratio: {info.filename}")

            data = _read_guarded(archive, info)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ParseError("Archive expands to more than the allowed total size")
            contents.members.append(ArchiveMember(info.filename, data))

    return contents
