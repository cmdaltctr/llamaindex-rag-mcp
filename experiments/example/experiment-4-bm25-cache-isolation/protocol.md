# Experiment 4 — BM25 cache isolation and invalidation

**Template ID:** `example/experiment-4-bm25-cache-isolation`  
**Status:** PASS  
**Protocol version:** 1.0  
**Executed:** 2026-08-19  
**Role:** deterministic sparse-state correctness gate

## 1. Research question

Does the process-local BM25 cache isolate indexes by vector-store instance and collection, and does each successful store mutation invalidate exactly the intended cache namespace once?

## 2. Pre-registered hypotheses

- **H1 — store isolation:** two stores containing the same collection name but different documents never reuse each other's cached BM25 rows.
- **H2 — collection isolation:** two collections in one store never share cache state.
- **H3 — stable reuse:** repeated queries without mutation reuse the same cached index.
- **H4 — mutation invalidation:** write/upsert/delete/drop invalidates only the affected namespace and triggers a lazy rebuild on next query.
- **H5 — single generation owner:** each logical mutation advances generation exactly once in both direct-store and production-orchestration paths.

## 3. Experimental unit

One `(store instance, collection)` sparse namespace.

Use tiny text fixtures with mutually exclusive rare tokens, e.g.:

- Store A / `documents`: token `alpha_only`;
- Store B / `documents`: token `beta_only`;
- Store A / `other`: token `gamma_only`.

## 4. Manipulated / independent variables

Factor A — store identity:
- store A
- store B

Factor B — collection:
- `documents`
- `other`

Factor C — mutation state:
- before mutation
- after write/upsert
- after filtered delete
- after collection delete/recreate where relevant.

Backend may be parameterised over ChromaDB and LanceDB, but backend is a block/control rather than the causal treatment.

## 5. Controlled variables

- BM25 implementation/tokenizer/settings;
- query terms;
- collection names deliberately reused across stores;
- generation starting values arranged to collide where possible;
- no dense retrieval/reranker/fusion;
- same process so cache sharing bugs can manifest.

## 6. Blocking / stratification variables

Run the same namespace test battery separately against:

- ChromaDB;
- LanceDB.

Do not average a backend-specific failure away.

## 7. Dependent variables

- returned document IDs for rare-token queries;
- cache key/namespace diagnostics;
- cache build count;
- generation before/after mutation;
- unaffected-namespace cache build count;
- stale-row count (must be zero after rebuild).

## 8. Cell / sequence matrix

For each backend:

1. build/query A:`documents` (`alpha_only`) -> cache build expected;
2. query A:`documents` again -> reuse expected;
3. query B:`documents` (`beta_only`) with equal generation -> distinct build expected;
4. query A:`other` (`gamma_only`) -> distinct collection build;
5. mutate A:`documents` -> generation +1;
6. query A:`documents` -> rebuild contains mutation;
7. verify B:`documents` and A:`other` did not rebuild;
8. filtered delete from A:`documents` -> +1 and rebuild removes deleted row;
9. compare direct-store mutation sequence with orchestration mutation sequence.

## 9. Ground truth

Ground truth is exact token membership and expected generation arithmetic. Commit fixture documents and expected result IDs.

## 10. Randomisation / counterbalancing

The sequence is intentionally ordered to trigger contamination; do not randomise the primary sequence. Add a second reversed A/B sequence as a regression for order dependence.

## 11. Repetitions and warm-up

One exact run of each forward/reversed sequence per backend + deterministic rerun.

## 12. Preflight assertions

- store A and B are distinct runtime instances;
- both have a collection literally named `documents`;
- contents are verified different;
- initial generations are recorded and intentionally equal for the collision step;
- BM25 cache starts empty.

## 13. Abort / invalid-cell criteria

- hidden global fixture/store patch makes A and B point to the same storage;
- query token appears in more than its intended namespace;
- cache was not cleared before the sequence.

## 14. Success gates

- H1/H2: zero cross-namespace result contamination.
- H3: repeated unmutated query causes zero additional cache builds.
- H4: exactly the affected namespace rebuilds after each mutation.
- H5: generation delta is exactly +1 per successful logical mutation for direct and orchestration paths.

All gates are correctness blockers.

## 15. Analysis plan

Exact sequence assertions; report cache keys/build counters and generation traces. No statistical test needed.

## 16. Threats to validity

- process-local identity intentionally permits duplicate caches if the same underlying database is wrapped by two Python objects; this is acceptable inefficiency, not contamination.
- native sparse backend is not covered.

## 17. Reproduction command placeholder

```bash
uv run python experiments/<promoted-dir>/run_eval.py
```

## 18. Required raw artefacts

- namespace fixture manifest;
- generation trace;
- cache-build trace;
- per-step query result IDs;
- runtime manifest.

## 19. Interpretation rules

Any contamination or incorrect invalidation blocks hybrid calibration. A performance complaint about duplicate but isolated caches is follow-up optimisation, not failure.

## 20. Cleanup

Clear BM25 cache and remove temporary store directories.

## Execution record (v1.0 — 2026-08-19)

Executed in worktree `harden-pipeline-correctness-before-calibration`
at commit `c475852cf195658ce6af8654e11e07dce4c39fec` (chromadb 1.5.9,
lancedb 0.37.1, rank_bm25 NOT installed — the deterministic internal
`_SimpleBM25Okapi` mirror served the sparse path, recorded honestly in
every manifest as `sparse.effective_backend:
"bm25-internal-okapi"`). Harness: `run_eval.py` + `battery.py` (+
`make_fixtures.py`, `plan.json`, `summarise_eval.py`) in this
directory. Pre-registered sections above are unchanged.

**Status: PASS** — all five hypotheses pass in every cell (4 cells:
{chroma, lancedb} x {forward, reversed}), 60 query rows and 36
recorded mutations total.

### Actual cache keying mechanism (reported as-is)

`BM25SparseRetriever._cache` is a CLASS-level dict at
`src/rag_mcp/core/retrieval/sparse.py:183`, keyed by
`(store.cache_identity, collection_name)` (`sparse.py:244-247`), where
`cache_identity` defaults to the store object itself
(`src/rag_mcp/core/vectordb/base.py:22-25`). Two runtime store
instances with a collection literally named `documents` therefore hold
two distinct cache entries; the battery records
`documents_key_entries == 2` at the collision step (s3) in every cell.

### Verdicts (from `output/run1/results.summary.json`)

| Hypothesis | Verdict | Numbers |
|---|---|---|
| H1 store isolation | PASS | 0 cross-store contaminations across all 60 rows in 4 cells; two distinct `documents` cache entries observed at the equal-generation collision step in every cell |
| H2 collection isolation | PASS | 0 cross-collection contaminations; every (namespace, token, phase) result matched the pre-registered expected ids exactly (0 mismatches) |
| H3 stable reuse | PASS | 6 repeated unmutated queries per cell (s2/s3x/s6b/s7a/s7b/s8b; 24 across all 4 cells) — 0 caused an additional cache build |
| H4 mutation invalidation | PASS | Every affected-namespace post-mutation query rebuilt exactly once (build delta 1); unaffected totals held: B/documents 1 build, A/other 3, A/documents 5 in all 4 cells |
| H5 single generation owner | PASS | All 36 mutations advanced generation by exactly +1, including the production-orchestration path (`embed_and_write_async` with pre-embedded nodes: +1; `remove_document`: +1), matching the direct-store deltas (upsert +1, delete_where +1, drop +1, recreate +1) |

### Step 9 orchestration choice (documented per protocol §8 step 9)

The production orchestration path driven is the ingestion WRITER API:
`embed_and_write_async` (writer.py:31) with pre-embedded `TextNode`s —
no embedding model call occurs (nodes carry vectors; `MockEmbedding`
stands in only for the writer's `model_name` log line) — plus
`remove_document` (writer.py:157) for the orchestration delete. This
is the minimal honest path below `ingest_path_async`: it exercises the
real `write_nodes` mutation contract (generation ownership, lock,
store dispatch) without dragging file parsing/chunking into a sparse
cache experiment. The Factor C level-4 collection delete/recreate
battery runs after the comparison (direct `delete_collection` +
recreate via `upsert_precomputed`).

### Preflight evidence (§12)

Per cell: stores A/B are distinct runtime instances (identity check),
both hold a collection literally named `documents`, contents verified
different (id sets recorded), initial generations equal at the
collision step (both 1 after setup upserts), and
`BM25SparseRetriever._cache` cleared to empty before the sequence. All
recorded in each manifest's `preflight` block and asserted by the
plan's preflight assertions.

### Determinism

Two full executions (`output/run1`, `output/run2`) produce
byte-identical canonical projections (latency/timestamp/cleanup-path
fields removed, floats rounded to 9 dp):
`sha256:ef3e15d179819e6b01a7dbe89a61277d51adc8de58225897778871a3432662c3`.
Proof: `output/deterministic_rerun_proof.txt`.

### Cleanup (§20)

Temporary store directories (4 per run) deleted after raw results were
saved (recorded in each raw file's `cleanup` list; 0 leftover);
`BM25SparseRetriever._cache` cleared after every battery.

### Artefacts

`fixtures/{docs,queries,qrels}.json` (committed before runs),
`plan.json`, `output/run1/` and `output/run2/` (`results.raw.json`,
`results.summary.json`, `results.canonical.json`, `cells/`),
`output/deterministic_rerun_proof.txt`, `results.md`.

### Reproduction

```bash
uv run --no-sync python experiments/example/experiment-4-bm25-cache-isolation/run_eval.py --output-dir experiments/example/experiment-4-bm25-cache-isolation/output/run1
uv run --no-sync python experiments/example/experiment-4-bm25-cache-isolation/summarise_eval.py experiments/example/experiment-4-bm25-cache-isolation/output/run1/results.raw.json
```
