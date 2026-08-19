# Stage 4 repair plan — audit reds → D17/D18/D19 harness repairs

Provenance: written 2026-08-19 during Stage 4 (task 4.3 pre-analysis). Branch
`harden-pipeline-correctness-before-calibration`. The three audit regressions in
`tests/test_precalibration_audit_regressions.py` are the executable spec; this
document maps each failing test to its root defect and the repair required by
`design.md` D17/D18/D19. The audit tests are frozen — repairs land in the
harnesses only.

## How the audit tests inspect the runners

`_search_call_literal_values(source, keyword)` parses each runner with `ast`,
walks every `Call` whose function name is `search` (bare or attribute), and
collects literal constant values for the given keyword. Consequences:

- A runner whose generic evaluation helper passes `hybrid=hybrid_flag` or
  `rerank=rerank_on` (variables) contributes nothing to the collected set —
  the literals must appear at real call sites.
- `test_experiment_10b_...` asserts the collected sets are exactly
  `{False, True}` for both `hybrid` and `rerank`: every literal `hybrid=` /
  `rerank=` value in the file must be `False` or `True`, and both must occur.
- `test_experiment_13_...` asserts `None in` the collected `rerank` values.
- `test_experiment_14_...` is a substring check on `build_indexes.py`:
  `glob("*.pdf")` (or single-quoted) AND (`get_pdf_reader` or
  `read_and_chunk_file_async`).

## Experiment 10b — runner/protocol mismatch (audit red 1)

**Test**: `test_experiment_10b_runner_contains_hybrid_and_dense_treatments`.

**Defect**: `experiments/10b-reranker-pool-size-corrected-2026-06-29/run_eval.py`
executes dense-only, reranker-on cells (`search(..., rerank=True, hybrid=False)`)
while `protocol.md` declares a dense × hybrid × rerank × fetch_k matrix. The
hybrid hypothesis was claimed but never executed. The fetch_k axis also lacks
the D17 pool 150, and the runner duplicates no shared reranker-off controls
(the protocol's `dense_off`/`hybrid_off` rows were never implemented).

**Repair per D17** (tasks 4.3.1–4.3.4, 4.3.7):

1. Preserve the historical runner as `run_eval_v1_pre-hardening.py` with a
   header marking it INVALID pre-hardening (dense-only confound); rewrite
   `run_eval.py` as the combined 9a-rerun + 10b factorial runner.
2. Cell matrix (12 cells, machine-readable in `plan.json`, D15):
   - shared reranker-off controls: `dense_off`, `hybrid_off`
     (`fetch_k` absent — off cells are not duplicated per pool);
   - reranker-on: `{dense,hybrid}_on_{50,100,150,200,500}` — pool 150 is the
     current post-ADR-021 production equivalent at `top_k=50`.
3. One fixed query set evaluated in every applicable cell (paired); warm-up
   queries recorded with `phase="warmup"`, separate from measured rows (D16).
4. Four literal `search()` call sites in one dispatch (audit-visible):
   `hybrid=False, rerank=False` / `hybrid=True, rerank=False` /
   `hybrid=False, rerank=True, fetch_k=...` / `hybrid=True, rerank=True,
   fetch_k=...` — `fetch_k` passed as a variable so the literal sets stay
   exactly `{False, True}`.
5. Counterbalanced cell order via a seeded pure function.
6. Preflight before measured work: per-cell runtime manifest from
   `_lib/manifest.py`; `assert_no_fallback`; `assert_distinct_values` on the
   five effective fetch_k pools; `assert_controlled_constant` across cells;
   `evaluate_assertions` from the plan's `preflight_assertions`.
7. Outputs: per-query rows (`cell_id`, `query_id`, `phase`, `latency_ms`,
   `metrics`) validated by `_lib/stats.py`; cells finalised with
   `complete`/`incomplete`/`invalid` status, never numeric failure.
8. `summarise_eval.py` updated to the new cell shape; primary contrasts
   (D17: H1a/H1b current-policy, H2 ceiling, H3 pool sensitivity, H4
   diminishing returns, H5 hybrid-off lift) with paired bootstrap CIs from
   `_lib/stats.paired_bootstrap_ci`.
9. Agreement test: `plan.json` (via `ExperimentPlan.from_json`) vs
   `build_cell_matrix()` via `assert_runner_cells`; 12 cells; exactly two
   reranker-off cells; five distinct pools.

## Experiment 13 — policy bypass (audit red 2)

**Test**: `test_experiment_13_threshold_cells_do_not_force_reranking`.

**Defect**: `experiments/13-hard-technical-threshold-calibration-2026-06-29/run_eval.py`
calls `search(..., rerank=True)` in every cell. Forcing rerank-on bypasses the
`HARD_TECHNICAL_THRESHOLD` policy resolver entirely, so the swept threshold
never affects routing — the experiment measures a forced arm, not the policy.
Secondary defects: a fresh random query sample per (threshold × fraction) cell
breaks pairing across thresholds, and there are no reference arms.

**Repair per D18** (tasks 4.3.5, 4.3.7):

1. Policy cells call `search(..., rerank=None)` with the per-cell
   `EffectiveSettings` carrying the swept `hard_technical_threshold` (the
   existing `model_copy` mechanism is sound; only the forced flag is wrong).
2. One fixed query block per technical fraction, drawn once from the declared
   seed and reused for every threshold (paired across the threshold axis;
   fraction remains a blocked analysis factor).
3. Reference arms per fraction: `search(..., rerank=False)` (off ceiling) and
   `search(..., rerank=True)` (forced-on envelope) — threshold-independent, so
   run once per fraction, never duplicated per threshold.
4. Cell matrix in `plan.json`: 5 thresholds × 6 fractions policy cells +
   6 fractions × 2 reference arms = 42 cells.
5. Preflight: `assert_policy_rerank_mode` (manifest records
   `retrieval.rerank_requested = None` for policy cells), `assert_no_fallback`,
   controlled-variable pinning, and plan/runner agreement.
6. Outputs per 4.4: per-query rows with `phase`, cell status records,
   paired bootstrap CIs in the summariser for the semantic-benefit and
   technical-guard contrasts.

## Experiment 14 — parser not in the build path (audit red 3)

**Test**: `test_experiment_14_build_path_reads_real_pdf_bytes`.

**Defect**: `experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py`
globs `*.md` and embeds pre-extracted Markdown; the `--reader` flag only
renames the output directory (and is stamped into metadata), so the PDF reader
factor cannot affect indexed text. The parser comparison was fictional.

**Repair per D19** (tasks 4.3.6, 4.3.7):

1. Glob real PDF bytes (`sorted(corpus_dir.glob("*.pdf"))`); corpus identity =
   sha256 over the sorted per-file hashes; files are immutable inputs.
2. Parse through the production factory `get_pdf_reader(reader)` — no
   harness-side parser imports.
3. Before any embedding: record a parse event log (parser, file, start/end
   timestamps, extracted character count, page count, errors) and write a
   per-parser parsed-text artefact whose identity is its sha256; distinct
   parsers must produce distinct artefact identities when text differs.
4. `assert_parser_invoked_before_embeddings` (from `_lib/preflight.py`) runs
   on the event log before the embed stage; parse time and embedding/write
   time are recorded separately (D19 decomposition).
5. Each parser gets its own index via `experiment_storage_config(parser=...)`
   (collection identity already includes the parser).
6. Tiny fixture PDFs committed under the experiment directory for the
   agreement tests (identity = sha256; never mutated); tests exercise the
   parse stage with `pypdf` only (deterministic per AGENTS.md gotcha 6) and
   never touch Ollama.
7. `plan.json` covers the protocol's four evaluation cells (reader × rerank)
   plus the two build cells; agreement tests compare against the runners'
   pure cell generators.

## Shared infrastructure already landed (Phase 1)

- `experiments/_lib/manifest.py` — D13 manifest builder, observation hooks
  (ONNX provider/variant, Torch device, chunker fallback, document reader),
  secret scrubbing. Tasks 4.1.1–4.1.5.
- `experiments/_lib/preflight.py` — D14 assertions: requested-vs-effective,
  fallback abort, distinctness, controlled-variable pinning, parser-before-
  embeddings, policy rerank mode. Tasks 4.2.2–4.2.6.
- `experiments/_lib/plan.py` — `cell_dicts()` helper (D15, task 4.2.1).
- `experiments/_lib/stats.py` — D16 outputs: per-query row validation,
  warm-up split, paired bootstrap CI, incomplete-cell records. Tasks 4.4.1–
  4.4.4.
- Production observation attributes: `CrossEncoderReranker.last_loaded_variant`,
  `SentenceTransformerReranker.last_loaded_device` (task 4.1.3).
