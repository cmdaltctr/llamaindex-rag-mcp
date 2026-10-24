## ADDED Requirements

### Requirement: Settings > Chat sets the reasoning level

The Chat form SHALL show a Reasoning control under the model name. The judge form SHALL show its own Reasoning control. When the user opens the form or changes the provider or model, the page SHALL call `GET /v1/settings/chat/reasoning-levels`. When the levels are known, the control SHALL be a dropdown with "Provider default" first, then the supported levels. "Provider default" SHALL show the model's default level when the catalogue gives one. When the levels are not known, the control SHALL be a text box. When the provider ignores the level, the page SHALL say so under the control. Save SHALL write the level with the provider and model in one write. The read-only view SHALL show the saved level, or "Provider default".

#### Scenario: OpenRouter model with a catalogue entry

- **WHEN** the user edits Chat with provider `openrouter` and model `z-ai/glm-5.3-flash`
- **THEN** the Reasoning dropdown MUST list "Provider default (max)", `max`, `high` and `low`, and MUST NOT list `none`

#### Scenario: Provider without a catalogue

- **WHEN** the user edits Chat with provider `openai_compatible`
- **THEN** the Reasoning control MUST be a text box

#### Scenario: Saved level shown

- **WHEN** the user saves the level `low` and closes the form
- **THEN** the read-only view MUST show `Reasoning: low`

#### Scenario: Locked by the environment

- **WHEN** `.env` sets `ANSWER__REASONING`
- **THEN** the Reasoning control MUST be read-only, and a save MUST return 409 naming `ANSWER__REASONING`

### Requirement: The provider list says why a provider cannot answer

The provider select in the Chat and judge forms SHALL list every registered provider. A provider that cannot answer yet SHALL stay in the list, disabled, with its reason. Under the select, the form SHALL show one line for each provider that is not ready, giving the fix: the install command for `not installed`, and a link to its card under Settings > Providers for a missing key.

#### Scenario: Optional extra not installed

- **WHEN** the Anthropic module is not installed
- **THEN** the select MUST show "Anthropic (not installed)" as disabled, and the form MUST show the install command for the `anthropic` extra

#### Scenario: Required key missing

- **WHEN** no OpenRouter key is set
- **THEN** the select MUST show "OpenRouter (no key)" as disabled, and the form MUST link to the OpenRouter card under Settings > Providers

#### Scenario: Every provider ready

- **WHEN** every registered provider is ready
- **THEN** the form MUST show no fix lines
