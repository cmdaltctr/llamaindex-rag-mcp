## 1. Async chunking offload

- [x] 1.1 Identify the synchronous chunking call inside the async ingestion path
- [x] 1.2 Wrap chunk splitting with `asyncio.to_thread` or an equivalent loop-yielding mechanism
- [x] 1.3 Add or extend a responsiveness test that triggers chunking with a non-trivial document size and verifies a concurrent search responds promptly
- [x] 1.4 Run `uv run pytest -m "not slow" -v` and confirm responsiveness tests pass
- [x] 1.5 Run **Experiment 4** (`experiments/4-async-chunking-responsiveness-2026-05-27/`) end-to-end and confirm post-fix search P95 ≤ 2× idle baseline P95 and ingest wall-clock not regressed by more than 5 % — PASS (P95 ratio 1.42×, see `experiments/4-async-chunking-responsiveness-2026-05-27/results.md`)
- [x] 1.6 If Experiment 4 fails its pass criteria: revisit task 1.2 ... re-run the experiment, loop until criteria pass — not triggered, 1.5 passed first attempt

## 2. MCP search metadata filter exposure

- [x] 2.1 Add an optional `metadata_filter: dict | None = None` parameter to the `search_documents` MCP tool
- [x] 2.2 Pass `metadata_filter` through unchanged to `retrieval.search()`
- [x] 2.3 Add an MCP-level test verifying that filtered search returns only chunks that match the filter
- [x] 2.4 Add an MCP-level test verifying that unfiltered search behaviour is unchanged

## 3. MCP search error envelope

- [x] 3.1 Wrap `search_documents` body in error handling that converts expected retrieval/ChromaDB exceptions into a one-element list `[{"status": "error", "error_type": ..., "message": ...}]` per design Decision 5
- [x] 3.2 Map exception classes to `error_type` values (`"validation"` for invalid `metadata_filter`, `"retrieval"` for ChromaDB query failure, `"internal"` for anything else)
- [x] 3.3 Ensure successful responses keep their existing list-of-dict shape and field set (no `status` key on success)
- [x] 3.4 Add a test that supplies an invalid metadata filter and asserts the handler returns a one-element list with `status="error"`, `error_type="validation"` without raising
- [x] 3.5 Add a test that simulates a ChromaDB query failure and asserts `error_type="retrieval"` is returned
- [x] 3.6 Add a test asserting that successful responses contain no `status` key on any result dict

## 4. Score-metric consistency

- [x] 4.1 Reuse the metadata-filtered direct ChromaDB path's conversion `score = 1.0 / (1.0 + distance)` as the canonical formula
- [x] 4.2 Rework the unfiltered LlamaIndex path so the returned `score` field equals `1.0 / (1.0 + distance)` against the same underlying ChromaDB L2 distance — either by querying ChromaDB directly or by post-processing LlamaIndex retriever output
- [x] 4.3 Confirm the calibrated ÷30 reranker threshold scaling is unaffected (reranker scores remain on the sigmoid scale)
- [x] 4.4 Add a regression test that runs equivalent filtered and unfiltered searches against the same chunk and asserts the pre-threshold `score` values are equal within `1e-6`
- [x] 4.5 Add a regression test asserting that with the same `similarity_threshold`, no result below the threshold appears in either response

## 5. Ollama metadata extraction hardening

- [x] 5.1 Strip common markdown code fences (```` ```json ... ``` ````, ```` ``` ... ``` ````) from the Ollama response before `json.loads` in `_parse_ollama_json_response`
- [x] 5.2 Add a bounded async retry loop around the Ollama HTTP call with configurable max attempts and per-attempt timeout (env vars: `OLLAMA_CLASSIFY_MAX_ATTEMPTS`, `OLLAMA_CLASSIFY_TIMEOUT`)
- [x] 5.3 Apply exponential backoff between retry attempts (`await asyncio.sleep(2 ** attempt)`) so successive retries do not pile up against a slow Ollama
- [x] 5.4 Decide whether to enable Ollama JSON mode (`format: "json"`) and apply it only if it does not regress existing tests; default off for this change
- [x] 5.5 Add tests covering: success, transient failure followed by retry success, exhausted retries fallback, markdown-fenced JSON, and that backoff sleeps grow between attempts

## 6. ADR — record the architectural decisions

After implementation passes validation, write **ADR-015: RAG Reliability and Correctness Fixes** under `docs/adr/015-rag-reliability-correctness-fixes.md` following the existing ADR convention (Context, Decision, Consequences, Alternatives Considered, References). Use ADR-014 as the structural template — one ADR per OpenSpec change, with sub-decisions as numbered bullets inside the Decision section.

- [x] 6.1 Capture the five sub-decisions from `design.md` as numbered bullets in the Decision section:
  1. Offload chunk splitting via `asyncio.to_thread` (extends ADR-014's async path)
  2. Expose optional `metadata_filter` on the MCP `search_documents` tool
  3. Both retrieval paths convert ChromaDB L2 distance via `score = 1.0 / (1.0 + distance)` with a `1e-6` equality contract
  4. Ollama metadata extraction gains bounded retry, exponential backoff, and markdown fence stripping
  5. MCP `search_documents` returns errors as a single-element list `[{"status": "error", "error_type": ..., "message": ...}]` with three named `error_type` categories (`validation` / `retrieval` / `internal`)
- [x] 6.2 In the Consequences section, note: positive (consistent threshold semantics, no event-loop blocking on chunking, deterministic error shape, qwen3 fence-wrapped JSON now parses); negative (retry latency when Ollama is down, although bounded by `OLLAMA_CLASSIFY_MAX_ATTEMPTS` and exponential backoff); neutral (LlamaIndex retriever-chain replaced by direct ChromaDB call on the unfiltered branch — code path now mirrors the filtered branch).
- [x] 6.3 In Alternatives Considered, record the two rejected options for each substantive decision (ChromaDB cosine recreation vs `1/(1+d)`, dict envelope vs single-element list, tenacity vs manual retry loop).
- [x] 6.4 Cross-reference ADR-014 in the References section as the foundation this ADR extends; reference the OpenSpec change directory `openspec/changes/rag-reliability-correctness-fixes/`.
- [x] 6.5 Update `docs/adr/ADR_README.md` index table with the new ADR row (number, title, date, status `Accepted`).
- [ ] 6.6 Set the ADR's status to `Accepted` once the change is archived; if archived before the ADR is written, set status to `Proposed` and flip to `Accepted` after archive.

## 7. Validation

- [x] 7.1 Run `openspec validate rag-reliability-correctness-fixes --strict` and confirm it passes
- [x] 7.2 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm coverage thresholds remain intact
- [x] 7.3 Update `AGENTS.md` only if any non-obvious rule has changed (no rule changes expected for this tier)
- [x] 7.4 Confirm ADR-015 is published, indexed, and cross-referenced before archiving the OpenSpec change
