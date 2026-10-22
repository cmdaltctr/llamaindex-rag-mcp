"""Maths-page detection from font evidence (design D5).

pdf-inspector drops the very symbols a text heuristic would count (35 of
35 Greek letters lost on ``eq01`` p11, Experiment 34 A4), and a maths
font's Unicode map restores characters but not equation structure. So a
page counts as a maths page when it uses a font from a closed, versioned
list of maths fonts, whether or not that font carries a Unicode map.

Detection reads font resources only, through ``pypdf`` (a core
dependency). It never renders a page, runs OCR, or calls a model or a
network service. Any error while reading returns the empty set: a PDF
whose fonts cannot be read keeps its normal route.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Bump on ANY change to :data:`MATHS_FONT_PATTERNS`. The version joins
#: the source index identity, so a list change re-ingests. A test pins
#: the pattern tuple to this version.
MATHS_DETECTOR_VERSION = 1

#: The closed maths-font list, matched against a normalised ``/BaseFont``
#: (subset prefix stripped, spaces and hyphens removed).
MATHS_FONT_PATTERNS: tuple[str, ...] = (
    # Computer Modern maths, any design size.
    r"^(CMMI|CMMIB|CMSY|CMBSY|CMEX)\d+$",
    # Latin Modern maths: the Type 1 families and the OpenType font.
    r"^LMMath(Italic|Symbols|Extension)\d+",
    r"^LatinModernMath",
    # AMS and Euler symbol fonts, any design size.
    r"^(MSAM|MSBM|EUFM|EUSM|EUEX)\d+$",
    # OpenType maths fonts.
    r"^(CambriaMath|STIXMath|STIXTwoMath|XITSMath|TeXGyre\w+Math|LibertinusMath|AsanaMath|FiraMath)",
)

_COMPILED = tuple(re.compile(pattern) for pattern in MATHS_FONT_PATTERNS)
_SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")

#: How deep Form XObjects nest before the walk stops.
MAX_FORM_DEPTH = 4


def normalise_font_name(base_font: str) -> str:
    """Strip a leading ``/``, any ``ABCDEF+`` subset prefix, spaces and hyphens."""
    name = base_font.lstrip("/")
    name = _SUBSET_PREFIX_RE.sub("", name)
    return name.replace(" ", "").replace("-", "")


def is_maths_font(base_font: str) -> bool:
    """Return True when *base_font* matches the maths-font list."""
    name = normalise_font_name(base_font)
    return any(pattern.search(name) for pattern in _COMPILED)


def maths_font_pages(file: Path | str) -> frozenset[int]:
    """Return the 1-based pages of *file* that use a maths font.

    Args:
        file: Path to the PDF.

    Returns:
        The flagged page numbers. Empty when no page uses a maths font,
        and empty when the font resources cannot be read.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(file))
        flagged = {
            number
            for number, page in enumerate(reader.pages, start=1)
            if _uses_maths_font(_resolve(page.get("/Resources")), depth=0, seen=set())
        }
    except Exception as exc:  # noqa: BLE001 - unreadable fonts keep the normal route
        logger.debug("maths-font detection skipped for %s: %s: %s", file, type(exc).__name__, exc)
        return frozenset()
    return frozenset(flagged)


def _resolve(value: Any) -> Any:
    """Return the object behind an indirect reference, else *value*."""
    getter = getattr(value, "get_object", None)
    return getter() if callable(getter) else value


def _uses_maths_font(resources: Any, *, depth: int, seen: set[int]) -> bool:
    """Walk one resource dictionary and its Form XObjects for a maths font.

    Raises:
        Exception: Whatever pypdf raises on a malformed dictionary; the
            caller turns that into "nothing flagged".
    """
    if resources is None or depth > MAX_FORM_DEPTH:
        return False
    if id(resources) in seen:
        return False
    seen.add(id(resources))
    fonts = _resolve(resources.get("/Font"))
    if fonts is not None:
        for font_ref in fonts.values():
            font = _resolve(font_ref)
            base_font = font.get("/BaseFont")
            if base_font is not None and is_maths_font(str(base_font)):
                return True
    xobjects = _resolve(resources.get("/XObject"))
    if xobjects is None:
        return False
    for xobject_ref in xobjects.values():
        xobject = _resolve(xobject_ref)
        if xobject.get("/Subtype") != "/Form":
            continue
        if _uses_maths_font(_resolve(xobject.get("/Resources")), depth=depth + 1, seen=seen):
            return True
    return False
