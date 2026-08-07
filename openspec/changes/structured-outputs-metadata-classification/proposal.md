## Why

The three LLM metadata classification backends ask for JSON **in the prompt only** and then clean up
afterwards. `_strip_markdown_fence` exists because `qwen3:0.6b` wraps its output in a ```` ```json ````
fence, and `_parse_ollama_json_response` falls back to treating the whole raw response as a category
label when parsing fails. That fallback path silently degrades a document to `uncategorised`, which
pollutes the hybrid category taxonomy that every subsequent classification prompt is built from — one
unparseable response makes the next prompt slightly worse.

Every backend we target already supports constrained decoding at the serving layer, where the model is
prevented from emitting invalid JSON rather than asked not to. We were not using it on any of them.

## What Changes

- **Ollama backend** (`core/metadata/ollama.py`): send `"format": "json"` on `/api/generate`.
- **llama.cpp backend** (`core/metadata/llamacpp.py`): send `"response_format": {"type": "json_object"}`
  on `/v1/chat/completions`; llama-server compiles this into a GBNF grammar.
- **OpenRouter backend** (`core/metadata/extractor.py`): send a full
  `response_format: {type: "json_schema", ...}` pinning the three-key classification shape, plus
  `provider: {require_parameters: true}` so the request is not routed to an endpoint that would ignore
  the schema.
- **New graceful downgrade for OpenRouter**: structured-output support there is per-*endpoint*, not
  per-model, and an unsupported request **fails** rather than degrading. On HTTP 400/404/422 the
  backend now drops `response_format` + `provider` once and retries on the prompt-only path, so a model
  with no schema-capable endpoint keeps working instead of returning `uncategorised` forever.
- **Existing fence-stripping and JSON fallback are retained**, not replaced — an older Ollama, a
  server that ignores the field, or a downgraded OpenRouter request all still land on that path.

Not breaking. No new dependencies, no new settings, no change to the returned metadata shape.

## Capabilities

### New Capabilities

None. This constrains *how* an existing behaviour is produced; it introduces no new capability.

### Modified Capabilities

- `metadata-extraction`: adds a requirement that LLM classification backends enforce JSON at the
  serving layer rather than relying on prompt instruction alone, and that enforcement degrades
  gracefully when a backend rejects it.

## Impact

**Code**
- `src/rag_mcp/core/metadata/ollama.py` — request payload.
- `src/rag_mcp/core/metadata/llamacpp.py` — request payload.
- `src/rag_mcp/core/metadata/extractor.py` — request payload, `_CLASSIFY_JSON_SCHEMA`,
  `_UNSUPPORTED_PARAM_STATUSES`, `_is_unsupported_params_error`, downgrade branch in the retry loop.

**Tests**
- `tests/test_metadata_extractor.py` — currently mocks at the response level and asserts nothing about
  the request payload, so all three changes pass unobserved. The OpenRouter downgrade is new *logic*
  and is entirely uncovered. Closing that gap is the substantive remaining work.

**Not affected**
- Dependencies: none added.
- Settings/env: none added. `.env.example` unchanged.
- Public API, MCP tool contracts, retrieval, ingestion, chunking: unchanged.
- Coverage tiers: `core/metadata` stays in the ≥95% tier and must not regress.

**External contracts relied upon**
- Ollama `/api/generate` `format` field.
- llama.cpp server OpenAI-compatible `response_format`.
- OpenRouter structured outputs + provider routing (`require_parameters`) —
  https://openrouter.ai/docs/features/structured-outputs
