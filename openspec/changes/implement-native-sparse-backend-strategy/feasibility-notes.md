# Feasibility notes: native FTS on locked lancedb 0.37.1 / pylance 10.0.0

Task 0.1 evidence for `implement-native-sparse-backend-strategy`.
Contract test: `tests/test_lancedb_native_fts_contract.py` (20 tests,
fast suite, real temporary stores under `tmp_path`; never touches the
production `LANCEDB_URI` or `output/chroma_*` indexes).

## Environment

- `lancedb` 0.37.1 (verified via `importlib.metadata`)
- `pylance` 10.0.0 (distribution; provides the `lance` module — it is
  not importable under the name `pylance`)
- No Tantivy-backed FTS mode exists in these versions; native FTS is
  the inverted-index implementation. No `tantivy` import is involved.

## Observed semantics

| Area | Behaviour on the locked versions |
| --- | --- |
| Index creation | `table.create_index("text", config=FTS())` — additive on populated tables, idempotent under the default `replace=True`, works on empty tables. Absent column names raise `ValueError` ("Field path `documents` not found in schema"). |
| Query | `table.search(q, query_type="fts")` with `.where(sql)` and `.limit(n)`; `.to_list()` returns plain row dicts. Empty query returns zero rows without error. |
| Column scoping | Only the indexed `text` column is searched. `id`/`doc_id` values do not leak matches. |
| Result shape | Row dict keys: `id`, `doc_id`, `vector`, `text`, `metadata`, `_score`. No `_distance` (dense-mode diagnostic). |
| Score semantics | `_score` is higher-is-better, BM25-like. A two-term match outranks a one-term match; matches score above zero. Raw scales are NOT comparable to in-process BM25Okapi scores — only rank order feeds RRF (as designed). |
| Freshness (adds) | **Fresh-by-construction**: rows added after index creation are found at query time (unindexed rows are scanned). Searching does not fold rows into the index — `num_unindexed_rows` is unchanged by queries. |
| Freshness (deletes) | Deleted rows disappear immediately (tombstones). |
| Refresh | `table.optimize()` folds unindexed rows into the index (`num_unindexed_rows` → 0) and compacts. This is the durable refresh operation. |
| Durability | The index is on-disk in the `.lance` table; a NEW connection reports the same index statistics and serves FTS immediately (cross-process durability). |
| Coverage diagnostics | `table.list_indices()` yields `IndexConfig(index_type="FTS", columns=[...], num_indexed_rows=..., num_unindexed_rows=..., ...)`. Mixed coverage = `0 < num_indexed_rows < total_rows`. |
| Absence signal | FTS search without an index raises `ValueError: ... Cannot perform full text search unless an INVERTED index has been created on at least one column`. This is the "native unavailable → BM25 fallback" trigger. |
| Filters + FTS | Chroma-style `where` dicts translated by `lance_filter.translate_where` (producing `metadata.<field>` SQL) are accepted by the FTS query builder and compose correctly with text matching. |

## Verification that the pins bite

Each critical pin was mutation-tested: temporarily breaking the pinned
behaviour (wrong index column name, dense `query_type` on the FTS shape
assertion, inverted score ordering, inverted freshness expectation,
weakened absence-message match, inverted deletion freshness, inverted
column-leakage expectation) made the corresponding test fail; the
restored file passes 20/20.

## Design alignment assessment (design.md decision 4)

The design specifies an FTS lifecycle in which "after a write,
replacement, or deletion, the index is stale until refresh completes"
and the query path must "never return stale native results as
successful". Observed reality on the locked versions is STRONGER than
that model:

- Writes make the index *partially indexed* (`num_unindexed_rows > 0`)
  but never make results wrong: unindexed rows are covered at query
  time and deletions are honoured through tombstones.
- Therefore the design's worst case (serving stale results as
  successful) cannot occur through the engine's query path. The
  lifecycle contract is implemented as follows:
  - **Stale marker** = `num_unindexed_rows > 0` (coverage lag; a
    performance property, surfaced in freshness diagnostics).
  - **Refresh** = `optimize()` after writes/replacements/deletions
    folds unindexed rows and compacts tombstones.
  - **Freshness verification** = index statistics read before serving
    native results (diagnostic surface), with the engine's
    query-time freshness guarantee pinned by contract tests.
  - **Fallback** still triggers on hard failures: absent index (the
    pinned `ValueError`) or any engine error during the native query.

This is a refinement of the mechanism, not a contradiction of the
design's requirements: every SHALL in the lifecycle requirement
remains implementable exactly as written, and the safety property the
design demands (never return stale results as successful) is satisfied
by construction. Implementation proceeds on this basis.

## Consequences for the adapter (design input)

1. The capability method on `VectorStore` maps to
   `create_index("text", config=FTS())` + `search(query,
   query_type="fts")` + `optimize()` + `list_indices()`.
2. Score normalisation: `_score` → canonical sparse score
   (higher-is-better); no distance transform applies.
3. Mixed-coverage diagnostics can use `list_indices()` statistics
   directly instead of paging `iter_metadatas` when an FTS index
   exists (the paged `has_sparse_vector` scan remains the Chroma-era
   path).
4. First-use on an unindexed collection: additive creation, then the
   query proceeds; creation failure or absence routes to BM25 with
   the pinned warning.
