"""Experiment 37 Q4: token recall on the script and handwriting set.

    uv run python experiments/37-.../score_recall.py --engine dots-mocr

For every page of ``E-script`` the engine's Markdown is scored against the
Experiment 33 reference transcription with the Experiment 33 tokeniser
(``build_labels.tokens`` and ``build_labels.recall``, imported). The
reference is the body text of the split transcript when it exists, else the
first transcription, the same rule as ``local_ocr._reference``. The
Experiment 33 local-tier recall comes from ``output/local_ocr/pages.json``
(same pages, ``body_recall``).

Two views, both reported:
- ``all``: a page with no output (timeout, empty result) scores 0.0;
- ``with_output``: only pages that returned text.

Writes ``output/recall_<engine>.json`` atomically. Reported, not gated.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
EXP33 = EXP_DIR.parent / "33-ocr-routing-natural-positive-2026-09-17"
sys.path.insert(0, str(EXP33))

from build_labels import recall, tokens  # noqa: E402  (Experiment 33 task 6.7 tokeniser)

TRANSCRIPTS = EXP_DIR / "corpus" / "exp33_transcripts"
SPLIT = EXP_DIR / "corpus" / "exp33_transcripts_split"
LOCAL_OCR = EXP33 / "output" / "local_ocr" / "pages.json"


def reference_tokens(doc_id: str, page: int) -> list[str]:
    """Return the reference body tokens (rule of ``local_ocr._reference``)."""
    stem = f"p{page:03d}.json"
    first = json.loads((TRANSCRIPTS / doc_id / stem).read_text("utf-8"))
    body = first.get("transcription") or ""
    split_path = SPLIT / doc_id / stem
    if split_path.is_file():
        body = json.loads(split_path.read_text("utf-8")).get("body_text") or ""
    return tokens(body)


def summary(values: list[float]) -> dict[str, Any]:
    """Return count, median, mean and the two share cuts of *values*."""
    if not values:
        return {"n": 0}
    n = len(values)
    return {
        "n": n,
        "median": round(statistics.median(values), 4),
        "mean": round(statistics.fmean(values), 4),
        "share_ge_0_8": round(sum(v >= 0.8 for v in values) / n, 4),
        "share_lt_0_5": round(sum(v < 0.5 for v in values) / n, 4),
    }


def main() -> int:
    """Score one engine."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--engine", required=True, choices=("dots-mocr", "paddleocr-vl"))
    args = parser.parse_args()

    plan = json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    system = {
        f"{p['doc_id']}:{p['page']}": p["writing_system"]
        for p in plan["sets"]["script_handwriting"]["pages"]
    }
    state = json.loads(
        (EXP_DIR / "output" / f"ocr_state_{args.engine}.json").read_text(encoding="utf-8")
    )
    done = state["engines"][args.engine]["runs"].get("E-script", {}).get("pages", {})
    local = {
        f"{r['doc_id']}:{r['page']}": r["body_recall"]
        for r in json.loads(LOCAL_OCR.read_text("utf-8"))["rows"]
    }

    pages: dict[str, dict[str, Any]] = {}
    for key, writing_system in system.items():
        if key not in done:
            continue
        doc_id, page = key.split(":")
        reference = reference_tokens(doc_id, int(page))
        if not reference:
            continue
        entry = done[key]
        out = EXP_DIR / "output" / args.engine / doc_id / f"p{int(page):03d}.md"
        has_output = entry["status"] == "ok" and out.is_file()
        score = recall(out.read_text("utf-8"), reference) if has_output else 0.0
        pages[key] = {
            "writing_system": writing_system,
            "reference_tokens": len(reference),
            "status": entry["status"] if has_output else entry.get("code", entry["status"]),
            "has_output": has_output,
            "recall": round(score, 4),
            "local_tier_recall": local.get(key),
        }

    by_system: dict[str, dict[str, Any]] = {}
    for writing_system in sorted({p["writing_system"] for p in pages.values()} | {"ALL"}):
        rows = [p for p in pages.values() if writing_system in ("ALL", p["writing_system"])]
        paired = [p for p in rows if p["local_tier_recall"] is not None]
        by_system[writing_system] = {
            "scored_pages": len(rows),
            "pages_without_output": sum(not p["has_output"] for p in rows),
            "all": summary([p["recall"] for p in rows]),
            "with_output": summary([p["recall"] for p in rows if p["has_output"]]),
            "local_tier_same_pages": summary([p["local_tier_recall"] for p in paired]),
            "engine_same_pages_as_local": summary([p["recall"] for p in paired]),
        }
    result = {
        "engine": args.engine,
        "e_script_pages_planned": len(system),
        "e_script_pages_finished": len(pages),
        "tokeniser": "experiments/33-.../build_labels.py tokens() and recall(), imported",
        "reference": (
            "body_text of the split transcript when present, "
            "else the first transcription (local_ocr._reference)"
        ),
        "by_writing_system": by_system,
        "pages": pages,
    }
    target = EXP_DIR / "output" / f"recall_{args.engine}.json"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(target)
    print(f"{args.engine}: {len(pages)} of {len(system)} E-script pages scored")
    for name, row in by_system.items():
        e, loc = row["engine_same_pages_as_local"], row["local_tier_same_pages"]
        print(
            f"  {name:16s} n={row['scored_pages']:3d} no-output={row['pages_without_output']:2d} "
            f"median all={row['all'].get('median')} "
            f"with-output={row['with_output'].get('median')} | "
            f"vs local tier on {e.get('n', 0)} paired pages: "
            f"engine {e.get('median')} / local {loc.get('median')}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
