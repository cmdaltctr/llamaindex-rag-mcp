"""Chunk overlap sensitivity sweep.

Sweeps `CHUNK_OVERLAP ∈ {32, 64, 100, 128}` over the same corpus and query
set to determine whether the proposed default of 100 (Stäbler et al. 2025)
matches or beats the previous default of 64 on this project's corpus.

Reranker is enabled to mirror production retrieval. Uses the reranker pool
defaults chosen in Exp 5.

Run with:
    cd experiments/7-chunk-overlap-sensitivity-2026-05-27
    uv run python run_eval.py \\
        --corpus ../3-e2e-smoke-test-metadata-2026-05-20/corpus \\
        --questions ../3-e2e-smoke-test-metadata-2026-05-20/questions.md \\
        --overlaps 32,64,100,128

Pass criterion: overlap=100 Hit@1 / MRR ≥ overlap=64 Hit@1 / MRR; chunk-count
delta vs overlap=64 ≤ 15 %.
"""

# NOTE (v2.0.0): this script targets the PRE-v2.0.0 import surface
# (rag_mcp.ingestion, rag_mcp.retrieval, rag_mcp.reranker, ...), which was
# removed by the architecture-v2 conformance change. It is an archived
# historical artefact, is not run in CI, and is intentionally NOT repaired:
# its results are already recorded in results.md, and rewriting it would
# change the code that produced them. See docs/adr/037.


from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Ensure project source is importable.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

EXPERIMENT_DIR = Path(__file__).parent

# Reranker pool defaults — should be set per Exp 5 outcome.
DEFAULT_RERANK_MAX_FETCH = int(os.getenv("RERANK_MAX_FETCH", "50"))
DEFAULT_RERANK_FETCH_MULTIPLIER = int(os.getenv("RERANK_FETCH_MULTIPLIER", "10"))


@dataclass
class QueryResult:
    query: str
    expected_source: str
    expected_answer: str | None
    top_k_sources: list[str] = field(default_factory=list)
    top_k_scores: list[float] = field(default_factory=list)
    hit_rank: int | None = None
    hit_at_1: bool = False
    hit_at_3: bool = False
    hit_at_5: bool = False
    answer_hit: bool = False
    latency_ms: float = 0.0


@dataclass
class OverlapEvaluation:
    overlap: int
    queries: list[QueryResult] = field(default_factory=list)
    chunk_count: int = 0
    ingest_seconds: float = 0.0
    hit_rate_at_1: float = 0.0
    hit_rate_at_3: float = 0.0
    hit_rate_at_5: float = 0.0
    mrr: float = 0.0
    answer_accuracy: float = 0.0


def _parse_questions_md(path: Path) -> list[dict]:
    """Parse Exp 3's questions.md into a list of {query, expected_source, expected_answer}.

    questions.md format (loose, by section):

        ## Document: <filename>
        Q: <query text>
        A: <expected answer substring>

    Falls back to JSON if the file is `.json`.
    """
    if path.suffix == ".json":
        with open(path) as f:
            data = json.load(f)
        return data.get("queries", [])

    text = path.read_text()
    queries: list[dict] = []
    current_source: str | None = None
    current_q: str | None = None

    for line in text.splitlines():
        m_doc = re.match(r"^##\s*Document:\s*(.+)$", line.strip())
        if m_doc:
            current_source = m_doc.group(1).strip()
            continue
        m_q = re.match(r"^Q:\s*(.+)$", line.strip())
        if m_q:
            current_q = m_q.group(1).strip()
            continue
        m_a = re.match(r"^A:\s*(.+)$", line.strip())
        if m_a and current_q and current_source:
            queries.append(
                {
                    "query": current_q,
                    "expected_source": current_source,
                    "expected_answer": m_a.group(1).strip(),
                }
            )
            current_q = None
    return queries


def _setup_overlap(overlap: int, chroma_dir: str) -> None:
    """Configure CHUNK_OVERLAP and ChromaDB before ingest/retrieval."""
    os.environ["CHUNK_OVERLAP"] = str(overlap)
    os.environ["CHROMA_PERSIST_DIR"] = chroma_dir
    os.environ["RERANK_MAX_FETCH"] = str(DEFAULT_RERANK_MAX_FETCH)
    os.environ["RERANK_FETCH_MULTIPLIER"] = str(DEFAULT_RERANK_FETCH_MULTIPLIER)

    for mod_name in ("rag_mcp.ingestion", "rag_mcp.retrieval", "rag_mcp.config"):
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        if hasattr(mod, "CHUNK_OVERLAP"):
            mod.CHUNK_OVERLAP = overlap
        if hasattr(mod, "CHROMA_PERSIST_DIR"):
            mod.CHROMA_PERSIST_DIR = chroma_dir

    try:
        from rag_mcp.reranker import CrossEncoderReranker
        CrossEncoderReranker._instance = None  # type: ignore[attr-defined]
    except Exception:
        pass


def _evaluate_overlap(
    overlap: int, corpus_dir: Path, queries: list[dict]
) -> OverlapEvaluation:
    """Ingest under one overlap value and run the query set."""
    import asyncio

    from rag_mcp.ingestion import ingest_path_async
    from rag_mcp.retrieval import search

    chroma_dir = str((EXPERIMENT_DIR / f"chroma_overlap_{overlap}").resolve())
    shutil.rmtree(chroma_dir, ignore_errors=True)
    os.makedirs(chroma_dir, exist_ok=True)
    _setup_overlap(overlap, chroma_dir)

    eval_result = OverlapEvaluation(overlap=overlap)

    started = time.perf_counter()
    ingest_result = asyncio.run(ingest_path_async(str(corpus_dir)))
    eval_result.ingest_seconds = round(time.perf_counter() - started, 2)
    eval_result.chunk_count = ingest_result.get("chunks_created", 0)

    if ingest_result.get("status") != "ok":
        print(f"  ERROR: ingest failed at overlap={overlap}")
        return eval_result

    for qa in queries:
        query_text = qa["query"]
        expected_source = qa["expected_source"]
        expected_answer = qa.get("expected_answer")

        started = time.perf_counter()
        results = search(
            query=query_text,
            top_k=5,
            similarity_threshold=0.0,
            rerank=True,  # production path
        )
        latency_ms = (time.perf_counter() - started) * 1000

        top_sources = [r.get("source", "") for r in results[:5]]
        top_scores = [r.get("score", 0.0) for r in results[:5]]

        hit_rank = None
        for rank, source in enumerate(top_sources, start=1):
            if expected_source.lower() in source.lower():
                hit_rank = rank
                break

        answer_hit = False
        if expected_answer and results:
            top_text = results[0].get("text", "")
            answer_hit = expected_answer.lower() in top_text.lower()

        eval_result.queries.append(
            QueryResult(
                query=query_text,
                expected_source=expected_source,
                expected_answer=expected_answer,
                top_k_sources=top_sources,
                top_k_scores=top_scores,
                hit_rank=hit_rank,
                hit_at_1=(hit_rank is not None and hit_rank <= 1),
                hit_at_3=(hit_rank is not None and hit_rank <= 3),
                hit_at_5=(hit_rank is not None and hit_rank <= 5),
                answer_hit=answer_hit,
                latency_ms=round(latency_ms, 2),
            )
        )

    n = len(eval_result.queries)
    if n > 0:
        eval_result.hit_rate_at_1 = round(
            sum(1 for q in eval_result.queries if q.hit_at_1) / n, 4
        )
        eval_result.hit_rate_at_3 = round(
            sum(1 for q in eval_result.queries if q.hit_at_3) / n, 4
        )
        eval_result.hit_rate_at_5 = round(
            sum(1 for q in eval_result.queries if q.hit_at_5) / n, 4
        )
        rr = [(1.0 / q.hit_rank) if q.hit_rank else 0.0 for q in eval_result.queries]
        eval_result.mrr = round(sum(rr) / n, 4)
        eval_result.answer_accuracy = round(
            sum(1 for q in eval_result.queries if q.answer_hit) / n, 4
        )

    return eval_result


def _print_table(evaluations: list[OverlapEvaluation]) -> None:
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Chunk Overlap Sensitivity Sweep")
        table.add_column("Overlap", justify="right")
        table.add_column("Hit@1", justify="right")
        table.add_column("Hit@3", justify="right")
        table.add_column("Hit@5", justify="right")
        table.add_column("MRR", justify="right")
        table.add_column("Ans acc", justify="right")
        table.add_column("Chunks", justify="right")
        table.add_column("Ingest s", justify="right")

        for ev in evaluations:
            table.add_row(
                str(ev.overlap),
                f"{100 * ev.hit_rate_at_1:.1f}%",
                f"{100 * ev.hit_rate_at_3:.1f}%",
                f"{100 * ev.hit_rate_at_5:.1f}%",
                f"{ev.mrr:.3f}",
                f"{100 * ev.answer_accuracy:.1f}%",
                str(ev.chunk_count),
                f"{ev.ingest_seconds:.2f}",
            )
        console.print()
        console.print(table)
        console.print()
    except ImportError:
        for ev in evaluations:
            print(
                f"  overlap={ev.overlap:>3}  "
                f"hit@1={100*ev.hit_rate_at_1:>5.1f}%  "
                f"mrr={ev.mrr:.3f}  "
                f"chunks={ev.chunk_count}  "
                f"ingest={ev.ingest_seconds:.2f}s"
            )


def _check_pass_criteria(evaluations: list[OverlapEvaluation]) -> dict:
    by_overlap = {ev.overlap: ev for ev in evaluations}
    e64 = by_overlap.get(64)
    e100 = by_overlap.get(100)
    if e64 is None or e100 is None:
        return {"error": "sweep must include both 64 and 100"}

    hit_non_regression = e100.hit_rate_at_1 >= e64.hit_rate_at_1
    mrr_non_regression = e100.mrr >= e64.mrr

    chunk_ratio = (e100.chunk_count / e64.chunk_count) if e64.chunk_count else float("inf")
    chunk_within_15pct = chunk_ratio <= 1.15

    return {
        "hit_at_1_64": e64.hit_rate_at_1,
        "hit_at_1_100": e100.hit_rate_at_1,
        "hit_at_1_non_regression_pass": hit_non_regression,
        "mrr_64": e64.mrr,
        "mrr_100": e100.mrr,
        "mrr_non_regression_pass": mrr_non_regression,
        "chunk_ratio_100_over_64": round(chunk_ratio, 3),
        "chunk_within_15pct_pass": chunk_within_15pct,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=str, required=True)
    parser.add_argument("--questions", type=str, required=True)
    parser.add_argument("--overlaps", type=str, default="32,64,100,128")
    args = parser.parse_args()

    corpus_dir = Path(args.corpus).resolve()
    if not corpus_dir.exists():
        print(f"  ERROR: corpus not found: {corpus_dir}")
        sys.exit(1)

    questions_path = Path(args.questions).resolve()
    if not questions_path.exists():
        print(f"  ERROR: questions file not found: {questions_path}")
        sys.exit(1)

    queries = _parse_questions_md(questions_path)
    if not queries:
        print(f"  ERROR: no queries parsed from {questions_path}")
        sys.exit(1)

    overlaps = [int(x) for x in args.overlaps.split(",")]
    print("Experiment 7: Chunk Overlap Sensitivity")
    print("=" * 60)
    print(f"  Corpus: {corpus_dir}")
    print(f"  Queries: {len(queries)}")
    print(f"  Overlaps: {overlaps}")
    print(f"  Rerank pool: max_fetch={DEFAULT_RERANK_MAX_FETCH}, "
          f"multiplier={DEFAULT_RERANK_FETCH_MULTIPLIER}")

    import rag_mcp.ingestion  # noqa: F401
    import rag_mcp.retrieval  # noqa: F401

    evaluations: list[OverlapEvaluation] = []
    for overlap in overlaps:
        print(f"\n  --- overlap={overlap} ---")
        ev = _evaluate_overlap(overlap, corpus_dir, queries)
        evaluations.append(ev)
        print(
            f"  hit@1={100*ev.hit_rate_at_1:.1f}%  "
            f"mrr={ev.mrr:.3f}  "
            f"chunks={ev.chunk_count}"
        )

    _print_table(evaluations)
    criteria = _check_pass_criteria(evaluations)
    print("  Pass Criteria")
    for k, v in criteria.items():
        print(f"  {k}: {v}")

    output_path = EXPERIMENT_DIR / "eval_results.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "experiment": "chunk-overlap-sensitivity",
                "corpus_dir": str(corpus_dir),
                "questions_path": str(questions_path),
                "overlaps": overlaps,
                "rerank_pool": {
                    "max_fetch": DEFAULT_RERANK_MAX_FETCH,
                    "multiplier": DEFAULT_RERANK_FETCH_MULTIPLIER,
                },
                "evaluations": [asdict(ev) for ev in evaluations],
                "pass_criteria": criteria,
            },
            f,
            indent=2,
        )
    print(f"\n  Raw results saved to: {output_path}")


if __name__ == "__main__":
    main()
