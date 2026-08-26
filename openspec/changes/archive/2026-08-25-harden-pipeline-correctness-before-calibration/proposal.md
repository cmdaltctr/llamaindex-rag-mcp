## Why

The v3 branch has reached the point where further retrieval calibration would produce evidence faster than it can currently produce *trustworthy* evidence. A code-first audit of the production pipeline and the active experiment harnesses found correctness, semantic-swappability, observability, ingestion-reliability, and experimental-validity gaps that can change conclusions independently of model quality or hardware speed.

The highest-risk findings are concrete rather than hypothetical:

- the code chunker calls LlamaIndex `CodeSplitter` with constructor arguments that are not part of the v0.14.5 API; the broad fallback then makes the path silently behave like `SentenceSplitter`, while existing tests only assert that nodes are returned;
- hybrid metadata filters reach dense retrieval but not BM25, so RRF can re-introduce chunks that violate the caller filter;
- the process-wide BM25 cache is keyed by collection name only, so two store instances containing the same collection name can reuse the wrong sparse index when their generation values coincide;
- dense retrieval owns a Chroma-shaped `distance -> 1/(1+d)` conversion even though `VectorStore.query_dense()` does not specify a distance metric or scale, so a backend can satisfy the Python ABC while changing score semantics;
- a post-fusion RRF score is compared with `similarity_threshold` as though it were a dense similarity score, although the two scales are not comparable;
- metadata extraction slices text by `max_chunks * chunk_size` characters even though the configured chunk size is token-based;
- normal directory ingestion deletes old chunks before replacement is proven writable, accumulates all replacement nodes in memory, and serialises the full embed+write call under one global write lock;
- Experiment 10b does not implement the cell matrix or hypotheses in its protocol;
- Experiment 13 forces `rerank=True`, which bypasses the very `HARD_TECHNICAL_THRESHOLD` policy it claims to calibrate;
- Experiment 14 never feeds PDFs through pypdf or LiteParse: its preparation step exports Qasper's already-extracted text to Markdown and its builder embeds those Markdown files directly.

Hardware is therefore not the first blocker. A larger machine would make invalid cells finish faster. This change creates a hard correctness-and-validity gate before expensive experiments resume.

## What Changes

### 1. Correct deterministic pipeline behaviour before measuring quality

- Repair AST-aware code chunking against the installed LlamaIndex contract. Code-specific units SHALL be explicit (`chunk_lines`, line overlap, character ceiling or their supported successor API) rather than passing token-oriented document settings into incompatible arguments.
- Make fallback observable. Tests SHALL prove that the AST path actually ran; a test that passes through a fallback is not evidence that CodeSplitter works.
- Make hybrid filtering symmetric across dense and sparse retrieval.
- Scope BM25 caches by both store identity and collection identity.
- Give dense retrieval a store-neutral score contract. Backend adapters SHALL own conversion from native distance/score semantics; core retrieval SHALL NOT assume Chroma L2 semantics.
- Stop applying dense-similarity thresholds directly to RRF scores. Threshold behaviour for dense, hybrid and reranked modes SHALL be explicit and testable.
- Make mutation-generation ownership single and symmetric across ChromaDB and LanceDB.
- Fix token/character unit mismatches in metadata extraction and documentation.

### 2. Make production ingestion safe and bounded before optimising it

- Remove the all-files `all_nodes` accumulation path: ingestion SHALL have a bounded file/batch lifetime so corpus size does not linearly grow the in-process node list before the first write.
- Restore/complete content-hash change detection so unchanged files are not re-embedded on repeated ingests.
- Change replacement ordering so an old searchable version is not deleted merely because a later parse/embed/write fails. The implementation SHALL use a version/hash-aware replace strategy or another store-neutral mechanism with the same safety property.
- Separate correctness from concurrency optimisation. First land bounded, failure-safe ingestion; then measure lock/embedding behaviour. Only widen concurrency if an experiment demonstrates benefit without breaking store safety.

### 3. Make backend selection observable, not inferred

Add a runtime/experiment manifest that records and can assert at least:

- embedding provider and model;
- vector-store backend, deployment mode, collection/index identity, and dense score semantics;
- sparse backend and cache namespace;
- reranker backend, model, actual execution device/provider, model variant/precision when knowable;
- chunking strategy actually executed, including whether fallback occurred;
- PDF/document backend actually executed;
- effective retrieval knobs such as `top_k`, `fetch_k`, `hybrid`, `rrf_k`, threshold semantics and rerank policy reason.

Experiment preflight SHALL abort when a manipulated variable is not actually active or when a silent fallback would invalidate the cell.

### 4. Repair the active calibration harnesses before running them

- Replace the current Experiment 10b implementation with a protocol-conformant paired/factorial design that includes dense/hybrid, reranker-off controls, and genuinely distinct reranker pool sizes. Where possible, fold the old 9a-rerun question into the same factorial run to avoid duplicate compute.
- Rebuild Experiment 13 so the policy resolver is exercised with `rerank=None`, every threshold sees the same blocked query samples, and a reranker-off reference exists for semantic-benefit/technical-regression deltas.
- Rebuild Experiment 14 around actual source PDFs (or another immutable real-PDF corpus) so pypdf and LiteParse are genuine manipulated variables.
- Add fail-fast protocol/code agreement tests so a runner cannot claim a hypothesis for cells it does not execute.

### 5. Add small, cheap verification experiments before large calibration

Add protocol templates under `experiments/example/` for focused experiments that establish component correctness and backend parity before FreshStack/Qasper-scale runs. Templates define hypotheses, manipulated variables, controlled variables, dependent variables, blocking, randomisation, repetitions, abort criteria, artefacts and interpretation rules.

## Staging / Commit Boundary

This change is deliberately staged. Each stage is independently committable and has a mandatory PAUSE GATE in `tasks.md`. The next stage MUST NOT begin until the prior stage's deterministic tests or bounded experiment passes and the operator has had an opportunity to inspect the commit.

1. **Stage 0 — freeze and executable baseline audit**
2. **Stage 1 — deterministic component correctness**
3. **Stage 2 — semantic swappability and retrieval contracts**
4. **Stage 3 — bounded/failure-safe ingestion**
5. **Stage 4 — experiment preflight and harness validity**
6. **Stage 5 — cheap component experiments**
7. **Stage 6 — repaired calibration campaign**

## Capabilities

### New Capabilities

- `experiment-validity-gates`: executable protocol/runner agreement, runtime manifests, fail-fast backend/device/fallback assertions, fixed experimental-design rules, and evidence provenance required before a calibration result may be marked PASS/FAIL/INCONCLUSIVE.
- `retrieval-score-semantics`: store-neutral dense score semantics and explicit rules for when dense, RRF and reranker scores may be thresholded or compared.

### Modified Capabilities

- `hybrid-retrieval`: symmetric metadata filtering, store-scoped BM25 caching, single-owner invalidation, and score/threshold semantics that do not compare RRF values to dense similarity thresholds.
- `vectordb-abstraction`: backend adapters expose canonical retrieval score semantics and mutation-generation behaviour consistently across ChromaDB and LanceDB.
- `async-ingestion`: bounded processing, unchanged-file skipping, and failure-safe replacement ordering.
- `reranking`: diagnostics expose the backend that ran and the actual device/execution provider/variant needed to validate performance experiments.

## Out of Scope

- changing production retrieval defaults before repaired experiments provide evidence;
- implementing the real native sparse backend;
- promoting LanceDB, hybrid retrieval, Torch/MPS, a new reranker model, a new embedding model or a PDF reader by default;
- `add-per-collection-persist-dirs`, login watcher installation, or post-v3 tripwire cleanup;
- agentic multi-query/self-correcting retrieval. The purpose of this change is to create a trustworthy static baseline before that work begins.

## Impact

**Code:** `core/chunking/`, `core/retrieval/`, `core/vectordb/`, `core/metadata/`, `core/ingestion/`, composition/runtime diagnostics, focused transport diagnostics where needed.

**Tests:** new regression tests SHALL reproduce every confirmed audit defect before its fix; cross-backend contract tests SHALL run the same fixtures against ChromaDB and LanceDB; experiment harnesses gain protocol/preflight tests independent of expensive models.

**Experiments:** no existing PASS result is retroactively invalidated. The active planned calibration runs are blocked until Stage 4. Existing 10b/13/14 runner output produced before the repaired harnesses SHALL NOT be used to change defaults.

**Performance:** this change does not promise a faster pipeline in early stages. It first makes execution bounded and observable, then uses measured evidence to choose performance changes. On Apple Silicon, MPS/GPU and CoreML/Neural-Engine routes are treated as distinct execution backends and MUST be recorded rather than inferred.

**Branching:** implementation targets `harden-pipeline-correctness-before-calibration`, created from `v3`. Each PAUSE GATE is intended to map to a reviewable commit before continuing.
