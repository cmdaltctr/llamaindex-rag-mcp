# Add grounded answer synthesis with deterministic citations

## Why

This server retrieves and stops. `search()` returns ranked chunks; no query
engine, no response synthesiser, no RAG prompt, no citation rendering exists
anywhere in `src/`. For the MCP transport that is correct and should stay
correct: the client on the other end of stdio already holds a language model,
already has the conversation, and can ask follow-up questions. A server that
generated its own answer would spend a model call to produce a worse,
context-free answer the client then has to read anyway.

But "the client does it" is only true for MCP. Three real consumers get
nothing:

- **The CLI.** `rag-mcp search` prints a table of chunks. There is no way to
  ask a question and get an answer, so the CLI cannot be used to check whether
  retrieval is actually good enough to answer with.
- **The planned HTTP transport.** `transports/api/openapi.yaml` is a
  contract-first document for an API with no answering endpoint. An HTTP
  caller is not an LLM client; it has no model to fall back on.
- **Evaluation.** Retrieval correctness and generation correctness are
  currently impossible to separate empirically, because there is no generation
  step to hold constant. Faithfulness, answer relevance and context recall
  cannot be measured at all.

There is also a grounding gap that only a synthesis step can close. The system
already produces everything a verifiable citation needs — `source`,
`source_id`, `chunk_id`, `source_version`, `source_chunk_index`, `score`,
`score_kind` — and a test already proves a `chunk_id` filter re-fetches
exactly the cited row. Nothing assembles those into an answer, so the
provenance work stops one step short of being usable.

Doing this changes no existing behaviour: `search()` is untouched, and the new
capability is additive.

## What Changes

- A new core operation, `answer()`, that retrieves through the existing
  `search()` path, synthesises a grounded answer, and returns the answer
  together with the exact chunks it was built from.
- Citations are constructed deterministically from retrieved chunk lineage, not
  parsed out of model output. A cited chunk is always re-fetchable by
  `chunk_id`.
- The prompt instructs the model to answer only from the supplied sources and
  to say so when the sources do not support an answer. Retrieval finding
  nothing produces an explicit "no supporting evidence" result, never an
  unsupported answer.
- Exposed as a new MCP tool and a new CLI command. The MCP tool is additive;
  clients that want raw chunks keep using `search_documents` unchanged.
- The LLM is injected by the composition root, exactly as the reranker and the
  vector store already are, using the provider registry that already serves
  metadata extraction. No new import edge, no new dependency, no new
  architectural layer.
- Where the MCP client advertises sampling capability, the tool SHALL be able
  to obtain the completion from the **client's** model rather than a
  server-side one, so a user with no local LLM configured still gets grounded
  answers on the model they already pay for.

Not in scope: multi-turn conversation or chat memory, agentic or multi-step
retrieval, query transformation, streaming responses, tool-calling inside the
answer, changing `search()` or any ranking behaviour.

## Capabilities

### New Capabilities

- `grounded-answer-synthesis`: the contract for turning retrieved chunks into
  an answer with verifiable citations, including the no-evidence case, the
  provider-absent case, and the separation of retrieval failure from
  generation failure.

### Modified Capabilities

None. `transport-separation`'s existing "Thin transports over a shared core"
requirement already governs how a new operation must be exposed; this change
conforms to it rather than altering it. The OpenAPI document gains an endpoint
under the existing versioned-contract requirement for the same reason.

## Impact

- **Purely additive.** No stored data changes, no re-ingest, no change to
  `search()` results, no change to any existing tool's shape.
- Cost and latency: this is the first query-time LLM call in the project.
  Today a query costs one embedding call plus a vector search; an answer adds
  one completion over the retrieved context. That must be stated plainly in
  the tool description and the docs so a caller chooses knowingly.
- Code: new `core/answer/`, `compose.build_answer_llm`, new
  `transports/mcp/answer.py`, new `transports/cli/answer.py`,
  `transports/api/openapi.yaml`.
- Configuration: a new settings block for the answer LLM and prompt limits.
  Every value defaults to something that works with the existing local-first
  provider configuration.
- Dependencies: none. `get_response_synthesizer`, `CitationQueryEngine` and
  `BaseRetriever` are already installed with `llama-index-core`, and the LLM
  provider registry already builds Ollama, llama.cpp and OpenRouter clients.
