# TDR-037: OpenRouter answers used the legacy completions endpoint, so reasoning leaked into the answer

- **Date:** 2026-10-23
- **Status:** Accepted
- **Deciders:** Aizat Hawari
- **Tags:** providers | openrouter | answer | reasoning

## Context

A Chat answer on the `documents` collection was 14,105 characters long. It held three parts: a draft with no citations, the model's own review of that draft ("Okay, let's evaluate the user's request… Analyze the `good_attempt`"), and a final cited answer. The diagnostics showed one completion call of 31 s. OMRS code never writes the words "good_attempt", so the model wrote all three parts in one reply.

The Chat model was `z-ai/glm-5.3-flash` on OpenRouter. The OpenRouter catalogue marks its reasoning as mandatory, with `max` as the default effort.

### Root Cause Analysis

`core/providers/llm/openrouter.py` built `OpenAILike(...)` without `is_chat_model`. The library default is `False`. With `False`, `acomplete()` calls the legacy `/completions` endpoint with the raw prompt. That endpoint has no separate reasoning field, so the model's reasoning goes into the answer text. The OpenAI-compatible provider already set `is_chat_model=True`.

## Decision

Set `is_chat_model=True` in the OpenRouter `build()`. `acomplete()` then goes through `/chat/completions`, and OpenRouter returns reasoning in its own `reasoning` field, apart from `content`.

`tests/unit/test_openrouter_chat_endpoint.py` pins the flag and checks that `acomplete()` calls the chat path, never the completions path. Both tests failed before the change.

## Consequences

### Positive

- Answers hold only the answer text. Reasoning no longer goes into the saved turn or the citation check.
- OpenRouter now behaves the same as the OpenAI-compatible provider.

### Negative

- OMRS still drops the reasoning text and sends no reasoning effort. Mandatory-reasoning models still run at their default effort, so answers stay slow. The change `add-chat-reasoning-and-usage` covers this.

### Neutral

- Metadata classification through OpenRouter uses the same `build()` and now also uses the chat endpoint.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Strip `<think>` blocks or "reasoning-like" text from the reply | The leaked text has no fixed markers. A text filter would guess and could cut real answer text. |
| Tell users to pick the OpenAI-compatible provider with the OpenRouter address | A workaround. The OpenRouter provider would stay broken for everyone else. |

## How to Recognise / Handle This Again

1. Symptom: an answer holds a draft, then text that reviews the draft, then a second answer.
2. Look at `diagnostics.completion_calls` in the saved turn. A value of 1 means the model wrote all of it in one reply.
3. Check that the provider `build()` sets `is_chat_model=True` on any `OpenAILike` instance.

## Revisit Triggers

- `llama-index-llms-openai-like` changes the default of `is_chat_model`.
- OpenRouter retires the legacy `/completions` endpoint.

## References

- `src/omrs/core/providers/llm/openrouter.py`
- `src/omrs/core/providers/llm/openai_compatible.py`
- `tests/unit/test_openrouter_chat_endpoint.py`
- OpenSpec change `add-chat-reasoning-and-usage`
