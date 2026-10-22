"""Experiment 24 supplementary analysis: the task 5.1 wording items.

The frozen gates in ``plan.json`` were evaluated by ``summarise_eval.py``
and are untouched here. This script adds the four descriptive items task
5.1 asks to *record* but that no gate measures — reading order,
table/structure fidelity, missing content, and downstream evidence
retrieval — computed from the artefacts already committed in
``output/ablation.json``. Nothing is re-run and no gate verdict changes.

Reading order uses a longest-common-subsequence word recall: the share of
ground-truth words the extraction reproduces *in the original sequence*.
Compared with the order-blind set recall already in the summary, a small
gap means the reading order survived; a large gap means words were
recovered but shuffled.

Downstream evidence retrieval indexes each cell's extracted Markdown
through the production chunker and ranks it with the production BM25
implementation (``core/retrieval/sparse``). It is a lexical retrievability
probe over five documents, not a competitive ranking benchmark: with two
routed fixtures it has no statistical power, and its purpose is to show
whether OCR-recovered content becomes reachable evidence at all.

Writes ``output/task_5_1_analysis.json`` with tmp-then-rename.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
ABLATION = EXP_DIR / "output/ablation.json"
EXPECTED_DIR = PROJECT_ROOT / "tests/fixtures/pdf_baseline/evaluation"
OUT_PATH = EXP_DIR / "output/task_5_1_analysis.json"

os.environ.setdefault("METADATA__EXTRACTION_MODE", "disabled")
os.environ.setdefault("PDF_READER", "pypdf")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

WORD_RE = re.compile(r"[a-z']{3,}")
# Ground-truth section headings on the two routed source pages.
EXPECTED_HEADINGS = {
    "eval_scanned.pdf": ["Rule 3", "Rule 4", "Rule 5"],
    "eval_image.pdf": ["Rule 8", "Rule 9"],
}
# Evidence queries: gold fixture is the one whose ground truth answers it.
EVIDENCE_QUERIES = [
    ("what does the introduction of a ten simple rules article define", "eval_scanned.pdf"),
    (
        "who is listed as first last or sole author of most ten simple rules articles",
        "eval_scanned.pdf",
    ),
    ("why collaborate with coauthors when writing a rules article", "eval_scanned.pdf"),
    ("how long should the introduction be", "eval_scanned.pdf"),
    ("what p-value is reported for the frequent author", "eval_scanned.pdf"),
    ("can there be too many references in a rules article", "eval_image.pdf"),
    ("are ten simple rules articles viewed more often than cited", "eval_image.pdf"),
    ("what tool helps keep sentences under thirty words", "eval_image.pdf"),
    ("why should others read and workshop your article", "eval_image.pdf"),
    ("how should the rules be ordered when editing", "eval_image.pdf"),
    ("what does this held-out document measure", "eval_clean_text.pdf"),
    ("which page carries a full extractable paragraph", "eval_mixed.pdf"),
]


def _words(text: str) -> list[str]:
    """Lowercase word sequence, three characters or more."""
    return WORD_RE.findall(text.lower())


def _lcs_length(left: list[str], right: list[str]) -> int:
    """Longest common subsequence length, linear in memory."""
    previous = [0] * (len(right) + 1)
    for item in left:
        current = [0]
        for index, other in enumerate(right):
            if item == other:
                current.append(previous[index] + 1)
            else:
                current.append(max(current[index], previous[index + 1]))
        previous = current
    return previous[-1]


def _table_rows(text: str) -> list[str]:
    """Markdown table rows in a block of text."""
    return re.findall(r"^\s*\|.*\|\s*$", text, flags=re.MULTILINE)


def _ground_truth(fixture: str) -> str | None:
    path = EXPECTED_DIR / (fixture.rsplit(".", 1)[0] + ".expected.txt")
    return path.read_text(encoding="utf-8") if path.exists() else None


def _fidelity(fixture: str, extracted: str) -> dict | None:
    """Reading order, structure and missing-content figures for one fixture."""
    truth = _ground_truth(fixture)
    if truth is None:
        return None
    gt_words, got_words = _words(truth), _words(extracted)
    gt_set, got_set = set(gt_words), set(got_words)
    in_order = _lcs_length(gt_words, got_words)
    missing = sorted(gt_set - got_set)
    headings = re.findall(r"^#{1,6}\s+(.*)$", extracted, flags=re.MULTILINE)
    expected_headings = EXPECTED_HEADINGS.get(fixture, [])
    return {
        "ground_truth_words": len(gt_words),
        "extracted_words": len(got_words),
        "set_word_recall": round(len(gt_set & got_set) / len(gt_set), 4),
        "in_order_word_recall": round(in_order / len(gt_words), 4),
        "reading_order_gap_pp": round(
            (len(gt_set & got_set) / len(gt_set) - in_order / len(gt_words)) * 100, 1
        ),
        "missing_unique_words": len(missing),
        "missing_word_sample": missing[:25],
        "expected_section_headings": expected_headings,
        "emitted_markdown_headings": headings,
        "section_headings_recovered": [
            name for name in expected_headings if any(name in h for h in headings)
        ],
        # The held-out evaluation pages are prose with figures. Neither
        # side carries tabular structure, so table fidelity is reported
        # as unmeasurable on this set rather than scored as a pass.
        "ground_truth_table_rows": len(_table_rows(truth)),
        "emitted_table_rows": len(_table_rows(extracted)),
    }


async def _chunk_cell(cell_rows: list[dict]) -> list[dict]:
    """Chunk every non-empty extraction through the production chunker."""
    from omrg.core.ingestion.chunker import read_and_chunk_file_async

    chunks: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        for row in cell_rows:
            text = row["markdown"]
            if not text.strip():
                continue
            path = Path(tmp) / (row["fixture"].rsplit(".", 1)[0] + ".md")
            path.write_text(text, encoding="utf-8")
            nodes = await read_and_chunk_file_async(path)
            for node in nodes:
                chunks.append({"fixture": row["fixture"], "text": node.get_content()})
    return chunks


def _retrieval(chunks: list[dict]) -> dict:
    """Rank the evidence queries over one cell's chunks with production BM25."""
    from omrg.core.retrieval.sparse import _make_bm25, tokenize_english

    if not chunks:
        return {"chunks": 0, "recall_at_1": 0.0, "mrr_at_10": 0.0, "per_query": []}
    bm25 = _make_bm25([tokenize_english(c["text"]) for c in chunks])
    per_query, hits, reciprocal = [], 0, 0.0
    for query, gold in EVIDENCE_QUERIES:
        scores = bm25.get_scores(tokenize_english(query))
        order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
        ranked = [chunks[i]["fixture"] for i in order if scores[i] > 0]
        rank = next((i + 1 for i, f in enumerate(ranked) if f == gold), None)
        hits += 1 if rank == 1 else 0
        reciprocal += 1.0 / rank if rank and rank <= 10 else 0.0
        per_query.append({"query": query, "gold": gold, "first_gold_rank": rank})
    total = len(EVIDENCE_QUERIES)
    return {
        "chunks": len(chunks),
        "recall_at_1": round(hits / total, 4),
        "mrr_at_10": round(reciprocal / total, 4),
        "unretrievable_queries": sum(1 for q in per_query if q["first_gold_rank"] is None),
        "per_query": per_query,
    }


def main() -> None:
    """Compute the supplementary figures and write them atomically."""
    from omrg.compose import ensure_runtime_setup

    ensure_runtime_setup()
    state = json.loads(ABLATION.read_text(encoding="utf-8"))
    result: dict = {"experiment": EXP_DIR.name, "note": "supplementary; no gate changes"}

    fidelity: dict = {}
    for cell, payload in state["cells"].items():
        fidelity[cell] = {
            row["fixture"]: _fidelity(row["fixture"], row["markdown"])
            for row in payload["rows"]
            if _ground_truth(row["fixture"]) is not None
        }
    result["fidelity"] = fidelity

    retrieval: dict = {}
    for cell, payload in state["cells"].items():
        chunks = asyncio.run(_chunk_cell(payload["rows"]))
        retrieval[cell] = _retrieval(chunks)
        print(f"[analyse] {cell}: {retrieval[cell]['chunks']} chunks", flush=True)
    result["downstream_evidence_retrieval"] = retrieval

    from omrg.core.settings import resolve_effective_settings

    resolved = resolve_effective_settings(None)
    result["chunking_context"] = {
        "markdown_chunk_size": resolved.chunking.markdown_chunk_size,
        "chunk_overlap": resolved.chunking.chunk_overlap,
        "tokenizer_model": resolved.embedding.tokenizer_model,
        "tokenizer_revision": resolved.embedding.tokenizer_revision,
    }

    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tmp.replace(OUT_PATH)
    print(f"[analyse] wrote {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
