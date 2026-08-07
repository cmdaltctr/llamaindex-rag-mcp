> **Note on ordering.** Groups 1–3 were implemented ahead of this proposal being written and are
> recorded here as completed for traceability, not because they were planned first. Group 4 closed the
> gap that made this worth proposing at all: the pre-existing tests mock at the response level and
> assert nothing about the request payload, so groups 1–3 were invisible to CI until group 4 landed.
> Remaining: 5.6 (PR + merge) and 5.7 (archive, which must wait until after merge).

## 1. Ollama backend enforcement

- [x] 1.1 Add `"format": "json"` to the `/api/generate` request payload in `core/metadata/ollama.py`
- [x] 1.2 Confirm `_strip_markdown_fence` and the unparseable-response fallback are left in place, with a
      comment recording why (servers that ignore or predate the field)

## 2. llama.cpp backend enforcement

- [x] 2.1 Add `"response_format": {"type": "json_object"}` to the `/v1/chat/completions` request payload
      in `core/metadata/llamacpp.py`
- [x] 2.2 Confirm the shared `_parse_ollama_json_response` path is unchanged

## 3. OpenRouter backend enforcement and downgrade

- [x] 3.1 Add `_CLASSIFY_JSON_SCHEMA` in `core/metadata/extractor.py` pinning `category` (string),
      `keywords` (array of string) and `summary` (string), all required, `additionalProperties: false`,
      `strict: true`
- [x] 3.2 Add `response_format: {type: "json_schema", json_schema: _CLASSIFY_JSON_SCHEMA}` and
      `provider: {require_parameters: true}` to the OpenRouter request payload
- [x] 3.3 Add `_UNSUPPORTED_PARAM_STATUSES = {400, 404, 422}` and `_is_unsupported_params_error()`,
      excluding 429 (transient) and 401/403 (auth)
- [x] 3.4 Add the one-shot downgrade branch to the retry loop: drop `response_format` + `provider`, log at
      INFO, `continue` without backoff
- [x] 3.5 Verify `extractor.py` stays under the 500-line ceiling (`tests/test_file_size_ceiling.py`)
- [x] 3.6 Run `uv run pytest -m "not slow"` and `uv run lint-imports` — 972 passed, 6/6 contracts kept

## 4. Test coverage for the new behaviour

- [x] 4.1 Add a payload-capturing httpx mock helper to `tests/test_metadata_extractor.py` that records the
      `json=` kwarg of each POST, so request bodies become assertable
- [x] 4.2 Assert the Ollama payload carries `format == "json"` alongside the prompt (spec: *Ollama request
      constrains output format*)
- [x] 4.3 Assert the llama.cpp payload carries `response_format == {"type": "json_object"}` (spec:
      *llama.cpp request constrains output format*)
- [x] 4.4 Assert the OpenRouter payload carries the JSON Schema with all three required fields and
      `provider.require_parameters is True` (spec: *OpenRouter request carries the classification schema*)
- [x] 4.5 Test the downgrade on HTTP 404: second request omits `response_format` and `provider`, and a
      successful retry returns real metadata rather than `uncategorised` (spec: *No schema-capable endpoint
      available*)
- [x] 4.6 Test the downgrade on HTTP 400 and 422 (spec: *Schema rejected as invalid by the upstream
      provider*)
- [x] 4.7 Test that HTTP 429 does **not** downgrade — schema still present on retry, and `_retry_sleep` is
      invoked (spec: *Rate limiting does not trigger downgrade*)
- [x] 4.8 Test that HTTP 401/403 do **not** downgrade (spec: *Authentication failure does not trigger
      downgrade*)
- [x] 4.9 Test that a second rejection after downgrading does not downgrade again and falls through to the
      `uncategorised` fallback with a WARNING (specs: *Downgrade is attempted at most once*, *Downgrade path
      exhausts the retry budget*)
- [x] 4.10 Regression-test that a fenced ```` ```json ```` response still parses under enforcement, so the
      retained fallback stays covered (spec: *Fence stripping still applies when enforcement is ignored*)
- [x] 4.11 Assert the returned dict still has exactly `category`, `keywords`, `summary` (spec: *Returned
      metadata shape is unchanged*)

## 5. Verification and close-out

- [x] 5.1 `uv run pytest -m "not slow" --cov=rag_mcp` — confirm `core/metadata` holds ≥95% and overall ≥90%
- [x] 5.2 `uv run lint-imports` — 6/6 contracts kept
- [x] 5.3 `openspec validate --all --strict`
- [x] 5.4 Decide whether this warrants an ADR or is a sub-decision of ADR-024's graceful-degradation
      contract; write it only if the OpenRouter downgrade policy is worth citing independently
      → TDR, not ADR: this is "how to make a specific technology behave correctly", not an
      architectural choice. Written as `docs/tdr/006-openrouter-structured-outputs-per-endpoint.md`.
      The Ollama/llama.cpp payload keys warrant no record — using a documented feature correctly is
      not a decision.
- [x] 5.5 Conventional Commits on branch `feat/structured-outputs-metadata-classification`
      → `e25338a` feat(metadata) (impl + tests + this change), `29ee8b0` docs (TDR-006)
- [ ] 5.6 Open the PR against `main` and merge when green
- [ ] 5.7 **After merge**, archive the change (`openspec archive`) so the spec deltas fold into
      `openspec/specs/metadata-extraction/spec.md`. Deliberately not done before merge: archiving
      rewrites the permanent spec, which must not claim behaviour that is not yet on `main`.
