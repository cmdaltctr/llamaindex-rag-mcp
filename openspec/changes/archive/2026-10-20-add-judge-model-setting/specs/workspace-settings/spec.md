## ADDED Requirements

### Requirement: The Chat section sets the claim check judge

The Chat section SHALL show a "Claim check judge" block under the Chat choice. The block SHALL show the judge provider and the judge model from `GET /v1/settings/judge` as setting rows with their source. An alias SHALL show with the provider it resolves to, for example "cloud (OpenRouter)". An empty model SHALL show "Not set" and the sentence "Claim checks are skipped until you set a judge model." When the choice is not locked, the block SHALL offer Edit, and SHALL offer Remove when the source is `config-file`. Edit SHALL open the same provider select, model name field, List models and Test actions as the Chat choice, filled with the current values, with Save and Cancel. Save SHALL be disabled while the model name is empty. When the choice is locked, the block SHALL name the variable and where it is set, and SHALL offer no Edit or Remove. The block SHALL state that the judge runs only for collections whose profile turns on "Check claims", and that a profile that sets its own judge overrides this choice. When the selected judge provider is cloud, the block SHALL state that claims and cited passages are sent off this machine.

#### Scenario: Default judge shown

- **WHEN** no source sets the judge
- **THEN** the block MUST show "cloud (OpenRouter)" with "default", the model "Not set" with "default", the skipped-checks sentence, and Edit, and MUST NOT offer Remove

#### Scenario: Edit opens filled

- **WHEN** `omrg.jsonc` sets the judge to `openrouter` and `openai/gpt-5-mini` and the user presses Edit
- **THEN** the provider select MUST show OpenRouter and the model field MUST hold `openai/gpt-5-mini`

#### Scenario: Pick a judge model from the list

- **WHEN** the user presses Edit, selects Ollama, presses List models and picks `qwen3:4b`
- **THEN** the model name field MUST hold `qwen3:4b` and nothing MUST be saved until the user presses Save

#### Scenario: Remove the judge

- **WHEN** the judge comes from `omrg.jsonc` and the user presses Remove
- **THEN** the page MUST send the clear request and MUST show the default judge with the source "default"

#### Scenario: Locked judge

- **WHEN** `.env` sets `ANSWER__VERIFY_PROVIDER`
- **THEN** the block MUST show the judge as locked, name the variable and `.env`, and offer no Edit or Remove

#### Scenario: Narrow screen

- **WHEN** the Chat section shows at 390 px wide
- **THEN** the judge rows and the form MUST fit with no horizontal page scroll

## MODIFIED Requirements

### Requirement: The Chat section says where the choice applies

The Chat section SHALL state that the choice also answers MCP clients of this web server that cannot supply their own model, that metadata extraction keeps its own model, that the claim check judge has its own choice in the block below, and that `omrg` over stdio and the CLI read the same `omrg.jsonc` at their next launch. When the selected provider is cloud, the section SHALL state that questions and retrieved passages leave this machine.

#### Scenario: Cloud choice warns

- **WHEN** the user selects OpenRouter in the Chat section
- **THEN** the section MUST state that questions and retrieved passages are sent to openrouter.ai

#### Scenario: Local choice

- **WHEN** the user selects Ollama with an address on this machine
- **THEN** the section MUST NOT show the cloud statement
