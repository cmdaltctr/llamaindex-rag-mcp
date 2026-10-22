# Spec Delta

## ADDED Requirements

### Requirement: Profiles overlay the authority levers
The profile bundle SHALL accept an optional `authority` section with `enabled` (bool) and `model_tier` (`off`, `onnx_decision`, `nli`). The resolver SHALL overlay these onto `EffectiveSettings.authority`: environment (`AUTHORITY__ENABLED`, `AUTHORITY__MODEL_TIER`) wins over the bundle, which wins over the server default. The `documents` bundle SHALL keep `authority.enabled: false` until Experiment 43 passes its gates; the `codebase` bundle SHALL set `authority.enabled: false` explicitly.

#### Scenario: Codebase profile never enables authority
- **WHEN** a collection is bound to the `codebase` profile and no `AUTHORITY__ENABLED` environment override is present
- **THEN** the resolved `EffectiveSettings.authority.enabled` is `false`

#### Scenario: Documents profile ships disabled
- **WHEN** a collection is bound to the shipped `documents` profile and no override is present
- **THEN** the resolved `EffectiveSettings.authority.enabled` is `false`

#### Scenario: Invalid model tier names the key
- **WHEN** the `documents` bundle sets `authority.model_tier: gpt`
- **THEN** profile resolution raises an error naming `authority.model_tier` and the accepted values
