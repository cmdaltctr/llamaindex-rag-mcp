# Proposal

## Why

Reasoning models (for example `z-ai/glm-5.3-flash`) think before they answer. OMRS sends no reasoning setting, so these models run at their default effort, which is `max` for GLM. Answers are slow and the user cannot change this. OMRS also drops the reasoning text and every usage figure the provider returns, so the user cannot see why an answer took 30 s or what it cost. TDR-037 fixed the endpoint bug that put reasoning into the answer text. This change gives the user control of reasoning and shows reasoning, tokens and cost in Chat.

## What Changes

- Add an `answer.reasoning` setting for the Chat model and an `answer.verify_reasoning` setting for the claim judge. Each one holds a level such as `none`, `low`, `high` or `max`, or is empty. An empty value sends nothing, which is the current behaviour.
- Add a Reasoning control to Settings > Chat, under the provider and model:
  - For OpenRouter, a dropdown lists the levels the model supports. The list comes from the public OpenRouter model catalogue, on request. "Provider default" is always the first option. `none` shows only when the model can turn reasoning off.
  - For a provider with no published level list, a text box takes the level.
  - The judge block gets the same control.
- Send the saved level to the provider on each answer call. A provider that cannot take a level ignores it, and the Settings page says so.
- Keep the model's reasoning text apart from the answer and save it with the turn. Chat shows it above the answer as a collapsed "Reasoning" box in small grey text. Saved turns without reasoning show no box.
- Record the tokens and cost of each answer: input tokens, output tokens, reasoning tokens and cost in US dollars, summed over every model call for that answer, including judge calls. Show them on a single line of small grey text at the top right of the question box, for the latest answer in the chat.
- For OpenRouter, show the remaining credit on that line when the key has a spending limit (for example "$2.81 left").
- Settings > Chat: make the provider list explain itself. Every registered provider shows in the list. A provider that cannot answer yet stays visible, with the reason and the fix next to it (for example "Anthropic: not installed. Run `uv tool install 'omrs[anthropic]'`"). This answers "why are there no other options?"

## Capabilities

### New Capabilities

- `answer-reasoning-and-usage`: the reasoning level sent to the answer and judge models, the reasoning text kept apart from the answer, and the token, cost and credit figures recorded for each answer.

### Modified Capabilities

- `workspace-chat`: Chat shows a collapsed reasoning box and a usage line for the latest answer.
- `llm-provider-settings`: Settings > Chat gets Reasoning controls for the Chat model and the judge, and the provider list shows why a provider is not ready and how to fix it.

## Impact

- Settings model: two new fields in the `answer` block (`reasoning`, `verify_reasoning`), saved to `omrs.jsonc` by the Settings page. Env names `ANSWER__REASONING` and `ANSWER__VERIFY_REASONING`.
- Providers (`core/providers/llm/`): each `build()` takes the level and maps it to its own request field. OpenRouter maps it to `reasoning.effort`, OpenAI-compatible to `reasoning_effort` and Ollama to `think`. llama.cpp and Anthropic accept the text box value but send nothing in this change (see design).
- Answer seam (`engine_answer.py`): the server seam records reasoning text and usage from each raw reply. The core seam contract stays "prompt in, text out".
- Answer result: new optional `reasoning` field and `usage` object. These are additive; existing callers ignore them. The MCP tool returns `usage` always and `reasoning` only when asked.
- HTTP API: `GET/PUT /v1/settings/chat` and the judge route carry the reasoning level. New `GET /v1/settings/chat/reasoning-levels?provider=&model=` and `GET /v1/usage/credit`. OpenAPI contract updated.
- Web: `web/src/settings/ChatModelForm.tsx`, `JudgeBlock.tsx`, `web/src/chat/AssistantTurn.tsx`, `Composer.tsx`.
- No new dependency. The level list and credit both use plain HTTPS calls to OpenRouter, sent only when the user opens the form or after an answer.
- Docs: `docs/guides/web-workspace.md`, `docs/guides/configuration.md`, `docs/guides/mcp-tools.md`; ADR for the reasoning and usage design.
