#!/usr/bin/env python3
"""Freeze the Experiment 34 worker-review sample (task 2.1).

Selects at most 42 pages from the Experiment 33 frozen corpus, including
every operator-spot-checked problem page named in the proposal, plus a
clean born-digital control document. Deterministic: fixed seed, fixed
selection rule. Writes ``sample.json``; the corpus and labels are read
only.

Usage:
    python3 freeze_sample.py --exp33 <path-to-experiment-33-dir>
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent

#: doc_id -> (count, forced pages). Forced pages are the operator's
#: spot-checked problem pages plus one early page for orientation.
PLAN = {
    "io06": (12, [28, 30, 46, 53, 63, 68, 75, 78]),
    "io04": (12, [16, 20, 33, 52]),
    "bd01": (4, [4]),
    "bd02": (4, [1]),
    "tl03": (4, [5]),
}
CONTROL_COUNT = 6
SEED = 34


def _page_count(sources: dict, doc_id: str) -> int:
    return int(sources[doc_id]["page_count"])


def _pick(doc_id: str, want: int, forced: list[int], total: int, rng: random.Random) -> list[int]:
    """Forced pages first, then a seeded spread over the rest."""
    forced = [p for p in forced if 1 <= p <= total]
    pool = [p for p in range(1, total + 1) if p not in forced]
    rng.shuffle(pool)
    chosen = forced + pool[: max(0, want - len(forced))]
    return sorted(chosen)[:want]


def _control_doc(sources: dict, labels: dict) -> str:
    """The first born-digital, all-usable document not already sampled."""
    for doc_id, doc in sorted(labels["documents"].items()):
        if doc_id in PLAN or sources[doc_id].get("stratum") != "born_digital":
            continue
        page_labels = doc.get("page_labels", {})
        if (
            page_labels.get("usable", 0) == doc.get("pages", 0)
            and doc.get("pages", 0) >= CONTROL_COUNT
        ):
            return doc_id
    raise SystemExit("no clean born-digital control document found")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exp33", required=True, type=Path, help="Experiment 33 directory")
    args = parser.parse_args()

    sources = {
        d["doc_id"]: d for d in json.loads((args.exp33 / "sources.json").read_text())["documents"]
    }
    labels = json.loads((args.exp33 / "labels.json").read_text())
    if not labels.get("frozen"):
        raise SystemExit("labels.json is not frozen; refusing to sample")
    evidence = json.loads((args.exp33 / "output" / "page_evidence.json").read_text())["pages"]
    labelled_pages = {(r["doc_id"], r["page"]) for r in evidence}

    # Seeded pseudo-random sampling selects review pages; not cryptographic.
    rng = random.Random(SEED)  # noqa: S311
    control = _control_doc(sources, labels)

    sample: list[dict] = []
    for doc_id, (want, forced) in PLAN.items():
        total = _page_count(sources, doc_id)
        for page in _pick(doc_id, want, forced, total, rng):
            if (doc_id, page) not in labelled_pages:
                raise SystemExit(f"{doc_id} p{page} missing from evidence")
            sample.append({"doc_id": doc_id, "page": page, "role": "problem"})
    total = _page_count(sources, control)
    for page in _pick(control, CONTROL_COUNT, [1], total, rng):
        sample.append({"doc_id": control, "page": page, "role": "control"})

    manifest = {
        "seed": SEED,
        "control_doc": control,
        "page_count": len(sample),
        "cap": 50,
        "exp33_dir": str(args.exp33),
        "pages": sample,
    }
    out = EXP_DIR / "sample.json"
    out.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    per_doc: dict[str, int] = {}
    for row in sample:
        per_doc[row["doc_id"]] = per_doc.get(row["doc_id"], 0) + 1
    print(json.dumps(per_doc, sort_keys=True))
    print(f"total pages: {len(sample)} (cap {manifest['cap']}), control: {control}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
