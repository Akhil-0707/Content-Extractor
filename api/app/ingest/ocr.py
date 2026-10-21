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
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)

TESSERACT = "tesseract"
LANGUAGE = "eng"
TIMEOUT_SECONDS = 120

# "Assume a single column of text of variable sizes" — measured as the best fit for
# slides, which mix a large title with smaller body text. The default (3) fragments
# display titles; sparse modes (11/12) read line-art diagrams as streams of junk.
PAGE_SEGMENTATION_MODE = "4"

# A real word: three or more letters in a row. Diagram edges and stray marks come back
# as one- and two-letter fragments, so a line containing none is noise rather than text.
WORD_RE = re.compile(r"[A-Za-z]{3,}")


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
        [TESSERACT, "stdin", "stdout", "-l", LANGUAGE, "--psm", PAGE_SEGMENTATION_MODE],
        input=png,
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"Tesseract failed: {message[:200]}")
    return drop_noise(result.stdout.decode("utf-8", "replace"))


def drop_noise(text: str) -> str:
    """Remove lines that contain no readable word.

    Slides put text over illustrations, and OCR reports the drawing's edges as short
    character fragments. Keeping them would feed nonsense to the quiz writer. A line
    survives if it holds at least one run of three or more letters, which keeps short
    real headings such as "Part 2" while dropping debris like "=e ' Ss eR i".
    """
    return "\n".join(line for line in text.splitlines() if WORD_RE.search(line))
