"""Amendments A7 to A9: Gemini 3.8 Flash references, Experiment 33 procedure.

Calls Experiment 33 ``label_pages._process`` unchanged: poppler ``pdftoppm``
render (150 dpi, 1,600 px), ``pdftotext -layout`` and pypdf text layers, then
the Gemini transcription. Only the module's folder constants point here.
Population: rescued documents only (A8). Spend stops at the plan's USD cap.

    # pass 1: full transcription of every rescued page
    uv run --no-sync python -u gemini_references.py --pass full
    # pass 2: body/figure split of pages whose all-text label is needs_ocr or ambiguous
    uv run --no-sync python -u gemini_references.py --pass split

One JSON file per page under gitignored ``output/.transcripts/`` or
``output/.transcripts_split/``; an existing file is skipped, so reruns resume.
``OPENROUTER_API_KEY`` is read from the environment and never written.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from build_labels import rescued_ids
from exp42_io import EXP33, EXP_DIR, OUTPUT, atomic_json, load_module, plan, read_json

LABELLER = load_module(EXP33 / "label_pages.py", "exp33_label_pages")
LABELLER.EXP_DIR = EXP_DIR
LABELLER.PAGES_DIR = OUTPUT / ".pages"
LABELLER.TRANSCRIPTS_DIR = OUTPUT / ".transcripts"
LABELLER.SPLIT_DIR = OUTPUT / ".transcripts_split"
SPEND = OUTPUT / "gemini_spend.json"


def spent() -> float:
    """USD already spent on every saved transcript (both passes)."""
    total = 0.0
    for folder in (LABELLER.TRANSCRIPTS_DIR, LABELLER.SPLIT_DIR):
        for path in folder.glob("*/*.json"):
            usage = json.loads(path.read_text("utf-8")).get("usage") or {}
            total += float(usage.get("cost") or 0.0)
    return total


def all_text_label(rule, doc_id: str, page: int) -> str:
    """Experiment 33 all-text page label (r_best over pdftotext and pypdf)."""
    stem = f"p{page:03d}"
    record = json.loads((rule.TRANSCRIPTS_DIR / doc_id / f"{stem}.json").read_text("utf-8"))
    reference = rule.tokens(record.get("transcription") or "")
    layers = [
        (rule.PAGES_DIR / doc_id / f"{stem}.{name}.txt").read_text("utf-8")
        for name in ("pdftotext", "pypdf")
    ]
    r_best = max(rule.recall(layer, reference) for layer in layers)
    return rule.page_label(record, reference, r_best)


def main() -> int:
    """Transcribe pending pages with a thread pool, stopping at the budget cap."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass", dest="mode", required=True, choices=("full", "split"))
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    cap = float(plan()["labelling"]["budget_usd_cap"])
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1
    if LABELLER.MODEL != "google/gemini-3.8-flash":
        raise SystemExit("Experiment 33 model id changed")
    from build_labels import load_rules
    from pypdf import PdfReader

    rule = load_rules()
    split = args.mode == "split"
    out_dir: Path = LABELLER.SPLIT_DIR if split else LABELLER.TRANSCRIPTS_DIR
    rescued = set(rescued_ids())
    documents = [
        d for d in read_json(EXP_DIR / "sources.json")["documents"] if d["doc_id"] in rescued
    ]
    items = [
        (doc, page)
        for doc in documents
        for page in range(1, doc["page_count"] + 1)
        if not (out_dir / doc["doc_id"] / f"p{page:03d}.json").exists()
        and (not split or all_text_label(rule, doc["doc_id"], page) in {"needs_ocr", "ambiguous"})
    ]
    readers = {
        d["doc_id"]: PdfReader(str(EXP_DIR / d["local_path"]))
        for d in {d["doc_id"]: d for d, _ in items}.values()
    }
    cost = spent()
    print(f"[gemini {args.mode}] {len(items)} pages; spent so far ${cost:.4f}", flush=True)
    done, errors, stopped = 0, 0, False
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(LABELLER._process, d, p, key, readers, split): (d, p)  # noqa: SLF001
            for d, p in items
        }
        for future in as_completed(futures):
            doc, page = futures[future]
            try:
                record = future.result()
            except LABELLER.AccountError as exc:
                stopped = True
                print(f"[gemini] STOPPED: {exc}", flush=True)
            else:
                done += 1
                cost += float((record.get("usage") or {}).get("cost") or 0.0)
                errors += bool(record.get("label_error"))
                if done % 50 == 0 or record.get("label_error"):
                    print(
                        f"[gemini {args.mode}] {done}/{len(items)} {doc['doc_id']} p{page} "
                        f"error={record.get('label_error')} cost=${cost:.4f}",
                        flush=True,
                    )
            if stopped or cost >= cap:
                cancelled = [pending.cancel() for pending in futures]
                if any(cancelled):
                    print(f"[gemini] budget or account stop at ${cost:.4f}", flush=True)
    atomic_json(SPEND, {"cap_usd": cap, "spent_usd": spent(), "errors_last_pass": errors})
    print(f"[gemini {args.mode}] done: {done} pages, {errors} errors, ${cost:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
