## 1. Shared infrastructure — fetch_k override

- [x] 1.1 `fetch_k` override on `_resolve_fetch_k()` and `search()` in `retrieval.py` — already implemented per TDR-005 (`docs/tdr/005-fetch-k-override-for-experiment-pool-sweeps.md`). The reranker (`reranker.py`) does not need modification; it processes whatever candidates it receives. The pool size is controlled upstream by `_resolve_fetch_k()`.
- [x] 1.2 Unit tests verifying override produces distinct pool sizes, clamps to collection, and preserves formula when `None` — already in `tests/test_rerank_fetch_pool.py` (`test_override_bypasses_formula`, `test_override_distinct_values_no_collapse`, `test_override_still_clamps_to_collection`, `test_override_none_preserves_formula`)
- [x] 1.3 Verify `uv run pytest -m "not slow" --cov=rag_mcp` passes with no regressions before starting experiment work

## 2. Experiment 10b — Corrected reranker pool-size sweep

- [x] 2.1 Create experiment directory `experiments/10b-reranker-pool-size-corrected-2026-06-29/`
- [x] 2.2 Write `protocol.md` following the full protocol template: hypotheses, variables, cell matrix with distinct `fetch_k ∈ {50, 100, 200, 500}`, pass gates (pool-size lift ≥ 3pp, diminishing returns ≤ 2pp, reranker-off ceiling reference), interpretation rules
- [x] 2.3 Verify Exp 9a scripts (`prepare_freshstack.py`, `build_indexes.py`) are available. Note: Exp 9a corpus and ChromaDB indexes are gitignored and not on disk — they must be rebuilt
- [x] 2.4 Write `build_indexes.py` that runs `prepare_freshstack.py` (seed 20260530) then builds dense + hybrid indexes in the 10b experiment directory
- [x] 2.5 Write `run_eval.py` that calls `retrieval.search()` with per-cell `fetch_k=` parameter (the Python API override per TDR-005), runtime assertion that all four pool sizes are genuinely distinct, and atomic checkpoint/resume
- [x] 2.6 Write `summarise_eval.py` that computes pool-size lift, diminishing returns, and reranker-off vs best reranker-on comparison
- [ ] 2.7 Run evaluation: `PYTHONUNBUFFERED=1 uv run python -u experiments/10b-.../run_eval.py --modes dense-only,hybrid_bm25 --rerank-cross --k-values 5 10 20 50 --resume 2>&1 | tee experiments/10b-.../output/run_eval.log`
- [ ] 2.8 Summarise results and write `results.md` with executive summary, per-pool metrics table, pass gate evaluation, and recommendation (does any pool size recover hybrid's advantage?)
- [ ] 2.9 Update `experiments/EXP_README.md` index with Exp 10b entry and status
- [ ] 2.10 If results warrant an ADR-019 amendment, draft the amendment text (do not file yet — separate change)

## 3. Experiment 10.1 — DOC_SIMILARITY_THRESHOLD calibration

- [x] 3.1 Create experiment directory `experiments/10.1-doc-similarity-threshold-calibration-2026-06-29/`
- [x] 3.2 Write `protocol.md`: sweep `DOC_SIMILARITY_THRESHOLD ∈ {0.70, 0.75, 0.80, 0.85, 0.90}`, metrics (edge count, cluster count, mean cluster size, modularity, false-positive rate), pass gate (maximise modularity with FP rate < 20%), interpretation rules
- [x] 3.3 Build mixed corpus: representative sample of this repo's own codebase (≥ 30 code files) plus prose documentation (≥ 20 doc files), ensuring ≥ 50 documents with pairwise similarity above 0.70
- [x] 3.4 Write `run_eval.py` that builds the document graph for each threshold value using `rag_mcp.doc_graph.build_document_graph()` and records structural metrics
- [x] 3.5 Manually rate 10 random edges per threshold as "meaningful link" or "noise" to compute false-positive rate (record in a `manual_ratings.json`)
- [x] 3.6 Write `summarise_eval.py` that identifies the threshold maximising modularity with FP < 20%
- [ ] 3.7 Run evaluation and write `results.md` with executive summary, per-threshold table, pass gate evaluation, recommendation (is 0.85 acceptable?)
- [ ] 3.8 Update `experiments/EXP_README.md` index with Exp 10.1 entry
- [ ] 3.9 If results warrant an ADR-023 amendment, draft the amendment text (separate change)

## 4. Experiment 12 — Hybrid default promotion (post-ADR-019)

- [x] 4.1 Create experiment directory `experiments/12-hybrid-default-promotion-2026-06-29/`
- [x] 4.2 Write `protocol.md`: cell matrix `{dense, hybrid} × {rerank-off, rerank-on}` (rerank-on cells are reference only), revised quality gate (≥ 3pp Coverage@20 lift), semantic guardrail (≤ −2pp regression), statistical confidence (bootstrap 95% CI), interpretation rules
- [x] 4.3 Verify Exp 9a scripts are available and run `prepare_freshstack.py` + `build_indexes.py` to rebuild indexes (gitignored, not on disk)
- [x] 4.4 Write `run_eval.py` reusing the Exp 9a FreshStack LangChain corpus with post-ADR-019 reranker-off as the decision cells
- [x] 4.5 Write `summarise_eval.py` with bootstrap confidence intervals on the Coverage@20 lift
- [ ] 4.6 Run evaluation and write `results.md` with executive summary, cell metrics, pass gate evaluation (including CI), recommendation (flip `HYBRID_ENABLED=true`?)
- [ ] 4.7 Update `experiments/EXP_README.md` index with Exp 12 entry
- [ ] 4.8 If results pass all gates, draft a new ADR for hybrid default promotion (separate change)

## 5. Experiment 9a-rerun — Post-ADR-021 reranker validation

- [x] 5.1 Create experiment directory `experiments/9a-rerun-post-adr021-reranker-2026-06-29/`
- [x] 5.2 Write `protocol.md`: same 4-cell grid as Exp 9a but with post-ADR-021 config (`MULTIPLIER=3`, `MAX_FETCH=100`), effective `fetch_k=150` at `top_k=50`, pass gate (does reranker-on still degrade Coverage@20?), latency comparison to original Exp 9a
- [x] 5.3 Verify Exp 9a scripts are available and run `prepare_freshstack.py` + `build_indexes.py` to rebuild indexes (gitignored, not on disk)
- [x] 5.4 Write `run_eval.py` reusing Exp 9a corpus with post-ADR-021 reranker config
- [x] 5.5 Write `summarise_eval.py` comparing results to original Exp 9a (`fetch_k=500` vs `fetch_k=150`)
- [ ] 5.6 Run evaluation and write `results.md` with executive summary, comparison table (9a original vs 9a-rerun), pass gate evaluation, conclusion (ADR-019 validated/invalidated/uncertain)
- [ ] 5.7 Update `experiments/EXP_README.md` index with Exp 9a-rerun entry
- [ ] 5.8 If ADR-019 is invalidated, draft amendment text (separate change)

## 6. Experiment 13 — HARD_TECHNICAL_THRESHOLD calibration

- [x] 6.1 Create experiment directory `experiments/13-hard-technical-threshold-calibration-2026-06-29/`
- [x] 6.2 Write `protocol.md`: sweep `HARD_TECHNICAL_THRESHOLD ∈ {0.1, 0.2, 0.3, 0.5, 0.7}`, mixed corpus (FreshStack technical + Qasper semantic), sweep technical-query fraction {100%, 90%, 75%, 50%, 25%, 0%}, per-threshold quality measurement (Coverage@20 for technical and semantic queries separately), minimum 30 queries per cell
- [x] 6.3 Prepare Qasper corpus: download full dev set from HuggingFace (`allenai/qasper`), export queries and PDFs (Exp 6b/7a fixtures are too small for the 30 queries/cell minimum)
- [x] 6.4 Build mixed-corpus ground truth: combine FreshStack LangChain ground truth with Qasper ground truth, tagging each query as technical or semantic
- [x] 6.5 Write `run_eval.py` that sweeps both threshold and query-fraction dimensions
- [x] 6.6 Write `summarise_eval.py` that identifies the threshold preserving semantic benefit (≥ +1pp) while minimising technical regression (≤ −1pp)
- [ ] 6.7 Run evaluation and write `results.md` with executive summary, per-threshold × per-fraction table, pass gate evaluation, recommendation (is 0.3 acceptable?)
- [ ] 6.8 Update `experiments/EXP_README.md` index with Exp 13 entry
- [ ] 6.9 If results warrant an ADR-019 amendment, draft the amendment text (separate change)

## 7. Experiment 14 — LiteParse promotion on harder corpus

- [x] 7.1 Create experiment directory `experiments/14-liteparse-qasper-promotion-2026-06-29/`
- [x] 7.2 Write `protocol.md`: Qasper corpus (academic two-column PDFs, ≥ 100 queries across ≥ 30 PDFs), H3 validation (reranker benefit vs LiteParse), H2 speed validation (post-ADR-021 latency), corpus validity gate (dense baseline < 100% Hit@5)
- [x] 7.3 Prepare Qasper PDF corpus: export full dev set PDFs from `allenai/qasper` dataset (≥ 30 PDFs, not the 20-paper Exp 6b/7a subset), ingest via both `PDF_READER=pypdf` and `PDF_READER=liteparse`
- [x] 7.4 Write `run_eval.py` comparing `{pypdf, liteparse} × {rerank-on, rerank-off}` on Qasper queries
- [x] 7.5 Write `summarise_eval.py` with H3 comparison (reranker lift per reader) and H2 speed comparison to Exp 11
- [ ] 7.6 Run evaluation and write `results.md` with executive summary, per-reader metrics, H3/H2 gate evaluation, recommendation (flip `PDF_READER=auto` default?)
- [ ] 7.7 Cross-reference and supersede the unfilled TODO sections in Exp 11's `results.md` (add a pointer from Exp 11 to Exp 14)
- [ ] 7.8 Update `experiments/EXP_README.md` index with Exp 14 entry
- [ ] 7.9 If results warrant an ADR-020 amendment for LiteParse promotion, draft the amendment text (separate change)

## 8. Close-out

- [x] 8.1 Verify all six experiment directories contain `protocol.md`, `results.md`, `run_eval.py`, `eval_results.json`, and `eval_results.summary.json`
- [x] 8.2 Update `experiments/EXP_README.md` index with all new entries and statuses
- [x] 8.3 Move experiment review notes (`experiments/notes/experiment_review-repeat-*.md`) to `experiments/notes/archive/` with a cross-reference to this change
- [x] 8.4 Run `openspec validate calibrate-rag-retrieval-defaults --strict` to verify change integrity
