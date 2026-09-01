# Tasks: add-grounded-answer-synthesis

Purely additive. Nothing here changes `search()`, stored data, or any existing
tool's shape. Land after the two fix changes so answers are built on corrected
embeddings and assembled context.

## 1. Red-first coverage

- [ ] 1.1 Add a test asserting `search()` makes no language-model call. Confirm
  it PASSES today and keep it as a regression guard.
- [ ] 1.2 Add a test asserting that answering an empty collection returns a
  no-evidence result and makes no model call. Confirm it FAILS today
  (operation does not exist).
- [ ] 1.3 Add a test asserting every `chunk_id` in a returned citation list
  re-fetches exactly one stored chunk by metadata filter.
- [ ] 1.4 Add a test asserting a model failure after successful retrieval is
  attributed to generation and still returns the retrieved chunks.

## 2. Core operation

- [ ] 2.1 Create `core/answer/` with `__init__.py` exporting `answer`, lazily
  imported per the established PEP 562 registry pattern.
- [ ] 2.2 Add `core/answer/retriever.py`: a `BaseRetriever` adapter over
  `search()` that preserves `chunk_id`, `source_id`, `source_version`,
  `source`, `source_chunk_index` and score in node metadata.
- [ ] 2.3 Add `core/answer/prompt.py` holding the grounded-answer instruction
  block, adapted from upstream's `CITATION_QA_TEMPLATE`. British English.
- [ ] 2.4 Add `core/answer/pipeline.py` with
  `answer(query, *, llm, collection_name, effective_settings, store, ...)`
  using `get_response_synthesizer(response_mode=COMPACT)`.
- [ ] 2.5 Short-circuit before any model call when retrieval returns nothing.
- [ ] 2.6 Build the citation mapping from supplied chunks; discard any source
  number the model emits outside the supplied range.
- [ ] 2.7 Report every constituent `chunk_id` when context assembly merged
  rows.
- [ ] 2.8 Attribute failures to `retrieval` or `generation`; always return the
  retrieved chunks on a generation failure.
- [ ] 2.9 Confirm no file exceeds the 500-line ceiling.

## 3. Composition root

- [ ] 3.1 Add `compose.build_answer_llm(settings)` resolving through
  `core/providers/llm/registry.py`.
- [ ] 3.2 Return `None` (not an exception) when no answer provider is
  configured, so the caller can produce the actionable error.
- [ ] 3.3 Add an answer settings block: provider selection, model, timeout,
  and the client-sampling preference flag. Every value defaults to something
  that works with the existing local-first configuration.
- [ ] 3.4 Validate the configured answer provider at startup through
  `_resolve_active_strategies`, failing fast on a bad name.
- [ ] 3.5 Confirm `uv run lint-imports` passes with **no new ignore entry**.
  If one is needed, D1 has been violated — fix the injection instead.

## 4. MCP transport

- [ ] 4.1 Add `transports/mcp/answer.py` with the new tool, `ToolAnnotations`
  `read_only_hint=True`, `destructive_hint=False`.
- [ ] 4.2 Description states plainly that the tool performs a language-model
  call and names `search_documents` as the cheaper alternative.
- [ ] 4.3 Never raise: return `{"status": "error", ...}` per gotcha #1.
- [ ] 4.4 Detect client sampling capability; when advertised and enabled,
  obtain the completion via `ctx.session.create_message()`.
- [ ] 4.5 Fall back to the injected server-side model; report which ran.
- [ ] 4.6 Return an actionable error naming both options when neither is
  available.
- [ ] 4.7 Register the handler in the package's bottom import block.

## 5. CLI transport

- [ ] 5.1 Add `transports/cli/answer.py` with `rag-mcp answer "<question>"`,
  supporting `--collection`, `--top-k`, `--hybrid/--no-hybrid`,
  `--rerank/--no-rerank`, `--diagnostics`, `--json`.
- [ ] 5.2 Print the answer, then the numbered sources with file, chunk id and
  score. Output to stderr per gotcha #5; `--json` to stdout.
- [ ] 5.3 Actionable message when no answer provider is configured.

## 6. Contract

- [ ] 6.1 Add the answering endpoint and its response schema to
  `transports/api/openapi.yaml`, including the citation list and the
  no-evidence shape.
- [ ] 6.2 Extend the OpenAPI conformance test to cover it.

## 7. Evaluation hook

- [ ] 7.1 Add a slow-marked test that answers a golden query over the existing
  quality corpus and asserts the cited chunk is the expected source.
- [ ] 7.2 Do NOT add faithfulness or answer-relevance scoring in this change —
  record it as the follow-up experiment now that a generation step exists to
  measure.

## 8. Validation and documentation

- [ ] 8.1 `uv run pytest -m "not slow" --cov=rag_mcp` — green, floors held.
- [ ] 8.2 `uv run lint-imports` — clean, no new ignores.
- [ ] 8.3 `openspec validate add-grounded-answer-synthesis --strict`.
- [ ] 8.4 Document the tool in `docs/guides/mcp-tools.md`, including the cost
  statement and the prompt-injection caveat.
- [ ] 8.5 Document the CLI command in `docs/guides/cli-reference.md`.
- [ ] 8.6 Write ADR: "Answering is additive and injected" recording D1, D3, D6
  and D7, and stating explicitly that MCP clients generating their own answers
  remains a supported and preferred mode.
