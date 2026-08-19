# Experiment 2 results — dense cross-store score parity

**Status: FAIL** (correctness blocker; see the production finding)
**Executed:** 2026-08-19, worktree `harden-pipeline-correctness-before-calibration`
**Commit:** `c475852cf195658ce6af8654e11e07dce4c39fec` (dirty: experiment artefacts uncommitted)
**Runtime:** Python 3.12.10, chromadb 1.5.9, lancedb 0.37.1, pyarrow 25.0.1, llama-index 0.14.23
**Protocol:** `protocol.md` v1.0, pre-registered sections unchanged; execution record appended there.

## Hypothesis verdicts

| Hypothesis | Verdict | Numbers |
|---|---|---|
| H1 ranking parity | **PASS** | 50 measured repetitions (5 fixtures × 5 reps × 2 backends); 0 ordering violations; ties permuted only inside pre-labelled tie sets (`f3`: {t1a,t1b}, {t2a,t2b}; `f5`: {b,c,d}) |
| H2 canonical score monotonicity | **PASS** | 190 monotonicity comparisons; 0 violations; tied docs score-equal per engine; every score equals `1/(1+native)` exactly |
| H3 threshold parity | **FAIL** | 300 membership checks; 110 mismatch the pre-registered analytic expectation, identically in both backends; cross-store identity itself held (0 differences between Chroma and Lance memberships) |
| H4 metadata-filter parity | **PASS** | 50 checks (5 filters × 5 reps × 2 backends); query-id sets and `count_where` counts all match; includes `$in` and nested `$and`+`$gte` operator filters |
| H5 backend opacity | **PASS** | AST scan: 0 backend literals in executable strings of `dense.py`, 0 `native_distance` accesses, 1 abstract `store.query_dense` call site; adapters cite `canonical_score_from_l2` (chroma.py, lancedb.py); core-path rows identical to adapter rows in every repetition |

Overall: any H1–H5 failure blocks semantic-swappability claims (protocol §14), so the experiment is FAIL.

## Production finding (recorded, NOT hotfixed)

**`exp2-f1-squared-l2-canonical-score`** — severity: production-defect-documentation.

- **Observed:** both engines' `"l2"` metric reports **squared** Euclidean
  distance. Fixture evidence (identical in both backends' raw rows):
  doc `[0,1,0,0]` vs query `[1,0,0,0]` → native `2.0` (= (√2)²);
  `[0.5,0,0,0]` → `0.25`; `[-2,0,0,0]` → `9.0`. The adapters pass this
  value straight into `canonical_score_from_l2`, so the production
  canonical dense score is `1/(1+d²)`.
- **Expected:** `src/rag_mcp/core/vectordb/score.py:27-51` documents the
  transform as `1/(1+distance)` over a "native non-negative L2
  distance"; the committed `fixtures/qrels.json` encodes that geometric
  interpretation, and H3 fails against it.
- **Locations:** `src/rag_mcp/core/vectordb/score.py:27-51` (contract
  text), `src/rag_mcp/core/vectordb/chroma.py:264` (pass-through of the
  Chroma `l2` value), `src/rag_mcp/core/vectordb/lancedb.py:370`
  (pass-through of Lance `_distance`).
- **Impact:** monotonicity and cross-store swappability HOLD (`d²` is
  monotone in `d` and both engines square identically — which is why
  H1/H4 and H3's cross-store clause pass). The ABSOLUTE score and
  threshold meaning deviates from the documented formula: any
  `similarity_threshold` calibrated or documented against `1/(1+d)`
  semantics is mis-scaled.
- **Required follow-up (protocol §19):** fix the adapter/contract before
  any cross-store RAG quality experiment; Stage 5 gate blocks Stage 6 on
  this FAIL. Either the adapters take `sqrt` before conversion, or the
  contract text and threshold documentation are amended to `1/(1+d²)` —
  a decision for the orchestrator, not patched inside this experiment.

## Manifest identities (per cell)

| Cell | backend | index_identity | corpus / queries / qrels |
|---|---|---|---|
| `chroma_dense` | chroma | `exp2-fixtures::chroma::39919461e937` | `sha256:39919461…` / `sha256:fad16f2b…` / `sha256:c972fefe…` |
| `lancedb_dense` | lancedb | `exp2-fixtures::lancedb::39919461e937` | identical (pinned `assert_controlled_constant`) |

Full identities: `repo_commit` `c475852cf195658ce6af8654e11e07dce4c39fec`,
`dependency_lock_hash` `3a225230a6ebe0f7…` (sha256 of `uv.lock`), full
hex values in each cell manifest inside `output/run1/results.raw.json`.

## Preflight (TDR-014 / protocol §12)

Plan agreement (`assert_runner_cells`) green before measured work; per
cell `build_runtime_manifest` with all store-experiment mandatory fields
non-null (embedding honestly recorded as `precomputed` /
`fixed-fixture-vectors`); plan assertions green including
`upsert_path == "upsert_precomputed"`,
`embedding_model_calls_during_upsert == 0` (proved with a counting
lookup model on the `Settings.embed_model` seam), and identical
`query_vector_checksum` across cells; controlled constants pinned
across cells after the run. Fresh stores verified to hold exactly the
fixture ids before querying.

## Determinism proof

Two full executions → canonical projections byte-identical:
`sha256:95ea1b1999ee97d77412c4843709eff52c12c67c6ae6746bb2548161c7896d9b`
(both files). Canonicalisation removes `latency_ms`, `timestamp_utc`,
random cleanup paths, and rounds floats to 9 dp — see
`output/deterministic_rerun_proof.txt`.

## Reproduction

```bash
uv run --no-sync python experiments/example/experiment-2-dense-cross-store-score-parity/run_eval.py \
  --output-dir experiments/example/experiment-2-dense-cross-store-score-parity/output/run1
uv run --no-sync python experiments/example/experiment-2-dense-cross-store-score-parity/summarise_eval.py \
  experiments/example/experiment-2-dense-cross-store-score-parity/output/run1/results.raw.json
```

Fixtures regenerate deterministically with `make_fixtures.py` (committed
JSONs are the ground truth; do not regenerate without re-reviewing
`qrels.json`).

## Artefacts (all verified non-gitignored)

- `fixtures/manifest.json`, `fixtures/queries.json`, `fixtures/qrels.json` — committed BEFORE runs
- `plan.json` — 2 cells, loadable via `ExperimentPlan.from_json`
- `output/run1/`, `output/run2/` — `results.raw.json` (60 D16 rows + manifests + static check), `results.summary.json`, `results.canonical.json`, `cells/<cell>.json`
- `output/deterministic_rerun_proof.txt`

## Cleanup (protocol §20)

Temporary Chroma/Lance fixture databases created under `tempfile` roots
deleted after raw results were saved: 2 directories per run, paths
recorded in each raw file's `cleanup` list; 0 leftover on disk at close.

## Judgement calls

1. **Measured path** runs through the CORE dense function
   (`_dense_query_rows`) with a fixture lookup `BaseEmbedding` on the
   `Settings.embed_model` seam (the sanctioned test seam), so H5 has
   dynamic evidence on top of the AST scan; the adapter diagnostic call
   (`store.query_dense`) supplies native distances and a core-vs-adapter
   cross-check. No embedding model runs.
2. **H2/H3 verdict semantics:** the pre-registered hypothesis TEXT of H2
   is monotonicity (passes); the committed qrels additionally pin the
   documented `1/(1+d)` formula, and that invariant check fails — it is
   reported as a production finding rather than silently folded into
   either verdict. H3 FAILS because the pre-registered expected
   membership is the binding ground truth, even though both backends
   mismatch it identically (cross-store parity clause itself passed).
3. **Static check docstring carve-out:** H5's AST scan flags backend
   tokens only in executable string constants; the docstring mention of
   "ChromaDB" in `dense.py` is recorded transparently
   (`docstring_backend_mentions`) without failing — prose is not a
   branch.
4. **Canonical projection** (for the rerun proof) strips
   latency/timestamp/random-tempdir fields; raw files keep everything.
5. `run_eval.py` interleaves repetition groups (backend order alternated
   per group, protocol §10) rather than running cells strictly
   sequentially; checkpoints are written after every group (finer than
   per-cell) and per-cell artefacts after each cell completes.
