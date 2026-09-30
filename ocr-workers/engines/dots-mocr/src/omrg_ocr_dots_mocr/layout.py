"""Convert dots.mocr layout JSON to per-page Markdown (design D4).

The converter is the Experiment 34 probe converter
(``experiments/34-worker-sample-review-2026-09-19/probe_dots_mocr.py``)
with two changes:

- page-header and page-footer regions are dropped (upstream's ``_nohf``
  behaviour; Experiment 34 counts page furniture as a problem);
- each formula gets exactly one pair of ``$$`` delimiters, whatever the
  model already wrapped it in.

A page whose generation reached the token cap, or whose layout JSON does
not parse, is not usable text: :func:`page_markdown` returns ``""`` and
the reason, and the engine logs the reason on standard error.

This module is pure: no model code, no PyTorch. Tests run it in the
main OMRG environment on the committed Experiment 34 fixtures.
"""

from __future__ import annotations

import json
import re
from typing import Any

#: Layout categories whose text never enters the Markdown.
DROPPED_CATEGORIES = frozenset({"Picture", "Page-header", "Page-footer"})

#: Bump when the Markdown this module emits changes for the same input.
#: It joins the engine's pipeline revision, so a change re-ingests.
CONVERTER_VERSION = "1"

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")
_DISPLAY_OPEN_RE = re.compile(r"^(?:\$\$|\\\[)\s*")
_DISPLAY_CLOSE_RE = re.compile(r"\s*(?:\$\$|\\\])$")

REASON_TOKEN_CAP = "token_cap"  # noqa: S105 - a reason code, not a secret
REASON_UNPARSABLE = "unparsable_layout"


def parse_layout(raw: str) -> list[dict[str, Any]] | None:
    """Return the layout cells in *raw*, or ``None`` when it does not parse.

    Args:
        raw: The decoded model output for one page.

    Returns:
        The list of cell objects. A single object that wraps its cells
        under ``layout`` or ``elements`` is unwrapped.
    """
    text = _FENCE_RE.sub("", raw.strip())
    try:
        cells = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(cells, dict):
        cells = cells.get("layout") or cells.get("elements") or [cells]
    if not isinstance(cells, list):
        return None
    return [cell for cell in cells if isinstance(cell, dict)]


def _formula(body: str) -> str:
    """Return *body* as one display block with exactly one ``$$`` pair."""
    inner = body.strip()
    # Strip every wrapper the model added, however many layers.
    while True:
        stripped = _DISPLAY_CLOSE_RE.sub("", _DISPLAY_OPEN_RE.sub("", inner, count=1), count=1)
        if stripped == inner:
            break
        inner = stripped.strip()
    return f"$$\n{inner}\n$$"


def cells_to_markdown(cells: list[dict[str, Any]]) -> str:
    """Convert layout cells to Markdown in the given reading order.

    Titles become ``#`` headings and section headers ``##`` headings.
    Formulas become display blocks. Tables keep the model's HTML. Other
    text keeps its Markdown. Pictures, page headers and page footers
    are dropped.
    """
    out: list[str] = []
    for cell in cells:
        category = str(cell.get("category", ""))
        body = str(cell.get("text") or "").strip()
        if category in DROPPED_CATEGORIES or not body:
            continue
        if category in ("Title", "Section-header"):
            # The model sometimes emits its own heading marks.
            body = body.lstrip("#").strip()
        if category == "Title":
            out.append(f"# {body}")
        elif category == "Section-header":
            out.append(f"## {body}")
        elif category == "Formula":
            out.append(_formula(body))
        else:
            out.append(body)
    return "\n\n".join(out) + "\n" if out else ""


def page_markdown(raw: str, *, hit_token_cap: bool) -> tuple[str, str | None]:
    """Return one page's Markdown, or ``""`` with the reason it is unusable.

    Args:
        raw: The decoded model output for the page.
        hit_token_cap: Whether generation stopped at the token limit.

    Returns:
        ``(markdown, None)`` for a usable page, else ``("", reason)``
        with :data:`REASON_TOKEN_CAP` or :data:`REASON_UNPARSABLE`.
    """
    if hit_token_cap:
        return "", REASON_TOKEN_CAP
    cells = parse_layout(raw)
    if cells is None:
        return "", REASON_UNPARSABLE
    return cells_to_markdown(cells), None
