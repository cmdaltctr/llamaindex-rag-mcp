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

- [ ] 3.1.1 Remove the directory-sized `all_nodes` accumulation.
- [ ] 3.1.2 Process at most one source file (or another explicitly bounded batch) through parse/chunk/write before releasing its nodes.
- [ ] 3.1.3 Add generated-corpus tests that record maximum simultaneously retained node count independently of total file count.

### 3.2 Change detection / index identity

- [ ] 3.2.1 Rebase the archived `add-ingestion-change-detection` intent onto current Chroma + Lance abstractions.
- [ ] 3.2.2 Store `source_content_hash` plus an index-shaping identity covering embedding model/provider, parser and chunking settings that invalidate existing chunks/vectors.
- [ ] 3.2.3 Skip unchanged files only when both content identity and index-shaping identity match.
- [ ] 3.2.4 Test repeated ingest, content edit, embedding-model change, parser change and chunk-setting change.

### 3.3 Failure-safe replacement

- [ ] 3.3.1 Write the new source version before deleting stale versions.
- [ ] 3.3.2 Verify new rows are durable before stale deletion.
- [ ] 3.3.3 Delete only stale versions of the same source using store-neutral filtering/version metadata.
- [ ] 3.3.4 Add injected parse failure: old version remains searchable.
- [ ] 3.3.5 Add injected embedding failure: old version remains searchable.
- [ ] 3.3.6 Add injected store-write failure: old version remains searchable.
- [ ] 3.3.7 Add interrupted-run recovery test for a collection containing both old and new versions.

### 3.4 Instrument before optimising concurrency

- [ ] 3.4.1 Add timing counters for parse/chunk, embed, write, lock wait and total per bounded unit.
- [ ] 3.4.2 Add peak-RSS sampling helper for the ingestion benchmark where supported.
- [ ] 3.4.3 Do NOT widen concurrency in the same commit unless deterministic safety requires it.

### 3.5 Required architecture decision record

- [ ] 3.5.1 Write or amend an ADR for **bounded, failure-safe source replacement** covering: bounded memory lifetime, content + index-shaping identity, write-new-before-delete-stale ordering, durability verification, stale-version cleanup/recovery, and the guarantee that a failed re-ingest leaves the last good searchable version intact.
- [ ] 3.5.2 Cross-reference the rebased change-detection design rather than treating the archived unchecked task list as implemented history.

### PAUSE GATE 3A — bounded/safe ingestion commit

- [ ] 3.GA.1 Run fault-injection and bounded-memory tests.
- [ ] 3.GA.2 Run repeated-ingest/change-detection tests on both stores where supported.
- [ ] 3.GA.3 Commit bounded/failure-safe ingestion.
- [ ] 3.GA.4 ADR gate: update the Stage 3A ADR with the tested failure/recovery guarantees and Stage 3A commit SHA before proceeding to any concurrency optimisation.

### 3.6 Optional Stage 3B — concurrency optimisation after measurement

- [ ] 3.6.1 Run Example Experiment 6 against Stage 3A.
- [ ] 3.6.2 If lock scope demonstrably limits embedding throughput, design a narrow mutation lock with embedding outside the lock using precomputed embeddings.
- [ ] 3.6.3 Preserve generation and replacement atomicity contracts.
- [ ] 3.6.4 Re-run Experiment 6 A/B and only retain the change if throughput improves without worse correctness/memory gates.

### PAUSE GATE 3B — optional performance commit

- [ ] 3.GB.1 Commit concurrency work separately or explicitly mark 3B “not warranted by evidence”.
- [ ] 3.GB.2 If Stage 3B is implemented, write a TDR recording the measured bottleneck, candidate lock/concurrency designs considered, chosen lock scope/batching strategy, Experiment 6 evidence, and rollback conditions. If Stage 3B is not warranted, record `TDR not required — optimisation rejected by measurement` in the gate notes.

---

## 4. Stage 4 — Experiment preflight and harness validity

### 4.1 Shared runtime manifest

- [ ] 4.1.1 Add a JSON-safe runtime manifest helper under `experiments/_lib/` with the fields listed in `design.md` D13.
- [ ] 4.1.2 Ensure secrets are never included; reuse production redaction where appropriate.
- [ ] 4.1.3 Add backend-specific observation hooks for ONNX execution provider/variant and Torch device.
- [ ] 4.1.4 Add effective chunker/document-reader/fallback observation hooks.
- [ ] 4.1.5 Include repo SHA, lock hash, corpus/query/qrel hashes and immutable index identity.

### 4.2 Machine-readable plans and preflight

- [ ] 4.2.1 Represent factor levels/cell matrices in machine-readable form next to each protocol.
- [ ] 4.2.2 Add a shared preflight that compares requested/effective manipulated variables and aborts on mismatch/fallback.
- [ ] 4.2.3 Assert controlled variables are constant across cells.
- [ ] 4.2.4 Assert distinct intended `fetch_k` values remain distinct after resolution.
- [ ] 4.2.5 Assert parser experiments actually invoke distinct parser backends before embedding starts.
- [ ] 4.2.6 Assert threshold-policy experiments use `rerank=None`, not a force override.

### 4.3 Repair/supersede active harnesses

- [ ] 4.3.1 Mark the current Experiment 10b runner as pre-hardening invalid/superseded; do not delete historical code without preserving provenance.
- [ ] 4.3.2 Implement the combined 9a-rerun + 10b factorial runner described in D17.
- [ ] 4.3.3 Use one fixed query set for every applicable cell and counterbalance cell order.
- [ ] 4.3.4 Add reranker-off shared controls and fetch pools `{50, 100, 150, 200, 500}` for reranker-on arms.
- [ ] 4.3.5 Repair Experiment 13 per D18: policy mode, fixed blocked samples, reranker-off/on references.
- [ ] 4.3.6 Rebuild Experiment 14 per D19 using real immutable PDF bytes; parser output identities must differ by parser when parsing differs.
- [ ] 4.3.7 Add protocol/runner agreement tests for every repaired experiment.

### 4.4 Statistical output contract

- [ ] 4.4.1 Store per-query raw metrics and per-repetition latency, not aggregates only.
- [ ] 4.4.2 Add paired bootstrap CI calculation for primary quality deltas.
- [ ] 4.4.3 Record warm-up separately from measured repetitions.
- [ ] 4.4.4 Record incomplete/interrupted cells as invalid/incomplete, never as numeric failures.

### 4.5 Required technical decision record

- [ ] 4.5.1 Write a TDR for the **experiment-validity framework** covering the runtime manifest, requested-vs-effective assertions, protocol/runner cell agreement, controlled-variable pinning, fallback abort policy, paired raw-output requirements, checkpoint semantics, and incomplete-run handling.
- [ ] 4.5.2 The TDR SHALL define which manifest fields are mandatory for an experiment to be considered admissible evidence for an ADR.

### PAUSE GATE 4 — harness-only commit

- [ ] 4.G.1 Run all harness unit/preflight tests with tiny fixtures/mocks.
- [ ] 4.G.2 Do not run FreshStack/Qasper-scale cells yet.
- [ ] 4.G.3 Commit experiment infrastructure/harness repair independently.
- [ ] 4.G.4 TDR gate: link the Stage 4 commit and preflight tests from the experiment-validity TDR before any Stage 5/6 results are accepted as decision evidence.

---

## 5. Stage 5 — Cheap component experiments

- [ ] 5.1 Run `experiments/example/experiment-1-sentencesplitter-vs-codesplitter/` and record raw + summary artefacts.
- [ ] 5.2 Run `experiment-2-dense-cross-store-score-parity`.
- [ ] 5.3 Run `experiment-3-hybrid-filter-and-threshold-semantics`.
- [ ] 5.4 Run `experiment-4-bm25-cache-isolation`.
- [ ] 5.5 Run `experiment-5-reranker-backend-device-parity`; on Apple Silicon, distinguish ONNX CPU/CoreML and Torch CPU/MPS as separate effective execution cells.
- [ ] 5.6 Run `experiment-6-ingestion-boundedness-and-atomicity` against Stage 3A; decide whether Stage 3B is warranted.
- [ ] 5.7 Run `experiment-7-metadata-cap-and-granularity`.
- [ ] 5.8 Update `experiments/example/README.md` with status and links to any promoted real experiment directories.

### PAUSE GATE 5 — component evidence commit

- [ ] 5.G.1 Every correctness experiment MUST PASS; any FAIL blocks Stage 6.
- [ ] 5.G.2 Performance-only experiments may be INCONCLUSIVE without blocking, provided correctness gates pass and the inconclusive reason is documented.
- [ ] 5.G.3 Commit raw machine-readable results and human summary; exclude large generated indexes.
- [ ] 5.G.4 Decision-record check: update the Stage 2/3 ADRs and Stage 4 TDR with Stage 5 evidence where it validates or limits their claims. Write an additional TDR only when a component experiment selects a durable implementation technique not already captured; otherwise record `no new ADR/TDR — evidence only`.

---

## 6. Stage 6 — Repaired calibration campaign

### 6.1 Combined reranker/retrieval/pool experiment

- [ ] 6.1.1 Promote `experiment-8-reranker-retrieval-pool-factorial` template to a dated real experiment directory.
- [ ] 6.1.2 Freeze FreshStack corpus/query/qrel/index identities before running cells.
- [ ] 6.1.3 Run shared reranker-off controls for dense and hybrid.
- [ ] 6.1.4 Run reranker-on pools 50/100/150/200/500 for both retrieval modes.
- [ ] 6.1.5 Checkpoint at least per cell and preferably per query batch.
- [ ] 6.1.6 Report paired deltas + CIs for current policy (150), best observed pool, and reranker-off ceiling.
- [ ] 6.1.7 Decide whether ADR-019 remains valid; do not amend it inside this experiment commit.

### PAUSE GATE 6A — reranker campaign result

- [ ] 6.GA.1 Commit result artefacts and interpretation before deciding whether threshold calibration is worth running.
- [ ] 6.GA.2 **After** the result commit, amend ADR-019 or write a successor ADR if the evidence changes/strengthens the production reranker policy. If the existing policy remains unchanged, add an evidence update to ADR-019 (or a TDR if repository convention prefers keeping the ADR immutable) that links the new experiment and explains why no policy change was made.

### 6.2 Conditional threshold experiment

- [ ] 6.2.1 If semantic reranker benefit is practically meaningful, promote `experiment-9-technical-threshold-policy` template.
- [ ] 6.2.2 If benefit is absent/uniformly harmful, record “not warranted” and skip the threshold-policy campaign.
- [ ] 6.2.3 If run, reuse fixed workload blocks across thresholds and include forced-off/forced-on reference arms.

### PAUSE GATE 6B — threshold result

- [ ] 6.GB.1 Commit result or skip rationale separately.
- [ ] 6.GB.2 If the experiment changes `HARD_TECHNICAL_THRESHOLD`, semantic-rerank enablement, or another production routing policy, amend/write the relevant ADR only after the result commit. If no production policy changes, record the retained-policy rationale in the experiment results or a TDR rather than manufacturing a new ADR.

### 6.3 Real PDF parser experiment

- [ ] 6.3.1 Promote `experiment-10-real-pdf-parser-ab` template.
- [ ] 6.3.2 Freeze PDF bytes and question/qrel set.
- [ ] 6.3.3 Parse each PDF with both readers; record parser invocation, parse failures, page/text/token counts and parse time before embeddings.
- [ ] 6.3.4 Build separate immutable indexes from parser outputs using identical embedding/chunking configuration.
- [ ] 6.3.5 Evaluate paired quality and decompose parse vs embed/write vs query timing.

### PAUSE GATE 6C — PDF result

- [ ] 6.GC.1 Commit results separately; any production default change belongs in a follow-up ADR/OpenSpec.
- [ ] 6.GC.2 If the evidence changes the default PDF reader or fallback policy, amend ADR-020 or write its successor **after** the result commit. If the current default is retained, link the experiment as confirming/limiting evidence without rewriting history.

---

## 7. Closeout

- [ ] 7.1 Run `uv run pytest -m "not slow" --cov=rag_mcp` at repository coverage floors.
- [ ] 7.2 Run optional-backend contract jobs required by touched code (LanceDB real store, Torch backend as applicable).
- [ ] 7.3 Run `ruff check`, `ruff format --check`, Pyright if configured, and `uv run lint-imports`.
- [ ] 7.4 Run `openspec validate harden-pipeline-correctness-before-calibration --strict` and `openspec validate --all --strict`.
- [ ] 7.5 Update experiment index with supersession links for old 10b/13/14 planned harnesses.
- [ ] 7.6 Audit the decision-record trail: every PAUSE GATE MUST have either a linked ADR/TDR action or an explicit `ADR/TDR not required` rationale; verify records distinguish planned design, deterministic test evidence, and empirical experiment evidence.
- [ ] 7.7 Verify required records survived the evidence: Stage 2 semantic-swappability ADR, Stage 3A failure-safe-ingestion ADR, Stage 4 experiment-validity TDR, optional Stage 3B optimisation TDR, and any Stage 6 production-policy ADR amendments/successors.
- [ ] 7.8 Re-evaluate the remaining open OpenSpecs (`add-per-collection-persist-dirs`, document backend registry, native sparse backend, login watcher) against the hardened pipeline before resuming them.
