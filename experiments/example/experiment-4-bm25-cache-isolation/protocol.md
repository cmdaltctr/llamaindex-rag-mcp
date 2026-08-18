# Experiment 4 — BM25 cache isolation and invalidation

**Template ID:** `example/experiment-4-bm25-cache-isolation`  
**Status:** PLANNED  
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
