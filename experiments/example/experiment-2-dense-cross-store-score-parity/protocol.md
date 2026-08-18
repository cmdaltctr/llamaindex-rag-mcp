# Experiment 2 — Dense cross-store score parity

**Template ID:** `example/experiment-2-dense-cross-store-score-parity`  
**Status:** PLANNED  
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
