# Tasks: harden-pipeline-correctness-before-calibration

> This change is intentionally staged. **STOP at every PAUSE GATE.** Commit, inspect the diff/results, and only then continue. A later stage MUST NOT be used to hide a failing earlier-stage correctness test.
>
> **Remote progress note (2026-08-18):** Stage 0 now has all ten audit regressions plus the lightweight experiment-plan contract/tests, and `audit-baseline.md` records the parent/start SHA and archive-vs-implementation rule. Exact local dependency versions still require the worktree. Stage 1 implementation, deterministic tests, configuration/docs and a Proposed TDR were written remotely. No local test/lint/OpenSpec validation or manual chunk inspection was possible, so every execution/acceptance gate remains unchecked. **Do not start Stage 2 until Gates 0 and 1 have been run locally and any failures fixed.**

## Decision-record policy for every stage

Every PAUSE GATE MUST include an explicit decision-record check. The goal is not to create paperwork for every code edit; it is to preserve the reasoning for decisions that future stages, experiments, or backends depend on.

- **Write or amend an ADR** when the stage changes an architectural or behavioural contract: public configuration semantics, persistence/durability guarantees, ownership boundaries, score/threshold meaning, backend swappability guarantees, or a production default/policy.
- **Write a TDR** when the decision is primarily technical and implementation-scoped: a reversible implementation technique, test/preflight mechanism, benchmark-driven optimisation, cache-key shape, experiment-runner mechanism, or tooling convention that does not itself redefine a public architectural contract.
- **Write neither only with an explicit gate note** stating `ADR/TDR not required` and why the stage did not create a durable technical decision.
- Decision records MUST reference the evidence that justified them: failing/passing regression tests, benchmark/experiment IDs, relevant raw artefacts, and the implementation/result commit SHA where available.
- A planned fix MUST NOT be written as measured fact. Records that depend on empirical evidence stay proposed/draft until the corresponding pause-gate evidence exists.
- Experiment-result commits and production-policy ADR changes MUST remain separate where a later gate says so; first commit the evidence, then record/adopt the decision.

---

## 0. Stage 0 — Freeze and executable baseline audit

### 0.1 Baseline provenance

- [x] 0.1.1 Record the `v3` parent SHA and hardening-branch starting SHA in `audit-baseline.md`.
- [x] 0.1.2 Record Python, locked LlamaIndex, ChromaDB, LanceDB, ONNX Runtime, tokenizers, and optional Torch/SentenceTransformers versions used by the audit environment. (Recorded in `audit-baseline.md` Gate 0 table: Python 3.12.10, llama-index 0.14.23, chromadb 1.5.9, lancedb 0.37.1, onnxruntime 1.28.0, tokenizers 0.22.2; torch/sentence-transformers absent.)
- [x] 0.1.3 Record which archived OpenSpecs are design intent only versus confirmed in current production code; do not infer “archived == implemented”.

### 0.2 Reproduce audit defects with failing tests

- [x] 0.2.1 Add a CodeSplitter regression that proves the AST implementation is invoked with the installed LlamaIndex API and fails on the current invalid `chunk_size` / `chunk_overlap` call.
- [x] 0.2.2 Add a structural code fixture where CodeSplitter and SentenceSplitter produce observably different boundaries; assert the AST result, not merely that nodes exist.
- [x] 0.2.3 Add a hybrid metadata-filter regression in which BM25 ranks a forbidden document highly and prove current RRF leaks it back into results.
- [x] 0.2.4 Add a two-store/same-collection BM25 cache regression with equal generation values and different contents.
- [x] 0.2.5 Add a hybrid non-reranked threshold regression demonstrating that an RRF top score (~`2/(rrf_k+1)`) is not on the dense threshold scale.
- [x] 0.2.6 Add Chroma/Lance generation-counter assertions showing the current ownership asymmetry/double-bump path.
- [x] 0.2.7 Add a metadata-extractor cap regression using text where token count and character count make the current early truncation observable.
- [x] 0.2.8 Add a static/unit test comparing Experiment 10b protocol-declared cells/hypotheses with its current runner cell generator; it MUST fail before the runner repair.
- [x] 0.2.9 Add an Experiment 13 regression proving `rerank=True` bypasses `HARD_TECHNICAL_THRESHOLD`; test the current runner calls the bypassing path.
- [x] 0.2.10 Add an Experiment 14 regression proving parser selection cannot affect the current Markdown-only build path.

### 0.3 Experiment protocol skeleton

- [x] 0.3.1 Add a tiny shared machine-readable experiment plan representation (dataclass/JSON schema/plain dict contract) with experiment ID, factors, cells, controlled variables and required manifest assertions.
- [x] 0.3.2 Add unit tests that compare declared cells against runner-generated cells without loading large models or corpora.

### PAUSE GATE 0 — audit-only commit

- [x] 0.G.1 Run the targeted regressions and confirm each intended defect fails for the intended reason. (2026-08-18 local run: 2 Stage 1 regressions pass; 5 Stage 2 and 3 Stage 4 regressions fail — each assertion failure matches its intended defect: sparse signature lacks `metadata_filter`, BM25 cache leaks across stores, RRF score over-filtered by dense threshold, Chroma `write_nodes` does not own generation bump, orchestration duplicates bumps, exp 10b runner lacks hybrid treatment, exp 13 pins `rerank=True`, exp 14 lacks `glob("*.pdf")`.)
- [x] 0.G.2 Run unaffected fast tests to ensure audit tests themselves did not mutate runtime behaviour. (`uv run pytest -m "not slow"`: 1575 passed, 17 skipped, 8 failed — the failures are exactly the intentional audit regressions from 0.G.1.)
- [x] 0.G.3 Commit **tests/docs only** with a message such as `test: pin pre-calibration pipeline audit failures`. (Commit `1ed2daf` touches `tests/` only.)
- [x] 0.G.4 Review whether any finding is actually a changed requirement. Amend `design.md` before implementing if so. (Reviewed: all findings are defects against existing specs; the metadata per-chunk claim was a documentation error fixed in 1.3.3, not a requirement change. No amendment needed.)
- [x] 0.G.5 Decision-record check: if Stage 0 establishes a durable audit/experiment-plan convention, write a TDR such as **“Pre-calibration audit and executable experiment-plan validation”**; otherwise record `ADR/TDR not required` because Stage 0 only captures baseline evidence. (`docs/tdr/011-pre-calibration-audit-and-experiment-plan-validation.md`, Accepted.)

---

## 1. Stage 1 — Deterministic component correctness

### 1.1 CodeSplitter API and units

- [x] 1.1.1 Add code-specific settings (`code_chunk_lines`, `code_chunk_lines_overlap`, `code_max_chars`) to chunking settings / EffectiveSettings with documented units.
- [x] 1.1.2 Construct LlamaIndex CodeSplitter with the installed/supported parameter names; remove the invalid token-setting argument names.
- [x] 1.1.3 Keep SentenceSplitter fallback, but surface requested/effective strategy and fallback reason in internal diagnostics/logs.
- [x] 1.1.4 Make fallback tests assert fallback explicitly; make success tests fail if fallback occurred.
- [x] 1.1.5 Add at least Python + one brace-based language fixture to verify structural boundaries and no parser/API silent degradation.
- [x] 1.1.6 Correct comments/docstrings that label SentenceSplitter token settings as characters.

### 1.2 Markdown/sentence helper consistency

- [x] 1.2.1 Forward `markdown_heading_prepend` and `markdown_min_chunk_fraction` through standalone `chunk_sentence_file_async()` exactly as the main ingestion path does.
- [x] 1.2.2 Add parity tests showing the helper and main document path apply the same configured Markdown post-processing.

### 1.3 Metadata cap semantics

- [x] 1.3.1 Replace `text[: max_chunks * chunk_size]` with split-then-cap (preferred) or a tokenizer-faithful equivalent.
- [x] 1.3.2 Test that exactly the configured maximum number of metadata-extraction chunks reach expensive extractors on a synthetic long document.
- [x] 1.3.3 Correct docs: the current LlamaIndex extractor uses temporary per-chunk enrichments but aggregates them to file-level metadata that is copied to final stored chunks.

### PAUSE GATE 1 — deterministic component commit

- [x] 1.G.1 Run targeted chunking + metadata tests. (2026-08-18 local run: `test_chunking_hardening.py` + `test_metadata_cap_hardening.py` + `test_experiment_plan_contract.py` + `tests/unit/test_type_aware_ingestion.py` — 21 passed.)
- [x] 1.G.2 Run `ruff check` / `ruff format --check` for touched files. (One I001 import-sort and three format drifts fixed 2026-08-18; both commands now clean.)
- [x] 1.G.3 Commit as a standalone correctness change; do not include retrieval or experiment-runner changes. (Stage 1 implementation commits `7a3840d`–`95046fc` touch only chunking/metadata/config paths; retrieval and experiment-runner changes live in separate commits.)
- [x] 1.G.4 Inspect several emitted chunks manually from the structural fixtures before proceeding. (2026-08-18 manual probe via `read_and_chunk_file_async` with default settings: 148-line Python fixture → 3 chunks starting at `def function_0/6/12`; 163-line JS fixture → 3 chunks starting at `function handler0/5/10`; all chunks under `code_max_chars=1500`, no mid-function cuts, `chunk_strategy_effective == "code"` throughout.)
- [x] 1.G.5 Decision-record check: write a TDR for the **CodeSplitter parameter/unit mapping, fallback-observability rule, and metadata-cap implementation** if those choices are implementation-scoped. If the new code-specific settings redefine a stable public chunking/configuration contract beyond the existing OpenSpec delta, promote that portion to an ADR or amend the relevant existing ADR instead. (`docs/tdr/010-separate-code-chunking-units-and-metadata-budget.md`, Accepted 2026-08-18 after the Stage 1 validation gate.)

---

## 2. Stage 2 — Semantic swappability and retrieval contracts

### 2.1 Canonical dense score contract

- [x] 2.1.1 Change the VectorStore dense-query contract so adapters return a higher-is-better canonical `score` plus `score_kind`; core retrieval SHALL not convert generic `distance` itself.
- [x] 2.1.2 Implement Chroma conversion at the Chroma adapter boundary and pin its native metric assumptions in tests.
- [x] 2.1.3 Implement LanceDB conversion at the Lance adapter boundary and pin its native metric assumptions in tests.
- [x] 2.1.4 Add identical precomputed-vector fixtures across both stores; assert expected nearest-neighbour order, monotonic score behaviour, score range and score-kind identity.
- [x] 2.1.5 If exact cross-store score equality is not mathematically justified, assert the documented invariant rather than forcing equality; amend the score spec before continuing.

### 2.2 Threshold semantics

- [x] 2.2.1 Remove direct application of dense `similarity_threshold` to RRF `fused_score`.
- [x] 2.2.2 Pin dense/no-rerank threshold behaviour against canonical dense score.
- [x] 2.2.3 Pin hybrid/no-rerank behaviour: dense threshold is evaluated on dense evidence before fusion; sparse-only rows SHALL NOT claim to satisfy a positive minimum dense similarity.
- [x] 2.2.4 Pin hybrid+rerank behaviour: RRF chooses candidates; successful reranker score is the final thresholdable quantity.
- [x] 2.2.5 Pin reranker-failure behaviour so threshold semantics return to the correct pre-rerank score kind.
- [x] 2.2.6 Surface threshold score-kind in diagnostics/runtime manifest.

### 2.3 Hybrid filter symmetry

- [x] 2.3.1 Thread the caller metadata filter into the sparse branch through a store-neutral mechanism.
- [x] 2.3.2 Test dense-only and hybrid return no forbidden metadata rows for equivalent filters.
- [x] 2.3.3 Test nested/operator filter shapes already supported by both store backends.
- [x] 2.3.4 Document any unavoidable performance trade-off separately from correctness.

### 2.4 BM25 cache namespace

- [x] 2.4.1 Key BM25 cache by `(store identity token, collection_name)` rather than collection name alone.
- [x] 2.4.2 Clear/rebuild only the affected namespace on generation change.
- [x] 2.4.3 Add Chroma-vs-Lance and two-Chroma-instance collision tests.

### 2.5 Generation ownership

- [x] 2.5.1 Make every VectorStore mutation advance its own generation exactly once.
- [x] 2.5.2 Add missing Chroma bumps for store-owned mutation paths as required.
- [x] 2.5.3 Remove writer/orchestration duplicate bumps.
- [x] 2.5.4 Run direct-store and pipeline mutation contract tests against ChromaDB and LanceDB.

### 2.6 Swappability boundary documentation

- [x] 2.6.1 Document embedding provider selection as process/deployment-scoped because LlamaIndex embed model is still process-global.
- [x] 2.6.2 Add a guard/test preventing claims of concurrent per-collection embed-provider selection without a future explicit design.

### 2.7 Required architecture decision record

- [x] 2.7.1 Write or amend an ADR covering **semantic VectorStore swappability**: canonical higher-is-better score semantics, native-metric conversion at adapter boundaries, `score_kind`, dense/RRF/reranker threshold semantics, metadata-filter symmetry, store-scoped sparse-cache identity, exactly-once generation ownership, and the current deployment-scoped embedding-provider limitation.
- [x] 2.7.2 Reference the cross-store contract tests and Example Experiments 2–4 as evidence inputs; do not claim experiment PASS before Stage 5 actually runs them.

### PAUSE GATE 2 — retrieval-contract commit

- [x] 2.G.1 Run the same retrieval/vector-store contract suite against ChromaDB and LanceDB. (`tests/test_vectordb_contract.py`, `tests/test_lancedb_store.py`, and direct/pipeline mutation parametrizations pass against both adapters.)
- [x] 2.G.2 Run hybrid filter/cache/threshold regression suites. (`tests/test_hybrid_retrieval.py` and the five Stage 2 audit regressions pass.)
- [x] 2.G.3 Review score semantics and diagnostics before committing. (Canonical dense, RRF, and reranker score kinds are explicit; diagnostics name the thresholded score kind.)
- [x] 2.G.4 Commit Stage 2 separately; no ingestion or experiment-runner edits in this commit. (Commit `6dffece`; the only ingestion-path change is the Stage 2 generation-ownership fix required by 2.5.3—no Stage 3 ingestion behaviour or experiment runner was changed.)
- [x] 2.G.5 ADR gate: the Stage 2 ADR MUST exist in draft/proposed form before implementation is considered complete; after the deterministic contract suite passes, update its status/wording to reflect tested facts and link the Stage 2 commit. (ADR-047 was Proposed before implementation commit `6dffece`, is now Accepted with deterministic evidence, and links that commit; Experiments 2–4 remain explicitly unrun.)

---

## 3. Stage 3 — Bounded and failure-safe ingestion

### 3.1 Bound memory lifetime

- [x] 3.1.1 Remove the directory-sized `all_nodes` accumulation.
- [x] 3.1.2 Process at most one source file (or another explicitly bounded batch) through parse/chunk/write before releasing its nodes.
- [x] 3.1.3 Add generated-corpus tests that record maximum simultaneously retained node count independently of total file count.

### 3.2 Change detection / index identity

- [x] 3.2.1 Rebase the archived `add-ingestion-change-detection` intent onto current Chroma + Lance abstractions.
- [x] 3.2.2 Store `source_content_hash` plus an index-shaping identity covering embedding model/provider, parser and chunking settings that invalidate existing chunks/vectors.
- [x] 3.2.3 Skip unchanged files only when both content identity and index-shaping identity match.
- [x] 3.2.4 Test repeated ingest, content edit, embedding-model change, parser change and chunk-setting change.

### 3.3 Failure-safe replacement

- [x] 3.3.1 Write the new source version before deleting stale versions.
- [x] 3.3.2 Verify new rows are durable before stale deletion.
- [x] 3.3.3 Delete only stale versions of the same source using store-neutral filtering/version metadata.
- [x] 3.3.4 Add injected parse failure: old version remains searchable.
- [x] 3.3.5 Add injected embedding failure: old version remains searchable.
- [x] 3.3.6 Add injected store-write failure: old version remains searchable.
- [x] 3.3.7 Add interrupted-run recovery test for a collection containing both old and new versions.

### 3.4 Instrument before optimising concurrency

- [x] 3.4.1 Add timing counters for parse/chunk, embed, write, lock wait and total per bounded unit.
- [x] 3.4.2 Add peak-RSS sampling helper for the ingestion benchmark where supported.
- [x] 3.4.3 Do NOT widen concurrency in the same commit unless deterministic safety requires it.

### 3.5 Required architecture decision record

- [x] 3.5.1 Write or amend an ADR for **bounded, failure-safe source replacement** covering: bounded memory lifetime, content + index-shaping identity, write-new-before-delete-stale ordering, durability verification, stale-version cleanup/recovery, and the guarantee that a failed re-ingest leaves the last good searchable version intact.
- [x] 3.5.2 Cross-reference the rebased change-detection design rather than treating the archived unchecked task list as implemented history.

### PAUSE GATE 3A — bounded/safe ingestion commit

- [x] 3.GA.1 Run fault-injection and bounded-memory tests.
- [x] 3.GA.2 Run repeated-ingest/change-detection tests on both stores where supported.
- [x] 3.GA.3 Commit bounded/failure-safe ingestion.
- [x] 3.GA.4 ADR gate: update the Stage 3A ADR with the tested failure/recovery guarantees and Stage 3A commit SHA before proceeding to any concurrency optimisation.

### 3.6 Optional Stage 3B — concurrency optimisation after measurement

- [x] 3.6.1 Run Example Experiment 6 against Stage 3A. (Experiment 18 `experiments/18-ingestion-lock-scope-ab-2026-08-19/`, baseline commit `25f130f`: Phase A H1–H5 all PASS — bounded units, RSS ≤2× per 4× files, parse/embed/store-write failure safety, swap, unchanged skip. Timing: single-stream lock wait ≈0 (sequential by construction); two-stream contended with real Ollama embeddings fully serialised — lock wait 95.6% of wall, speedup 1.002.)
- [x] 3.6.2 If lock scope demonstrably limits embedding throughput, design a narrow mutation lock with embedding outside the lock using precomputed embeddings. (Measurement met the D12 condition for *concurrent* ingest. Chose minimal D1a — hoist `_embed_missing_nodes` + `stamp_source_attempt` above the lock; `write_nodes`/verify/cleanup stay inside. `upsert_precomputed` was surveyed and rejected as the write path: it cannot reproduce `write_nodes` row identity (see experiment `design-notes.md`); nodes arrive pre-embedded so `write_nodes` reuses populated vectors, satisfying "precomputed embeddings" without a store-contract change. Implemented in commit `b4b01b6` with failing-first regression tests `tests/test_ingestion_stage3b_narrow_lock.py`.)
- [x] 3.6.3 Preserve generation and replacement atomicity contracts. (Stamp keys are excluded from embed text and row IDs derive during stamping (`source_state.py`), so vectors/IDs are bit-identical; write → verify → stale-delete ordering unchanged inside the lock; each mutation still bumps generation exactly once. Test-contract map recorded 0 would-break-by-design contracts; full fast suite 1622 passed with only the 3 deferred Stage 4 audit reds.)
- [x] 3.6.4 Re-run Experiment 6 A/B and only retain the change if throughput improves without worse correctness/memory gates. (3 interleaved repetitions per arm, arms differ only in `replacement.py`: real-embed contended docs/s 5.49 → 7.40 (+34.7%, per-rep ranges non-overlapping), contender lock-wait fraction 96.7% → 0.0%, peak RSS ratio 0.99; fake-embed contended −0.6% (noise). H6 ≥20% PASS; H7 ≤1.25× RSS + Phase A H1–H5 re-green on treatment PASS. **Retained.**)

### PAUSE GATE 3B — optional performance commit

- [x] 3.GB.1 Commit concurrency work separately or explicitly mark 3B "not warranted by evidence". (Three commits: `25f130f` experiment 18 baseline evidence; `b4b01b6` Stage 3B narrow-lock implementation + failing-first regression tests; final commit adds the A/B artefacts, TDR-013, and gate bookkeeping. No correctness work is mixed into the concurrency commit.)
- [x] 3.GB.2 If Stage 3B is implemented, write a TDR recording the measured bottleneck, candidate lock/concurrency designs considered, chosen lock scope/batching strategy, Experiment 6 evidence, and rollback conditions. (`docs/tdr/013-narrow-ingestion-write-lock-to-mutation-section.md`, Accepted — records the 95.6% contended lock-wait bottleneck, designs D1a/D1b/D2/D3/D4 with rejection reasons, the D1a choice, the A/B evidence table, rollback (revert `b4b01b6`, no re-ingest), and scope limits: single-stream unchanged, Chroma local only.)

---

## 4. Stage 4 — Experiment preflight and harness validity

### 4.1 Shared runtime manifest

- [x] 4.1.1 Add a JSON-safe runtime manifest helper under `experiments/_lib/` with the fields listed in `design.md` D13. (`experiments/_lib/manifest.py::build_runtime_manifest`, commit `53ba31b`; all 33 D13 leaves populate, unavailable inputs become explicit nulls with dotted-path `null_reasons`.)
- [x] 4.1.2 Ensure secrets are never included; reuse production redaction where appropriate. (`scrub_secrets` applies `core/vectordb/identity.redact_secret` recursively as defence in depth; builder never receives secrets; test proves a planted key string cannot survive `json.dumps`.)
- [x] 4.1.3 Add backend-specific observation hooks for ONNX execution provider/variant and Torch device. (`observe_onnx_providers` reads the live session's `get_providers()`; `CrossEncoderReranker.last_loaded_variant` records the downloaded ONNX variant (production attribute, +7 lines); `SentenceTransformerReranker.last_loaded_device` + `observe_torch_device` cover the Torch device.)
- [x] 4.1.4 Add effective chunker/document-reader/fallback observation hooks. (`observe_chunking` reads `CodeChunkResult` requested/effective/fallback_reason; `observe_document_reader` resolves `auto` through the production factory's preference order.)
- [x] 4.1.5 Include repo SHA, lock hash, corpus/query/qrel hashes and immutable index identity. (`git_commit`/`lock_hash` (sha256 of uv.lock)/`sha256_file` produce `sha256:<hex>` identities; `index_identity` parameter carries the immutable collection name and overrides any mapping key.)

### 4.2 Machine-readable plans and preflight

- [x] 4.2.1 Represent factor levels/cell matrices in machine-readable form next to each protocol. (`plan.json` companions in experiments 10b/13/14 loadable via `ExperimentPlan.from_json`; `plan.cell_dicts()` added; repairs per D15.)
- [x] 4.2.2 Add a shared preflight that compares requested/effective manipulated variables and aborts on mismatch/fallback. (`experiments/_lib/preflight.py::evaluate_assertions`/`assert_manifest` with operators eq/ne/in/not_in/not_null/is_null/contains; `assert_no_fallback` aborts on reranker/document-backend/embedding mismatch or chunker fallback.)
- [x] 4.2.3 Assert controlled variables are constant across cells. (`assert_controlled_constant` — one non-None value per dotted field across all cell manifests; a None cell is unobserved, not controlled.)
- [x] 4.2.4 Assert distinct intended `fetch_k` values remain distinct after resolution. (`assert_distinct_values`; the 10b runner keys the map by declared pool level so collapsed pools abort — exactly the original 10b confound.)
- [x] 4.2.5 Assert parser experiments actually invoke distinct parser backends before embedding starts. (`assert_parser_invoked_before_embeddings` over chronological parse event logs; exp 14 `preflight_check` runs it before the embed stage.)
- [x] 4.2.6 Assert threshold-policy experiments use `rerank=None`, not a force override. (`assert_policy_rerank_mode` requires `retrieval.rerank_requested is None`; exp 13 policy cells call `search(..., rerank=None)` at a real literal call site — frozen audit test green.)

### 4.3 Repair/supersede active harnesses

- [x] 4.3.1 Mark the current Experiment 10b runner as pre-hardening invalid/superseded; do not delete historical code without preserving provenance. (`run_eval_v1_pre_hardening.py` retained with an INVALID provenance header; `protocol.md` status block marks the v1 design superseded; commit `181a726`.)
- [x] 4.3.2 Implement the combined 9a-rerun + 10b factorial runner described in D17. (`run_eval.py` rewritten: 12-cell matrix = 2 shared reranker-off controls + 10 on-cells (dense/hybrid_bm25 × fetch_k {50,100,150,200,500}); four literal `search()` dispatch arms; running at scale remains Stage 6.)
- [x] 4.3.3 Use one fixed query set for every applicable cell and counterbalance cell order. (One ground-truth query list per cell; `counterbalanced_order(cells, iteration)` is a seeded pure shuffle; warm-up rows tagged separately.)
- [x] 4.3.4 Add reranker-off shared controls and fetch pools `{50, 100, 150, 200, 500}` for reranker-on arms. (Off cells `dense_off`/`hybrid_off` carry no fetch_k and are never duplicated per pool; agreement test pins exactly 12 cells.)
- [x] 4.3.5 Repair Experiment 13 per D18: policy mode, fixed blocked samples, reranker-off/on references. (Commit `b92f152`: policy cells `search(rerank=None)` with per-threshold EffectiveSettings; `build_fixed_blocks` draws one fixed block per fraction reused across thresholds; reranker-off/forced-on reference arms per fraction; 42-cell plan.json.)
- [x] 4.3.6 Rebuild Experiment 14 per D19 using real immutable PDF bytes; parser output identities must differ by parser when parsing differs. (Commit `205ec0e`: `sorted(corpus_dir.glob("*.pdf"))` through production `get_pdf_reader`; per-parser parsed-text artefact with `artefact_identity` sha256; parse event log + preflight before embeddings; parse vs embed/write timing split; two immutable fixture PDFs under `fixtures/` with recorded sha256.)
- [x] 4.3.7 Add protocol/runner agreement tests for every repaired experiment. (`tests/test_experiment_10b_harness.py` (7), `tests/test_experiment_13_harness.py` (6), `tests/test_experiment_14_harness.py` (8) — all load plan.json and call `assert_runner_cells`; tiny fixtures/mocks only.)

### 4.4 Statistical output contract

- [x] 4.4.1 Store per-query raw metrics and per-repetition latency, not aggregates only. (`stats.validate_per_query_rows` requires cell_id/query_id/phase/latency_ms/metrics on every row; repaired runners persist raw rows per cell.)
- [x] 4.4.2 Add paired bootstrap CI calculation for primary quality deltas. (`stats.paired_bootstrap_ci` — joint pair resampling, seeded `random.Random`, percentile CI; summarisers compute the D17/D18 contrasts with it.)
- [x] 4.4.3 Record warm-up separately from measured repetitions. (`stats.split_warmup` by phase; warm-up rows excluded from every aggregate.)
- [x] 4.4.4 Record incomplete/interrupted cells as invalid/incomplete, never as numeric failures. (`stats.cell_record`/`finalise_cells` — statuses complete/incomplete/invalid, reason mandatory for the latter two.)

### 4.5 Required technical decision record

- [x] 4.5.1 Write a TDR for the **experiment-validity framework** covering the runtime manifest, requested-vs-effective assertions, protocol/runner cell agreement, controlled-variable pinning, fallback abort policy, paired raw-output requirements, checkpoint semantics, and incomplete-run handling. (`docs/tdr/014-experiment-validity-framework.md`, Accepted — eight decision rules with mechanism citations.)
- [x] 4.5.2 The TDR SHALL define which manifest fields are mandatory for an experiment to be considered admissible evidence for an ADR. (TDR-014 §"Mandatory manifest fields for admissible ADR evidence": 18 always-mandatory non-null fields plus conditional reranker/sparse/document-backend requirements, permitted-null list, and the inadmissibility rule for aggregate-only or interrupted evidence.)

### PAUSE GATE 4 — harness-only commit

- [x] 4.G.1 Run all harness unit/preflight tests with tiny fixtures/mocks. (2026-08-19: manifest 14 + preflight/stats/plan-contract 43 + harness 21 = 78 passed; audit regressions 10 passed; full fast suite `1698 passed, 17 skipped, 14 deselected` — zero failures, no model/network/corpus used by any new test.)
- [x] 4.G.2 Do not run FreshStack/Qasper-scale cells yet. (No campaign cell executed; the D17/D18/D19 runners were built with contract tests only — exp 14 verification used two ~640-byte fixture PDFs; exp 18 remains the only measured Stage 3B system experiment.)
- [x] 4.G.3 Commit experiment infrastructure/harness repair independently. (Four commits: `53ba31b` _lib manifest+preflight+stats + observation attributes; `181a726` 10b supersession + D17 factorial; `b92f152` exp 13 repair; `205ec0e` exp 14 rebuild; TDR committed separately after.)
- [x] 4.G.4 TDR gate: link the Stage 4 commit and preflight tests from the experiment-validity TDR before any Stage 5/6 results are accepted as decision evidence. (TDR-014 Evidence section links all four commits, the 78-test preflight/agreement bundle, and the audit-green fast-suite state; its admissibility contract binds Stage 5/6 evidence.)

---

## 5. Stage 5 — Cheap component experiments

- [x] 5.1 Run `experiments/example/experiment-1-sentencesplitter-vs-codesplitter/` and record raw + summary artefacts. (PASS: 18/18 effective code cells; `experiment-1-*/{results.md,output/summary.json,output/cells/}`.)
- [x] 5.2 Run `experiment-2-dense-cross-store-score-parity`. (v1.0 FAIL found 110/300 H3 mismatches; adapter fix `7bf16b3`; unchanged v1.1 harness and ground truth PASS at 0/300; `experiment-2-*/{results.md,results.summary.json,output/v1.1_run1/}`.)
- [x] 5.3 Run `experiment-3-hybrid-filter-and-threshold-semantics`. (PASS: zero filter leaks and compatible threshold score kinds; `experiment-3-*/{results.md,results.raw.json,output/cells/}`.)
- [x] 5.4 Run `experiment-4-bm25-cache-isolation`. (PASS: zero contamination and exactly-once generation across both stores; `experiment-4-*/{results.md,output/run1/results.raw.json}`.)
- [x] 5.5 Run `experiment-5-reranker-backend-device-parity`; on Apple Silicon, distinguish ONNX CPU/CoreML and Torch CPU/MPS as separate effective execution cells. (Correctness PASS: H1/H5; H2 speed PASS; H3 performance FAIL at 2.370× RSS and 13.826× cold start; no route promotion; `experiment-5-*/{results.md,output/eval_results.summary.json,output/raw_rows.jsonl}`.)
- [x] 5.6 Run `experiment-6-ingestion-boundedness-and-atomicity` against Stage 3A; decide whether Stage 3B is warranted. (PASS: H1-H5; Phase B real Ollama arm 0.911× Experiment 18 Stage 3B within the frozen 0.9 gate, lock wait 0.0, RSS 1.039×; `experiment-6-*/{results.md,output/results.raw.json,output/results.summary.json}`.)
- [x] 5.7 Run `experiment-7-metadata-cap-and-granularity`. (PASS: exact chunk-unit cap, first-N identity, file-level propagation, and call-count formula; `experiment-7-*/{results.md,output/summary.json,output/cells/}`.)
- [x] 5.8 Update `experiments/example/README.md` with status and links to any promoted real experiment directories. (Final status table, raw links, Exp 2 repair lineage, and explicit Stage 6 not-started marker added.)

### PAUSE GATE 5 — component evidence commit

- [x] 5.G.1 Every correctness experiment MUST PASS; any FAIL blocks Stage 6. (All correctness gates passed, including Exp 5 H1 device parity and H5 manifest truth. Exp 5 H3 is a resource-performance FAIL and does not invalidate its correctness evidence.)
- [x] 5.G.2 Performance-only experiments may be INCONCLUSIVE without blocking, provided correctness gates pass and the inconclusive reason is documented. (Exp 5 H2 passed at 0.677× median latency. H3 produced a conclusive non-promotion result: 2.370× RSS and 13.826× cold start. This performance result does not block Stage 6 correctness work.)
- [x] 5.G.3 Commit raw machine-readable results and human summary; exclude large generated indexes. (Raw rows, per-cell manifests, checkpoints, deterministic rerun proofs, and `results.md` committed in experiment commits `9b18652` through `1a12249`; no generated vector index committed.)
- [x] 5.G.4 Decision-record check: update the Stage 2/3 ADRs and Stage 4 TDR with Stage 5 evidence where it validates or limits their claims. Write an additional TDR only when a component experiment selects a durable implementation technique not already captured; otherwise record `no new ADR/TDR — evidence only`. (TDR-014 and ADR-047 gained Stage 5 evidence sections and ADR-048 gained a Stage 5 Experiment 6 confirming-evidence section in this changeset; TDR-015, Accepted, records the squared-L2 adapter repair at commit `7bf16b3` and the Stage 6 recalibration obligation. Experiments 1, 3, 4, 6, and 7 require no new ADR/TDR — evidence only.)

**Security review (2026-08-19):** the Stage 5 diff is APPROVED. The repository release remains BLOCKED by pre-existing ChromaDB advisory GHSA-f4j7-r4q5-qw2c (CVE-2026-45829), which affects the locked 1.5.9 release and has no patched version. Current embedded `PersistentClient` and trusted `CloudClient` adapter paths do not expose the vulnerable Python FastAPI server or execute remote collection configuration. Track the dependency in a separate security change and do not merge to `main` until the release gate clears.

**Security re-adjudication (2026-08-22):** the release gate for base installs is now CLEARED by the merged `make-lancedb-default-and-isolate-chromadb` change (PR #61, merge `e0fa536`; ADR-049): chromadb left the base dependency closure, the fresh-install SBOM shows 133 base dependencies with zero known vulnerabilities and no Chroma distribution, no server entrypoint exists, and the import-linter contract `chromadb-confined-to-vectordb` plus the fail-closed legacy guard confine the advisory to the opt-in `chroma` extra. That change and its evidence trail constitute the "separate security change" the 2026-08-19 note required. The residual advisory on the opt-in extra is accepted-risk and re-audited on every chromadb release. Full record: [`security-readjudication-2026-08-22.md`](security-readjudication-2026-08-22.md).

---

## 6. Stage 6 — Repaired calibration campaign

### 6.1 Combined reranker/retrieval/pool experiment

- [x] 6.1.1 Promote `experiment-8-reranker-retrieval-pool-factorial` template to a dated real experiment directory.
- [x] 6.1.2 Freeze FreshStack corpus/query/qrel/index identities before running cells. (2026-08-22: qrels regenerated byte-identical to committed digests; corpus manifest frozen sha256 `f6e7bb09…`, 10,024 parent docs, `missing_qrel_ids` empty, one-distractor upstream drift recorded as harmless; LanceDB index built and query-verified — 10,024 chunks, collection `exp10b-freshstack-langchain-seed-20260530-ollama-qwen3-embedding-0-6b`, `qwen3-embedding:0.6b` 1024-dim, 6,251 s. Full record: `experiments/10b-reranker-pool-size-corrected-2026-06-29/IDENTITY-FREEZE-2026-08-22.md`. Index inputs re-based on LanceDB per user-ratified ADR-049 D11 decision; the chroma manipulated-factor declaration is withdrawn.)
- [x] 6.1.3 Run shared reranker-off controls for dense and hybrid. (2026-08-23: `dense_off` and `hybrid_off`, 223 measured queries each.)
- [x] 6.1.4 Run reranker-on pools 50/100/150/200/500 for both retrieval modes. (2026-08-23: all 10 cells complete, 223 measured queries each, zero invalid.)
- [x] 6.1.5 Checkpoint at least per cell and preferably per query batch. (2026-08-23: per-cell `--resume` checkpoints used; run completed in one process, ~3.5 h wall clock.)
- [x] 6.1.6 Report paired deltas + CIs for current policy (150), best observed pool, and reranker-off ceiling. (2026-08-23: `output/results.md` — H1a/H1b reranker harms at policy pool 150; H2 best pool (50) still below off-ceiling on hybrid and statistically inconclusive on dense; H3/H4 larger pools monotonically worse; H5 hybrid beats dense off-reranker. Ambient-load deviation: `output/DEVIATION-2026-08-23-ambient-load.md` — latency columns invalid, quality valid.)
- [x] 6.1.7 Decide whether ADR-019 remains valid; do not amend it inside this experiment commit. (2026-08-23: ADR-019 REMAINS VALID — D17 confirms the technical-workload disable with corrected methodology. Evidence update appended to ADR-019 post-result-commit, per gate ordering. User-ratified option 3: policy unchanged, documents-profile setting flagged as lacking post-correction supporting evidence, task 6.3 designated as its first real test.)

### PAUSE GATE 6A — reranker campaign result

- [x] 6.GA.1 Commit result artefacts and interpretation before deciding whether threshold calibration is worth running. (2026-08-23: results.md + deviation note committed, 873e6d3 harness fix precedes.)
- [x] 6.GA.2 **After** the result commit, amend ADR-019 or write a successor ADR if the evidence changes/strengthens the production reranker policy. If the existing policy remains unchanged, add an evidence update to ADR-019 (or a TDR if repository convention prefers keeping the ADR immutable) that links the new experiment and explains why no policy change was made. (2026-08-23: evidence update appended to ADR-019 §Evidence — policy unchanged; D17 result commit d49be1e precedes this decision commit, gate ordering honoured.)

### 6.2 Conditional threshold experiment

- [x] 6.2.1 If semantic reranker benefit is practically meaningful, promote `experiment-9-technical-threshold-policy` template. (2026-08-23: condition NOT met — D17 found no reranker benefit at any pool size on the technical corpus; item closed as not applicable.)
- [x] 6.2.2 If benefit is absent/uniformly harmful, record “not warranted” and skip the threshold-policy campaign. (2026-08-23: NOT WARRANTED — reranker harm is uniform across pools 50–500 and both retrieval modes, with paired CIs excluding zero on hybrid at every pool and on dense at pools ≥100. No operating point exists on this workload that threshold calibration could improve. Recorded in `10b/output/results.md` §Interpretation and in the ADR-019 evidence update.)
- [x] 6.2.3 If run, reuse fixed workload blocks across thresholds and include forced-off/forced-on reference arms. (2026-08-23: not run — campaign skipped per 6.2.2.)

### PAUSE GATE 6B — threshold result

- [x] 6.GB.1 Commit result or skip rationale separately. (2026-08-23: skip rationale committed with the 6.2.2 close-out and the ADR-019 evidence update, separate from the D17 result commit d49be1e.)
- [x] 6.GB.2 If the experiment changes `HARD_TECHNICAL_THRESHOLD`, semantic-rerank enablement, or another production routing policy, amend/write the relevant ADR only after the result commit. If no production policy changes, record the retained-policy rationale in the experiment results or a TDR rather than manufacturing a new ADR. (2026-08-23: no production policy changed. **÷30 disposition (TDR-015 obligation): RETAINED WITH RATIONALE.** The `similarity_threshold / 30` rule in `core/retrieval/policy.py` is unchanged. Rationale: D17 ran rerank-on cells under the ÷30 rule and found harm at every pool size on the technical corpus — there is no beneficial rerank operating point on this workload for which a recalibrated threshold could matter. D17 did not isolate threshold effects (it was not designed to), so the rule is neither revalidated nor recalibrated. Semantic-workload revalidation transfers to task 6.3 (Qasper PDF A/B), the designated first real test of the documents-profile reranker path; if 6.3 ever changes that policy, threshold revalidation reopens there. TDR-015 obligation discharged: recorded explicitly as retained-with-rationale, per its own taxonomy.)

### 6.3 Real PDF parser experiment

> **Design amendment (2026-08-23, user-ratified):** pdf-inspector (Firecrawl's Rust PDF classification and markdown-extraction library; PyPI `pdf-inspector`, Python module `pdf_inspector`) joins pypdf and LiteParse as a third reader arm. The A/B becomes an A/B/C: `{pypdf, liteparse, pdf_inspector} × {rerank off, on}` in `experiments/14-liteparse-qasper-promotion-2026-06-29/plan.json` (three build cells plus six evaluation cells). Per the 6.1.7 note, this experiment is also designated the first real test of the documents-profile reranker setting (ADR-019 evidence update). The reader adapter and corpus-download script land as separate code changes. Gate 6C ordering is unchanged: no ADR-020 amendment before the result commit.

- [x] 6.3.1 Promote `experiment-10-real-pdf-parser-ab` template. (2026-08-23: harness live at `experiments/14-liteparse-qasper-promotion-2026-06-29/` since Stage 4; today amended to protocol v2.1 — three readers (pypdf, liteparse, pdf-inspector) × rerank off/on, 6 cells; plan/runner agreement tests green.)
- [x] 6.3.2 Freeze PDF bytes and question/qrel set. (2026-08-23: 35 Qasper-dev arXiv PDFs (25 MB) downloaded deterministically — first 35 articles by sorted arXiv ID, zero skips; 112 queries, 107 with qrels; both protocol minimums met. Freeze record with per-file sha256 and corpus identity `sha256:466b21f0…`: `14/output/qasper_corpus_freeze.json`. Parquet provenance sha256 recorded; PDF bytes and qrels stay gitignored, digests are the frozen truth.)
- [x] 6.3.3 Parse each PDF with all three readers; record parser invocation, parse failures, page/text/token counts and parse time before embeddings. (2026-08-24: each reader recorded 35 parse-start/parse-end events and zero parse errors. The parser-only rerun records 359 source-PDF pages for every reader, emitted-document totals of 359/358/35, and LlamaIndex-default token totals of 339,825/331,664/324,503 for pypdf/LiteParse/pdf-inspector. It ran before embedding and did not write indexes; timing evidence remains the approved quiet rerun.)
- [x] 6.3.4 Build separate immutable indexes from parser outputs using identical embedding/chunking configuration. (2026-08-24: three distinct artefact identities and immutable Chroma collection identities built from the frozen 35-PDF corpus with `qwen3-embedding:0.6b`.)
- [x] 6.3.5 Evaluate paired quality and decompose parse vs embed/write vs query timing. (2026-08-24: all six 112-query cells complete. Rerun ingestion times: pypdf 379.4s, LiteParse 356.3s, pdf-inspector 346.7s; see `14/output/results.md` and the deviation record.)

### PAUSE GATE 6C — PDF result

- [ ] 6.GC.1 Commit results separately; any production default change belongs in a follow-up ADR/OpenSpec.
- [ ] 6.GC.2 If the evidence changes the default PDF reader or fallback policy, amend ADR-020 or write its successor **after** the result commit. If the current default is retained, link the experiment as confirming/limiting evidence without rewriting history.

---

## 7. Closeout

- [ ] 7.1 Run `uv run pytest -m "not slow" --cov=rag_mcp` at repository coverage floors.
- [ ] 7.2 Run optional-backend contract jobs required by touched code (LanceDB real store, Torch backend as applicable).
- [ ] 7.3 Run `ruff check`, `ruff format --check`, Pyright if configured, and `uv run lint-imports`.
- [x] 7.4 Run `openspec validate harden-pipeline-correctness-before-calibration --strict` and `openspec validate --all --strict`. (2026-08-22: change valid; all-strict 40 passed, 0 failed.)
- [x] 7.5 Update experiment index with supersession links for old 10b/13/14 planned harnesses. (2026-08-22: `experiments/EXP_README.md` rows for 10b/13/14 changed PLANNED → REBUILT — Stage 6 pending, each naming its superseding Stage 4 commit — `181a726`/`b92f152`/`205ec0e` — and linking the supersession section of the respective `protocol.md`; row 13 also binds the TDR-015 ÷30 revalidation obligation.)
- [ ] 7.6 Audit the decision-record trail: every PAUSE GATE MUST have either a linked ADR/TDR action or an explicit `ADR/TDR not required` rationale; verify records distinguish planned design, deterministic test evidence, and empirical experiment evidence.
- [ ] 7.7 Verify required records survived the evidence: Stage 2 semantic-swappability ADR, Stage 3A failure-safe-ingestion ADR, Stage 4 experiment-validity TDR, optional Stage 3B optimisation TDR, and any Stage 6 production-policy ADR amendments/successors.
- [x] 7.8 Re-evaluate the remaining open OpenSpecs (`add-per-collection-persist-dirs`, document backend registry, native sparse backend, login watcher) against the hardened pipeline before resuming them. (2026-08-22: recorded in [`open-openspec-reevaluation-2026-08-22.md`](open-openspec-reevaluation-2026-08-22.md) — persist-dirs needs re-scope (Chroma-centric problem largely dissolved by the LanceDB default, ADR-049), native-sparse needs re-target (Chroma runtime quarantined), document-backend registry and login-watcher unchanged and safe to resume.)
