# Design: add-judge-model-setting

## Context

Settings > Chat saves `answer.provider` and `answer.model` through `PUT /v1/settings/chat` (`src/omrg/transports/api/routes/chat_settings.py`). The two keys apply at once because they are in `PROVIDER_FIELDS` (`src/omrg/config/provider_sources.py:38-45`). That one tuple drives four things:

- the keys the page may write (`ALLOWED_KEYS`, `src/omrg/config/settings_file_write.py:51`);
- the keys that apply at once (`LIVE_KEYS`, `src/omrg/transports/settings_view.py:38`);
- the overlay of file values onto the running settings (`src/omrg/compose_providers.py:135` and `:333`);
- the lock detection for env and `.env` (`explicit_provider_fields`, `provider_sources.py:84-94`).

The Engine accepts a live change only for the fields in `_EDITABLE_TOP` and `_EDITABLE_ANSWER = ("provider", "model")` (`src/omrg/engine_providers.py:35-36`). Any other difference makes `use_provider_settings` raise `ValueError`, and `ProviderState.save_fields` rolls the file back (`provider_state.py`, `EngineRefused`).

The judge is built per answer by `build_verify_llm` (`src/omrg/compose_answer.py:152-228`) through the generation's `verify_llm_factory`. A new generation already calls `self._pipelines.reset_judges()` (`engine_providers.py`, end of `use_provider_settings`). So the judge picks up a new generation's values with no further change.

### Verified: empty-model behaviour

The note "an empty `verify_model` falls back to the provider's default model" is still true. `build_verify_llm` passes `answer_model=None` when the model is blank (`compose_answer.py:222`). Each provider then does this:

| Provider | Blank judge model gives | Source |
| --- | --- | --- |
| `openrouter` (the `cloud` alias default) | `openrouter_llm_model`, default `""`; OpenRouter refuses the call ("No models provided") | `core/providers/llm/openrouter.py:55`, `config/__init__.py:135` |
| `llamacpp` (the `local` alias default) | `llamacpp_chat_model`, default `""` | `core/providers/llm/llamacpp.py:50`, `config/__init__.py:132` |
| `ollama` | `metadata.ollama_classify_model`, default `qwen3:0.6b` | `core/providers/llm/ollama.py:47` |
| `anthropic`, `openai_compatible` | `ValueError` ("needs a Chat model name") | `anthropic.py:51-52`, `openai_compatible.py:53-54` |

`engine_answer.build_verifier` (`src/omrg/engine_answer.py:95-105`) turns a build error into `verification_skipped`. An OpenRouter refusal happens later, at the first judge call. So with the shipped defaults (`verify_provider: cloud`, `verify_model: ""`, `cloud_backend: openrouter`) the judge cannot work until a model is set. The failure is still possible today.

### Verified: precedence

A profile YAML bundle can set `answer.verify_model` and `answer.verify_provider` and wins at operation time (grounded-answer-synthesis, "Profiles can override verification settings"; `compose_answer.py:127-140`). A user profile graph cannot set them: `levers.py:103-104` marks both host-owned. No built-in profile sets them (`config/profiles/documents.yaml:44-46` holds them as comments). So the page value is the judge for every collection today.

## Goals / Non-Goals

**Goals:**

- Set and clear the judge provider and model from Settings > Chat, with the source shown and env locks respected.
- Apply a saved or hand-edited judge choice at once in `omrg web`.
- Show the user why claim checks are skipped when the judge model is empty.

**Non-Goals:**

- A global `answer.verify_claims` toggle on the page (see D3).
- Changing the empty-model fallback in `build_verify_llm` or in the provider builders.
- Showing the provider-default model name for an empty judge model (see D4, option B).
- Changing the Providers card "verification" role, which still shows only when `ANSWER__VERIFY_CLAIMS` is true globally (`compose_connections.py:83-87`).

## Decisions

### D1. Save the provider and the model as one unit

`PUT /v1/settings/judge` takes `{provider, model, revision?}` or a clear body, like the Chat route. A model id only makes sense with a provider. Either env variable locks both fields, like `_CHAT_FIELDS` in `compose_providers.py:77`.

The page writes registry names only. It reads the aliases `cloud` and `local` and shows them as "cloud (OpenRouter)". Alias resolution reuses the rule in `build_verify_llm` (`cloud` or blank resolves to `cloud_backend`, `local` to `local_backend`). Move that rule into one small function in `compose_answer.py` so the route and the builder share it. The route takes it through the composition root and does not branch on provider names.

Alternatives: model only (rejected: the default provider alias resolves to OpenRouter, so a user with only Ollama has no path); extend `PUT /v1/settings/chat` with judge fields (rejected: an empty Chat body clears the Chat choice, so mixed bodies get unclear clear rules, and `ChatSaveBody` forbids extra fields).

### D2. Apply at once

"At once" needs these code changes. All are small.

1. Add `answer.verify_provider` and `answer.verify_model` to `PROVIDER_FIELDS`. This makes them writable, live, overlaid and lock-checked.
2. Add `verify_provider` and `verify_model` to `_EDITABLE_ANSWER` in `engine_providers.py:36`, and update the `ValueError` message that names the editable fields.
3. Add a `_JUDGE_FIELDS` lock unit beside `_CHAT_FIELDS` in `compose_providers.py`.
4. Validate the provider name on save (registry name only). `compose_answer.validate_verify_provider` runs only at startup.
5. Update `tests/unit/test_llm_new_providers.py:246`, which asserts the exact `PROVIDER_FIELDS` set.

No change is needed in the judge build path: `reset_judges()` already runs on each new generation.

Alternative: apply at next launch and open the restart dialog (rejected: it is the current pain point, and the Chat choice already shows the live path works).

### D3. Leave `verify_claims` off the page

`answer.verify_claims` is a profile lever ("Check claims", `web/src/studio/labels.ts:26`; `levers.py:63`). A profile value wins over the global default, so a global toggle on the page would often have no effect and would mislead. The judge block states that the judge runs only for collections whose profile turns on "Check claims".

Alternative: show it read-only in the Chat section (rejected: the Configuration section already lists it read-only).

### D4. Block an empty model; report `no-model`

PUT returns 400 for an empty model. GET reports `ready: false` with the new reason `no-model` when the model in force is empty. The page shows "Not set" and "Claim checks are skipped until you set a judge model."

This is slightly strict for Ollama, where an empty model falls back to `qwen3:0.6b`. It is correct for the default provider (OpenRouter) and for llama.cpp, Anthropic and OpenAI-compatible.

Option B (deferred): add a `default_model(settings)` hook to `ConnectionDescriptor` in each provider file, so GET can name the fallback model without a branch on provider names. This touches every provider module.

### D5. Reuse the Chat model form

Turn `ChatModelForm.tsx` into a form that takes its save mutation, labels and initial values as props. Use it for the Chat choice and for the judge. List models uses `POST /v1/connections/{provider}/models` as now. Test reuses `POST /v1/settings/chat/test` with an explicit `{provider, model}` body: that route already tests any typed choice and saves nothing. A judge-specific test route would duplicate it.

Alternative: free text only (rejected: model ids are long and error-prone, and List models already exists).

### D6. New route module

Add `src/omrg/transports/api/routes/judge_settings.py`. `chat_settings.py` is 328 lines, so the judge routes go in their own file to stay well under 500. Share the model-name rule (`_valid_model`) and `_not_ready_reason` by import from `chat_settings.py`. Add `ProviderState.save_judge` beside `save_chat`. Add both operations (`getJudgeSettings`, `setJudgeSettings`) and the schemas `JudgeSettings` and `JudgeSaveRequest` to `openapi.yaml`.

### D7. Row layout

Each row reads `Label  value · source  [Edit] [Remove]`, using the existing `ChoiceRow` and `sourceText` words in `ChatSection.tsx`. Remove shows only for a `config-file` source and sends the clear body. A locked row shows the lock reason and no buttons.

## Baseline spec fixes

Project gotcha 12 says to fix a factually wrong baseline. This change fixes three in `openspec/specs/`:

1. `llm-provider-settings`, scenario "Choose a cloud model": the source was `saved`. The code returns `config-file` (`chat_settings.py`, `_chat_source`), and the same spec says "The source `saved` SHALL NOT exist".
2. `workspace-settings`, "The Chat section says where the choice applies": said stdio and the CLI "do not see saved values". They read the same `omrg.jsonc` at launch (ADR-087; `ChatSection.tsx` says so).
3. `workspace-settings`, "Settings is split into sections": the list missed Configuration, which `SettingsView.tsx` shows at `#/settings/configuration`.

## Risks / Trade-offs

- [A judge choice that the Engine refuses rolls back the file] → The existing `EngineRefused` path returns 409 with a plain message; add a test that a refused judge save leaves `omrg.jsonc` unchanged.
- [Hand-edited aliases still work but the page cannot write them] → GET shows the alias with its resolved provider; Edit preselects the resolved provider.
- [A future profile YAML sets its own judge and the page value seems ignored] → The block states that a profile judge overrides this choice.
- [`no-model` is strict for Ollama] → Accept for now; D4 option B removes it if users ask.
- [Adding keys to `PROVIDER_FIELDS` touches the handover plan] → No workspace rows exist for the judge, so `settings_handover.py` needs no change. Confirm by test that the handover writes no judge key.

## Migration Plan

No data migration. Existing hand-edited `answer.verify_*` keys keep working and now apply at once. Rollback: revert the change; the keys stay valid in `omrg.jsonc` and apply at next launch again.

## Open Questions

These need the user's answer before `apply`. Each has a recommendation, and the specs and tasks follow it.

1. Include `verify_provider` with `verify_model`? Recommendation: yes, saved and locked as one unit (D1).
2. Apply at once or at next launch? Recommendation: at once (D2, five small changes).
3. Expose `verify_claims` as a global default on the page? Recommendation: no (D3).
4. Empty model: block saving, or show the fallback model? Recommendation: block saving and report `no-model` (D4). Option B shows the fallback name at the cost of a hook in every provider.
5. Model picker: reuse the Chat form and list, or free text? Recommendation: reuse the Chat form, List models and the Chat test route (D5).
