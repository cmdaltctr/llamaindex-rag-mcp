# Experiment 2 — Dense cross-store score parity

**Template ID:** `example/experiment-2-dense-cross-store-score-parity`  
**Status:** FAIL  
**Protocol version:** 1.0  
**Executed:** 2026-08-19  
**Role:** semantic-swappability gate for ChromaDB and LanceDB

## 1. Research question

When ChromaDB and LanceDB contain the same documents and exactly the same precomputed embeddings, do their adapters satisfy the same production dense-retrieval score/ranking contract without core retrieval knowing the backend?

This experiment tests the abstraction boundary, not which database is faster.

## 2. Pre-registered hypotheses

- **H1 — ranking parity:** both stores produce the expected nearest-neighbour ordering on deterministic vector fixtures.
- **H2 — canonical score monotonicity:** canonical score decreases as known geometric distance from the query increases.
- **H3 — threshold parity:** for pre-registered canonical threshold values, Chroma and Lance select the same fixture rows.
- **H4 — metadata-filter parity:** equivalent filters yield the same eligible IDs in both stores.
- **H5 — backend opacity:** core dense retrieval requires no backend-name branch or native-distance interpretation.

## 3. Experimental unit

One query vector evaluated against one frozen vector fixture. Use several small fixtures with analytically known geometry, for example:

- exact match + orthogonal + opposite vectors;
- progressively rotated normalised vectors;
- duplicate-distance ties with deterministic ID tie-handling documented separately;
- metadata subsets for filter tests.

All embeddings are precomputed and committed as JSON; no embedding model runs in this experiment.

## 4. Manipulated / independent variable

`vector_store_backend`:

1. `chroma`
2. `lancedb`

## 5. Controlled variables

- exact embedding float arrays;
- query vectors;
- IDs/documents/metadata;
- collection name and logical contents;
- no reranker;
- no hybrid/BM25;
- same `n_results` / top_k;
- same canonical score contract version;
- same Python process where practical, but each store has a distinct runtime identity/cache namespace.

## 6. Blocking / stratification variables

Each analytical fixture is a block. Compare stores within fixture, never aggregate away a fixture-level failure.

## 7. Dependent variables

- ordered result IDs;
- canonical scores;
- `score_kind`;
- threshold-selected ID set;
- metadata-filter-selected ID set;
- native diagnostic distance/metric if exposed (diagnostic only);
- query latency as descriptive secondary output only.

## 8. Cell matrix

For every fixture/query:

| Cell | Store | Retrieval |
|---|---|---|
| C | ChromaDB | dense canonical score |
| L | LanceDB | dense canonical score |

Threshold/filter subconditions are repeated identically for both cells.

## 9. Corpus / ground truth

Ground truth is analytical geometry, not human relevance labels. Commit:

- vectors and metadata;
- expected strict ordering where non-tied;
- expected equivalence groups for ties;
- expected threshold membership for each canonical threshold;
- expected metadata filter membership.

## 10. Randomisation / counterbalancing

Not required for correctness. If latency is retained as a descriptive metric, alternate backend order across repetitions to reduce cache/thermal ordering bias.

## 11. Repetitions and warm-up

Correctness: one execution plus deterministic rerun.  
Latency (secondary only): one warm-up + >=5 repetitions; do not draw performance conclusions from this micro test unless promoted to a dedicated benchmark.

## 12. Preflight assertions

- both stores are fresh and contain exactly the fixture IDs;
- embeddings were inserted via `upsert_precomputed` without recomputation;
- adapters report the same canonical `score_kind`;
- core dense function does not receive/backend-branch on a store name;
- query vector checksum is identical across cells.

## 13. Abort / invalid-cell criteria

- any fixture row differs between stores before query;
- a store recomputes embeddings;
- adapters report incompatible score-kind versions;
- a backend silently changes vector metric from the pinned contract without the plan being amended.

## 14. Success gates

- H1: exact ordering match for all non-tied fixtures; tied groups may permute only within pre-labelled tie sets.
- H2: zero monotonicity violations in either backend.
- H3: identical threshold membership for all pinned thresholds.
- H4: identical filter membership for all supported filter fixtures.
- H5: static/contract test confirms backend interpretation lives only in adapters.

Any H1-H5 failure blocks claims that the stores are semantically swappable for dense retrieval.

## 15. Analysis plan

Report per-fixture result tables. For larger synthetic fixtures optionally report Kendall tau / top-k overlap, but exact fixture assertions remain primary. Canonical score numeric equality is required only if the contract mathematically promises equality; otherwise compare documented invariants and threshold membership.

## 16. Threats to validity

- tiny analytical vectors do not test ANN/index approximation at large scale;
- exact ties can expose backend-specific tie ordering that is not a semantic defect;
- production embeddings may not be perfectly normalised; add a separate fixture if the canonical score contract depends on normalisation.

## 17. Reproduction command placeholder

```bash
uv run python experiments/<promoted-dir>/run_eval.py
```

## 18. Required raw artefacts

- fixture vectors/expected outcomes;
- per-store raw native diagnostics and canonical rows;
- runtime manifest;
- threshold/filter outcomes;
- results summary.

## 19. Interpretation rules

- correctness mismatch -> fix adapter/contract before any cross-store RAG quality experiment;
- correctness pass -> vector stores are semantically equivalent for the tested dense contract, not necessarily performance-equivalent;
- latency observations here are exploratory only.

## 20. Cleanup

Delete temporary Chroma/Lance fixture databases after raw results are saved.

## Execution record (v1.0 — 2026-08-19)

Executed in worktree `harden-pipeline-correctness-before-calibration` at
commit `c475852cf195658ce6af8654e11e07dce4c39fec` (chromadb 1.5.9,
lancedb 0.37.1, pyarrow 25.0.1, llama-index 0.14.23). Harness:
`run_eval.py` (+ `static_check.py`, `make_fixtures.py`, `plan.json`,
`summarise_eval.py`) in this directory. Pre-registered sections above
are unchanged; this record reports what ran.

**Status: FAIL** — H3 fails against the pre-registered analytic ground
truth. Per §14 this blocks claims that the stores are semantically
swappable for the dense contract AS DOCUMENTED, and per the Stage 5
gate this FAIL blocks Stage 6 until the contract defect below is
resolved.

### Verdicts (from `output/run1/results.summary.json`)

| Hypothesis | Verdict | Numbers |
|---|---|---|
| H1 ranking parity | PASS | 50 measured repetitions (5 fixtures x 5 reps x 2 backends), zero ordering violations; ties permuted only within labelled tie sets |
| H2 canonical score monotonicity | PASS | 190 monotonicity comparisons across fixtures/backends, zero violations; scores reproduce `1/(1+native)` exactly — but see the finding below: `native` is squared L2 |
| H3 threshold parity | FAIL | 300 membership checks (5 fixtures x 5 reps x 6 thresholds x 2 backends): 110 mismatch the pre-registered analytic expectation, IDENTICALLY in both backends; cross-store identity itself held (0 cross-store membership differences) |
| H4 filter parity | PASS | 50 filter checks (5 filters x 5 reps x 2 backends): query-id sets and `count_where` all match; includes `$in` and nested `$and`+`$gte` operator filters |
| H5 backend opacity | PASS | AST scan of `dense.py`: 0 backend literals in executable strings, 0 `native_distance` accesses, 1 abstract `store.query_dense` call site; both adapters cited for `canonical_score_from_l2` conversion; every measured core-path row identical to the adapter path |

### Production finding (recorded, NOT hotfixed)

**`exp2-f1-squared-l2-canonical-score`** — both engines' `"l2"` metric
reports SQUARED Euclidean distance (native `[0,1,0,0]` vs query
`[1,0,0,0]` = 2.0; `[0.5,0,0,0]` = 0.25; `[-2,0,0,0]` = 9.0 — identical
in Chroma and Lance rows), and the adapters pass it straight into
`canonical_score_from_l2`, so the production canonical score is
`1/(1+d**2)` while `src/rag_mcp/core/vectordb/score.py:27-51` documents
`1/(1+d)` over a "native non-negative L2 distance". Monotonicity and
cross-store swappability hold (both engines square identically); the
absolute threshold meaning does not match the documented contract.
Locations: `score.py:27-51`, `chroma.py:264`, `lancedb.py:370`.
Per §19: correctness mismatch → fix adapter/contract before any
cross-store RAG quality experiment. Full record in
`output/run1/results.summary.json` under `production_findings`.

### Preflight evidence (§12)

Both stores fresh with exactly the fixture ids (verified per cell);
upserts via `upsert_precomputed` with zero embedding-model calls during
the upsert phase (counted via the fixture lookup model, manifest field
`embedding_model_calls_during_upsert: 0`); both cells report
`score_kind: dense_similarity_v1`; query vector checksum identical
across cells (`sha256` of `fixtures/queries.json`, pinned by
`assert_controlled_constant`). No reranker, no parser, no embedding
provider — `assert_no_fallback` not applicable per plan.

### Determinism

Two full executions (`output/run1`, `output/run2`) produce
byte-identical canonical projections (latency/timestamp/cleanup-path
fields removed, floats rounded to 9 dp):
`sha256:95ea1b1999ee97d77412c4843709eff52c12c67c6ae6746bb2548161c7896d9b`.
Proof: `output/deterministic_rerun_proof.txt`.

### Cleanup (§20)

Temporary Chroma/Lance fixture databases created under `tempfile`
roots were deleted after raw results were saved (2 directories per
run, recorded in each raw file's `cleanup` list; 0 leftover).

### Artefacts

`fixtures/{manifest,queries,qrels}.json` (committed before runs),
`plan.json`, `output/run1/` and `output/run2/` (`results.raw.json`,
`results.summary.json`, `results.canonical.json`, `cells/`),
`output/deterministic_rerun_proof.txt`, `results.md`.

### Reproduction

```bash
uv run --no-sync python experiments/example/experiment-2-dense-cross-store-score-parity/run_eval.py --output-dir experiments/example/experiment-2-dense-cross-store-score-parity/output/run1
uv run --no-sync python experiments/example/experiment-2-dense-cross-store-score-parity/summarise_eval.py experiments/example/experiment-2-dense-cross-store-score-parity/output/run1/results.raw.json
```
