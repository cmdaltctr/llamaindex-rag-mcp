"""Evidence-level evaluator for Experiment 6c quick-win sweeps."""

# NOTE (v2.0.0): this script targets the PRE-v2.0.0 import surface
# (rag_mcp.ingestion, rag_mcp.retrieval, rag_mcp.reranker, ...), which was
# removed by the architecture-v2 conformance change. It is an archived
# historical artefact, is not run in CI, and is intentionally NOT repaired:
# its results are already recorded in results.md, and rewriting it would
# change the code that produced them. See docs/adr/037.


from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv


load_dotenv()

EXPERIMENT_DIR = Path(__file__).parent
GROUND_TRUTH_PATH = EXPERIMENT_DIR / "ground-truth.json"
CHUNK_SIZE = 512
SIZE_CAP_TOKENS = int(CHUNK_SIZE * 1.1)


@dataclass
class QueryResult:
    id: str
    query: str
    category: str
    expected_source: str
    expected_section: str | None
    evidence_snippets: list[str]
    top_k_sources: list[str] = field(default_factory=list)
    top_k_scores: list[float] = field(default_factory=list)
    top_k_texts: list[str] = field(default_factory=list)
    top_k_sections: list[str | None] = field(default_factory=list)
    relevance_grades: list[int] = field(default_factory=list)
    evidence_hit_rank: int | None = None
    source_hit_rank: int | None = None
    section_match_at_1: bool = False
    ndcg_5: float = 0.0
    ndcg_10: float = 0.0
    latency_ms: float = 0.0


@dataclass
class ChunkStats:
    total_chunks: int
    mean_token_estimate: float
    p95_token_estimate: float
    max_token_estimate: int
    over_cap_count: int
    heading_metadata_rate: float


@dataclass
class Evaluation:
    label: str
    chroma_dir: str
    dataset_source: str
    queries: list[QueryResult] = field(default_factory=list)
    chunk_stats: ChunkStats | None = None
    metrics_by_category: dict[str, dict[str, float]] = field(default_factory=dict)


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _token_estimate(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _load_ground_truth() -> tuple[str, list[dict[str, Any]]]:
    if not GROUND_TRUTH_PATH.exists():
        raise SystemExit(f"ground-truth not found: {GROUND_TRUTH_PATH}")
    data = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    queries = data.get("queries", [])
    _validate_evidence_density(queries)
    return data.get("dataset_source", "unknown"), queries


def _validate_evidence_density(queries: list[dict[str, Any]]) -> None:
    if not queries:
        raise SystemExit("No queries found in ground-truth.json")
    evidence_labelled = [
        q for q in queries
        if q.get("evidence_ids") or q.get("evidence_snippets") or q.get("expected_answer")
    ]
    density = len(evidence_labelled) / len(queries)
    missing_source = [q.get("id", q.get("query", "unknown")) for q in queries if not q.get("expected_source")]
    missing_hierarchy = [
        q.get("id", q.get("query", "unknown"))
        for q in queries
        if q.get("category") in {"heading-targeted", "hierarchy-targeted"}
        and not (q.get("expected_section") or q.get("hierarchy_path"))
    ]
    errors = []
    if density < 0.8:
        errors.append(f"evidence density {density:.1%} < 80%")
    if missing_source:
        errors.append(f"missing expected_source for {missing_source[:5]}")
    if missing_hierarchy:
        errors.append(f"missing expected_section/hierarchy_path for {missing_hierarchy[:5]}")
    if errors:
        raise SystemExit("Evidence-sparse evaluation set rejected: " + "; ".join(errors))


def _setup_chroma_dir(chroma_dir: str) -> None:
    os.environ["CHROMA_PERSIST_DIR"] = chroma_dir
    for mod_name in ("rag_mcp.ingestion", "rag_mcp.retrieval", "rag_mcp.config"):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "CHROMA_PERSIST_DIR"):
            mod.CHROMA_PERSIST_DIR = chroma_dir


def _section_from_metadata(meta: dict[str, Any], text: str) -> str | None:
    for key in ("heading_path", "header", "section", "Header_1", "Header_2", "Header_3"):
        value = meta.get(key)
        if value:
            if isinstance(value, list):
                return " / ".join(str(v) for v in value)
            return str(value)
    headings = re.findall(r"(?m)^#{1,6}\s+(.+?)\s*$", text)
    return " / ".join(headings[-3:]) if headings else None


def _collect_chunk_stats(chroma_dir: str) -> ChunkStats:
    import statistics
    import chromadb

    client = chromadb.PersistentClient(path=chroma_dir)
    collections = client.list_collections()
    if not collections:
        return ChunkStats(0, 0.0, 0.0, 0, 0, 0.0)
    collection = collections[0]
    data = collection.get(include=["documents", "metadatas"])
    docs = data.get("documents") or []
    metas = data.get("metadatas") or []
    lengths = [_token_estimate(d or "") for d in docs]
    if not lengths:
        return ChunkStats(0, 0.0, 0.0, 0, 0, 0.0)
    sorted_lengths = sorted(lengths)
    cuts = statistics.quantiles(sorted_lengths, n=100, method="inclusive") if len(lengths) > 1 else [lengths[0]] * 99
    heading_count = 0
    for doc, meta in zip(docs, metas):
        if _section_from_metadata(meta or {}, doc or ""):
            heading_count += 1
    return ChunkStats(
        total_chunks=len(lengths),
        mean_token_estimate=round(statistics.mean(lengths), 1),
        p95_token_estimate=round(cuts[94], 1),
        max_token_estimate=max(lengths),
        over_cap_count=sum(1 for length in lengths if length > SIZE_CAP_TOKENS),
        heading_metadata_rate=round(heading_count / len(lengths), 4),
    )


def _snippet_hit(text: str, snippets: list[str]) -> bool:
    norm_text = _norm(text)
    return any(_norm(snippet) in norm_text for snippet in snippets if snippet and _norm(snippet))


def _source_match(expected_source: str, source: str) -> bool:
    return bool(expected_source) and expected_source.lower() in source.lower()


def _section_match(expected_section: str | None, section: str | None, text: str) -> bool:
    if not expected_section:
        return False
    target = _norm(expected_section)
    return target in _norm(section or "") or target in _norm(text)


def _dcg(grades: list[int]) -> float:
    return sum((2 ** grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, start=1))


def _ndcg(grades: list[int], k: int = 5) -> float:
    actual = grades[:k]
    ideal = sorted(grades, reverse=True)[:k]
    ideal_dcg = _dcg(ideal)
    return 0.0 if ideal_dcg == 0 else _dcg(actual) / ideal_dcg


def _evaluate(
    label: str,
    chroma_dir: str,
    dataset_source: str,
    queries: list[dict[str, Any]],
    *,
    rerank: bool = False,
    top_k: int = 5,
) -> Evaluation:
    from rag_mcp.retrieval import search

    _setup_chroma_dir(chroma_dir)
    ev = Evaluation(label=label, chroma_dir=chroma_dir, dataset_source=dataset_source)
    ev.chunk_stats = _collect_chunk_stats(chroma_dir)
    for qa in queries:
        snippets = list(qa.get("evidence_snippets") or [])
        if qa.get("expected_answer"):
            snippets.append(str(qa["expected_answer"]))
        started = time.perf_counter()
        results = search(qa["query"], top_k=top_k, similarity_threshold=0.0, rerank=rerank)
        latency_ms = (time.perf_counter() - started) * 1000
        sources = [r.get("source", "") for r in results[:top_k]]
        scores = [r.get("score", 0.0) for r in results[:top_k]]
        texts = [r.get("text", "") for r in results[:top_k]]
        # search() now exposes the full chunk metadata in each result row;
        # _section_from_metadata prefers structured heading metadata and
        # only falls back to parsing markdown headings from the chunk text
        # when none is present.
        sections = [
            _section_from_metadata(r.get("metadata", {}) or {}, r.get("text", ""))
            for r in results[:top_k]
        ]
        evidence_rank = None
        source_rank = None
        grades: list[int] = []
        for rank, (source, text, section) in enumerate(zip(sources, texts, sections), start=1):
            e_hit = _snippet_hit(text, snippets)
            s_hit = _source_match(qa.get("expected_source", ""), source)
            sec_hit = _section_match(qa.get("expected_section"), section, text)
            if e_hit and evidence_rank is None:
                evidence_rank = rank
            if s_hit and source_rank is None:
                source_rank = rank
            grades.append(2 if (e_hit or sec_hit) else (1 if s_hit else 0))
        qr = QueryResult(
            id=str(qa.get("id", qa.get("query", ""))),
            query=qa["query"],
            category=qa.get("category", "general"),
            expected_source=qa.get("expected_source", ""),
            expected_section=qa.get("expected_section"),
            evidence_snippets=snippets,
            top_k_sources=sources,
            top_k_scores=scores,
            top_k_texts=texts,
            top_k_sections=sections,
            relevance_grades=grades,
            evidence_hit_rank=evidence_rank,
            source_hit_rank=source_rank,
            section_match_at_1=bool(texts and _section_match(qa.get("expected_section"), sections[0], texts[0])),
            ndcg_5=round(_ndcg(grades, 5), 4),
            ndcg_10=round(_ndcg(grades, 10), 4),
            latency_ms=round(latency_ms, 2),
        )
        ev.queries.append(qr)
    ev.metrics_by_category = _aggregate(ev.queries)
    return ev


def _aggregate(queries: list[QueryResult]) -> dict[str, dict[str, float]]:
    by_cat: dict[str, list[QueryResult]] = defaultdict(list)
    for q in queries:
        by_cat[q.category].append(q)
    metrics: dict[str, dict[str, float]] = {}
    for cat, items in by_cat.items():
        n = len(items)
        rr = [(1 / q.evidence_hit_rank) if q.evidence_hit_rank else 0.0 for q in items]
        metrics[cat] = {
            "n": n,
            "evidence_recall_at_1": round(sum(q.evidence_hit_rank == 1 for q in items) / n, 4),
            "evidence_recall_at_3": round(sum(q.evidence_hit_rank is not None and q.evidence_hit_rank <= 3 for q in items) / n, 4),
            "evidence_recall_at_5": round(sum(q.evidence_hit_rank is not None and q.evidence_hit_rank <= 5 for q in items) / n, 4),
            "evidence_recall_at_10": round(sum(q.evidence_hit_rank is not None and q.evidence_hit_rank <= 10 for q in items) / n, 4),
            "evidence_recall_at_20": round(sum(q.evidence_hit_rank is not None and q.evidence_hit_rank <= 20 for q in items) / n, 4),
            "evidence_mrr": round(sum(rr) / n, 4),
            "section_match_at_1": round(sum(q.section_match_at_1 for q in items) / n, 4),
            "ndcg_5": round(sum(q.ndcg_5 for q in items) / n, 4),
            "ndcg_10": round(sum(q.ndcg_10 for q in items) / n, 4),
            "source_hit_at_1_diagnostic": round(sum(q.source_hit_rank == 1 for q in items) / n, 4),
        }
    return metrics


# Sources we accept as primary for the Experiment 6b run.  ``qasper`` is the
# substitute corpus the HiChunk paper itself uses as an in-domain evaluation;
# Qasper is the canonical 6b dataset; HiChunk-schema data is retained only
# for historical compatibility with the original experiment design.
_PRIMARY_DATASET_PREFIXES = ("qasper", "hicbench")


def _criteria(baseline: Evaluation, candidate: Evaluation, dataset_source: str) -> dict[str, Any]:
    heading_cats = ("heading-targeted", "hierarchy-targeted")

    def avg(ev: Evaluation, key: str, cats: tuple[str, ...]) -> float:
        vals = [ev.metrics_by_category[c][key] for c in cats if c in ev.metrics_by_category]
        return sum(vals) / len(vals) if vals else 0.0

    recall_lift = avg(candidate, "evidence_recall_at_5", heading_cats) - avg(baseline, "evidence_recall_at_5", heading_cats)
    ndcg_lift = avg(candidate, "ndcg_5", heading_cats) - avg(baseline, "ndcg_5", heading_cats)
    general_delta = (
        candidate.metrics_by_category.get("general", {}).get("evidence_recall_at_5", 0.0)
        - baseline.metrics_by_category.get("general", {}).get("evidence_recall_at_5", 0.0)
    )
    cs = candidate.chunk_stats
    is_primary = any(dataset_source.startswith(p) for p in _PRIMARY_DATASET_PREFIXES)
    return {
        "dataset_source": dataset_source,
        "fallback_only": not is_primary,
        "heading_evidence_recall_at_5_lift_pp": round(100 * recall_lift, 2),
        "heading_evidence_recall_at_5_lift_pass": recall_lift >= 0.05,
        "heading_ndcg_5_lift": round(ndcg_lift, 4),
        "heading_ndcg_5_lift_pass": ndcg_lift >= 0.03,
        "general_evidence_recall_at_5_delta_pp": round(100 * general_delta, 2),
        "general_non_regression_pass": general_delta >= -0.02,
        "candidate_chunk_p95_token_estimate": cs.p95_token_estimate if cs else None,
        "candidate_chunk_size_pass": bool(cs and cs.p95_token_estimate <= SIZE_CAP_TOKENS),
        "size_cap_token_threshold": SIZE_CAP_TOKENS,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", default=str(EXPERIMENT_DIR / "chroma_baseline"))
    parser.add_argument(
        "--candidate-dir",
        default=str(EXPERIMENT_DIR / "chroma_candidate_runs" / "baseline_6b"),
    )
    parser.add_argument("--top-k", type=int, default=5, help="Retrieval depth for this 6c run.")
    parser.add_argument(
        "--rerank",
        choices=("off", "on"),
        default="off",
        help="off = chunker isolation (Pass A); on = production shape (Pass B).",
    )
    parser.add_argument(
        "--pass-name",
        default="A",
        help="Label embedded in output JSON (e.g. 'A' or 'B').",
    )
    parser.add_argument(
        "--output",
        default=str(EXPERIMENT_DIR / "eval_results.json"),
        help="Path to write the per-pass results JSON.",
    )
    args = parser.parse_args()
    dataset_source, queries = _load_ground_truth()
    rerank_enabled = args.rerank == "on"
    print("Experiment 6c: Qasper Markdown chunking quick-win sweep")
    print(f"  Dataset source: {dataset_source}")
    print(f"  Queries: {len(queries)}")
    print(f"  Top-K: {args.top_k}")
    print(f"  Pass: {args.pass_name} ({'reranker enabled (production)' if rerank_enabled else 'reranker disabled (chunker isolation)'})")
    baseline = _evaluate(
        "baseline",
        str(Path(args.baseline_dir).resolve()),
        dataset_source,
        queries,
        rerank=rerank_enabled,
        top_k=args.top_k,
    )
    candidate = _evaluate(
        "candidate",
        str(Path(args.candidate_dir).resolve()),
        dataset_source,
        queries,
        rerank=rerank_enabled,
        top_k=args.top_k,
    )
    criteria = _criteria(baseline, candidate, dataset_source)
    for ev in (baseline, candidate):
        print(f"\n{ev.label}")
        for cat, metrics in ev.metrics_by_category.items():
            print(f"  {cat}: {metrics}")
        print(f"  chunks: {ev.chunk_stats}")
    print("\nPass criteria")
    for key, value in criteria.items():
        print(f"  {key}: {value}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "experiment": "qasper-markdown-chunking-quickwins",
        "pass_name": args.pass_name,
        "reranker_enabled": rerank_enabled,
        "top_k": args.top_k,
        "baseline_dir": str(Path(args.baseline_dir).resolve()),
        "candidate_dir": str(Path(args.candidate_dir).resolve()),
        "baseline": asdict(baseline),
        "candidate": asdict(candidate),
        "pass_criteria": criteria,
    }, indent=2), encoding="utf-8")
    print(f"\nRaw results saved to: {output}")


if __name__ == "__main__":
    main()
