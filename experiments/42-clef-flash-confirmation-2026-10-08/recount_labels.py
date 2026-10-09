"""Task 3.5 verify: recount labels.json from its rows with independent code.

Recomputes per-document LiteParse junk and healthy counts, the junk-layer flag
and the document label from the page labels, then compares with labels.json.
Exits non-zero on any difference.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LABELS = Path(__file__).resolve().parent / "output" / "labels.json"


def doc_label(counts: dict[str, int], pages: int) -> str:
    """Experiment 33 document rule, written out again."""
    if counts.get("unrecoverable", 0) * 2 >= pages:
        return "unrecoverable"
    if counts.get("needs_ocr", 0) * 10 >= pages:
        return "needs_ocr"
    if (counts.get("needs_ocr", 0) + counts.get("ambiguous", 0)) * 10 < pages:
        return "usable"
    return "ambiguous"


def main() -> int:
    """Compare every document."""
    data = json.loads(LABELS.read_text(encoding="utf-8"))
    errors = []
    for doc_id, doc in data["documents"].items():
        lite = [r for r in data["rows"] if r["doc_id"] == doc_id and r["tier"] == "liteparse"]
        pages: dict[str, int] = {}
        for r in lite:
            pages[r["page_label"]] = pages.get(r["page_label"], 0) + 1
        junk = sum(r["class"] == "junk" for r in lite)
        healthy = sum(r["class"] == "healthy" for r in lite)
        expected = {
            "pages": len(lite),
            "page_label_counts": pages,
            "label": doc_label(pages, len(lite)),
            "liteparse_junk_pages": junk,
            "liteparse_healthy_pages": healthy,
            "junk_text_layer": junk * 10 >= len(lite),
        }
        errors += [
            f"{doc_id} {key}: {doc[key]} != {value}"
            for key, value in expected.items()
            if doc[key] != value
        ]
    print("\n".join(errors) if errors else f"recount matches ({len(data['documents'])} documents)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
