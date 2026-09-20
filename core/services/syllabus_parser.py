"""Parse a PDF syllabus into a single cleaned string for LLM inference.

Deliberately coarse-grained: no schedule detection or section splitting —
the LLM receives the full document text and does its own categorization.
The only enrichment is in-place date annotation: every detected date gets a
normalized ISO form appended in brackets ("Sept. 1 [2009-09-01]"), with the
year inferred from the document header when the text omits one.

Usage:
    python -m core.services.syllabus_parser path/to/syllabus.pdf
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO, Optional, Union

from dateutil import parser as dateutil_parser
from pypdf import PdfReader

PdfSource = Union[str, Path, BinaryIO]

# --------------------------------------------------------------------------
# Regexes
# --------------------------------------------------------------------------

_MONTHS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)

# "Sep 19", "September 19th", "Sept. 19, 2026", "Dec. 14-19" (range —
# the annotation goes after the whole match).
_MONTH_DATE_RE = re.compile(
    rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?"
    rf"(?:\s*[-–—]\s*\d{{1,2}}(?:st|nd|rd|th)?)?\b",
    re.IGNORECASE,
)
# "9/19", "09/19/2026" — only "/" counts without a year. "-" without a year
# is almost always a time or page range ("5-6 P.M.", "pp. 3-10").
_NUMERIC_DATE_RE = re.compile(
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{1,2}-\d{1,2}-\d{2,4}\b")
# A trailing range end ("-19") is stripped before parsing — "Dec. 14-19"
# annotates as Dec 14.
_RANGE_END_RE = re.compile(r"[-–—]\s*\d{1,2}(?:st|nd|rd|th)?(?:\s*,?\s*\d{4})?$")
# Words like "Ch." or "pp." before a numeric token mean it's a reference
# ("Ch. 1-2", "pp. 3-10"), not a date.
_REF_CONTEXT_RE = re.compile(
    r"(?:ch|chap|chapter|pp|p|pg|page|sec|sect|section|fig|ex|exer|exercise|"
    r"no|num|weeks?|lectures?|sessions?|units?|modules?|parts?|days?|rows?|#)"
    r"\s*\.?\s*$",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
# Page furniture: "7", "Page 3", "3 of 12"
_PAGE_ARTIFACT_RE = re.compile(r"^(page\s+)?\d+(\s+of\s+\d+)?\.?$", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


# --------------------------------------------------------------------------
# Text extraction & cleanup
# --------------------------------------------------------------------------

def _extract_pages(source: PdfSource) -> list:
    """Return the raw text of each page, preferring layout mode."""
    reader = PdfReader(source)
    pages = []
    for page in reader.pages:
        text = ""
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except Exception:
            pass
        if len(text.strip()) < 20:
            # Layout mode sometimes yields nothing; try the default mode.
            try:
                fallback = page.extract_text() or ""
                if len(fallback.strip()) > len(text.strip()):
                    text = fallback
            except Exception:
                pass
        pages.append(text)
    return pages


def _clean_lines(pages: list) -> list:
    """Whitespace-normalized lines with page numbers/artifacts dropped."""
    lines = []
    for page in pages:
        for raw in page.splitlines():
            line = _WHITESPACE_RE.sub(" ", raw.replace("\ufffd", "")).strip()
            if line and not _PAGE_ARTIFACT_RE.match(line):
                lines.append(line)
    return lines


def _detect_year(lines: list) -> int:
    """Use the first 4-digit year found near the top of the document."""
    for line in lines[:50]:
        m = _YEAR_RE.search(line)
        if m:
            return int(m.group(1))
    return date.today().year


# --------------------------------------------------------------------------
# Date annotation
# --------------------------------------------------------------------------

def _try_parse(raw: str, year: int):
    try:
        return dateutil_parser.parse(
            raw, default=datetime(year, 1, 1), dayfirst=False
        ).date().isoformat()
    except (ValueError, OverflowError):
        return None


def _annotate_dates(line: str, year: int) -> str:
    """Append " [YYYY-MM-DD]" after each parseable date in the line.

    The raw text is never altered — annotations are additive only, so the
    LLM sees both the syllabus's own phrasing and normalized dates.
    """
    matches = [m for m in _MONTH_DATE_RE.finditer(line)]
    matches += [m for m in _NUMERIC_DATE_RE.finditer(line)
                if not _REF_CONTEXT_RE.search(line[:m.start()])]
    matches.sort(key=lambda m: m.start())

    insertions = []
    last_end = -1
    for m in matches:
        if m.start() < last_end:
            continue  # overlapping match already covered
        iso = _try_parse(_RANGE_END_RE.sub("", m.group(0)), year)
        if iso:
            insertions.append((m.end(), iso))
            last_end = m.end()

    for end, iso in reversed(insertions):
        line = f"{line[:end]} [{iso}]{line[end:]}"
    return line


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def parse_syllabus_pdf(
    source: PdfSource,
    *,
    default_year: Optional[int] = None,
    max_lines: int = 800,
) -> str:
    """Parse a PDF syllabus and return one cleaned string for an LLM.

    ``source`` may be a filesystem path or a binary file object (e.g. a
    Django ``UploadedFile``). ``default_year`` overrides year inference for
    dates that don't specify one. ``max_lines`` bounds the output for very
    long documents.
    """
    pages = _extract_pages(source)
    lines = _clean_lines(pages)
    if not lines:
        return (
            "WARNING: no extractable text found — the PDF is probably a "
            "scanned image and needs OCR before parsing."
        )

    year = default_year or _detect_year(lines)
    out = [f"PAGES: {len(pages)}", ""]
    out.extend(_annotate_dates(line, year) for line in lines[:max_lines])
    if len(lines) > max_lines:
        out.append(f"... ({len(lines) - max_lines} lines truncated)")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m core.services.syllabus_parser <file.pdf>")
    # PDFs can contain glyphs the Windows console can't encode.
    sys.stdout.reconfigure(errors="replace")
    print(parse_syllabus_pdf(sys.argv[1]))
