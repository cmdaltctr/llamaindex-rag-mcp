# ADR-093: Answer Reasoning and Usage through a Ledger beside the Seam

- **Date:** 2026-10-23
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-059](059-claim-verification-stage.md) (claim verification stage), [ADR-087](087-settings-live-in-omrg-jsonc.md) (settings in `omrs.jsonc`), [ADR-089](089-answer-stage-progress.md) (answer stage progress), [TDR-037](../tdr/037-openrouter-answers-used-the-legacy-completions-endpoint-so-reasoning-leaked-into-the-answer.md) (reasoning leaked into the answer)
- **Change:** `openspec/changes/add-chat-reasoning-and-usage/` (design D1 to D3)

## Context

Reasoning models such as `z-ai/glm-5.3-flash` think before they answer. OMRS
sent no reasoning setting, so these models ran at their default effort (`max`
for GLM). An answer took about 31 s and the user could not change it.

After TDR-037 the OpenRouter reply keeps the reasoning in
`choices[0].message.reasoning`, apart from `content`. The reply also carries a
`usage` block with input, output and reasoning tokens and the cost in US
dollars. OMRS read only `content` and dropped the rest.

The core answer seam is "prompt in, whole reply text out"
(`grounded-answer-synthesis`). Synthesis, refine rounds, the round bound, the
graph adapters, the CLI and the MCP client seam all depend on that contract.
Only `engine_answer.server_seam()` sees the raw provider reply. Each provider
returns a different raw shape: OpenAI-shaped (OpenRouter, OpenAI-compatible,
llama.cpp), Ollama and Anthropic.

## Decision

1. **A per-request ledger beside the seam.** `server_seam()` still returns
   `str`. After each `acomplete()` it gives `completion.raw` to the provider's
   reply reader and appends the result to a `CompletionLedger` that the
   request owns. The judge seam writes to the same ledger. After synthesis the
   Engine attaches the ledger totals to the answer result. Core never sees the
   ledger. A user-profile answer runs a saved graph, so core cannot take a
   ledger argument there: `engine_profiles.answer` sets the active ledger in
   a context variable, and `graph_host` wraps the `answer_llm` and
   `verify_llm` resources so each call records into it. A plain
   `Engine.run_pipeline` call sets no ledger and reports no usage.
   Judge calls add to `usage` only; their reasoning text stays out of
   `reasoning`, so Chat shows the answer model's thinking.
2. **Each provider reads its own reply and maps its own level.** A provider
   module defines `read_reply(raw) -> ReplyFacts` and
   `reasoning_kwargs(level) -> dict | None`. The registry finds both by module
   attribute, so dispatch has no `if/elif` on provider names (root invariant
   11). A provider without them reports nothing and ignores levels. A reader
   never raises: an unknown shape gives `None` figures and no reasoning.
3. **Additive result shape.**
   - `reasoning`: present only when a call returned reasoning. Calls join in
     call order with a blank line. The stored text is capped at 64 KB with a
     marker, so one runaway reply cannot bloat `workspace.db`.
   - `usage`: `input_tokens`, `output_tokens`, `reasoning_tokens`, `cost_usd`,
     `calls`, summed over every call including judge calls. A figure is
     `null` unless every call reported it, so a partial sum never shows as a
     total. Client-sampled answers carry no `usage`, because OMRS cannot see
     the client's model.
   - The MCP `answer_documents` tool returns `usage` always and `reasoning`
     only with `include_reasoning=true`, so agents do not pay tokens for text
     they did not ask for.
4. **One level per role in settings.** `answer.reasoning` (answer model) and
   `answer.verify_reasoning` (judge) hold an empty value or a level matching
   `^[A-Za-z0-9_-]{1,32}$`. An empty level sends nothing, which keeps the
   earlier requests unchanged.

## Consequences

### Positive

- The user controls reasoning effort and sees why an answer took long and
  what it cost.
- The whole-reply contract and every synthesis test stay unchanged.
- A new provider adds reasoning support in its own module, with no change to
  the seam or the registry.

### Negative

- Each provider carries a reader that tracks the provider's reply shape. A
  renamed field silently gives `null` figures until the reader is updated. A
  unit test pins the OpenRouter shape recorded on 2026-10-23.
- Reasoning text is stored with the turn. It can contain material from the
  evidence, which the same workspace file already holds.

### Neutral

- Anthropic (needs a token budget) and llama.cpp (no stable request field)
  accept a level but send nothing. Settings > Chat says so.
- OMRS keeps no price table. Cost shows only when the provider reports it.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Change the seam to return `(text, facts)` | Touches `synthesis.py`, `stages.py`, the graph adapters, the CLI and the MCP client seam, for data core never reads |
| Strip reasoning out of the answer text with a pattern | TDR-037 shows leaked reasoning has no fixed markers |
| Show a partial sum when some calls lack a figure | A partial total reads as the real total and misleads the user |
| One reasoning level shared by answer and judge | The judge is a short classification; it often needs a lower level than the answer |

## References

- `src/omrs/core/providers/llm/reply.py`, `reply_read.py` (shared OpenAI-shaped reader), `registry.py`
- `src/omrs/engine_answer.py` (`CompletionLedger`, `server_seam`), `src/omrs/engine_profiles.py`
- `src/omrs/core/answer/settings.py`
- `openspec/changes/add-chat-reasoning-and-usage/design.md`
