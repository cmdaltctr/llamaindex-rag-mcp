# TDR-036: Ollama failures became an "Empty Response" answer, so carry seam errors past refine

- **Date:** 2026-10-18
- **Status:** Proposed
- **Deciders:** Aizat Hawari
- **Tags:** answer | ollama | llamaindex | error-handling

## Context

In `omrg web`, Chat with Ollama `qwen3:4b` gave one good answer. Every later question returned the text `Empty Response` in less than one second. The status was `generation_unverified`, `failure_stage` and `error` were `null`, and there were 0 citations. A fresh server with no saved settings did the same, so the provider-settings change did not cause it. A direct `POST /api/chat` worked when the server was not under memory pressure.

### Root Cause Analysis

Three faults stack up:

1. **Ollama fails with HTTP 200.** omrg passes no `context_window`, so LlamaIndex reads `qwen3.context_length` (262,144) from `/api/show` and sends it as `num_ctx`. After the first answer, the query embedding loads `qwen3-embedding`, and Ollama reloads `qwen3:4b` beside it at 262,144 tokens. `~/.ollama/logs/server.log` then shows `Insufficient Memory (kIOGPUCommandBufferCallbackErrorOutOfMemory)` and `decode: Compute error` on every chat, each in about 0.5 s. Ollama still answers `200` with `message.role == ""` and empty content.
2. **LlamaIndex rejects the reply.** `llama_index/llms/ollama/base.py` `achat` builds `ChatMessage(role="")`, which raises a pydantic `ValidationError`.
3. **LlamaIndex refine hides the error.** `llama_index/core/response_synthesizers/refine.py` catches `ValidationError`, `ValueError` and `TypeError` from every LLM call, logs "Structured response error", and returns the text `"Empty Response"`. omrg treated that text as a model answer with no citations, so the status became `generation_unverified`.

The first answer works because `qwen3:4b` had the GPU memory to itself at that moment.

## Decision

1. `SeamLLM.acomplete` (`core/answer/synthesis.py`) re-raises a seam `ValueError` or `TypeError` as `SeamCompletionError`, chained to the original. Refine does not catch that type.
2. `synthesise_answer` (`core/answer/stages.py`) unwraps `SeamCompletionError` and reports the provider's own error: `Generation failed: ValidationError: ...`.
3. `SeamLLM` records whether any reply carried text. `run_synthesis` returns `""` when none did, never refine's placeholder.
4. `synthesise_answer` turns empty text into a generation failure with `EMPTY_REPLY_ERROR`. The `grounded-answer-synthesis` spec allows `generation_unverified` only for a non-empty answer.
5. A reply that the client library cannot parse (a pydantic `ValidationError`, such as Ollama's empty `role`) gives the fixed `MALFORMED_REPLY_ERROR`. It says the model sent a malformed reply and may be out of memory. The pydantic field paths never reach the caller.

## Consequences

### Positive

- A failed model call is now `status="error"`, `failure_stage="generation"`, with evidence kept and a reason the user can act on.
- The fix covers all providers and client completions, not only Ollama.

### Negative

- The fixed malformed-reply message hides the parser detail. The full exception stays in the server log for diagnosis.
- The out-of-memory cause stays until the context-window option for Ollama lands.

### Neutral

- Existing answer results do not change. Only empty or rejected replies change status.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Check for the string `"Empty Response"` | A real answer can contain that text, and the provider's error would still be lost. |
| Patch LlamaIndex's Ollama class to default an empty role | It hides a failed generation as an empty answer. |
| Upgrade `llama-index-llms-ollama` 0.10.1 to 0.11.0 | Upstream `main` still uses `response["message"].get("role", ...)`, so an empty role still fails. It also needs approval. |

## How to Recognise / Handle This Again

1. Symptom: the answer text is `Empty Response`, or the error is `Generation failed: ValidationError: ... ChatMessage role`, returned in less than one second.
2. Search the omrg log for `Structured response error`.
3. Search `~/.ollama/logs/server.log` for `Insufficient Memory` or `Compute error`.
4. Run `ollama ps` and look at the context size of the loaded model.
5. Stop Ollama to unload the broken runner. Set a smaller context window, then ask again.

## Revisit Triggers

- LlamaIndex refine stops catching `ValueError` from LLM calls.
- `llama-index-llms-ollama` rejects an empty role itself.
- omrg passes a context window to Ollama.

## References

- `src/omrg/core/answer/synthesis.py` (`SeamCompletionError`, `SeamLLM`, `run_synthesis`)
- `src/omrg/core/answer/stages.py` (`synthesise_answer`, `EMPTY_REPLY_ERROR`, `MALFORMED_REPLY_ERROR`)
- `tests/unit/test_answer_empty_reply.py`
- `openspec/specs/grounded-answer-synthesis/spec.md` (result shape per status)
- llama-index-core 0.14.23, llama-index-llms-ollama 0.10.1, ollama-python 0.6.2, Ollama 0.40.6
