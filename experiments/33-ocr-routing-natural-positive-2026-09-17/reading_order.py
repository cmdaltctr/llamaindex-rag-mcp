"""Experiment 33 LiteParse reading-order evidence gate (change liteparse-reading-order).

Scores the LiteParse join against the frozen reference transcriptions on the
operator-reviewed pages, before and after the change, on two measures: token
recall (did the words survive) and reading order (longest common subsequence of
the reader's token stream against the reference stream, divided by its length).

The code under test is loaded from another checkout, the way ``route.py`` does
it, so the measurement always describes a named worktree:

    PDFIUM_LIB_PATH=... uv run python reading_order.py \\
        --code-root ../llamaindex-rag-mcp-feat-page-level-ocr-routing

Read-only with respect to the experiment: it never touches labels and runs no
OCR. It refuses to run unless the freeze verifies.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR))

import freeze  # noqa: E402
from build_labels import TRANSCRIPTS_DIR, recall, tokens  # noqa: E402
from compare_readers import order_score  # noqa: E402

OUT = EXP_DIR / "output" / "reading_order.json"
#: Pages the operator flagged whose score must not fall (change design gate 2).
GUARD_PAGES = (("bd02", 1), ("tl03", 5))


def _baseline(items: list) -> str:
    """Return the join the adapter used before the change: library order."""
    return "\n".join(item.text for item in items)


def main() -> int:
    """Score both joins on every reviewed page and report the gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--code-root", type=Path, required=True, help="checkout whose src/ is measured"
    )
    args = parser.parse_args()

    drift = freeze.check()
    if drift:
        print("freeze check failed: " + "; ".join(drift), file=sys.stderr)
        return 1
    if not os.environ.get("PDFIUM_LIB_PATH"):
        print("PDFIUM_LIB_PATH is not set", file=sys.stderr)
        return 1
    if "omrg" in sys.modules:
        raise SystemExit("omrg was imported before --code-root took effect")

    code_root = args.code_root.resolve()
    sys.path.insert(0, str(code_root / "src"))
    import omrg
    from omrg.integrations.pdf.liteparse import _gutter_centre, _order_by_column

    loaded = Path(omrg.__file__).resolve()
    if code_root not in loaded.parents:
        raise SystemExit(f"omrg loaded from {loaded}, not from {code_root}")

    from liteparse import LiteParse

    sources = {
        d["doc_id"]: d for d in json.loads((EXP_DIR / "sources.json").read_text())["documents"]
    }
    sample = json.loads((EXP_DIR / "spot_check.json").read_text())["random_sample"]

    parsed: dict[str, object] = {}
    rows = []
    for entry in sample:
        doc_id, page_number = entry["doc_id"], entry["page"]
        if doc_id not in parsed:
            path = str(EXP_DIR / sources[doc_id]["local_path"])
            parsed[doc_id] = LiteParse(ocr_enabled=False, quiet=True).parse(path)
        pages = [p for p in parsed[doc_id].pages if p.page_num == page_number]
        transcript = TRANSCRIPTS_DIR / doc_id / f"p{page_number:03d}.json"
        if not pages or not transcript.exists():
            continue
        items = pages[0].text_items
        reference = tokens(json.loads(transcript.read_text("utf-8")).get("transcription") or "")
        if not reference or not items:
            continue
        gutter = _gutter_centre(items)
        before = _baseline(items)
        after = _baseline(_order_by_column(items, gutter) if gutter is not None else items)
        rows.append(
            {
                "doc_id": doc_id,
                "page": page_number,
                "page_class": "multi_column" if gutter is not None else "single",
                "note": entry.get("note") or "",
                "order_before": order_score(before, reference),
                "order_after": order_score(after, reference),
                "recall_before": round(recall(before, reference), 4),
                "recall_after": round(recall(after, reference), 4),
                "content_preserved": sorted(before.split("\n")) == sorted(after.split("\n")),
            }
        )
        print(
            f"[order] {doc_id} p{page_number}: {rows[-1]['page_class']} "
            f"{rows[-1]['order_before']:.2f} -> {rows[-1]['order_after']:.2f}",
            flush=True,
        )

    multi = [r for r in rows if r["page_class"] == "multi_column"]
    regressions = [r for r in rows if r["order_after"] < r["order_before"] - 0.001]
    recall_moves = [r for r in rows if abs(r["recall_after"] - r["recall_before"]) > 0.01]
    guards = {
        f"{d}_p{p}": r for d, p in GUARD_PAGES for r in rows if (r["doc_id"], r["page"]) == (d, p)
    }
    summary = {
        "code_root": str(code_root),
        "pages_scored": len(rows),
        "by_class": {
            name: {
                "pages": len(group),
                "median_order_before": round(
                    statistics.median(r["order_before"] for r in group), 4
                ),
                "median_order_after": round(statistics.median(r["order_after"] for r in group), 4),
                "median_recall_before": round(
                    statistics.median(r["recall_before"] for r in group), 4
                ),
                "median_recall_after": round(
                    statistics.median(r["recall_after"] for r in group), 4
                ),
            }
            for name in ("multi_column", "single")
            if (group := [r for r in rows if r["page_class"] == name])
        },
        "gate": {
            "multi_column_median_order_after": (
                round(statistics.median(r["order_after"] for r in multi), 4) if multi else None
            ),
            "guard_pages": {
                key: {
                    "before": r["order_before"],
                    "after": r["order_after"],
                    "class": r["page_class"],
                }
                for key, r in guards.items()
            },
            "order_regressions": [(r["doc_id"], r["page"]) for r in regressions],
            "recall_changes_over_0_01": [(r["doc_id"], r["page"]) for r in recall_moves],
            "content_preserved_on_every_page": all(r["content_preserved"] for r in rows),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"summary": summary, "pages": rows}, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
