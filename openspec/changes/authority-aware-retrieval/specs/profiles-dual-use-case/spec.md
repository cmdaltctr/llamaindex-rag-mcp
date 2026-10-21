# Spec Delta

## ADDED Requirements

### Requirement: Profiles overlay the authority levers
The profile bundle SHALL accept an optional `authority` section with `enabled` (bool) and `model_tier` (`off`, `onnx_decision`, `nli`). The resolver SHALL overlay these onto `EffectiveSettings.authority` using the same precedence as retrieval levers: environment (`AUTHORITY__ENABLED`, `AUTHORITY__MODEL_TIER`) wins over the bundle, which wins over the server default. The shipped `documents` bundle SHALL leave `authority.enabled` at `false` until Experiment 43 passes its gates; the shipped `codebase` bundle SHALL set `authority.enabled: false` explicitly.

#### Scenario: Codebase profile never enables authority
- **WHEN** a collection is bound to the `codebase` profile and no `AUTHORITY__ENABLED` environment override is present
- **THEN** the resolved `EffectiveSettings.authority.enabled` is `false`

#### Scenario: Invalid model tier names the key
- **WHEN** the `documents` bundle sets `authority.model_tier: gpt`
- **THEN** profile resolution raises an error naming `authority.model_tier` and the accepted values
