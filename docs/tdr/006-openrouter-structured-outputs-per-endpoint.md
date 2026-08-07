# TDR-006: OpenRouter structured outputs are per-endpoint, so `require_parameters` needs a downgrade path

**Date:** 2026-08-07
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Tags:** openrouter | metadata | cloud | graceful-degradation

## Context

The three LLM metadata classification backends asked for JSON in the prompt only,
then cleaned up afterwards — `_strip_markdown_fence` exists because `qwen3:0.6b`
wraps its output in a ` ```json ` fence. All three backends support
constrained decoding at the serving layer, which we were not using.

Ollama (`format: "json"`) and llama.cpp (`response_format: {"type":
"json_object"}`) are safe to enable unconditionally: an unsupported field is
ignored and the request still succeeds.

OpenRouter is not. Enabling it there the same way risks turning an occasional
parsing nuisance into total classification failure for some models.

### Root Cause Analysis

Two properties of OpenRouter, both documented, combine badly:

1. **Support is per serving _endpoint_, not per model.** The same model offered
   by two upstream providers may support `response_format` on only one of them.
   The OpenRouter docs state: _"Support is determined per endpoint, not just per
   model … Endpoint support can also change over time."_
2. **An unsupported request fails.** It does not silently ignore the parameter:
   _"Model doesn't support structured outputs: The request will fail with an
   error indicating lack of support."_

So sending a schema without `provider: {require_parameters: true}` produces
_nondeterministic_ failures — the request succeeds or 4xxs depending on which
endpoint the router happened to pick that call. Adding `require_parameters`
makes it deterministic but can leave nothing routable, which fails every time.

Either way, a failed classification returns the `uncategorised` fallback, so the
symptom is silent quality loss rather than a crash.

## Decision

Pair `require_parameters` with a one-shot downgrade inside the existing retry
loop, in `src/rag_mcp/core/metadata/extractor.py`.

Send the full schema on the first attempt:

```python
"response_format": {"type": "json_schema", "json_schema": _CLASSIFY_JSON_SCHEMA},
"provider": {"require_parameters": True},
```

On a hard 4xx, strip both keys and retry immediately — no backoff, because a
rejected payload is not a transient fault:

```python
_UNSUPPORTED_PARAM_STATUSES = frozenset({400, 404, 422})

if _is_unsupported_params_error(exc) and "response_format" in data:
    data.pop("response_format", None)
    data.pop("provider", None)
    continue
```

The status list is deliberately narrow:

| Status        | Downgrade? | Why                                                                                                                      |
| ------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------ |
| 400, 404, 422 | yes        | Parameter/routing fault — the identical payload can never succeed                                                        |
| 429           | **no**     | Rate limiting is transient; belongs on the existing exponential backoff                                                  |
| 401, 403      | **no**     | Auth failure is not fixed by a smaller payload, and downgrading would make the eventual WARNING point at the wrong cause |

`_strip_markdown_fence` and the unparseable-response fallback are **retained**
on all three backends. Enforcement lowers their hit rate; it does not make them
dead code.

## Consequences

### Positive

- Fewer documents fall back to `uncategorised`, so category filtering covers more
  of the corpus.
- Worst case for a model with no schema-capable endpoint is one wasted request
  per document, then exactly the pre-change behaviour. Honours ADR-024's rule
  that cloud features degrade gracefully.
- Failure mode is deterministic and logged at INFO, rather than depending on
  which endpoint the router picked.

### Negative

- `require_parameters` narrows routing, which may exclude cheaper or faster
  endpoints for the same model.
- The downgrade consumes one attempt from the retry budget rather than exceeding
  it. At a budget of one no downgraded request is sent, so a schema-incapable
  model degrades to `uncategorised` — no worse than before this change, but no
  better either. This is deliberate: a budget of one is an operator instruction
  to issue exactly one request per classification, and the downgrade does not
  override it. Default is 3. The budget is
  `METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS`, which despite the name governs all
  three backends — llama.cpp and OpenRouter both call
  `_get_ollama_max_attempts`.

  > **Update (rename-classify-settings, 2026-08-07):** this knob is now
  > `METADATA__CLASSIFY_MAX_ATTEMPTS` and the helper is
  > `_get_classify_max_attempts` in `_common.py`. The misleading `ollama_`
  > scope this passage flags has been retired.
- One extra round trip on the first classification against a schema-incapable
  model, repeated per document (the downgrade is not cached across calls).

### Neutral

- No new dependency, no new setting, no change to the returned metadata shape.
- Only the `local`-mode hand-built payloads are affected. The `llamaindex`
  extraction mode goes through LlamaIndex LLM objects and is untouched.

## Alternatives Considered

| Option                                                  | Rejected Because                                                                                                                                                                                                                                         |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Schema without `require_parameters`                     | Same hard failure, but nondeterministic — depends on which endpoint the router picks per call. Strictly harder to diagnose.                                                                                                                              |
| `require_parameters` with no downgrade                  | A model with zero schema-capable endpoints returns `uncategorised` for every document, silently. Violates ADR-024.                                                                                                                                       |
| Capability probe at startup                             | Extra network call in the composition root, cached state to invalidate, and it goes stale mid-run since endpoint support changes over time.                                                                                                              |
| Config flag listing known-good models                   | Pushes an OpenRouter routing detail onto the operator and goes stale silently.                                                                                                                                                                           |
| `json_object` instead of `json_schema`                  | Under-specified on OpenRouter, and `require_parameters` gating is documented against `json_schema`.                                                                                                                                                      |
| Add LiteLLM to unify `response_format` across providers | Introduces a third provider abstraction (the registries and LlamaIndex already exist), a large dependency tree, and module-level global config that conflicts with the injected-settings invariant. The feature it offers is one dict key away natively. |

## How to Recognise / Handle This Again

**Symptom:** documents classified as `uncategorised` at a much higher rate than
usual when `METADATA_LLM_PROVIDER=cloud` / `CLOUD_BACKEND=openrouter`, with no
obvious network fault.

1. **Check for the downgrade log line.** It is INFO, not WARNING:

   ```text
   OpenRouter rejected structured outputs for model <model> (HTTP 4xx) —
   retrying without response_format.
   ```

   If present on every document, the configured model has no schema-capable
   endpoint. Classification still works, but each document costs an extra
   request.

2. **Confirm endpoint support** on the model's page under Providers, checking
   the `structured_outputs` parameter — or filter the model list:
   https://openrouter.ai/models?order=newest&supported_parameters=structured_outputs

3. **If classification fails entirely**, check whether the status is 401/403
   (credentials — the downgrade deliberately does not fire) or 429 (rate limit —
   backoff path, schema retained). The final WARNING names the exception type
   and status.

4. **To rule structured outputs out as the cause**, set
   `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=ollama` and re-ingest one
   file. The local path uses plain `format: "json"` and cannot hit this class of
   failure.

## Revisit Triggers

- OpenRouter changes structured-output support from per-endpoint to per-model, or
  starts ignoring rather than rejecting unsupported `response_format`.
- The Response Healing plugin becomes usable for `json_schema` requests and makes
  the downgrade redundant.
- Ollama's minimum supported version rises far enough to justify sending a full
  `format: <schema>` on the local path too, unifying the three backends.
- The three near-identical retry loops in `ollama.py`, `llamacpp.py` and
  `extractor.py` are consolidated — the downgrade branch must survive that
  refactor.

## References

- OpenRouter structured outputs: https://openrouter.ai/docs/features/structured-outputs
- OpenRouter provider routing (`require_parameters`):
  https://openrouter.ai/docs/guides/routing/provider-selection#requiring-providers-to-support-all-parameters
- ADR-024 — cloud dependencies degrade gracefully to local
- OpenSpec change: `openspec/changes/structured-outputs-metadata-classification/`
  (proposal, spec deltas, design rationale)
- Implementation: `src/rag_mcp/core/metadata/extractor.py`
  (`_CLASSIFY_JSON_SCHEMA`, `_UNSUPPORTED_PARAM_STATUSES`,
  `_is_unsupported_params_error`)
- Local backends: `src/rag_mcp/core/metadata/ollama.py`,
  `src/rag_mcp/core/metadata/llamacpp.py`
- Tests: `tests/test_metadata_extractor.py`
  (`TestStructuredOutputEnforcement`, `TestOpenRouterStructuredOutputDowngrade`)
