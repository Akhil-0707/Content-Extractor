"""OCR for pages that have no text layer.

Tesseract is used rather than a GPU model: the 4 GB RTX 3050 can hold only one model at
a time, and that budget is reserved for Whisper and the LLM (see the GPU lock in the job
queue). OCR runs on the CPU, where it competes with nothing.

The engine is loaded lazily so the API starts even when Tesseract is not installed —
ingestion workers need it, the web API does not.
"""

from __future__ import annotations

import functools
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

TESSERACT = "tesseract"
LANGUAGE = "eng"
TIMEOUT_SECONDS = 120


class OcrUnavailable(Exception):
    """Raised when no OCR engine is installed."""


@functools.cache
def ocr_available() -> bool:
    return shutil.which(TESSERACT) is not None


def ocr_image(png: bytes) -> str:
    """Return the text found in a PNG image. Raises OcrUnavailable if Tesseract is missing."""
    if not ocr_available():
        raise OcrUnavailable(
            "Tesseract is not installed, so pages without a text layer cannot be read"
        )

    result = subprocess.run(
        [TESSERACT, "stdin", "stdout", "-l", LANGUAGE, "--psm", "3"],
        input=png,
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"Tesseract failed: {message[:200]}")
    return result.stdout.decode("utf-8", "replace")
