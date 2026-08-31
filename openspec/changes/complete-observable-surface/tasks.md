## 1. Thread A — pin the contract gap (red first)

- [ ] 1.1 Create `tests/test_openapi_conformance.py` with a helper that loads
      `src/rag_mcp/transports/api/openapi.yaml` and returns the property maps
      and `required` lists for `components.schemas.SearchRequest`,
      `components.schemas.DocumentInfo`, and `components.schemas.SearchResult`.
- [ ] 1.2 Add a helper deriving search parameters from
      `inspect.signature(rag_mcp.transports.mcp.search_documents)`, returning
      `{name: default}`. Exclude only `collection`, with a comment naming why:
      it is a path parameter in `/v1/collections/{collection}/search`, not a
      body field. `query` is NOT excluded — it is a declared body field and must
      stay under the check.
- [ ] 1.3 Add a helper deriving listing keys by calling `list_documents` against a
      stub store that returns one fully-populated lineage row, reusing the stub
      pattern in `tests/test_orphaned_source_visibility.py`.
- [ ] 1.4 Add a helper deriving search-result keys twice against a stub store:
      once from a default search and once with `include_diagnostics=True`.
      Return both key sets so required and optional fields can be distinguished.
- [ ] 1.5 Write the failing test: every derived search parameter appears in
      `SearchRequest.properties`. Confirm it fails naming `diagnostics`.
- [ ] 1.6 Write the failing test: every derived listing key appears in
      `DocumentInfo.properties`. Confirm it fails naming `orphaned` and
      `source_id`.
- [ ] 1.7 Write the failing test: every default search-result key appears in
      `SearchResult.properties` and is required. Confirm it fails naming
      `metadata`, `source_id`, `source_version`, `chunk_id`,
      `source_chunk_index` and `source_chunk_count`, and the six
      already-declared fields (`score`, `score_kind`, `source`, `page_label`,
      `text`, `reranked`), which are currently declared but not required
      (`required` is empty today). The test must fail on both counts so the
      red state is confirmed for the right reason.
- [ ] 1.8 Write the failing test: every diagnostics-only result key is declared
      and NOT required.
- [ ] 1.9 Write the default-comparison test implementing design D7's four
      rules, including the 3a/3b distinction between profile-resolved and
      absent-means-None parameters.
      Use `"default" in schema`, never `.get("default")` — the schema currently
      declares no defaults at all, so `.get` would compare `None` to `None` and
      pass `top_k`, `similarity_threshold`, `rerank` and `hybrid` for the wrong
      reason. Confirm the test fails for the right reason on each rule.
- [ ] 1.10 Write the tests for rules 3a and 3b: the profile-resolved four
      (`top_k`, `similarity_threshold`, `rerank`, `hybrid`) must state in
      their description that the value resolves from the collection profile,
      and any parameter whose Python default is `None`, including
      `metadata_filter`, must not assert a concrete default or claim profile
      resolution. Confirm it fails naming `similarity_threshold` for asserting
      "default 0.0".
- [ ] 1.11 Add a test asserting the failure message names the missing field and
      its expected schema, so the check is actionable when it fires.

## 2. Thread A — close the gap

- [ ] 2.1 Add `diagnostics` to `SearchRequest`: `type: boolean`,
      `default: false`, with a description stating it returns core-produced
      retrieval diagnostics.
- [ ] 2.2 Add `source_id` to `DocumentInfo` as nullable string, described as the
      stable identity derived from the canonical source path.
- [ ] 2.3 Add `orphaned` to `DocumentInfo` as nullable boolean, describing all
      three states and stating explicitly that it is machine-local.
- [ ] 2.4 Add `metadata` (object) and the five lineage fields to `SearchResult`,
      marking every default-response field required.
- [ ] 2.5 Add the diagnostic fields to `SearchResult` as optional: `id`,
      `fused_score`, `dense_score`, `dense_score_kind`, `dense_rank`,
      `sparse_rank`, `fused_rank`, `rerank_reason`, `threshold_score_kind`,
      `rerank_backend`, `sparse_backend`, `norm_guard`, and thread B's
      `timings`. Sequence this after task 4.7 so `timings` exists to derive.
- [ ] 2.6 Rewrite the `similarity_threshold` description to state that the value
      is resolved from the collection profile when omitted, removing the stale
      "default 0.0" claim. Apply the same wording rule to `top_k`, `rerank` and
      `hybrid`.
- [ ] 2.7 Run the Thread A tests and confirm all now pass.
- [ ] 2.8 Confirm `transports/api/` still contains only `README.md` and
      `openapi.yaml` (the no-runtime-code scenario).
- [ ] 2.9 Run the existing CI OpenAPI validation command locally to confirm the
      document is still a valid OpenAPI 3.1 spec after the edits.

## 3. Thread B — pin the timing contract (red first)

- [ ] 3.1 Add tests to the retrieval diagnostics suite asserting a hybrid search
      with diagnostics enabled returns a `timings` mapping on every row
      containing embedding, dense, sparse and fusion durations. Confirm it fails.
- [ ] 3.2 Add a test asserting a dense-only search omits the sparse and fusion
      keys rather than reporting zero.
- [ ] 3.3 Add a test asserting a non-reranked search omits the rerank key, and a
      reranked search includes it.
- [ ] 3.4 Add a test asserting a search without diagnostics carries no `timings`
      field and matches the existing default result shape exactly.
- [ ] 3.5 Add a test asserting identical result identities, order and scores with
      diagnostics on versus off, so timing is provably measurement-only.
- [ ] 3.6 Add a test asserting a repeated identical query calls the embedding
      provider only once, and that an embedding duration is still reported on
      the second call. Count provider calls; do NOT compare two wall-clock
      durations (design D9) — that assertion is flaky on a shared runner.
- [ ] 3.7 Add a test for the failed-rerank re-query: dense, sparse and fusion
      durations are each the SUM of both executions, and a rerank duration is
      present. Drive it with the stub reranker pattern already used in
      `tests/test_hybrid_retrieval.py:604`.
- [ ] 3.8 Add a test asserting a search returning zero results carries no
      timings, pinning the documented boundary rather than leaving it implied.

## 4. Thread B — implement stage timing

- [ ] 4.1 Add a keyword-only `timing_report: dict | None = None` parameter to
      `_dense_query_rows` in `core/retrieval/dense.py`, defaulting to `None` so
      the registry contract and all existing callers are unaffected.
- [ ] 4.2 In `_dense_query_rows`, time the `_embed_query` call (wrapping the LRU
      lookup per design D4) and the `store.query_dense` call, writing each into
      `timing_report` when supplied.
- [ ] 4.3 Add the same keyword-only parameter to the sparse runners in
      `core/retrieval/sparse_dispatch.py`, alongside the existing `report`
      argument, and record the sparse duration.
- [ ] 4.4 In `_hybrid_query_rows`, accept and forward `timing_report` to both
      branches, and time the fusion call.
- [ ] 4.5 In `search()`, create the timing dict, pass it to the dense-only and
      hybrid paths, and time the `reranker.rerank` call.
- [ ] 4.6 Accumulate durations per stage rather than overwriting, so the
      rerank-failure re-query path sums both executions of dense, sparse and
      fusion (design D5). Use `report[key] = report.get(key, 0.0) + elapsed`.
      Confirm the rerank duration is also present, since the reranker ran.
- [ ] 4.7 Attach `timings` to each result row only when `include_diagnostics` is
      true, placing it alongside the existing per-row diagnostic fields so it
      survives fusion and reranking.
- [ ] 4.8 Confirm no total is emitted, and that stage keys are omitted rather
      than zeroed when a stage did not run.
- [ ] 4.9 Run the Thread B tests and confirm all now pass.

## 5. Verification

- [ ] 5.1 Confirm `transports/mcp.py` and `transports/cli/search.py` are
      unmodified by this change (`git diff --stat` shows neither), proving the
      passthrough claim in the spec.
- [ ] 5.2 Confirm `transports/mcp.py` is still under the 500-line ceiling by
      running `tests/test_file_size_ceiling.py`.
- [ ] 5.3 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm no
      regression against the coverage floors.
- [ ] 5.4 Run the Tier 1 retrieval quality gate
      (`pytest tests/quality/test_metrics.py tests/quality/test_retrieval_quality_tier1.py -m slow`)
      and confirm Recall@10 and MRR@10 still meet their floors, proving timing
      did not alter ranking.
- [ ] 5.5 Run `uv run lint-imports` to confirm no new boundary violation.
- [ ] 5.6 Run `openspec validate --all --strict`.
- [ ] 5.7 Manually verify against a real collection:
      `uv run rag-mcp search "<query>" --hybrid --diagnostics --json` shows
      per-stage timings, and the same query without `--diagnostics` does not.

## 6. Documentation

- [ ] 6.1 Update `docs/guides/mcp-tools.md` to document the `timings` field under
      the diagnostics section, including the concurrency caveat that per-stage
      durations do not sum to wall time.
- [ ] 6.2 Update `docs/guides/cli-reference.md` for the same field under
      `--diagnostics`.
- [ ] 6.3 Update `src/rag_mcp/transports/api/README.md` to state that the
      contract is conformance-checked against the implementation and to name the
      test that enforces it.
- [ ] 6.4 Grep `docs/guides/` for any statement that the query path is
      uninstrumented and correct it (the documentation-drift check).
- [ ] 6.5 Run `graphify update .` so the knowledge graph reflects the new
      modules and the changed retrieval call paths.
- [ ] 6.6 Record a TDR only if an implementation surprise warrants one; this
      change is not expected to need one.
