# Proposal: add-judge-model-setting

## Why

The claim-verification judge (ADR-059) reads `answer.verify_provider` and `answer.verify_model`. The web Settings page cannot set them. Today the user edits `~/.config/omrg/omrg.jsonc` by hand and restarts `omrg web`.

The default judge model is empty. An empty model falls back to the provider's default model, and for the default cloud provider (OpenRouter) that default is also empty (`openrouter_llm_model = ""`). The judge call then fails ("No models provided") and the answer reports `verification_skipped`. The user has no way to see or fix this on the page.

## What Changes

- Add a "Claim check judge" block to Settings > Chat. It shows the judge provider and the judge model as rows: label, value in force, source, and Edit and Remove. A value from the environment or `.env` is locked with a note that names the variable.
- Edit opens a provider select and a model name field filled with the current values, with List models, Test, Save and Cancel. This reuses the Chat model form.
- Add `GET /v1/settings/judge` (read scope) and `PUT /v1/settings/judge` (browser session, `manage` scope). PUT writes or clears `answer.verify_provider` and `answer.verify_model` in `omrg.jsonc` as one unit, with the revision check (ADR-087).
- Make `answer.verify_provider` and `answer.verify_model` apply at once in `omrg web`, as `answer.provider` and `answer.model` do. A hand edit of either key also applies at once. The Configuration section stops showing "Restart to apply" for them.
- PUT refuses an empty model. GET reports the judge as not ready when the model in force is empty, so the page says why claim checks are skipped.
- `answer.verify_claims` stays a profile lever ("Check claims" in Studio). The page does not show it as an editable setting.
- Add both keys to the OpenAPI contract and the web API types.
- Fix three baseline spec errors found during research (see design.md, "Baseline spec fixes").

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `llm-provider-settings`: add the judge choice route, its lock rule and its readiness, and make the judge choice apply at once in the web server.
- `workspace-settings`: add the judge block to the Chat section, and state that the judge choice applies only when a profile or the environment turns claim checks on.
- `settings-file`: add the judge provider and model to the settings that apply at once after a hand edit.

## Impact

- Backend: `src/omrg/config/provider_sources.py` (`PROVIDER_FIELDS`), `src/omrg/engine_providers.py` (`_EDITABLE_ANSWER`), `src/omrg/compose_providers.py` (lock unit), `src/omrg/transports/api/provider_state.py` (save method), new route module `src/omrg/transports/api/routes/judge_settings.py`, `src/omrg/transports/api/openapi.yaml`.
- Front end: `web/src/settings/ChatSection.tsx`, `web/src/settings/ChatModelForm.tsx` (made reusable), `web/src/api/settings.ts`, `web/src/api/queries.ts`, `web/src/api/settingsMutations.ts`.
- Tests: `tests/unit/test_web_chat_settings.py` pattern, `tests/unit/test_engine_provider_update.py`, `tests/unit/test_settings_file_write.py`, `tests/unit/test_llm_new_providers.py` (asserts the exact `PROVIDER_FIELDS` set), OpenAPI conformance tests, web Vitest files.
- Docs: `docs/guides/configuration.md` (answer block, around lines 715 to 740), `docs/guides/web-workspace.md` ("Chat model" section, around line 384).
- No new dependency. No change to the stdio MCP server or the CLI: they already read `omrg.jsonc` at launch.
