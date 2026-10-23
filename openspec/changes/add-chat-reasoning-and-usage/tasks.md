# Tasks

## 1. Reasoning settings

- [ ] 1.1 Add `reasoning` and `verify_reasoning` to `AnswerSettings` with the level pattern. Verify: unit tests for empty, `low`, `max` and the refused value `high; drop` fail first, then pass.
- [ ] 1.2 Add both keys to the Settings page allow-list and the environment lock list (`ANSWER__REASONING`, `ANSWER__VERIFY_REASONING`). Verify: a test that a `.env` value locks the field and a save returns 409; `omrs config init` output contains both keys.
- [ ] 1.3 Update `docs/guides/configuration.md` with both keys. Verify: the docs drift test passes.

## 2. Provider level mapping and reply reading

- [ ] 2.1 Add `reasoning_kwargs()` and `read_reply()` to each Chat provider module and register them next to `build()`. Verify: one test per provider for the request fields of an empty level, `low` and `none`, and for a recorded raw reply (OpenRouter shape from 2026-10-23, Ollama, Anthropic). Each fails before the code.
- [ ] 2.2 Pass the level from `build()` through `additional_kwargs`; the composition root passes `answer.reasoning` for the answer model and `answer.verify_reasoning` for the judge. Verify: a test that an empty level leaves `additional_kwargs` unchanged, and that the judge gets its own level.
- [ ] 2.3 Live check against the local Ollama: send `think: "low"` to the configured chat model. Record the result in design.md Open Questions and pick the fallback.
- [ ] 2.4 Check the import-linter contracts and the registry rule (no `if/elif` on provider names). Verify: `uv run --no-sync lint-imports` passes.

## 3. Ledger and answer result

- [ ] 3.1 Add the per-request `CompletionLedger` and pass it to `server_seam()` and the judge seam. Verify: a test with a fake LLM returning two raw replies gives summed usage, `calls` 2 and joined reasoning.
- [ ] 3.2 Attach `reasoning` and `usage` to the answer result, with `null` for unreported figures, the 64 KB cap and no `usage` for client-sampled answers. Verify: result-shape tests for each case, and the existing synthesis and whole-reply tests stay green.
- [ ] 3.3 Add `include_reasoning` to the MCP `answer_documents` tool (default false) and keep `usage` always. Verify: MCP tests for both flag values; the tool description names the flag.
- [ ] 3.4 Update `docs/guides/mcp-tools.md` and the answer section of `docs/guides/architecture.md`. Verify: the file-size ceiling test passes for every touched file.

## 4. HTTP routes

- [ ] 4.1 Carry the levels on `GET/PUT /v1/settings/chat` and the judge route, with the 400 and 409 rules. Verify: route tests for save, refuse and lock.
- [ ] 4.2 Add `GET /v1/settings/chat/reasoning-levels` with the OpenRouter catalogue hook and the 10-minute cache. Verify: tests with a recorded catalogue for a mandatory model, a model with `none`, an unknown model, a fetch failure and a provider without a catalogue (no request sent).
- [ ] 4.3 Add `GET /v1/usage/credit` with the OpenRouter `/key` hook. Verify: tests for a key with a limit, a key without one, an error, and a check that the key text is not in the response or the log.
- [ ] 4.4 Update the OpenAPI 3.1 contract and its contract test.

## 5. Settings page

- [ ] 5.1 Load the `impeccable` or `omms-design` skill. Add the Reasoning control to the Chat and judge forms: dropdown when levels are known, text box when not, "ignored" note, read-only value. Verify: Vitest cases from the spec scenarios fail first, then pass.
- [ ] 5.2 Add the fix lines under the provider select (install command, link to the provider card). Verify: Vitest cases for "not installed", "no key" and "all ready".
- [ ] 5.3 Update `docs/guides/web-workspace.md` (Settings > Chat steps). Verify: lint and typecheck pass.

## 6. Chat page

- [ ] 6.1 Add the collapsed Reasoning box to `AssistantTurn`. Verify: Vitest cases for a turn with reasoning, an old turn and keyboard opening.
- [ ] 6.2 Add the usage line to `Composer` and the credit query, invalidated when an answer finishes. Verify: Vitest cases for the full line, null cost, credit suffix and a single credit request per answer.
- [ ] 6.3 Update `docs/guides/web-workspace.md` (Chat section). Verify: all web tests pass.

## 7. Records and checks

- [ ] 7.1 Write ADR-093 for the ledger, reply readers and result shape (load `s-adr`). Add it to the ADR index.
- [ ] 7.2 Run `./scripts/local_ci.sh`, `npm run lint`, `npm run typecheck`, `npm test` in `web/`, and `openspec validate add-chat-reasoning-and-usage --strict`. Verify: all pass.
- [ ] 7.3 Browser check on a scratch server at 1280 px and 390 px: Settings > Chat with GLM-5.3-flash shows the dropdown; one answer at `low` shows the Reasoning box and the usage line with credit. Record the timing at `low` against the 31 s baseline.
