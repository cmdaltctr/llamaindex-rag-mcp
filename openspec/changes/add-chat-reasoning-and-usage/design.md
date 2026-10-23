# Design

## Context

- TDR-037 (commit `d732d90`) moved OpenRouter answers to `/chat/completions`. The reply now keeps reasoning in `choices[0].message.reasoning`, apart from `content`. OMRS still reads only `content`.
- A live call on 2026-10-23 (`z-ai/glm-5.3-flash`, `reasoning: {effort: "low"}`) returned `usage` with `prompt_tokens`, `completion_tokens`, `completion_tokens_details.reasoning_tokens` and `cost` (US dollars). `GET /api/v1/key` returned `limit` 10 and `limit_remaining` 2.81. `GET /api/v1/models` gives each model a `reasoning` object with `supported_efforts`, `default_effort` and `mandatory`.
- The core seam contract is "prompt in, whole reply text out" (`grounded-answer-synthesis`: the model call stays whole-reply). `engine_answer.server_seam()` is the only place that sees the raw provider reply.
- Each Chat provider is one module under `core/providers/llm/` with `build()` and a `CONNECTION` descriptor, registered with one line. Dispatch must not branch on provider names (root invariant 11).
- Chat turns are saved as the whole answer result in `chat_turns.answer_json`, so a new result field is saved with no schema migration.

## Goals / Non-Goals

**Goals:**

- One reasoning level per role (answer, judge), saved in `omrs.jsonc`, sent by each provider in its own request field.
- Reasoning text and usage figures carried from the raw reply to the answer result with no change to the core seam contract.
- A level list for OpenRouter models from the public catalogue, and a text box for every other provider.

**Non-Goals:**

- Streaming the reasoning while the model thinks. The seam stays whole-reply.
- Reasoning for Anthropic (it needs a token budget, not a level) and llama.cpp (no stable request field). Both accept the saved level and report "ignored".
- Cost figures for providers that do not report cost. OMRS keeps no price table.
- A reasoning level per collection profile. The level is a server setting, like the Chat model.

## Decisions

### D1. A per-answer ledger beside the seam, not a richer seam

`server_seam(llm, ledger)` keeps returning `str`. After each `acomplete()` it passes `completion.raw` to the provider's reply reader and appends the result (reasoning text, usage) to a `CompletionLedger` owned by the request. The engine attaches the ledger totals to the result after synthesis. The judge seam writes to the same ledger.

- Why: the whole-reply requirement and every synthesis test stay unchanged. Refine rounds and the round bound need no change.
- Rejected: change the seam to return `(text, facts)`. It touches `synthesis.py`, `stages.py`, `graph_adapters.py`, the CLI and the MCP client seam, all for data that core never reads.

### D2. Each provider reads its own reply and maps its own level

Each provider module gains two functions, registered next to `build()`:

- `reasoning_kwargs(level) -> dict | None`: request fields for a level, or `None` when the provider ignores levels. OpenRouter: `{"extra_body": {"reasoning": {"effort": level}}}`. OpenAI-compatible: `{"reasoning_effort": level}`. Ollama: `{"think": False}` for `none`, `{"think": level}` for `low`, `medium` and `high`, else `{"think": True}`. llama.cpp and Anthropic: `None`.
- `read_reply(raw) -> ReplyFacts`: reasoning text and usage from the raw reply. The OpenAI-shaped reader (OpenRouter, OpenAI-compatible, llama.cpp) reads `message.reasoning` or `message.reasoning_content` and the `usage` block, including `cost` when present. The Ollama reader reads `message.thinking`, `prompt_eval_count` and `eval_count`. Anthropic reads `thinking` blocks and `usage.input_tokens` and `usage.output_tokens`.

`build()` takes `reasoning: str = ""` and passes `reasoning_kwargs(level)` as `additional_kwargs`. An empty level adds nothing. The registry dispatches by name, with no `if/elif`.

- Rejected: strip reasoning out of the answer text with a pattern. TDR-037 shows the leaked text has no fixed markers.

### D3. Result shape

- `reasoning`: string, present only when at least one call returned reasoning. Several calls are joined in call order with a blank line. The stored text is capped at 64 KB with a truncation marker, so one runaway reply cannot bloat `workspace.db`.
- `usage`: `{input_tokens, output_tokens, reasoning_tokens, cost_usd, calls}`. A figure is `null` unless every call reported it, so a partial sum is never shown as the total. Present whenever the server's own model answered. Client-sampled answers carry none, because the client's model is invisible to OMRS.
- MCP: `answer_documents` gets an `include_reasoning` flag (default false) so agents do not pay tokens for reasoning they did not ask for. `usage` is always included.

### D4. Settings

`AnswerSettings` gains `reasoning: str = ""` and `verify_reasoning: str = ""`, both checked against `^[A-Za-z0-9_-]{1,32}$` or empty. They are new allowed keys for the Settings page write, and are locked by `ANSWER__REASONING` and `ANSWER__VERIFY_REASONING`, like the model fields. `omrs config init` picks them up from the model.

### D5. Catalogue and credit routes

- `GET /v1/settings/chat/reasoning-levels`: the provider descriptor gains an optional `reasoning_levels(model)` hook. OpenRouter fetches `GET /api/v1/models` with no key, keeps the parsed map in process memory for 10 minutes, and returns the entry. Other providers return `{"known": false}` with no request. A fetch failure also returns `{"known": false}`, so the page falls back to the text box.
- `GET /v1/usage/credit`: descriptor hook `credit(settings)`. OpenRouter calls `GET /api/v1/key` with the key and returns `limit` and `limit_remaining`. No cache, because the web calls it once per finished answer. The key never leaves the server, and errors return `{"available": false}`.

### D6. Web

- Settings: `ChatModelForm` gains the Reasoning control, fed by a React Query call keyed on provider and model. The fix lines reuse the reasons the form already computes (`notReady`) and add the install command from the descriptor's `requires_extra`.
- Chat: `AssistantTurn` renders the reasoning box with the same disclosure pattern as the folder chevrons (button with `aria-expanded`), text class `text-meta text-muted-foreground`. `Composer` gets a right-aligned usage line in the same text class above the input row. It reads the latest turn's `usage` and the credit query, which is invalidated when an answer finishes.

### D7. Records

ADR-093 records D1 to D3 (ledger beside the seam, per-provider reply readers, result shape). TDR-037 already records the endpoint bug.

## Risks / Trade-offs

- [OpenRouter changes the `reasoning` or `usage` field names] → The readers return `null` figures and no reasoning instead of failing. A unit test pins the live shape recorded on 2026-10-23.
- [A model ignores the level] → The answer still works. The user sees the level was sent but timing does not change. The design adds no check.
- [The reasoning text can contain material from the evidence] → It is stored in the same workspace file as the evidence already is. No new exposure.
- [The credit route sends the key to OpenRouter after every answer] → It is the same host the answer already went to, and `GET /key` is read-only.
- [Mandatory-reasoning models still cost reasoning tokens at `low`] → The usage line makes this visible. The proposal does not promise to turn reasoning off for these models.

## Migration Plan

Additive. Old saved turns have no `reasoning` or `usage` and render as before. Empty levels keep today's requests byte-for-byte. Rollback is a revert of the change. Any saved `answer.reasoning` key in `omrs.jsonc` is then an unknown key, which the loader already ignores with a warning.

## Open Questions

- Ollama `think` accepts level strings only for some models. If a model rejects `"low"`, the fallback could be `True`. This is decided during task 2 by a live check against the local Ollama, with no change to the spec.
