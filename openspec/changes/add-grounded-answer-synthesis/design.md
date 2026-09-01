# Design: add-grounded-answer-synthesis

## Context

Verified against `v3` at `c9d2906`.

- No synthesis exists: `as_query_engine`, `ResponseSynthesizer`,
  `RetrieverQueryEngine` appear nowhere in `src/`.
- `core/providers/llm/registry.py` already registers `ollama`, `llamacpp` and
  `openrouter`, each `build(settings, *, timeout) -> LLM`. Its only consumer
  today is `core/metadata/llamaindex.py`, which holds a **named exemption** in
  the `core-business-avoids-providers-transports` import-linter contract.
- That contract lists `rag_mcp.core.retrieval` in `source_modules` and
  `rag_mcp.core.providers` in `forbidden_modules`, with
  `unmatched_ignore_imports_alerting = "error"`. Any new core→providers import
  needs a new ignore entry.
- `search()` already accepts injected `reranker=`, `store=` and
  `effective_settings=`. `transports/mcp/__init__.py` holds
  `_get_reranker()` → `compose.build_reranker()`; the pattern for injecting a
  process-wide object into the MCP layer already exists.
- `get_response_synthesizer`, `ResponseMode`, `CitationQueryEngine`,
  `BaseRetriever` and `NodeWithScore` all import successfully under the
  project's pinned `llama-index-core 0.14.23`. Verified.
- The installed MCP SDK exposes `ServerSession.create_message` and
  `Context.session`, so client-side sampling is available without a new
  dependency.
- A retriever adapter over `search()` plus `CitationQueryEngine` was built and
  run during the audit; source nodes carried `chunk_id`, `source_id` and
  `source_chunk_index` through to the answer.

## Goals / Non-Goals

**Goals**

- Give the CLI, the future HTTP transport, and evaluation an answering path.
- Make citations verifiable by construction rather than by trusting the model.
- Add no dependency, no new architectural layer, and no import-contract
  exemption.
- Leave `search()` byte-identical in behaviour.

**Non-Goals**

- Making answering the default. `search_documents` remains the primary tool.
- Chat memory, agentic retrieval, streaming, tool-calling within the answer.
- Query transformation. Still deliberately absent.
- Replacing the client's own generation for MCP callers who prefer it.

## Decisions

### D1: The LLM is injected, so no import-contract change is needed

`answer()` takes `llm=` as a parameter. `compose.build_answer_llm()`
constructs it through the existing provider registry; `transports/mcp` and
`transports/cli` obtain it the way they already obtain the reranker.

This is the whole reason the change costs nothing architecturally. The
alternative — importing the provider registry from `core/answer/` — would need
a second named ignore in `core-business-avoids-providers-transports`, weakening
a contract that currently has exactly one, well-justified exemption.

Alternatives considered:

- *Follow the `metadata.llamaindex` precedent and add an ignore entry* — it
  works, and there is prior art, but the precedent exists because metadata
  extraction runs deep inside ingestion where injection was awkward. Answering
  is a top-level entry point, which is precisely where this project resolves
  dependencies. Using the exemption here would be copying the exception rather
  than the rule.
- *Put answering in `transports/`* — it would then be unavailable to the CLI
  and the HTTP transport without duplication, which is the problem being
  solved.

### D2: `core/answer/` is a new subpackage, not an addition to `core/retrieval/`

`core/retrieval/pipeline.py` is at 441 lines against the 500-line ceiling, and
answering is a different concern with a different dependency (a language
model). A sibling package keeps the "no cross-imports between ingestion and
retrieval" spirit: `core/answer/` depends on `core/retrieval` one way, and
`core/retrieval` never imports it.

### D3: Retrieval reuses `search()` through a thin `BaseRetriever` adapter

`core/answer/retriever.py` adapts `search()` to LlamaIndex's `BaseRetriever`,
converting result dicts into `NodeWithScore` with lineage preserved in node
metadata. Roughly 25 lines, proven working during the audit.

This is the "don't reinvent the wheel" seam: once `search()` looks like a
`BaseRetriever`, every LlamaIndex postprocessor and synthesiser composes with
it, and the project's own profile resolution, hybrid fusion, reranking and
context assembly all still run exactly as they do for a plain search.

### D4: `CompactAndRefine` is the response mode

`ResponseMode.COMPACT` packs retrieved chunks into as few LLM calls as the
context window allows and refines across them. It is the mode that degrades
most gracefully as `top_k` grows, and it does not require a hierarchy the
project does not have (`tree_summarize` builds one).

Alternatives considered:

- *`simple_summarize`* — one call, but truncates silently when the context
  overflows. Silent truncation is the failure mode this project consistently
  refuses elsewhere.
- *`tree_summarize`* — better for very large context, more calls, and its
  benefit appears at a `top_k` far above this project's defaults.

### D5: Citations are built from lineage, then intersected with the answer

The system numbers the supplied chunks, gives the model those numbers, and
returns the mapping. Model output is used only to know *which* supplied
sources it leaned on; it is never the origin of an identifier. A number the
model invents outside the supplied range is discarded rather than resolved.

Upstream's `CITATION_QA_TEMPLATE` is the starting point for the prompt: it
already instructs "answer based solely on the provided sources", "every answer
should include at least one source citation", and "if none of the sources are
helpful, you should indicate that". Adapting it costs nothing and it is
better-tested prose than a fresh attempt.

### D6: Client sampling is preferred, server-side model is the fallback

For MCP callers, `ctx.session.create_message()` asks the *client's* model. The
server keeps ownership of the prompt, the evidence and the citation mapping —
only the completion is delegated. This means a user with no local LLM
configured still gets grounded answers, on a model they already have, at no
server-side inference cost.

Preference order is explicit and reported in the result: client sampling when
advertised and enabled, else the configured server-side model, else an
actionable error naming both options. It never silently returns chunks
labelled as an answer.

The CLI and HTTP transports have no client model, so they always use the
server-side path. This is why D1's injection matters: one core operation, two
completion sources, no branching inside `core/`.

### D7: No-evidence short-circuits before the model call

If retrieval yields nothing, the operation returns a no-evidence result
without calling the model. This is both cheaper and safer: a model handed an
empty context is at its most likely to answer from parametric memory, which is
exactly the failure this capability exists to prevent.

## Risks

| Risk | Mitigation |
| --- | --- |
| Users assume answering replaces searching and pay for a model call per query | Answering is a separate tool whose description names the cost and points at `search_documents`; nothing changes the default |
| A weak local model produces poor answers and the retrieval work gets blamed | Retrieval and generation failures are separately attributed, retrieved chunks are always returned, and diagnostics time the two stages separately |
| Prompt injection from ingested document content | The prompt is constructed by the system with a fixed instruction block; retrieved text is presented as quoted sources. This does not eliminate the risk — it is inherent to RAG — and it is stated in the docs rather than claimed solved |
| Client sampling behaves differently across MCP clients | The result reports which completion source ran, so a behavioural difference is attributable rather than mysterious |
| The synthesis path drifts from `search()` behaviour over time | Answering has no retrieval code of its own; it calls `search()`. A drift would require someone to add a second retrieval path, which review should reject |
