## Why

The diagnostics passthrough (`search-diagnostics-passthrough-1`) and orphan
visibility (`orphaned-source-visibility-2`) changes both widened the public
surface. Neither updated `transports/api/openapi.yaml`, which
`transport-separation` declares as the versioned contract for the future REST
transport. Nothing detects this: CI validates that the document is well-formed
OpenAPI 3.1, never that it agrees with the code it describes.

The drift is wider than the two recent changes. Measured against the current
tree, three schemas are incomplete:

- `SearchRequest` omits `diagnostics`.
- `DocumentInfo` omits `orphaned` and `source_id`.
- `SearchResult` omits `metadata` and all five lineage fields (`source_id`,
  `source_version`, `chunk_id`, `source_chunk_index`, `source_chunk_count`),
  every one of which every search result has carried since the lineage work.

`SearchResult` is the worst of the three and the oldest, which is the strongest
argument that review alone does not hold this contract.

The same round left the diagnostics surface half-answered. A caller can now see
*what* retrieval decided — ranks, fusion scores, rerank reason, sparse backend —
but not *what it cost*. `core/ingestion/pipeline.py` reports six timing buckets
per source; `core/retrieval/` measures nothing. Latency claims still require
running an experiment.

Both threads are small, both close a gap the last round opened, and the
diagnostics seam that thread B needs was built last week and is currently unused
for timing. Doing them together avoids touching the same result-shape contract
twice.

## What Changes

### Thread A — the declared contract describes the implemented surface

- Add `diagnostics` (boolean, default `false`) to the `SearchRequest` schema in
  `openapi.yaml`.
- Add `orphaned` (nullable boolean) and `source_id` (nullable string) to the
  `DocumentInfo` schema.
- Add `metadata` and the five lineage fields to the `SearchResult` schema, plus
  the diagnostic fields (including thread B's `timings`) declared as optional
  because they appear only when diagnostics are enabled.
- Add a conformance test covering all three schemas. It derives the implemented
  surface from the Python — the `search_documents` signature, the
  `list_documents` result keys, and the search result keys in both default and
  diagnostics modes — and fails when `openapi.yaml` omits a field, naming the
  field and the schema that should carry it.
- Define exact default-comparison rules (see design D7). Today `openapi.yaml`
  declares no `default` key on any `SearchRequest` property, so a naive
  `.get("default")` check would compare `None` against `None` and pass four
  parameters for the wrong reason.
- Correct the stale `similarity_threshold` description, which states a `0.0`
  default while the Python default is `None` (profile-resolved).
- Extend the `transport-separation` requirement so contract fidelity is a stated
  obligation rather than a convention that held until it did not.

### Thread B — the diagnostics payload reports stage cost

- Measure wall time for the retrieval stages that can dominate a query: query
  embedding, dense search, sparse search, fusion, and reranking.
- Attach the measurements to each result row **only** when diagnostics are
  enabled, as a single `timings` mapping of stage name to seconds.
- Report only stages that ran. A dense-only query has no `sparse_seconds`; a
  non-reranked query has no `rerank_seconds`. Absence means "did not run", never
  "took zero time" — the same reporting rule the ingest norm band already
  follows.
- When a stage runs more than once in a query — which happens on the
  failed-rerank path, where hybrid retrieval is re-queried — accumulate its
  duration. The reported number is the total time the query spent in that
  stage, so every execution is counted (see design D5).
- Timings ride on result rows, so a query returning no rows reports none. That
  limitation is stated in the spec rather than worked around.
- No transport change. `search-diagnostics-surface` already specifies that core
  retrieval is the sole producer of diagnostic fields and that transports pass
  an evolving field set through without defining their own schema.

### Explicitly out of scope

- Splitting `transports/mcp.py` (495 of 500 lines). Behaviour-preserving module
  surgery with a different motivation; it belongs in its own refactor commit.
- The BM25 in-memory index, the `codebase` profile's `top_k=20` caller cost,
  table-aware parsing, and parent-chunk expansion. Each is gated on a measured
  problem, and none has been measured.

## Capabilities

### New Capabilities

None. Both threads extend existing capabilities.

### Modified Capabilities

- `transport-separation`: the versioned OpenAPI contract requirement gains an
  obligation that the declared schemas cover every field the implemented
  transports expose, enforced by an automated conformance check rather than
  review.
- `search-diagnostics-surface`: a new requirement that core retrieval produces
  per-stage timing under the existing diagnostics control, with omission
  denoting a stage that did not run.

## Impact

**Code**

- `src/rag_mcp/transports/api/openapi.yaml` — three schema fields added. No
  runtime code; the folder stays contract-only.
- `src/rag_mcp/core/retrieval/pipeline.py` — stage timing around the existing
  dense, hybrid, fusion, and rerank calls.
- `src/rag_mcp/core/retrieval/dense.py` — embedding-stage timing inside the
  cached-embedding boundary, so a cache hit is visibly cheap.
- New test module for the OpenAPI conformance check.
- Extensions to the existing retrieval diagnostics tests.
- `tests/test_clean_base_tripwire.py` and `tests/test_retrieval.py` —
  executed-count bump (1963→1986) and a fake-signature update for the new
  `timing_report` parameter.

**Not affected**

- `transports/mcp.py` and `transports/cli/search.py`. Both already pass the
  full core result through unchanged, so a new diagnostic key surfaces without
  a transport edit. This is the behaviour
  `search-diagnostics-surface`'s "Core diagnostic fields evolve" scenario
  already pins.
- Default response shape. Timing appears only under `diagnostics: true`.
- Retrieval behaviour, ranking, and scores. Measurement only.

**Risks**

- Timing instrumentation on a hot path must not itself cost meaningfully.
  `perf_counter` calls are nanosecond-scale and are taken once per stage, not
  per candidate row.
- The conformance test must derive the implemented surface rather than restate
  it, or it becomes a second thing to forget to update.

**Dependencies**

None. Both threads are independent of each other and of the in-flight
`tripwire-retirement-and-provider-symmetry` change.
