# Design: harden-pipeline-correctness-before-calibration

## Context

v3 deliberately moved the project toward strategy registries, injected settings, multiple vector stores, pluggable rerankers, local/cloud storage and explicit experiment harnesses. That architecture is useful only if two stronger properties hold:

1. **semantic equivalence at abstraction boundaries** — swapping an implementation changes the intended factor and not hidden score units, cache state, filter semantics or mutation bookkeeping; and
2. **experimental identifiability** — a reported result must be attributable to the manipulated variable rather than a silent fallback, different corpus sample, stale cache, device change, interrupted run or mismatched runner/protocol.

This design therefore treats tests and experiments as a hierarchy:

`deterministic contract test -> small controlled experiment -> expensive calibration`

A later layer may never be used to compensate for a failed earlier layer.

---

## Design principles

### P1. Correctness before calibration

Anything provable without a model-quality experiment SHALL be proved with deterministic tests first. Examples: CodeSplitter constructor compatibility, filter leakage, cache contamination, threshold-scale misuse, policy bypass and protocol/cell mismatch.

### P2. One source of runtime truth

Experiment metadata SHALL describe what actually ran, not only what environment variables requested. Requested and effective values MAY both be recorded, but effective backend/device/provider/fallback state is authoritative.

### P3. Paired comparisons by default

Quality experiments SHALL reuse the same immutable corpus, query set, qrels, index identity and query order across treatment cells unless the manipulated variable requires rebuilding the index. This makes comparisons paired and reduces variance.

### P4. Block before randomise

When multiple workload classes exist (for example technical vs semantic), build fixed blocks first and reuse the exact block membership across all treatment levels. Cell execution order MAY then be randomised/counterbalanced to reduce thermal/cache/time drift.

### P5. Separate quality from systems performance

Quality metrics and latency/memory metrics SHALL be reported separately. Hardware throttling, MPS/CPU fallback or storage/network stalls can invalidate performance inference without invalidating already-completed quality rows. Interrupted/incomplete cells are never interpreted as negative quality evidence.

### P6. Fallback is an experimental event

Fallbacks are allowed in production where specified, but an experiment manipulating that backend SHALL abort if fallback occurs. A fallback may be the subject of a dedicated reliability experiment, never an unrecorded implementation detail.

### P7. Freeze before expensive runs

Every expensive campaign SHALL record repository commit SHA, dependency lock hash, experiment protocol version, corpus identity, query/qrel identity and runtime manifest. Changing any factor that can alter index contents creates a new immutable index identity.

---

# Stage architecture

## Stage 0 — Freeze and executable baseline audit

**Goal:** convert the audit findings into failing tests before implementation changes.

Deliverables:

- pin the branch baseline SHA and produce `audit-baseline.md` containing each confirmed finding, reproduction, expected invariant and intended test owner;
- add regression tests that fail for:
  - CodeSplitter path actually falling back;
  - hybrid metadata-filter leakage through BM25/RRF;
  - BM25 cross-store collection-name collision;
  - RRF score being compared against dense `similarity_threshold`;
  - inconsistent mutation-generation ownership;
  - metadata max-chunks character/token mismatch;
  - Experiment 10b protocol/cell mismatch;
  - Experiment 13 explicit-rerank policy bypass;
  - Experiment 14 parser not participating in corpus construction;
- add a lightweight experiment-protocol schema/helper used by later stages.

**PAUSE GATE 0:** commit only tests/docs. Confirm the expected failures represent real defects and not changed requirements. No production fix lands in this commit.

---

## Stage 1 — Deterministic component correctness

### D1. CodeSplitter uses code-specific units

The current document settings `chunk_size` / `chunk_overlap` are token-oriented because `SentenceSplitter` consumes tokenizer units. LlamaIndex v0.14.5 `CodeSplitter` instead accepts `chunk_lines`, `chunk_lines_overlap` and `max_chars`. Passing one vocabulary as the other is invalid.

Add code-specific settings to the chunking block:

- `code_chunk_lines` — default pinned to the upstream value currently relied on intentionally;
- `code_chunk_lines_overlap` — explicit line overlap;
- `code_max_chars` — explicit character ceiling.

`chunk_code_file_async()` SHALL construct CodeSplitter using those units. The generic document token settings remain the SentenceSplitter fallback settings only.

The result object SHALL carry or diagnostics SHALL expose `chunk_strategy_requested`, `chunk_strategy_effective`, and `fallback_reason` when fallback occurs. Tests SHALL assert AST-aware boundaries using a fixture where SentenceSplitter and CodeSplitter necessarily produce distinguishable output; merely asserting `len(nodes) > 0` is insufficient.

### D2. Metadata caps are token-aware

`LLAMANDEX_EXTRACTOR_MAX_CHUNKS` expresses a chunk budget, not a character budget. Replace direct Python character slicing derived from token chunk size with one of:

1. token-aware truncation using the same tokenizer contract as SentenceSplitter; or
2. split first, then cap to `max_chunks` nodes before expensive extractors.

Preference: **split first, then cap nodes**, because it uses the actual chunker as the unit of work and avoids a second tokenizer approximation.

The stored metadata contract remains file-level unless a separate change deliberately adopts per-chunk metadata. Documentation SHALL stop describing the current aggregation path as persisted per-chunk LLM enrichment.

**PAUSE GATE 1:** all deterministic chunking/metadata regressions green; run only cheap fixtures. Do not run FreshStack/Qasper.

---

## Stage 2 — Semantic swappability and retrieval contracts

### D3. Vector-store adapters own native score conversion

`core/retrieval/dense.py` SHALL no longer know that Chroma returns a distance named `_distance`/`distance` or assume `1/(1+d)` is valid for every backend.

`VectorStore.query_dense()` SHALL return store-neutral rows containing at least:

- `id`
- `document`
- `metadata`
- `score` — higher is better;
- `score_kind` — canonical identifier for the semantics used, e.g. `dense_similarity_v1`.

Each backend adapter owns conversion from its native metric into the canonical score. Cross-backend contract tests SHALL ingest the same precomputed embeddings and assert:

- identical expected nearest-neighbour order on deterministic fixtures;
- score monotonicity with vector closeness;
- score range and threshold semantics required by `dense_similarity_v1`;
- clear failure if a backend cannot satisfy the canonical contract.

The contract SHALL not claim that a transformed score is mathematically equal to cosine similarity unless it actually is.

### D4. Thresholds apply only to compatible score kinds

RRF scores are rank-fusion utilities, not dense similarities. The pipeline SHALL never compare an RRF score directly to `similarity_threshold`.

Rules:

- **dense, no rerank:** apply `similarity_threshold` to canonical dense score;
- **rerank succeeded:** apply the calibrated reranker threshold transform to reranker score;
- **hybrid, no rerank:** dense thresholding occurs on the dense evidence before fusion. If a positive similarity threshold is requested, sparse-only rows without qualifying dense evidence SHALL NOT be presented as satisfying that minimum semantic similarity. RRF itself is not thresholded by the dense threshold;
- **hybrid + rerank:** fusion chooses the candidate pool, reranker produces the final thresholdable score if reranking succeeds;
- **reranker failure:** fall back to the appropriate pre-rerank rule and surface the failure.

If a future API needs an RRF cutoff, it SHALL use a separately named setting/parameter.

### D5. Metadata filters are branch-invariant

A caller filter is a query constraint, not a dense-only hint. BM25/native sparse input SHALL be restricted to the same eligible document set before RRF. No result failing the caller filter may be reintroduced by fusion.

Implementation may use a filtered store iterator/read or post-filter sparse rows against store-neutral metadata, but correctness takes precedence over sparse efficiency in this stage.

### D6. BM25 cache identity includes store identity

The cache key SHALL include a process-local store identity token plus collection name. Two stores with the same collection name MUST NOT share cached rows/index state. Re-wrapping the same underlying store MAY create duplicate caches; duplicate work is acceptable, contamination is not.

### D7. Stores own generation mutation exactly once

The `VectorStore` contract already states that every mutation advances generation. Make that statement true in every backend and remove duplicate orchestration bumps. Direct and pipeline callers then have identical invalidation semantics.

Required mutation cases:

- write nodes;
- precomputed upsert;
- filtered delete;
- collection delete;
- any later mutation method added to the ABC.

### D8. Deployment-swappable vs runtime-swappable is explicit

Embedding provider selection currently resolves to a process-global LlamaIndex embed model. This change SHALL document that as **deployment-scoped swappability**. It SHALL NOT pretend concurrent per-collection embedding providers are supported.

No per-collection embedding-provider redesign is included here. A test SHALL instead make the boundary explicit so future agentic work cannot accidentally rely on unsupported concurrent provider switching.

**PAUSE GATE 2:** ChromaDB and LanceDB run the same deterministic vector-store/retrieval contract suite. Hybrid filter/cache/threshold tests are green. Review the score contract before any quality experiment.

---

## Stage 3 — Bounded and failure-safe ingestion

### D9. Eliminate corpus-sized `all_nodes`

`ingest_path_async()` SHALL process and persist bounded units. Minimum acceptable boundary: one source file at a time. Large single-file batching MAY be added if needed, but the pipeline MUST NOT retain every node for an entire directory before the first write.

This stage optimises peak memory predictability, not throughput.

### D10. Complete content-hash change detection

Revive the intent of archived `add-ingestion-change-detection` against current v3 and both vector-store backends. Every written chunk SHALL carry a stable source content hash/version identifier. Unchanged files SHALL skip parse/chunk/embed/write on repeated ingestion.

The identity used for skip decisions SHALL also incorporate any index-shaping inputs that would make existing vectors/chunks invalid if changed, or the system SHALL store an explicit index-config identity alongside the content hash. A content-only hash MUST NOT incorrectly skip after embedding-model/chunking/parser changes.

### D11. Replace old data only after new data is durable

The old searchable version of a file SHALL survive parse, chunk or embed failure. Preferred design:

1. calculate new source/index version identity;
2. parse/chunk;
3. write new version rows;
4. verify expected rows are durable;
5. delete stale rows for the same source whose version identity differs.

During the small overlap window, duplicate versions MAY exist internally, but public retrieval SHOULD de-duplicate by source/version or the swap SHALL occur under a narrow store mutation lock. The exact mechanism must work through the VectorStore abstraction.

### D12. Measure before widening concurrency

Do not redesign `write_nodes()` around speculative concurrency in the correctness commit. After bounded ingestion lands, Experiment 6 measures:

- peak RSS;
- wall time;
- embedding time;
- store-write time;
- lock wait time;
- failure recovery.

Only if embedding concurrency is demonstrably constrained by the current lock scope SHALL a follow-up commit separate embedding from the write-critical section (likely using precomputed embeddings and a narrow mutation lock).

**PAUSE GATE 3:** fault-injection tests prove old data survives parse/embed/write failures; memory stays bounded on a generated corpus; repeated unchanged ingest skips work. Commit before any concurrency optimisation.

---

## Stage 4 — Experiment validity infrastructure

### D13. Runtime manifest

Create a shared experiment helper that returns a JSON-serialisable manifest. Minimum fields:

```text
repo_commit
dependency_lock_hash
experiment_id
protocol_version
corpus_identity
query_set_identity
qrels_identity
embedding.requested_provider
embedding.effective_provider
embedding.model
vector_store.backend
vector_store.mode
vector_store.index_identity
vector_store.score_kind
sparse.requested_backend
sparse.effective_backend
sparse.cache_namespace
reranker.requested_backend
reranker.effective_backend
reranker.model
reranker.device
reranker.execution_provider
reranker.variant_or_precision
chunker.requested
chunker.effective
chunker.fallback_reason
document_backend.requested
document_backend.effective
retrieval.top_k
retrieval.fetch_k
retrieval.hybrid
retrieval.rrf_k
retrieval.threshold
retrieval.threshold_score_kind
retrieval.rerank_policy_reason
```

Unavailable fields are explicit `null` with a reason where useful, never silently omitted.

### D14. Preflight assertions

Each experiment declares which manifest fields are manipulated and which are controlled. Before measured work begins:

- manipulated values MUST equal their declared cell value;
- controlled values MUST equal the protocol constant;
- no fallback is allowed for a manipulated backend;
- index/corpus identity MUST match the expected cell;
- the runner MUST enumerate exactly the protocol cell matrix;
- expected distinct values (e.g. `fetch_k`) MUST actually be distinct;
- required hardware/device conditions MUST be satisfied for performance claims.

### D15. Protocol/runner agreement is tested without expensive models

Protocol expectations SHALL be represented in importable/static data (or a machine-readable companion file) so unit tests can compare expected cells against runner-generated cells. Markdown prose alone is not executable evidence.

### D16. Statistical design defaults

For quality comparisons:

- use fixed paired queries across cells;
- report per-query raw metrics, not aggregate only;
- report paired bootstrap confidence intervals for primary deltas where sample size permits;
- define practical effect-size gates before execution;
- do not promote a default based only on a point estimate whose CI spans zero unless the protocol explicitly defines an equivalence/non-inferiority analysis.

For latency:

- separate warm-up from measured repetitions;
- randomise or counterbalance cell order when the same machine runs multiple cells;
- record thermal/power/device state when feasible;
- report median and P95 plus raw repetitions;
- never interpret an interrupted/hung cell as a numerical latency observation.

**PAUSE GATE 4:** repaired runners pass contract/preflight tests with mocks and tiny fixtures. No large corpus is run yet.

---

## Stage 5 — Cheap component experiments

Run the templates under `experiments/example/` in order. These are deliberately small and answer whether the components are behaving as intended before quality calibration consumes substantial compute.

1. `experiment-1-sentencesplitter-vs-codesplitter`
2. `experiment-2-dense-cross-store-score-parity`
3. `experiment-3-hybrid-filter-and-threshold-semantics`
4. `experiment-4-bm25-cache-isolation`
5. `experiment-5-reranker-backend-device-parity`
6. `experiment-6-ingestion-boundedness-and-atomicity`
7. `experiment-7-metadata-cap-and-granularity`

Experiments 1-4 and 7 should run on tiny deterministic fixtures and are expected to be cheap. Experiment 5 may use the M1/MPS route but is a bounded inference benchmark, not a corpus-scale RAG run. Experiment 6 uses generated text and fault injection rather than a large semantic dataset.

**PAUSE GATE 5:** all required correctness gates PASS. Performance results may be PASS/FAIL/INCONCLUSIVE, but any correctness failure blocks Stage 6.

---

## Stage 6 — Repaired calibration campaign

### D17. Merge 9a-rerun and 10b where possible

Use one paired factorial experiment rather than two mostly overlapping runs.

Factors:

- retrieval mode: `dense`, `hybrid_bm25`;
- reranker: `off`, `on`;
- for reranker-on only, candidate pool `fetch_k`: `{50, 100, 150, 200, 500}` (150 represents current post-ADR-021 policy at `top_k=50`).

The reranker-off cells are shared controls, not duplicated for each meaningless `fetch_k`. Every query is evaluated in every applicable cell. Cell order is counterbalanced. Primary hypotheses are declared in the example protocol template.

This single run answers both: “is reranking still harmful at the current 150 pool?” and “does pool size causally change that conclusion?”

### D18. Threshold calibration is conditional

Only run the HARD_TECHNICAL_THRESHOLD experiment if the factorial reranker experiment shows a meaningful semantic benefit worth preserving.

The threshold experiment SHALL:

- call `search(..., rerank=None)` so policy is actually exercised;
- reuse the same fixed query block for every threshold;
- include explicit reranker-off and force-reranker-on reference arms to estimate the achievable benefit/harm envelope;
- treat workload composition as a blocked analysis factor, not a source of a new random sample for every threshold.

If reranking is uniformly harmful or negligible, do not spend compute calibrating a routing threshold whose purpose has disappeared.

### D19. Real PDF reader experiment

The pypdf/LiteParse experiment SHALL use immutable real PDF bytes. Each parser produces a separately identified parsed-text artefact and index. Before embeddings are computed, preflight SHALL prove that the parser was actually invoked and record parse time, extracted character/token counts, page mapping and parser errors.

Quality comparison is paired by document/question. Ingestion speed MUST be decomposed into parse time and embedding/write time so “faster parser” is not hidden by a dominant embedding stage.

*(Amended 2026-08-23, user-ratified: pdf-inspector joins as a third reader arm — plan level `pdf_inspector`; see the "Three-parser extension (v2.1)" section of the Experiment 14 protocol. Every D19 mechanism above is reader-agnostic and unchanged.)*

**PAUSE GATE 6:** each calibration result is reviewed and committed independently before any default/ADR change. A PASS result does not automatically change production defaults; the decision lands in a separate reviewed change/ADR.

---

# Experimental design standard for `experiments/example/`

Every protocol template SHALL include these headings:

1. Research question
2. Pre-registered hypotheses
3. Experimental unit
4. Manipulated/independent variables
5. Controlled variables
6. Blocking/stratification variables
7. Dependent variables and primary metric
8. Cell matrix
9. Corpus/query/qrel identity
10. Randomisation/counterbalancing
11. Repetitions and warm-up
12. Preflight assertions
13. Abort/invalid-cell criteria
14. Success/equivalence/non-inferiority gates
15. Analysis plan
16. Threats to validity
17. Reproduction commands (placeholder until runner exists)
18. Required raw artefacts
19. Interpretation rules
20. Cleanup

No template may use “works”, “better” or “faster” without a numeric operational definition.

---

# Alternatives considered

## Run current experiments on a larger cloud machine first

Rejected. It reduces wall-clock time but leaves protocol/runner mismatches and policy bypasses untouched.

## Fix only the three broken experiment scripts

Rejected. The hybrid filter leak, BM25 cache identity and score semantics can alter the production path the repaired experiments call.

## Rewrite the entire RAG pipeline around a new framework

Rejected. The current architecture has useful seams. Most findings are local contract/validity defects and can be repaired incrementally.

## Promote Torch/MPS immediately because Experiment 17 was faster

Rejected. MPS performance is promising, but backend precision changed rankings relative to ONNX int8. Backend choice remains an explicit experiment factor until quality equivalence is established for the target workload.

---

# Risks and mitigations

- **Scope growth:** hardening can turn into architecture rewrite. Mitigation: stages and pause gates; no new default changes in this OpenSpec.
- **Cross-store canonical score design is underspecified:** first add failing parity tests; if Chroma/Lance native semantics cannot map cleanly, pause at Stage 2 and amend the design rather than inventing a silent transform.
- **Failure-safe replacement is store-dependent:** require a store-neutral behavioural contract, not identical internal transactions.
- **More diagnostics can leak secrets:** runtime manifests MUST exclude API keys/tokens and use existing redaction helpers.
- **Experiment templates become stale prose:** cell definitions and preflight expectations must have machine-readable counterparts tested against runners.

# Validation

At every stage:

- `openspec validate harden-pipeline-correctness-before-calibration --strict`
- targeted tests for that stage
- `ruff check` and `ruff format --check` for touched code
- import-linter when package boundaries change

Full `pytest -m "not slow" --cov=rag_mcp` is required before Stage 5 and again before Stage 6. Expensive/optional-backend jobs are run only where the stage requires them.
