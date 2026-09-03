# Tasks: add-grounded-answer-synthesis-3

Purely additive. Nothing here changes `search()`, stored data, or any existing
tool's shape. Land after the two fix changes so answers are built on corrected
embeddings and assembled context.

## 1. Red-first coverage

- [x] 1.1 Add a test asserting `search()` makes no language-model call. Confirm
  it PASSES today and keep it as a regression guard.
- [x] 1.2 Add a test asserting that answering an empty collection returns a
  no-evidence result and makes no model call. Confirm it FAILS today
  (operation does not exist).
- [x] 1.3 Add a test asserting every `chunk_id` in a returned citation list
  re-fetches exactly one stored chunk by metadata filter.
- [x] 1.4 Add tests for generation failure and for missing, malformed,
  duplicate and out-of-range citations; successful retrieval evidence must be
  retained and a substantive uncited answer must not be labelled grounded.
- [x] 1.5 Add protocol-era tests for modern MRTR, negotiated legacy sampling,
  server fallback and neither available; add retrieval-failure, merged
  constituent and diagnostics tests.

## 2. Core operation

- [x] 2.1 Create `core/answer/` with `__init__.py` exporting `answer`, lazily
  imported per the established PEP 562 registry pattern.
- [x] 2.2 Add `core/answer/retriever.py`: a `BaseRetriever` adapter over
  `search()` that preserves `chunk_id`, `source_id`, `source_version`,
  `source`, `source_chunk_index` and score in node metadata.
- [x] 2.3 Add `core/answer/prompt.py` holding the grounded-answer instruction
  block, adapted from upstream's `CITATION_QA_TEMPLATE`. British English.
- [x] 2.4 Add an async `core/answer/pipeline.py` with an injected async
  completion/LLM seam, using
  `get_response_synthesizer(response_mode=COMPACT, use_async=True)` and
  `asynthesize()`. Bound refinement rounds and report their count.
- [x] 2.5 Short-circuit before any model call when retrieval returns nothing.
- [x] 2.6 Build the citation mapping from supplied chunks; discard malformed,
  duplicate and out-of-range source numbers. A substantive answer with no
  valid supplied citation returns generation-unverified/error, never a
  grounded success.
- [x] 2.7 Report every constituent `chunk_id` when context assembly merged
  rows.
- [x] 2.8 Attribute failures to `retrieval` or `generation`; always return the
  retrieved chunks on a generation failure.
- [x] 2.9 Produce retrieval/generation timings in core and confirm no file
  exceeds the 500-line ceiling; split cohesive helpers before editing the
  already-hot `compose.py` and `config/__init__.py`.

## 3. Composition root

- [x] 3.1 Add `compose.build_answer_llm(settings)` resolving through
  `core/providers/llm/registry.py`; extend every registered builder with a
  backwards-compatible answer-model override so it does not reuse a metadata
  classifier model accidentally.
- [x] 3.2 Return `None` (not an exception) when answering is disabled or no
  usable provider/model is configured, and resolve it lazily so retrieval-only
  startup remains usable.
- [x] 3.3 Add an answer settings block: provider selection, model, timeout,
  and the client-sampling preference flag. Every value defaults to something
  that works with the existing local-first configuration.
- [x] 3.4 Validate the configured answer provider at startup through
  `_resolve_active_strategies`, failing fast on a bad name.
- [x] 3.5 Add `rag_mcp.core.answer` to
  `core-business-avoids-providers-transports.source_modules`, then confirm
  `uv run lint-imports` passes with **no new ignore entry**. If an ignore is
  needed, D1 has been violated — fix the injection instead.

## 4. MCP transport

- [x] 4.1 Add `transports/mcp/answer.py` with the new tool, `ToolAnnotations`
  `read_only_hint=True`, `destructive_hint=False`.
- [x] 4.2 Description states plainly that the tool performs a language-model
  call and names `search_documents` as the cheaper alternative.
- [x] 4.3 Never raise: return `{"status": "error", ...}` per gotcha #1.
- [x] 4.4 Implement the modern MCP path with a `Sample` resolver or
  `InputRequiredResult` MRTR, adapting the resolved response to the injected
  async completion seam. Bound and test COMPACT refinement rounds.
- [x] 4.5 Keep `ctx.session.create_message()` only for a negotiated legacy
  session; prove a modern session never calls it. Fall back lazily to the
  injected server-side model and report which path ran.
- [x] 4.6 Return an actionable error naming both options when neither is
  available; surface retrieval/generation timings and completion count when
  diagnostics are requested.
- [x] 4.7 Register the handler in the package's bottom import block.

## 5. CLI transport

- [x] 5.1 Add `transports/cli/answer.py` with `rag-mcp answer "<question>"`,
  supporting `--collection`, `--top-k`, `--hybrid/--no-hybrid`,
  `--rerank/--no-rerank`, `--diagnostics`, `--json`.
- [x] 5.2 Print the answer, then numbered sources with file, chunk id and
  score. Keep both human and `--json` output on stderr per gotcha #5.
- [x] 5.3 Actionable message when no answer provider is configured.

## 6. Contract

- [x] 6.1 Add the answering endpoint and its response schema to
  `transports/api/openapi.yaml`, including the citation list and the
  no-evidence shape.
- [x] 6.2 Extend the OpenAPI conformance test to cover it.

## 7. Evaluation hook

- [x] 7.1 Add a slow-marked test that answers a golden query over the existing
  quality corpus and asserts the cited chunk is the expected source.
- [x] 7.2 Do NOT add faithfulness or answer-relevance scoring in this change —
  record it as the follow-up experiment now that a generation step exists to
  measure.

## 8. Validation and documentation

- [x] 8.1 `uv run pytest -m "not slow" --cov=rag_mcp` — green, floors held.
- [x] 8.2 `uv run lint-imports` — clean, no new ignores.
- [x] 8.3 `openspec validate add-grounded-answer-synthesis-3 --strict`.
- [x] 8.4 Document the tool in `docs/guides/mcp-tools.md`, including the cost
  statement and the prompt-injection caveat.
- [x] 8.5 Document the CLI command in `docs/guides/cli-reference.md`.
- [x] 8.6 Write ADR: "Answering is additive and injected" recording D1, D3, D6
  and D7, and stating explicitly that MCP clients generating their own answers
  remains a supported and preferred mode.

## 9. Second review round remediation (2026-09-02)

A second review round returned BLOCKED (1 CRITICAL, 7 HIGH, 6 MEDIUM). The
completed boxes above were checked prematurely in two cases (5.2's stderr rule
was violated by the `--json` path; 4.3's never-raise rule was violated by the
resolver chain; 8.1-8.3 failed ruff at review time). All findings were
remediated and every gate re-verified:

- [x] 9.1 Filter construction hardened fail-closed (engine literal verification
  with round-trip re-decode, structural bounds, 48-test adversarial suite);
  verdict and residual policy decision recorded in `security-review.md`.
- [x] 9.2 MRTR evidence cache re-keyed to a stable per-connection identity;
  one retrieval per answer, evicted by the tool body.
- [x] 9.3 Resolver and sampling failures return the structured error contract
  with `failure_stage`; `ANSWER__ENABLED` gates modern, legacy, and server
  completion paths before any model call.
- [x] 9.4 Client rounds capped at the four-resolver chain (`max_rounds`
  bounded 1..8); seam exhaustion is a structured generation failure.
- [x] 9.5 Optional-provider `ModuleNotFoundError` degrades to `None`;
  credential `ImportError` stays loud.
- [x] 9.6 Hard input limits at the core entry (query ≤ 4096 chars, `top_k`
  1..100, `expand_window` 0..10, finite `similarity_threshold` 0..1),
  synthesis prompt ceiling 262,144 chars with truncation notice, filter
  bounds, and OpenAPI constraints pinned to the core constants.
- [x] 9.7 CLI `--json` (success and failure) on stderr with one result schema
  and stdout asserted empty; `--hybrid` tri-state defers to the profile;
  empty collections short-circuit to `no_evidence`.
- [x] 9.8 Retrieval off the event loop; diagnostics report real retrieval,
  sampling, and completion counts; oversized citation ordinals rejected with
  evidence retained; OpenAPI `failure_stage` accepts JSON null.
- [x] 9.9 Gates re-verified: `ruff check` and `ruff format` clean;
  `lint-imports` 8 kept / 0 broken with no new ignores; file-size ceiling
  green; `openspec validate --all --strict` 50/50; fast suite green
  (2368 passed, base manifest re-baselined at 2364) with 90% branch
  coverage; documentation drift corrected (`mcp-tools.md`,
  `configuration.md`, `cli-reference.md`, `.env.example`).
