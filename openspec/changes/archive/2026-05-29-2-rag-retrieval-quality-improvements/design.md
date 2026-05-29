## Context

The current ingestion path uses a single `SentenceSplitter` with `chunk_size=512` and `chunk_overlap=64` for every file type. The reranker fetches `top_k * 2` candidates and reranks them, then the highest-scoring `top_k` are returned. Every search re-embeds the query through Ollama even if the same query has just been issued.

These choices are fine defaults but are conservative compared to the most recent published benchmarks for retrieval quality on structured documents and cross-encoder reranking. None of these changes require a new vector dimension, model swap, or reranker recalibration.

## Goals / Non-Goals

**Goals:**

- Improve recall and ranking quality for structured Markdown documents through heading-aware chunking.
- Improve top-k precision when reranking is enabled by feeding the cross-encoder a larger candidate pool.
- Reduce Ollama embedding load on repeat queries (common in agentic loops).
- Keep all changes opt-out friendly via existing or new env vars.

**Non-Goals:**

- No semantic chunking, hierarchical chunking, or proposition-style chunking. The Qu, Tu & Bao (2024) findings argue these are not consistently worth the compute overhead.
- No reranker model swap. Changing model would require re-running the calibration experiment in `experiments/reranker-threshold-calibration-2026-05-12/`.
- No HyDE-style query expansion. It introduces an LLM call per query and known hallucination risk.
- No hybrid retrieval. That is the scope of the separate `rag-hybrid-retrieval` change.

## Decisions

### Decision 1: Use `MarkdownNodeParser` chained with a sentence splitter for `.md` files

Branch on `file_path.suffix == ".md"` inside the chunking step and feed the documents through `MarkdownNodeParser` first, then through the existing `SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)`. Both parsers ship with `llama-index-core` so no new dependency is required. The two-stage pipeline keeps heading boundaries intact wherever they fall under `CHUNK_SIZE`, and falls back to splitting *within* a section only when a single heading-bounded block exceeds `CHUNK_SIZE`. Non-Markdown files continue with the existing `SentenceSplitter` alone.

The chained-splitter pattern matters because `MarkdownNodeParser` on its own will happily emit a single 10K-character node for a long H2 section, which would defeat embedding-batch sizing and produce one chunk that drowns out the rest of the document at retrieval time.

Experiment 6's first corpus did not validate this retrieval-quality claim: it measured source-file Hit@K on five topically distinct documents, and the baseline reached 100 % Hit@1. That is the evidence-sparsity failure mode described by Lu et al. (2025) in HiChunk / HiCBench: a benchmark with too few explicit evidence labels, or labels only at document level, cannot distinguish a correct evidence chunk from merely retrieving the right file. The follow-up validation SHALL therefore be Experiment 6b: a Qasper-dev evidence-level evaluator that uses gold evidence snippets and hierarchy labels. HiCBench was investigated but the published dataset URL was unavailable/404, so Qasper is canonical and HiChunk-schema support is retained only as historical compatibility.

Alternative considered: replace `SentenceSplitter` globally with a recursive splitter. Rejected because non-Markdown files (PDF, DOCX, TXT) do not benefit equally and risk-reward is asymmetric.

Alternative considered: use `MarkdownNodeParser` alone without a size cap. Rejected because of the long-section behaviour above.

### Decision 2: Configurable larger reranker fetch pool with empirical latency target

Replace `fetch_k = top_k * 2` with `fetch_k = max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)` when `rerank=True`. Defaults: `RERANK_MAX_FETCH=50`, `RERANK_FETCH_MULTIPLIER=10`. This implements the "Wide Net, Tight Filter" pattern.

The existing reranker calibration experiment (`experiments/reranker-threshold-calibration-2026-05-12/`) recorded ~85 ms mean and ~120 ms post-warmup latency for the *current* `top_k * 2 = 10` candidate pool, with vector-only baseline ~30 ms. Going from 10 to 50 candidates means roughly 5× more cross-encoder work; expected post-warmup latency for the new default lands in the 250–450 ms range on the same hardware.

To prevent quiet regressions, the implementation SHALL re-run the existing calibration experiment script with the new defaults and record the post-warmup mean and P95 latency in `experiments/reranker-threshold-calibration-2026-05-12/results.md` (or a new dated experiment directory if the corpus changes). The acceptance criterion is **post-warmup P95 ≤ 500 ms** on the calibration corpus. If the measured P95 exceeds 500 ms on the target hardware, the defaults SHALL be lowered (e.g. `RERANK_MAX_FETCH=30`, `RERANK_FETCH_MULTIPLIER=6`) until the criterion is met, and the chosen defaults documented in the experiment results.

An internal cap on `fetch_k` (e.g. clamp to `min(fetch_k, collection.count())`) ensures an unbounded `top_k` on a small collection does not produce a fetch larger than the collection itself.

Alternative considered: keep `top_k * 2` and rely on better embeddings. Rejected because the reranker is the most precise component in the pipeline and is currently starved of candidates.

Alternative considered: pick a P95 target without measuring. Rejected because the calibration script already exists and gives us a free, repeatable measurement.

### Decision 3: Move default chunk overlap from 64 to 100

The default `CHUNK_OVERLAP=64` is below the empirical sweet spot reported by Stäbler et al. (2025) and other recent benchmarks. Bumping the default to 100 keeps the same algorithm but improves boundary recovery. Existing `.env` overrides remain untouched.

Alternative considered: change `CHUNK_SIZE` too. Rejected because the existing experiment data uses 512 and the threshold calibration is implicitly tied to the current chunk-size behaviour.

### Decision 4: LRU cache for query embeddings, with `search()` refactored to a single embed call

Wrap the query embedding step in an in-process `functools.lru_cache(maxsize=128)` keyed on `(query, embed_model_name)`. The cache is process-local and resets on restart. The cache SHALL NOT extend to ingestion-time chunk embeddings because those have very low repeat rates and consume more memory.

The current `retrieval.search()` has two branches: the metadata-filtered branch explicitly calls `Settings.embed_model.get_query_embedding(query)`, while the unfiltered branch goes through `index.as_retriever(...).retrieve(query)` which embeds the query *inside* LlamaIndex. A naive `lru_cache` decorator will only catch the first branch and silently miss the second, which is the default path. To avoid this, `search()` SHALL be refactored so the query is embedded exactly once at the top of the function via the cached helper, and the resulting vector is threaded into both branches:

- The metadata-filtered branch already accepts a `query_embeddings=[...]` argument to `collection.query(...)`.
- The unfiltered branch SHALL be reworked to call `collection.query(query_embeddings=[vec], n_results=fetch_k)` directly, replacing the `VectorStoreIndex.from_vector_store(...).as_retriever(...).retrieve(query)` chain.

This refactor also collapses the two paths onto the same code, which makes Tier 1's score-normalisation work (`1.0 / (1.0 + distance)` everywhere) trivial to satisfy on this branch — the formula is already there in the filtered path.

Alternative considered: a persistent cache on disk. Rejected as overkill for a local MCP server.

Alternative considered: decorate `Settings.embed_model.get_query_embedding` and accept the LlamaIndex internal embed-call miss. Rejected because the spec scenario "the same query SHALL be embedded only once" would silently fail on the unfiltered default path.

## Risks / Trade-offs

- **Risk: heading-aware chunking on malformed Markdown produces fewer/larger chunks.** → Mitigate by preserving a chunk-size cap inside the heading branch.
- **Risk: source-level chunking evaluations saturate and create false negatives.** → Mitigate by validating Markdown chunking with Experiment 6b's Qasper evidence-level metrics instead of source-file Hit@K alone.
- **Risk: larger rerank pool increases search latency on slow CPUs.** → Mitigate with env vars so users can lower `RERANK_FETCH_MULTIPLIER`. Document the trade-off.
- **Risk: changing default chunk overlap affects existing collections only on re-ingestion.** → Acceptable; behaviour change is opt-in via re-ingest.
- **Risk: query embedding cache hides Ollama outages because cached results return.** → Mitigate by limiting `maxsize` and noting in module docstring that the cache is process-local and bypassed on cache miss.

## Migration Plan

No data migration required. Bumping `CHUNK_OVERLAP` only affects newly ingested chunks. Existing chunks continue to work at their previous overlap until they are re-ingested. Rollback is a code rollback.

## Open Questions

- None blocking. The reranker pool latency target is empirical and will be confirmed by re-running the calibration experiment during implementation; if P95 exceeds 500 ms, the defaults are tightened per Decision 2.

## Resolved Questions

- **Markdown parser opt-in vs always-on?** — always-on for `.md` files (per Decision 1). The chained sentence-splitter cap removes the main downside.
- **Should `RERANK_FETCH_MULTIPLIER` apply when reranking is disabled?** — no. Pool sizing is a reranker-only concern; non-reranked search continues to use `fetch_k = top_k`.
- **Where does the query embedding cache live?** — inside a refactored `search()` that embeds once at the top and threads the vector into both ChromaDB calls (per Decision 4).
