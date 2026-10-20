# Tasks

Prepare the feature worktree with `uv sync --frozen --extra web`. Each task writes a failing test first, confirms it fails, then writes the code that makes it pass.

## 0. Confirm the open questions

- [x] 0.1 Get the user's answers to the five open questions in design.md. If an answer differs from the recommendation, run `openspec-update-change` before task 1.1 and verify with `openspec validate add-judge-model-setting --strict`. (2026-10-20: the user accepted all five recommendations, so no plan update was needed.)

## 1. Live judge fields in config and the Engine

- [x] 1.1 Write failing tests: `answer.verify_provider` and `answer.verify_model` are in `ALLOWED_KEYS` (`tests/unit/test_settings_file_write.py`) and in `LIVE_KEYS` (`tests/unit/test_web_configuration.py`); update the exact-set assertion in `tests/unit/test_llm_new_providers.py:246`. Confirm they fail on the current code.
- [x] 1.2 Add both paths to `PROVIDER_FIELDS` in `src/omrg/config/provider_sources.py`. Verify the 1.1 tests pass.
- [x] 1.3 Write a failing test in `tests/unit/test_engine_provider_update.py`: `use_provider_settings` accepts a change of `answer.verify_model` and `answer.verify_provider`, and still refuses a change of `answer.verify_claims`. Confirm it fails.
- [x] 1.4 Add `verify_provider` and `verify_model` to `_EDITABLE_ANSWER` in `src/omrg/engine_providers.py` and update the refusal message. Verify 1.3 passes.
- [x] 1.5 Write a failing test in `tests/unit/test_compose_providers.py`: `ANSWER__VERIFY_MODEL` in the environment locks both judge fields. Confirm it fails.
- [x] 1.6 Add the `_JUDGE_FIELDS` lock unit in `src/omrg/compose_providers.py`. Verify 1.5 passes.
- [x] 1.7 Write a failing test in `tests/test_answer_verify.py` (or a new unit file): after a judge save, the next answer builds the judge with the new model, and an answer that started earlier keeps the old judge. Make it pass; no change to the build path is expected (design D2).
- [x] 1.8 Write a test in `tests/unit/test_settings_handover.py` that the handover writes no `answer.verify_*` key. Verify it passes with and without the 1.2 change, then break the handover plan on purpose to confirm the test can fail.

## 2. Judge settings routes and contract

- [x] 2.1 Move the alias rule (`cloud`, `local`, registry name) out of `build_verify_llm` into one function in `src/omrg/compose_answer.py`. Write a failing unit test for the function first. Verify `tests/test_answer_verify.py` still passes.
- [x] 2.2 Write failing route tests in a new `tests/unit/test_web_judge_settings.py` for every scenario in the `llm-provider-settings` delta: default `no-model`, ready judge, no provider request, save, empty model 400, unknown provider 400, one field only 400, clear, `.env` lock 409, stale revision 409, Engine refusal 409 with the file unchanged. Confirm they fail.
- [x] 2.3 Add `ProviderState.save_judge` in `src/omrg/transports/api/provider_state.py` and the routes in `src/omrg/transports/api/routes/judge_settings.py` (`getJudgeSettings`, `setJudgeSettings`). Register the router. Verify 2.2 passes and the file stays under 500 lines.
- [x] 2.4 Add both operations and the `JudgeSettings` and `JudgeSaveRequest` schemas to `src/omrg/transports/api/openapi.yaml`. Verify `uv run pytest tests/unit/test_web_openapi_conformance*.py` passes.

## 3. Web Settings judge block

- [ ] 3.1 Add `JudgeSettings`, `getJudgeSettings` and `setJudgeSettings` to `web/src/api/settings.ts`, the query to `web/src/api/queries.ts` and `useSetJudgeSettings` to `web/src/api/settingsMutations.ts`, with a failing test in `web/src/api/settings.test.ts` first. Verify `npm test` passes in `web/`.
- [ ] 3.2 Write failing tests in `web/src/settings/ChatSection.test.tsx` for every scenario in the `workspace-settings` delta: default judge shown, Edit opens filled, pick from list, Remove, locked judge, and the "where the choice applies" text. Add judge fixtures to `web/src/settings/test/fixtures.ts`. Confirm they fail.
- [ ] 3.3 Make `ChatModelForm.tsx` take its save mutation, labels and initial values as props, with Save disabled for an empty model. Keep all existing `ChatSection.test.tsx` tests green.
- [ ] 3.4 Add the "Claim check judge" block to `web/src/settings/ChatSection.tsx` (rows, Edit, Remove, lock note, profile note, cloud note). Verify 3.2 passes, then run `npm run lint`, `npm run typecheck` and `npm test` in `web/`.
- [ ] 3.5 Rebuild the static bundle in `src/omrg/transports/api/static/` with the project's web build command. Verify `omrg web` serves the new block.

## 4. Documentation

- [x] 4.1 Update `docs/guides/configuration.md` (answer block, around lines 715 to 740): Settings > Chat now sets the judge; both keys apply at once; an empty model with the default cloud provider cannot work. Verify with `grep -n "judge keep their own settings" docs/guides/configuration.md` that the old sentence is gone.
- [x] 4.2 Add a "Claim check judge" subsection after "Chat model" in `docs/guides/web-workspace.md`. Verify it names the lock variables, the "Check claims" profile lever and the cloud statement.
- [x] 4.3 Grep `docs/guides/` for "Restart to apply" text about `verify_model` or `verify_provider` and fix any hit (documentation drift check).

## 5. Integration checks

- [ ] 5.1 Run `./scripts/local_ci.sh` and `openspec validate add-judge-model-setting --strict`. Both must pass.
- [ ] 5.2 Ask the user before starting a server (heavy-run warning). Then start `omrg web` from the feature worktree with `OMRG_CONFIG_DIR` set to a scratch folder, never `~/.config/omrg` or `~/.omrg`.
- [ ] 5.3 In the browser at 1280 px wide, open `#/settings/chat`. Save a judge, see the `config-file` source, Remove it, and see the default return. Take a screenshot.
- [ ] 5.4 Repeat 5.3 at 390 px wide. Verify there is no horizontal page scroll and every button can be reached. Take a screenshot.
- [ ] 5.5 With a profile that turns on "Check claims", ask one question in Chat after a judge save. Verify the answer reports verification with no restart, or `verification_skipped` with a plain reason when the provider has no key.
