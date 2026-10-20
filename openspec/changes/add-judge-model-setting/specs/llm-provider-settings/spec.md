## ADDED Requirements

### Requirement: The judge status says whether the judge is ready

`GET /v1/settings/judge` (read scope) SHALL return the judge provider as set (a registry name, or the alias `cloud` or `local`), the registry provider that the alias resolves to, the judge model, their source (`env`, `dotenv`, `config-file` or `default`), whether the choice is locked and why, whether answering is enabled, and whether the judge is ready. When the judge is not ready, the route SHALL give a reason from a fixed set: `disabled`, `unknown-provider`, `not-installed`, `not-configured` (a required value, such as a key, is missing) and `no-model` (the judge model in force is empty). The server SHALL NOT contact a provider for this route. The route SHALL NOT report whether claim checks are turned on, because a profile decides that per collection.

#### Scenario: Default judge has no model

- **WHEN** no source sets `answer.verify_provider` or `answer.verify_model`
- **THEN** `GET /v1/settings/judge` MUST report the provider `cloud`, the resolved provider `openrouter`, the model `""`, the source `default`, ready false and the reason `no-model`

#### Scenario: Ready judge

- **WHEN** `omrg.jsonc` sets `answer.verify_provider` to `openrouter` and `answer.verify_model` to `openai/gpt-5-mini`, and an OpenRouter key is set
- **THEN** `GET /v1/settings/judge` MUST report that choice with the source `config-file` and ready true

#### Scenario: No provider request

- **WHEN** the Chat section reads `GET /v1/settings/judge`
- **THEN** the server MUST NOT send any request to a provider

### Requirement: The judge choice sets the web server's claim-verification judge

`PUT /v1/settings/judge` (browser session, `manage` scope) SHALL save a registered provider name and a model name of 1 to 200 characters with no control characters, or clear both. The route SHALL write `answer.verify_provider` and `answer.verify_model` to `omrg.jsonc` as one unit, with the revision check. A body that sends only one of the two SHALL return 400 and save nothing. A save SHALL NOT write an alias (`cloud` or `local`). The saved choice SHALL be the judge of the web server from the next answer, with no restart, for every collection whose profile turns claim checks on and does not set its own judge. The route SHALL return 409 and change nothing when `ANSWER__VERIFY_PROVIDER` or `ANSWER__VERIFY_MODEL` comes from the environment or `.env`; either variable SHALL lock both fields.

#### Scenario: Save a judge

- **WHEN** the user saves the provider `openrouter` and the model `openai/gpt-5-mini`
- **THEN** `omrg.jsonc` MUST hold both keys, `GET /v1/settings/judge` MUST report the source `config-file`, and the next answer with claim checks on MUST send its judge calls to that model with no restart

#### Scenario: Empty model refused

- **WHEN** the user saves the provider `openrouter` and an empty model name
- **THEN** the server MUST return 400 and MUST NOT change `omrg.jsonc`

#### Scenario: Unknown provider refused

- **WHEN** the user saves the provider `gemini`, which the registry does not hold
- **THEN** the server MUST return 400 and MUST save nothing

#### Scenario: Clear the judge

- **WHEN** `omrg.jsonc` holds a judge choice and the user sends an empty body
- **THEN** the server MUST remove both keys, and `GET /v1/settings/judge` MUST report the source `default`

#### Scenario: Locked by the environment

- **WHEN** `.env` sets `ANSWER__VERIFY_MODEL` and the user saves another judge
- **THEN** the server MUST return 409 naming `ANSWER__VERIFY_MODEL`, and the judge MUST NOT change

#### Scenario: A call that started keeps its judge

- **WHEN** an answer with claim checks is running and the user saves a new judge
- **THEN** the running answer MUST finish with the old judge, and the next answer MUST use the new one
