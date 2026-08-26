# Experiment 3 results — hybrid filter and threshold semantics

**Status: PASS** (all §14 success gates met; every cell `complete`, `exact_match=1.0`)
**Protocol version:** 1.0 · **Executed:** 2026-08-19 · **Repo commit:** `c475852cf195658ce6af8654e11e07dce4c39fec`

## Interpretation (protocol §19)

PASS establishes hybrid contract correctness for BM25 on this fixture. It does not justify enabling hybrid by default.

## Hypothesis verdicts (protocol §14 gates)

### H1 — filter closure: PASS

Zero forbidden final results in all six filtered hybrid cells. `row_C` (forbidden, second-strongest BM25 match, BM25 score 0.480675) never appears in any filtered final:

| Cell | Filter | Final IDs | Forbidden leaks |
| --- | --- | --- | ---: |
| cell_02 | `category=allowed` | `[E, B, D, A]` | 0 |
| cell_04 | `category=allowed`, thr 0.3 | `[E, A]` | 0 |
| cell_05 | `category=allowed`, fake success | `[E, A, B]` | 0 |
| cell_06 | `category=allowed`, fake failure | `[E, A]` | 0 |
| cell_08 | `{"category": {"$eq": "allowed"}}` | `[E, B, D, A]` | 0 |
| cell_10 | `{"category": {"$in": ["allowed"]}}` | `[E, B, D, A]` | 0 |

Control: unfiltered cell_03 does return `row_C` (rank 3), so the filter is what excludes it.

### H2 — branch parity: PASS

Every sparse candidate entering RRF satisfies the active filter. Sparse-branch filter violations: **0 in all six filtered hybrid cells**; `row_C` absent from every filtered sparse trace (`h2_forbidden_absent_from_filtered_sparse_traces` all true). Filtered sparse traces are `[B(1), E(2), D(3)]`; the unfiltered trace is `[B(1), C(2), E(3), D(4)]`. Dense-branch violations: 0 in every cell.

### H3 — zero-threshold sparse recovery: PASS

Unfiltered hybrid at threshold 0 returns `row_D` (keyword-only row, dense rank 5 of 5, BM25 rank 4). Final: `[E, B, C, D, A]`; `row_D` final rank 4 with fused score 129/4160 = 0.031009615, carried by both branches (dense rank 5, sparse rank 4).

### H4 — positive-threshold semantics: PASS

Filtered hybrid at threshold 0.3 with no reranker returns exactly `[E, A]` (fused 2/61 = 0.032786885, 1/62 = 0.016129032):

- `row_B` (strongest BM25, dense score 0.100000 under the observed squared-L2 convention) is **excluded** — no qualifying dense evidence, so it cannot ride its sparse rank into the results.
- `row_D` (dense 0.058824) likewise excluded.
- Trace eligibility: dense-qualifying `{A, E}`, sparse-eligible `{E}`.

**Static evidence (no threshold-vs-fused comparison anywhere):** `output/static_check/threshold_application_sites.json` records every threshold-vs-score comparison site in `pipeline.py`/`policy.py`:

- `src/rag_mcp/core/retrieval/pipeline.py:169` — `row["score"] >= dense_threshold` inside `_hybrid_query_rows`: rows here are pre-fusion dense-branch rows (`score_kind=dense_similarity_v1`).
- `src/rag_mcp/core/retrieval/pipeline.py:409` — `r["score"] >= effective_threshold`, guarded by `(rerank_succeeded or not hybrid)`: reachable only with dense-mode dense scores or post-rerank reranker scores; hybrid non-reranked rows are excluded because their threshold was already applied at line 169.
- `threshold_vs_fused_score_comparison_sites: []` — zero sites compare any threshold against `fused_score`.

Behavioural discrimination: if 0.3 were compared against fused scores (max 0.0325), cell_04 would return `[]`; it returns `[E, A]`. If the ÷30-scaled 0.01 were compared against fused scores, cell_04 would return all four rows; it returns two.

### H5 — reranked semantics: PASS

- **Fake success (cell_05):** final `[E, A, B]` with scores `[0.95, 0.5, 0.02]`, `threshold_score_kind=reranker_sigmoid_v1`, `final_score_kind=reranker_sigmoid_v1` on every row. `row_B` (0.02 ≥ 0.3/30 = 0.01) survives the reranker-semantics threshold; `row_D` (0.001 < 0.01) is dropped. A raw 0.3 comparison against reranker scores would have dropped B as well — the observed outcome is only reachable under reranker score semantics.
- **Fake failure (cell_06):** final `[E, A]` — identical to cell_04 (the declared pre-rerank rule restored). `threshold_score_kind=dense_similarity_v1`; `rerank_reason` equals the double's `last_failure_reason` (`"fake failure double: simulated reranker backend load failure"`) verbatim, proving the pipeline surfaces the reranker's own failure reason.

## Cell matrix outcome

All 10 cells `status=complete`, `exact_match=1.0` (exact ID sequence + score kind + analytic scores within 1e-12 + trace-composed cross-check). Operator-filter cells 7–10 reproduce cells 1–2 exactly (`$eq`, `$in` shapes).

Observed fixture geometry (sanity block, convention detected `squared_l2`): E 0.8, A 0.5, C 0.409836, B 0.1, D 0.058824 — dense ordering `[E, A, C, B, D]`, matching the pre-registered expectation; BM25 ordering `[B, C, E, D]` (A scores 0).

## Manifest identities (per cell)

- `repo_commit`: `c475852cf195658ce6af8654e11e07dce4c39fec`; `dependency_lock_hash`: `3a225230a6ebe0f7…` (sha256 of `uv.lock`)
- `vector_store.index_identity`: `exp3_hybrid_filter_threshold_fixture` (all cells); `vector_store.backend=chroma`, `mode=ephemeral`, `score_kind=dense_similarity_v1`
- `corpus_identity`: `sha256:d73b73f84f4d41c78b626b63e44660a37cb2a76258a79d6ea1cbdda73dfa189d` (fixtures/manifest.json)
- `query_set_identity`: `sha256:d6cb9dc6b84d2b14ccf9fb403c005eb30c8e420026c7d5e8107d76396c18f781`
- `qrels_identity`: `sha256:7434bc19e336109805e5e86b4408898004ba8e015ea1c8bfa4887f6177b9720e`
- `embedding`: requested/effective `precomputed_fixture`, model `fixture-fake-embed-model-v1` (the injected double — honest provenance, not a model claim)
- `sparse`: requested `bm25`; effective `bm25` + cache namespace in hybrid cells, null (branch inactive) in dense cells
- `reranker`: null in rerank-off cells; `FakeSuccessReranker`/`FakeFailureReranker` with model ids `fake-double://success/v1` / `fake-double://failure/v1` in cells 5/6 — the doubles are test seams per protocol §4 Factor D, recorded truthfully via `observe_reranker`
- `retrieval.threshold_score_kind`: `dense_similarity_v1` in cells 1–4, 6–10; `reranker_sigmoid_v1` in cell 5
- Controlled constants pinned and asserted across cells: `rrf_k=60`, `top_k=5`, `fetch_k=5`, `index_identity`, `corpus_identity`, `embedding.model`

## Reproduction

```bash
# from the repository root, shared worktree (no network, no Ollama, no model downloads)
uv run --no-sync python experiments/example/experiment-3-hybrid-filter-and-threshold-semantics/build_fixture.py   # refuses to overwrite without --force
uv run --no-sync python experiments/example/experiment-3-hybrid-filter-and-threshold-semantics/static_check_threshold.py
uv run --no-sync python experiments/example/experiment-3-hybrid-filter-and-threshold-semantics/run_eval.py        # --resume supported
```

**Determinism proof (protocol §11):** two independent full runs (fresh process, ephemeral store rebuilt each time) produced byte-identical canonical projections `results.canonical.json` — sha256 `fee8e0a347c7990a9eb2030c38b6089ffb1ee18b1c02379a2d7d0bf8c9a095c2` for both runs (verified with `diff` + `shasum`). The canonical projection strips exactly the volatile wall-clock/latency fields (`timestamp_utc`, `created_at_unix`, `latency_ms`); the raw artefact diff between runs shows only those fields.

## Artefacts (all committable; verified via `git check-ignore` + `git add -n` dry run)

- `fixtures/manifest.json` — pre-registered fixture + analytic expectations (ground truth committed before any run)
- `fixtures/queries.json`, `fixtures/qrels.json` — query set + per-cell expected outcomes
- `plan.json` — 10-cell machine-readable plan, loadable via `ExperimentPlan.from_json`
- `results.raw.json` — full payload: sanity, per-cell records (manifest + traces + per-query rows), hypothesis inputs
- `results.canonical.json` — volatile-stripped projection (rerun-proof diff target)
- `checkpoint.json` — per-cell atomic checkpoint (`.tmp`→rename), `--resume` capable
- `output/cells/<cell_id>.json` × 10 — per-cell records with branch traces (dense candidates + canonical scores, sparse candidates + ranks, fused IDs + RRF scores + dense/sparse ranks, eligibility stages, filter-violation counts)
- `output/static_check/threshold_application_sites.json` — H4 static evidence
- `build_fixture.py`, `run_eval.py`, `harness.py`, `static_check_threshold.py` — harness code

## Production defects found

None. All five hypotheses pass; no `src/` file was modified by this experiment.

## Preflight summary (TDR-014 contract)

Per cell: `build_runtime_manifest` → `assert_manifest` on the plan's 18 preflight assertions → `assert_no_fallback` → cell-type asserts (BM25 effective in hybrid cells and null in dense cells; fake-double identity armed in cells 5/6 and no reranker active in off cells; each double probed before measured work). Plan agreement (`plan.assert_runner_cells(build_cell_matrix())`) and the runner↔plan assertion-semantics check ran before any measured work. `assert_controlled_constant` over six pinned fields ran across the completed cells.

## Judgement calls

1. **Chroma distance convention:** the fixture encodes each row's canonical score as a closed band `[1/(1+d²), 1/(1+d)]` because ChromaDB's L2 reporting convention is a store implementation detail. The run detected `squared_l2`. Band gaps (≥ 0.045) and the 0.3 threshold margins (≥ 0.05) dwarf the 1e-6 tolerance used to absorb float32 HNSW arithmetic (~1e-8 observed on `row_C`).
2. **Dense-cell score assertions are ordering + band + score-kind, not exact numerics** — exact scores are asserted for every RRF cell (analytic fractions), the reranker cell (fixture literals) and the sanity block (band endpoints). Store-native dense values are asserted to the precision the store can guarantee.
3. **Branch traces reuse the production functions** (`_dense_query_rows`, `BM25SparseRetriever.query`, `rrf_with_metadata`) with the pipeline's gating rule mirrored, because the sparse branch's pre-fusion candidates are not externally observable without editing `src/`. Every cell additionally cross-checks that the trace-composed final equals the observed `search()` final (`composed_trace_match=1.0` in all 10 cells), so the traces are validated against the pipeline, not just against the fixture.
4. **Ephemeral store (protocol §20 cleanup):** the fixture store is an in-memory `chromadb.EphemeralClient` rebuilt per run, so there is no temporary store directory to delete; the collection identity is carried by `vector_store.index_identity` and the fixture file hashes instead of on-disk bytes.
5. **`set_default_effective_settings`** is installed once at the experiment boundary because the store's paged reads consult the composition-root default for the scan page size (AGENTS.md gotcha 8a); retrieval knobs still arrive per call via the injected `EffectiveSettings`.
6. **Runner/harness split:** `run_eval.py` (662 lines) + `harness.py` (380 lines after formatting) follow the experiment-18 precedent; both exceed the ~500-line convention for experiments, which `tests/test_file_size_ceiling.py` deliberately does not govern (it scopes `src/rag_mcp/` only).
7. **Plan-assertion drift check compares semantics** (field/operator/expected triples), not the plan's `reason` prose — the reasons are documentation.

## Files created/modified (all inside this experiment directory)

Created: `build_fixture.py`, `harness.py`, `run_eval.py`, `static_check_threshold.py`, `plan.json`, `fixtures/manifest.json`, `fixtures/queries.json`, `fixtures/qrels.json`, `results.raw.json`, `results.canonical.json`, `checkpoint.json`, `output/cells/*.json` (10), `output/static_check/threshold_application_sites.json`, `results.md`.
Modified: `protocol.md` (status header + appended execution record only; pre-registered content untouched).
