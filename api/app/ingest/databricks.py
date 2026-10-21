"""Parser for Databricks notebook HTML exports.

These look like ordinary web pages, but the notebook itself is stashed in a JavaScript
variable and encoded twice:

    __DATABRICKS_NOTEBOOK_MODEL = '<base64>'   ->  URL-encoded JSON  ->  notebook

Stripping HTML tags instead yields mostly bundled JS and deployment settings, so the
real content has to be decoded. Verified against all 269 exports in the first corpus.

Cells carry a magic prefix (`%md`, `%sql`, …) that sets the language for that cell and
is not part of the content.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import urllib.parse

from app.ingest.base import Block, BlockKind, ParsedDocument, ParseError, split_markdown

MODEL_RE = re.compile(rb"__DATABRICKS_NOTEBOOK_MODEL\s*=\s*(['\"])(.*?)\1", re.S)
MAGIC_RE = re.compile(r"^\s*%(\w+)\s*\n?", re.I)

# `%md` is prose; everything else is executable
TEXT_MAGICS = {"md", "markdown"}


def looks_like_databricks(raw: bytes) -> bool:
    return MODEL_RE.search(raw) is not None


def _decode_model(raw: bytes) -> dict:
    match = MODEL_RE.search(raw)
    if match is None:
        raise ParseError("No Databricks notebook model found in this HTML file")
    try:
        decoded = base64.b64decode(match.group(2)).decode("utf-8", "replace")
        return json.loads(urllib.parse.unquote(decoded))
    except (binascii.Error, ValueError) as exc:
        raise ParseError(f"Could not decode the Databricks notebook model: {exc}") from exc


def _split_magic(command: str, default_language: str) -> tuple[str, str]:
    """Return (language, body) after removing any leading `%magic` line."""
    match = MAGIC_RE.match(command)
    if match is None:
        return default_language, command
    return match.group(1).lower(), command[match.end() :]


def parse(raw: bytes) -> ParsedDocument:
    model = _decode_model(raw)
    default_language = (model.get("language") or "python").lower()

    # Databricks stores display order in `position`, which need not match list order
    commands = sorted(
        model.get("commands") or [],
        key=lambda c: (c.get("position") if isinstance(c.get("position"), (int, float)) else 0),
    )

    blocks: list[Block] = []
    code_cells = text_cells = 0

    for index, command in enumerate(commands):
        body = command.get("command") or ""
        if not body.strip():
            continue
        language, body = _split_magic(body, default_language)
        ref = {"cell": index}

        if language in TEXT_MAGICS:
            text_cells += 1
            blocks.extend(split_markdown(body, ref))
        else:
            code_cells += 1
            blocks.append(Block(BlockKind.CODE, body, ref, language=language))

    blocks = [b for b in blocks if b.text]
    return ParsedDocument(
        blocks=blocks,
        title=model.get("name") or None,
        meta={
            "source": "databricks_html",
            "cells": len(commands),
            "text_cells": text_cells,
            "code_cells": code_cells,
            "language": default_language,
        },
    )
