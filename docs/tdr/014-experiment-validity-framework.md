# TDR-014: Experiment-Validity Framework: Runtime Manifests, Preflight Aborts, and Cell Agreement

**Date:** 2026-08-19
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Tags:** experiments | stage4 | preflight | manifest | validity

## Context

The pre-calibration audit (TDR-011) froze ten failing regressions in
`tests/test_precalibration_audit_regressions.py`. Three were harness-validity
defects, not pipeline defects:

- Experiment 10b executed a dense-only, reranker-on subset of the dense ×
  hybrid × rerank × fetch_k matrix its protocol declared.
- Experiment 13 passed `rerank=True` in every cell, so the swept
  `HARD_TECHNICAL_THRESHOLD` never routed anything. The experiment measured a
  forced arm while claiming to measure policy.
- Experiment 14 globbed `*.md`. The parser A/B factor could not touch indexed
  text, so the comparison was fictional.

Each harness produced plausible numbers from a cell that never ran as
declared. design.md D13–D16 therefore requires a shared runtime manifest,
preflight assertions, agreement tests that load no models, and a statistical
output contract. Stage 4 implemented the framework in `experiments/_lib/`
(commit `53ba31b`) and repaired the three harnesses (commits `181a726`,
`b92f152`, `205ec0e`).

## Decision

Eight rules define a valid experiment run.

1. **Runtime manifest (D13).** Each cell records a JSON-safe manifest via
   `experiments/_lib/manifest.py::build_runtime_manifest`. Unavailable fields
   become explicit `null` plus a `null_reasons` entry naming the dotted path;
   nothing is silently omitted, and `json.dumps` runs before return so
   non-serialisable values fail loudly. Provenance covers `repo_commit`,
   `dependency_lock_hash`, sha256 identities for corpus, query set, and
   qrels, and the immutable `vector_store.index_identity` (an explicit
   parameter overrides the mapping key so it cannot be shadowed).
   Observation hooks read production attributes instead of re-deriving them:
   ONNX execution providers and `variant_or_precision` from
   `CrossEncoderReranker.last_loaded_variant` (`core/retrieval/reranker.py`),
   Torch device from `SentenceTransformerReranker.last_loaded_device`
   (`core/retrieval/reranker_torch.py`), chunker fallback, and document
   reader auto-resolution. `scrub_secrets` applies the production
   `redact_secret` helper as defence in depth; secrets never enter manifests
   by construction.
2. **Requested-vs-effective assertions (D14).**
   `preflight.evaluate_assertions` and `assert_manifest` evaluate the plan's
   `preflight_assertions` against dotted manifest paths with operators `eq`,
   `ne`, `in`, `not_in`, `not_null`, `is_null`, `contains`.
   `manifest_field` resolves a missing key to `None`, so an unrecorded field
   cannot pass a positive assertion.
3. **Protocol/runner cell agreement (D15).** Each repaired experiment carries
   a `plan.json` loadable via `ExperimentPlan.from_json`. Every harness runs
   `plan.assert_runner_cells(<runner cell matrix>)` before measured work; a
   differing matrix aborts the run, not just the cell.
4. **Controlled-variable pinning (D14).** `assert_controlled_constant`
   requires each controlled field to hold one non-`None` constant across all
   cell manifests. A field that differs between cells was manipulated. A
   field never observed is absent, not controlled.
5. **Fallback abort policy (D14).** `assert_no_fallback` treats a fallback as
   an experimental event: the declared cell did not run. It aborts on
   requested-vs-effective mismatch for the reranker, the document backend, or
   the embedding provider, and on any recorded `chunker.fallback_reason`.
   `PreflightError` propagates, so measurements from a failed configuration
   are never written.
6. **Paired raw output (D16).** `stats.validate_per_query_rows` requires
   per-query rows carrying `cell_id`, `query_id`, `phase`, `latency_ms`, and
   `metrics`; `phase` must be `warmup` or `measured`. `split_warmup` keeps
   warm-up rows out of aggregates. `paired_bootstrap_ci` resamples pairs
   jointly with a private seeded `random.Random` (Experiment 10b summariser
   seed 20260819; Experiment 13 seed 20260629). Summarisers aggregate
   complete cells only.
7. **Checkpoint semantics.** Each runner writes a checkpoint after every
   cell: serialise to a `.tmp` file, then `tmp.replace(path)`. `--resume`
   reloads completed cell ids and skips them, so an interrupted run loses at
   most one cell of work and never reads a half-written checkpoint.
8. **Incomplete-run handling (D16).** `stats.cell_record` accepts only
   `complete`, `incomplete`, or `invalid`; the latter two require a non-empty
   `reason`. `finalise_cells` upgrades a record without a status to
   `incomplete` with reason `missing status`. An interrupted cell is a status
   string, never a numeric observation.

## Mandatory manifest fields for admissible ADR evidence

An experiment's result is admissible as evidence for an ADR only when ALL of
the following hold.

1. **Identity and runtime fields are non-null and non-empty:**
   `repo_commit`, `dependency_lock_hash`, `experiment_id`,
   `protocol_version`, `corpus_identity`, `query_set_identity`,
   `qrels_identity`, `embedding.requested_provider`,
   `embedding.effective_provider`, `embedding.model`,
   `vector_store.backend`, `vector_store.mode`,
   `vector_store.index_identity`, `vector_store.score_kind`,
   `retrieval.top_k`, `retrieval.hybrid`, `retrieval.threshold`,
   `retrieval.threshold_score_kind`.
2. **When reranking is a manipulated factor or active in any cited cell:**
   `reranker.requested_backend`, `reranker.effective_backend`, and
   `reranker.model` must be non-null, `requested_backend` must equal
   `effective_backend`, and `assert_no_fallback` must be green for the cell.
3. **When hybrid retrieval is active in any cited cell:**
   `sparse.effective_backend` must be non-null.
4. **When the corpus is PDF:** `document_backend.requested` and
   `document_backend.effective` must be non-null and equal, and the parse
   event log must prove via `assert_parser_invoked_before_embeddings` that
   the parser ran before embeddings started.
5. **Agreement and raw evidence:** plan agreement green (`ExperimentPlan`
   versus runner cells) for the cited experiment; the plan's preflight
   assertions green; per-query raw rows present for every cited cell; every
   cited cell status `complete`.
6. **Permitted-null fields** carry `null_reasons` where implemented:
   `reranker.device` (the ONNX backend has no Torch device),
   `reranker.variant_or_precision` (a process-wide cache hit loses variant
   provenance; `last_loaded_variant` stays `None`), `sparse.*` for dense-only
   experiments, `document_backend.*` for non-PDF corpora, and
   `chunker.fallback_reason` (null means no fallback occurred; the null
   itself is the signal).
7. **Inadmissible outcomes.** Aggregates without per-query rows, cells
   recorded numeric after interruption, or manifests missing mandatory
   fields make the result INADMISSIBLE as ADR evidence. Such a result may
   still be informative as engineering telemetry; a decision record must not
   rest on it.

## Relation to the repaired harnesses

| Repair | Mechanism | Agreement tests |
| --- | --- | --- |
| D17, Experiment 10b (commit `181a726`) | `run_eval.py` combined factorial: `build_cell_matrix()` returns 12 cells (2 shared reranker-off controls plus 10 on-cells over 5 fetch_k pools × 2 modes); `plan.json` declares the same 12; four literal `search()` call sites; counterbalanced cell order | `tests/test_experiment_10b_harness.py` (7 tests) |
| D18, Experiment 13 (commit `b92f152`) | `build_fixed_blocks` draws one fixed mixed block per technical fraction, reused across thresholds; `threshold_effective_settings` is a pure overlay; policy cells call `search(..., rerank=None)`; reranker-off/on reference arms per fraction; `plan.json` declares 42 cells | `tests/test_experiment_13_harness.py` (6 tests) |
| D19, Experiment 14 (commit `205ec0e`) | `build_indexes.py` reads `sorted(corpus_dir.glob("*.pdf"))` through `get_pdf_reader`; `corpus_identity` and `artefact_identity` are sha256 over sorted files; chronological parse event log; `assert_parser_invoked_before_embeddings` runs before the embed stage; `build_eval_cell_matrix()` yields 4 eval cells alongside 2 build cells | `tests/test_experiment_14_harness.py` (8 tests) |

The frozen audit regressions are green again:
`tests/test_precalibration_audit_regressions.py`, 10 passed.

## Evidence

- Stage 4 commits on `harden-pipeline-correctness-before-calibration`:
  `53ba31b` shared runtime manifest, preflight, and stats helpers
  (4.1/4.2/4.4, plus the two production observation attributes);
  `181a726` 10b superseded, combined D17 factorial runner (4.3.1–4.3.4,
  4.3.7); `b92f152` Experiment 13 policy-mode repair (4.3.5, 4.3.7);
  `205ec0e` Experiment 14 real-PDF build path (4.3.6, 4.3.7).
- Framework and harness tests: `78 passed in 1.63s` across
  `tests/test_experiment_manifest.py` (14), `test_experiment_preflight.py`
  (21), `test_experiment_stats.py` (16), `test_experiment_plan_contract.py`
  (6), and the three harness files (7 + 6 + 8).
- Audit regressions: `10 passed in 1.41s`.
- Fast suite after Stage 4: `1698 passed, 17 skipped, 14 deselected, 114
  warnings in 103.19s`. At Stage 3B head `a8133b1` it stood at 1622 passed,
  17 skipped, 3 failed (TDR-013); those three failures were the frozen audit
  reds, now green.
- At acceptance, this evidence covered deterministic tests only. The Stage 5
  field evidence below was added after the component experiments completed.
  Stage 6 calibration has not started.

## Stage 5 field evidence

Stage 5 supplied the framework's first field validation. Experiment 2 v1.0
ran the declared ChromaDB and LanceDB cells with identical fixtures and found
110 threshold-membership mismatches in 300 H3 checks. Both stores agreed with
each other, so the failure identified a shared production contract defect
rather than backend noise. The adapters were transforming native squared L2
as though it were true L2.

The failing v1.0 execution ran at commit `c475852` with uncommitted harness
artefacts; the harness was committed at `98449c3`. Commit `7bf16b3` applied
the square root inside both adapters. The unchanged harness (byte-identical
to `98449c3`) then reused the same corpus, queries, and qrels. Experiment 2
v1.1, committed as `4c29377`, passed all gates with 0/300 H3 mismatches. Its
two canonical projections are byte-identical. Raw rows, per-cell manifests, summaries, and
the deterministic proof are under
`experiments/example/experiment-2-dense-cross-store-score-parity/output/`.
This FAIL-to-fix-to-PASS lineage proves that the manifest, preflight, fixed
ground truth, and raw-output rules can expose a real defect and verify its
repair without changing the assertion.

All seven Stage 5 experiments carried a machine-readable plan, runtime
observations, preflight checks, raw evidence, and atomic checkpoint or
per-cell records. The inference-only Experiment 5 records embedding,
vector-store, sparse, and document-backend fields as permitted nulls with
reasons because those components do not enter the measured path. Its route
claims rest on the conditionally mandatory reranker fields and the observed
ONNX provider or Torch device. No missing field was treated as positive
evidence.

Experiments 1, 3, 4, 6, and 7 need no new ADR or TDR; they add empirical
evidence to existing decisions. Experiments 3 and 4 evidence ADR-047's
filter, threshold, and cache-isolation decisions; Experiment 6 confirms
ADR-048's bounded and failure-safe ingestion decisions on the Stage 3B code
(see the ADR-048 Stage 5 section); Experiments 1 and 7 add chunking-unit and
metadata-granularity evidence to the existing ingestion and metadata
records. Experiment 2 selected a durable adapter repair, recorded separately
in TDR-015.

## Consequences

### Positive

- A harness that drifts from its protocol fails a fast test before compute
  is spent. Each audit defect class (unexecuted matrix, policy bypass,
  fictional factor) now has a dedicated deterministic guard.
- ADR evidence has an auditable floor: mandatory manifest fields, green
  preflight, and per-query raw rows are checkable from artefacts alone.

### Negative

- Harness code volume grew: the 10b and 13 runners (650 and 690 lines)
  exceed the ~500-line convention. `tests/test_file_size_ceiling.py` governs
  `src/rag_mcp/` only, so the experiments tree carries that debt openly.
- Every cell pays one manifest build and one assertion pass before measured
  work.

### Neutral

- Preflight runs per cell: a mid-run dependency or policy change aborts the
  remaining cells instead of being silently absorbed.

### Obligations for Stage 5 and Stage 6

- Run preflight (manifest plus plan assertions) in every campaign cell
  before measured work.
- Archive manifests together with raw per-query rows; never regenerate them.
- The Stage 6 promotion of the experiment-8 template (task 6.1.1) inherits
  this admissibility contract. Task 4.G.4 blocks accepting Stage 5/6 results
  as decision evidence without this TDR linking the Stage 4 commits and
  preflight tests.

## Rollback

Revert `53ba31b`, `181a726`, `b92f152`, `205ec0e`. This restores the
pre-Stage-4 harnesses and turns `tests/test_precalibration_audit_regressions.py`
red again. That red is the tripwire: it proves the framework, not paperwork,
keeps the harnesses honest. Reversion touches `experiments/`, `tests/`, and
the two observation attributes in `core/retrieval/reranker.py` and
`reranker_torch.py`; no retrieval behaviour changes, because the attributes
are write-only provenance.

## References

- `openspec/changes/harden-pipeline-correctness-before-calibration/design.md`
  §D13 (runtime manifest), §D14 (preflight assertions), §D15 (agreement
  without expensive models), §D16 (statistical design defaults).
- `openspec/changes/harden-pipeline-correctness-before-calibration/tasks.md`
  §4 (tasks 4.1–4.5, Pause Gate 4) and the decision-record policy.
- `openspec/changes/harden-pipeline-correctness-before-calibration/repair-plan.md`
  (audit red to repair mapping).
- Implementation: `experiments/_lib/{manifest,preflight,stats,plan}.py`;
  repaired harnesses under `experiments/10b-reranker-pool-size-corrected-2026-06-29/`,
  `experiments/13-hard-technical-threshold-calibration-2026-06-29/`, and
  `experiments/14-liteparse-qasper-promotion-2026-06-29/` (each with
  `plan.json`).
- Observation hooks: `src/rag_mcp/core/retrieval/reranker.py`
  (`last_loaded_variant`), `src/rag_mcp/core/retrieval/reranker_torch.py`
  (`last_loaded_device`).
- TDR-011 (pre-calibration audit and plan validation); TDR-013 (Stage 3B
  head suite state, 1622/17/3); TDR-015 (correct native squared L2 at the
  vector-store boundaries, the Stage 5 defect this framework exposed).
