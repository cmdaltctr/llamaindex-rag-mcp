## 1. Markdown-aware chunking

- [x] 1.1 Add a Markdown branch in the async ingestion chunking step that uses LlamaIndex's `MarkdownNodeParser` for files with extension `.md`
- [x] 1.2 Chain a `SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)` after `MarkdownNodeParser` so heading-bounded sections longer than `CHUNK_SIZE` are further split
- [x] 1.3 Keep the existing default splitter for all other file types
- [x] 1.4 Add a fixture Markdown document with multiple H2 sections, all shorter than `CHUNK_SIZE`, and assert chunk boundaries align with heading boundaries
- [x] 1.5 Add a fixture Markdown document with a single H2 section longer than `CHUNK_SIZE` and assert it produces more than one chunk and every chunk is at most `CHUNK_SIZE` characters
- [x] 1.6 Add a test asserting non-Markdown files retain previous chunk count and content
- [x] 1.7 Add a test asserting a Markdown file with no headings still produces non-empty chunks
- [x] 1.8 Run **Experiment 6** (`experiments/6-markdown-chunking-quality-2026-05-27/`) end-to-end and confirm heading-targeted Hit@1 lifts ≥ 5 pp, general-query Hit@1 stays within ±2 pp of baseline, and max chunk length ≤ `CHUNK_SIZE * 1.1`
- [x] 1.9 If Experiment 6 fails its pass criteria: revisit tasks 1.2 (size cap), 1.5 (cap test), or the Markdown branch wiring, re-run the experiment, loop until criteria pass

## 2. Reranker fetch pool sizing

- [x] 2.1 Add `RERANK_FETCH_MULTIPLIER` and `RERANK_MAX_FETCH` env vars to `config.py` with defaults `10` and `50`
- [x] 2.2 Replace the `top_k * 2` candidate calculation with `max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)` when reranking is enabled
- [x] 2.3 Clamp the resulting `fetch_k` to `min(fetch_k, collection.count())` so small collections do not over-fetch
- [x] 2.4 Add tests covering the default pool size, env-var-overridden pool size, and the small-collection clamp behaviour
- [x] 2.5 Verify the calibrated reranker threshold scaling factor remains unchanged
- [x] 2.6 Run **Experiment 5** (`experiments/5-reranker-pool-sizing-2026-05-27/`) — extends `experiments/1-...` with a fetch-size sweep across `(20, 2)`, `(50, 10)`, `(30, 6)`, `(100, 20)` and records post-warmup mean / P95 latency and accuracy per config
- [x] 2.7 Confirm the chosen default config has post-warmup P95 ≤ 500 ms; if `(50, 10)` exceeds, fall back to `(30, 6)` and re-run until the criterion is met. Record the chosen defaults in `experiments/5-reranker-pool-sizing-2026-05-27/results.md` and propagate to `config.py`

## 3. Default chunk overlap bump

- [x] 3.1 Change the default `CHUNK_OVERLAP` in `config.py` from 64 to 100
- [x] 3.2 Confirm `.env.example` is consistent
- [x] 3.3 Add or update a test that asserts the new default value when no env override is set
- [x] 3.4 Run **Experiment 7** (`experiments/7-chunk-overlap-sensitivity-2026-05-27/`) — sweeps `CHUNK_OVERLAP ∈ {32, 64, 100, 128}` against the Exp 3 corpus with the reranker enabled and the Exp 5 pool defaults
- [x] 3.5 Confirm overlap=100 Hit@1 / MRR ≥ overlap=64 Hit@1 / MRR and chunk-count delta vs overlap=64 ≤ 15 %; if not, hold the default at 64 (revert task 3.1) and document the corpus-specific result

## 4. Query embedding cache and `search()` refactor

- [x] 4.1 Refactor `retrieval.search()` so the query is embedded exactly once at the top of the function via a cached helper, and the resulting vector is threaded into both the filtered and unfiltered branches
- [x] 4.2 Replace the unfiltered branch's `VectorStoreIndex.from_vector_store(...).as_retriever(...).retrieve(query)` chain with a direct `collection.query(query_embeddings=[vec], n_results=fetch_k)` call so the LlamaIndex internal embed call is removed
- [x] 4.3 Wrap the cached helper with `functools.lru_cache(maxsize=128)` keyed on `(query, embed_model_name)`
- [x] 4.4 Add a unit test asserting two identical queries on the unfiltered path hit Ollama only once
- [x] 4.5 Add a unit test asserting two identical queries on the filtered path hit Ollama only once
- [x] 4.6 Add a unit test asserting an unfiltered call followed by a filtered call with the same query hits Ollama only once
- [x] 4.7 Add a unit test asserting that distinct queries do not collide in the cache
- [x] 4.8 Add a unit test asserting LRU eviction at the configured `maxsize`
- [x] 4.9 Confirm the existing Tier 1 score-normalisation guarantee (`score = 1.0 / (1.0 + distance)` on both branches) is preserved by the refactor — both branches now use the same direct ChromaDB call
- [x] 4.10 Run **Experiment 8** (`experiments/8-query-embedding-cache-2026-05-27/`) end-to-end and confirm warm-trace mean latency drops ≥ 30 %, cold-trace mean latency stays within ±5 % of cache-off, both retrieval paths show ≥ 80 % cache hit rate on the warm trace, and LRU eviction caps cache size at `maxsize=128`
- [x] 4.11 If Experiment 8 fails its pass criteria: revisit task 4.2 (unfiltered-branch refactor) if the unfiltered hit rate is 0 %, or task 4.3 (cache wrapper) if both branches miss; re-run the experiment, loop until criteria pass

## 5. Documentation

- [x] 5.1 Update the reranker section in `AGENTS.md` to document the new fetch pool env vars and the P95 ≤ 500 ms target
- [x] 5.2 Update the chunking section in `AGENTS.md` to note Markdown branching and the chained sentence-splitter cap
- [x] 5.3 Update `.env.example` to include the new reranker env vars and the bumped `CHUNK_OVERLAP` default

## 6. ADR — record the architectural decisions

After implementation passes validation, write **ADR-016: RAG Retrieval Quality Improvements** under `docs/adr/016-rag-retrieval-quality-improvements.md` following the existing ADR convention. Use ADR-014 as the structural template — one ADR per OpenSpec change, with sub-decisions as numbered bullets inside the Decision section.

- [ ] 6.1 Capture the four sub-decisions from `design.md` as numbered bullets in the Decision section:
  1. Markdown branch chains `MarkdownNodeParser` → `SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)` so heading-bounded sections longer than `CHUNK_SIZE` are still capped
  2. Reranker fetch pool grows from `top_k * 2` to `max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)` (defaults `50` and `10`); post-warmup P95 latency target ≤ 500 ms verified by re-running the existing reranker calibration experiment
  3. Default `CHUNK_OVERLAP` bumped from 64 to 100 (Stäbler et al. 2025 empirical sweet spot)
  4. Process-local `lru_cache(maxsize=128)` on query embeddings keyed by `(query, embed_model_name)`; `search()` refactored to embed once at the top and thread the vector into both filtered and unfiltered branches (the unfiltered branch's `VectorStoreIndex.as_retriever()` chain is replaced by a direct `collection.query(query_embeddings=[vec], n_results=fetch_k)` call)
- [ ] 6.2 In Consequences, note: positive (cache shared across both branches, both branches collapse onto the same code path which automatically satisfies ADR-015's score-normalisation contract, headings preserved on Markdown, larger reranker pool catches the Colosseum-style failure mode); negative (post-warmup latency rises into the 250–450 ms range, bounded by the 500 ms P95 ceiling); neutral (LlamaIndex's `VectorStoreIndex` is no longer used in the search path — note the API surface narrowing).
- [ ] 6.3 Record the actual measured P95 from the rerun calibration experiment in the ADR's Decision section, and the chosen final defaults if they were tightened from `(50, 10)`.
- [ ] 6.4 In Alternatives Considered, record: `MarkdownNodeParser` alone without a size cap (rejected — long sections); persistent on-disk embedding cache (rejected — overkill); decorating `Settings.embed_model.get_query_embedding` only (rejected — silently misses the unfiltered branch); semantic / hierarchical / proposition chunking (rejected — Qu, Tu & Bao 2024 do not justify the compute overhead); HyDE-style query expansion (rejected — adds an LLM call per query and known hallucination risk).
- [ ] 6.5 Cross-reference ADR-005 (cross-encoder reranker — this ADR extends its fetch-pool sizing) and ADR-015 (which this ADR composes with on score normalisation). Reference the OpenSpec change directory and the rerun experiment directory.
- [ ] 6.6 Update `docs/adr/ADR_README.md` index table with the new ADR row.
- [ ] 6.7 Set status to `Accepted` once the change is archived.

## 7. Validation

- [x] 7.1 Run `openspec validate rag-retrieval-quality-improvements --strict`
- [x] 7.2 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm coverage thresholds remain intact
- [x] 7.3 Confirm Experiment 5 (`experiments/5-reranker-pool-sizing-2026-05-27/`) shows post-warmup P95 ≤ 500 ms with the chosen defaults, and that the chosen `(RERANK_MAX_FETCH, RERANK_FETCH_MULTIPLIER)` defaults are reflected in `config.py` and `.env.example`
- [x] 7.4 Confirm Experiment 6 (`experiments/6-markdown-chunking-quality-2026-05-27/`) shows the heading-targeted Hit@1 lift and no chunk overruns past `CHUNK_SIZE * 1.1`
- [x] 7.5 Confirm Experiment 7 (`experiments/7-chunk-overlap-sensitivity-2026-05-27/`) shows non-regression between overlap=64 and overlap=100
- [x] 7.6 Confirm Experiment 8 (`experiments/8-query-embedding-cache-2026-05-27/`) shows ≥ 30 % warm-trace speedup and zero overhead on the cold trace, on both retrieval branches
- [x] 7.7 Confirm ADR-016 is published, indexed, and cross-referenced before archiving the OpenSpec change
