"""Full-size query embedding cache experiment (Experiment 8a).

This fixes the two caveats from Experiment 8:

1. uses full-size traces (250 warm calls, 200 cold calls, 250 agent-loop calls);
2. implements a real cache-disabled mode by monkey-patching
   ``omrg.retrieval._embed_query`` to bypass the production LRU helper.
"""

# NOTE (v2.0.0): this script targets the PRE-v2.0.0 import surface
# (omrg.ingestion, omrg.retrieval, omrg.reranker, ...), which was
# removed by the architecture-v2 conformance change. It is an archived
# historical artefact, is not run in CI, and is intentionally NOT repaired:
# its results are already recorded in results.md, and rewriting it would
# change the code that produced them. See docs/adr/037.


from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

EXPERIMENT_DIR = Path(__file__).parent
EXPERIMENT_COLLECTION = "eval_cache_fullsize_documents"


BASE_QUERIES = [
    "How does pretraining force language models to hallucinate?",
    "Why does cross-entropy loss reduce model trustworthiness?",
    "How does coding improve children's mathematical problem solving?",
    "Does coding improve social skills and collaboration in classrooms?",
    "What does handwriting do to brain connectivity that typing does not?",
    "How is istislah used in Al-Ghazali's al-Mustasfa?",
    "What features does the grep-ai tool offer?",
    "How does paper-search-mcp-cf integrate with academic databases?",
]

TOPIC_STEMS = [
    "language model hallucination", "cross entropy reliability", "coding and mathematics",
    "classroom collaboration", "handwriting brain connectivity", "istislah in al-Mustasfa",
    "semantic grep tool", "academic database integration", "attention mechanisms",
    "residual neural networks", "layer normalisation", "positional encodings",
    "multi-head attention", "masked language modelling", "next-token prediction",
    "temperature sampling", "top-p sampling", "beam search", "greedy decoding",
    "mixture of experts", "retrieval augmented generation", "vector databases",
    "metadata filtering", "reranking", "chunk overlap", "Markdown chunking",
    "Qasper evidence retrieval", "BM25 retrieval", "query embedding cache",
    "ChromaDB collection", "Ollama embeddings", "PDF ingestion", "document deletion",
    "file watcher ingestion", "MCP search tool", "source attribution", "nDCG metrics",
    "evidence recall", "agent verification loop", "latency benchmark", "Apple Silicon",
    "cross encoder threshold", "dense retrieval", "sparse retrieval", "hybrid search",
    "academic paper QA", "structured Markdown", "semantic code search", "local RAG",
    "collection statistics",
]

AGENT_LOOP_QUERIES = [
    f"Verify retrieval evidence for step {i:02d}: {stem}." for i, stem in enumerate(TOPIC_STEMS[:25], start=1)
]


@dataclass
class CallRecord:
    index: int
    query: str
    branch: str
    latency_ms: float
    cache_hit: bool


@dataclass
class CellResult:
    cache_enabled: bool
    trace: str
    rerank: bool
    calls: list[CallRecord] = field(default_factory=list)
    embed_calls: int = 0
    cache_info: dict = field(default_factory=dict)
    mean_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    hit_rate: float = 0.0
    hit_rate_filtered: float = 0.0
    hit_rate_unfiltered: float = 0.0


class EmbedCallCounter:
    """Counts actual calls to ``Settings.embed_model.get_query_embedding``."""

    def __init__(self) -> None:
        self.count = 0
        self._original = None
        self._embed_model = None

    def install(self) -> None:
        from llama_index.core import Settings

        self._embed_model = Settings.embed_model
        self._original = self._embed_model.get_query_embedding

        def wrapped(query: str):
            self.count += 1
            return self._original(query)  # type: ignore[misc]

        object.__setattr__(self._embed_model, "get_query_embedding", wrapped)

    def uninstall(self) -> None:
        if self._embed_model is not None:
            try:
                object.__delattr__(self._embed_model, "get_query_embedding")
            except AttributeError:
                pass
        self.count = 0


class CacheToggle:
    """Context manager that toggles production cache use for one cell."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._original_embed_query = None

    def __enter__(self):
        from llama_index.core import Settings
        import omrg.retrieval as retrieval

        self._original_embed_query = retrieval._embed_query
        if hasattr(retrieval._cached_query_embedding, "cache_clear"):
            retrieval._cached_query_embedding.cache_clear()
        if not self.enabled:
            def direct_embed(query: str):
                return list(Settings.embed_model.get_query_embedding(query))
            retrieval._embed_query = direct_embed
        return self

    def __exit__(self, exc_type, exc, tb):
        import omrg.retrieval as retrieval

        if self._original_embed_query is not None:
            retrieval._embed_query = self._original_embed_query
        if hasattr(retrieval._cached_query_embedding, "cache_clear"):
            retrieval._cached_query_embedding.cache_clear()


EXPECTED_TRACE_COUNTS = {
    "workload-warm.txt": 250,
    "workload-cold.txt": 200,
    "workload-agent-loop.txt": 250,
}


def _generate_traces(*, regenerate: bool = False) -> None:
    warm = []
    for _repeat in range(5):
        warm.extend(f"{stem}?" for stem in TOPIC_STEMS)
    cold = [f"Unique retrieval question {i:03d}: explain {TOPIC_STEMS[i % len(TOPIC_STEMS)]} with variant {i}." for i in range(200)]
    agent = []
    for _repeat in range(10):
        agent.extend(AGENT_LOOP_QUERIES)
    outputs = {
        "workload-warm.txt": warm,
        "workload-cold.txt": cold,
        "workload-agent-loop.txt": agent,
    }
    for name, lines in outputs.items():
        path = EXPERIMENT_DIR / name
        if regenerate or not path.exists():
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        actual = len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
        expected = EXPECTED_TRACE_COUNTS[name]
        if actual != expected:
            raise SystemExit(
                f"Trace {path} has {actual} non-empty lines; expected {expected}. "
                "Re-run with --regenerate-traces to recreate deterministic traces."
            )


def _load_trace(name: str) -> list[str]:
    path = EXPERIMENT_DIR / name
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_cache_info() -> dict:
    try:
        from omrg.retrieval import _cached_query_embedding
        info = _cached_query_embedding.cache_info()
        return {"hits": info.hits, "misses": info.misses, "maxsize": info.maxsize, "currsize": info.currsize}
    except Exception:
        return {}


def _ingest_corpus(corpus_dir: Path) -> str:
    import asyncio
    from omrg.ingestion import ingest_path_async

    tmp_dir = tempfile.mkdtemp(prefix="rag_cache_8a_")
    os.environ["CHROMA_PERSIST_DIR"] = tmp_dir
    os.environ["COLLECTION_NAME"] = EXPERIMENT_COLLECTION
    os.environ["METADATA_EXTRACTION_MODE"] = "disabled"
    for mod_name in ("omrg.ingestion", "omrg.retrieval", "omrg.config"):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "CHROMA_PERSIST_DIR"):
            mod.CHROMA_PERSIST_DIR = tmp_dir
        if mod is not None and hasattr(mod, "COLLECTION_NAME"):
            mod.COLLECTION_NAME = EXPERIMENT_COLLECTION
    result = asyncio.run(ingest_path_async(str(corpus_dir)))
    if result.get("status") != "ok":
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise SystemExit(result)
    print(f"Indexed {result.get('chunks_created', 0)} chunks into {tmp_dir}")
    return tmp_dir


def _run_cell(cache_enabled: bool, trace_name: str, queries: list[str], counter: EmbedCallCounter, *, rerank: bool) -> CellResult:
    from omrg.retrieval import search

    cell = CellResult(cache_enabled=cache_enabled, trace=trace_name, rerank=rerank)
    print(f"\nCell cache={'on' if cache_enabled else 'off'} trace={trace_name} rerank={'on' if rerank else 'off'} calls={len(queries)}")
    with CacheToggle(cache_enabled):
        counter.install()
        for i, q in enumerate(queries):
            branch = "unfiltered" if rerank else ("filtered" if i % 2 == 0 else "unfiltered")
            metadata_filter = {"file_type": "pdf"} if branch == "filtered" else None
            before = counter.count
            started = time.perf_counter()
            search(q, top_k=5, similarity_threshold=0.0, rerank=rerank, metadata_filter=metadata_filter)
            latency_ms = (time.perf_counter() - started) * 1000
            after = counter.count
            cell.calls.append(CallRecord(i, q, branch, round(latency_ms, 2), cache_hit=(after == before)))
        cell.embed_calls = counter.count
        cell.cache_info = _read_cache_info()
        counter.uninstall()
    if cell.calls:
        lats = sorted(c.latency_ms for c in cell.calls)
        cell.mean_latency_ms = round(statistics.mean(lats), 2)
        cuts = statistics.quantiles(lats, n=100, method="inclusive")
        cell.p95_latency_ms = round(cuts[94], 2)
        cell.hit_rate = round(sum(c.cache_hit for c in cell.calls) / len(cell.calls), 4)
        filt = [c for c in cell.calls if c.branch == "filtered"]
        unfilt = [c for c in cell.calls if c.branch == "unfiltered"]
        cell.hit_rate_filtered = round(sum(c.cache_hit for c in filt) / len(filt), 4) if filt else 0.0
        cell.hit_rate_unfiltered = round(sum(c.cache_hit for c in unfilt) / len(unfilt), 4) if unfilt else 0.0
    print(f"  mean={cell.mean_latency_ms}ms p95={cell.p95_latency_ms}ms embed_calls={cell.embed_calls} hit_rate={cell.hit_rate:.1%}")
    return cell


def _check(cells: list[CellResult]) -> dict:
    grid = {(c.cache_enabled, c.trace, c.rerank): c for c in cells}
    required = [
        (False, "warm", False),
        (True, "warm", False),
        (False, "cold", False),
        (True, "cold", False),
        (False, "agent-loop", False),
        (True, "agent-loop", False),
        (False, "warm", True),
        (True, "warm", True),
    ]
    missing = [key for key in required if key not in grid]
    if missing:
        return {"error": f"missing cells: {missing}"}
    warm_off = grid[(False, "warm", False)]
    warm_on = grid[(True, "warm", False)]
    cold_off = grid[(False, "cold", False)]
    cold_on = grid[(True, "cold", False)]
    agent_off = grid[(False, "agent-loop", False)]
    agent_on = grid[(True, "agent-loop", False)]
    prod_off = grid[(False, "warm", True)]
    prod_on = grid[(True, "warm", True)]
    def speedup(off, on):
        return (off.mean_latency_ms - on.mean_latency_ms) / off.mean_latency_ms if off.mean_latency_ms else 0.0
    cold_overhead = (cold_on.mean_latency_ms - cold_off.mean_latency_ms) / cold_off.mean_latency_ms if cold_off.mean_latency_ms else 0.0
    return {
        "warm_speedup_pct": round(100 * speedup(warm_off, warm_on), 2),
        "warm_speedup_pass": speedup(warm_off, warm_on) >= 0.30,
        "agent_loop_speedup_pct": round(100 * speedup(agent_off, agent_on), 2),
        "agent_loop_speedup_pass": speedup(agent_off, agent_on) >= 0.50,
        "production_rerank_warm_speedup_pct": round(100 * speedup(prod_off, prod_on), 2),
        "cold_overhead_pct": round(100 * cold_overhead, 2),
        "cold_overhead_pass": abs(cold_overhead) <= 0.05,
        "warm_cache_on_embed_calls": warm_on.embed_calls,
        "warm_embed_calls_pass": warm_on.embed_calls == 50,
        "cold_cache_on_embed_calls": cold_on.embed_calls,
        "cold_embed_calls_pass": cold_on.embed_calls == 200,
        "agent_cache_on_embed_calls": agent_on.embed_calls,
        "agent_embed_calls_pass": agent_on.embed_calls == 25,
        "warm_filtered_hit_rate": warm_on.hit_rate_filtered,
        "warm_unfiltered_hit_rate": warm_on.hit_rate_unfiltered,
        "agent_filtered_hit_rate": agent_on.hit_rate_filtered,
        "agent_unfiltered_hit_rate": agent_on.hit_rate_unfiltered,
        "both_branches_pass": all(x >= 0.80 for x in [warm_on.hit_rate_filtered, warm_on.hit_rate_unfiltered, agent_on.hit_rate_filtered, agent_on.hit_rate_unfiltered]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=EXPERIMENT_DIR / "corpus")
    parser.add_argument("--out", type=Path, default=EXPERIMENT_DIR / "eval_results.json")
    parser.add_argument(
        "--regenerate-traces",
        action="store_true",
        help="Overwrite workload-*.txt with deterministic full-size traces before running.",
    )
    args = parser.parse_args()
    if not args.corpus.exists():
        raise SystemExit(f"corpus not found: {args.corpus}")
    _generate_traces(regenerate=args.regenerate_traces)
    traces = {
        "warm": _load_trace("workload-warm.txt"),
        "cold": _load_trace("workload-cold.txt"),
        "agent-loop": _load_trace("workload-agent-loop.txt"),
    }
    chroma_dir = _ingest_corpus(args.corpus)
    counter = EmbedCallCounter()
    try:
        cells = []
        for trace_name in ("warm", "cold", "agent-loop"):
            for cache_enabled in (False, True):
                cells.append(_run_cell(cache_enabled, trace_name, traces[trace_name], counter, rerank=False))
        for cache_enabled in (False, True):
            cells.append(_run_cell(cache_enabled, "warm", traces["warm"], counter, rerank=True))
    finally:
        shutil.rmtree(chroma_dir, ignore_errors=True)
    criteria = _check(cells)
    print("\nPass criteria")
    for k, v in criteria.items():
        print(f"  {k}: {v}")
    args.out.write_text(json.dumps({"experiment": "8a-query-embedding-cache-fullsize", "cells": [asdict(c) for c in cells], "pass_criteria": criteria}, indent=2), encoding="utf-8")
    print(f"\nRaw results saved to: {args.out}")


if __name__ == "__main__":
    main()
