# Spec Delta

## MODIFIED Requirements

### Requirement: Settings resolution precedence

The system SHALL resolve the effective `Settings` by layering sources in a
documented precedence order: subpackage model defaults (lowest),
`config/defaults.yaml`, the selected YAML profile bundle when present,
`omrg.jsonc` in the user config folder, `.env`, the process environment, then
explicit per-operation options (highest). `config/defaults.yaml` and profile
bundles SHALL be expressed as nested mappings keyed by subpackage block
(`chunking:`, `retrieval:`, `metadata:`) plus top-level cross-cutting keys, and
SHALL be deep-merged rather than flattened. `omrg.jsonc` SHALL use the same
nesting and SHALL be deep-merged in the same way. The YAML files SHALL contain
no secrets, provider keys, or machine-specific absolute paths. YAML files SHALL
be loaded via `importlib.resources` so they resolve correctly in both
development (repository root) and installed (site-packages) contexts, and SHALL
be declared as package data in `pyproject.toml`. The resolver SHALL record the
source of each value so the transports can report it.

#### Scenario: Environment overrides YAML

- **WHEN** a setting is present in both `config/defaults.yaml` and the
  process environment
- **THEN** the environment value MUST win

#### Scenario: omrg.jsonc overrides YAML

- **WHEN** `config/defaults.yaml` sets `retrieval.top_k` to 10 and `omrg.jsonc`
  sets it to 7, and no environment value sets it
- **THEN** the resolved value MUST be 7 with the source `config-file`

#### Scenario: .env overrides omrg.jsonc

- **WHEN** `omrg.jsonc` sets `retrieval.top_k` to 7 and `.env` sets
  `RETRIEVAL__TOP_K=12`
- **THEN** the resolved value MUST be 12 with the source `dotenv`

#### Scenario: Nested YAML is deep-merged

- **WHEN** `config/defaults.yaml` declares `retrieval.top_k` and the selected
  profile declares only `retrieval.rerank_enabled`
- **THEN** the resolved settings MUST carry both values
- **AND** the profile MUST NOT replace the whole `retrieval` block

#### Scenario: Nested omrg.jsonc is deep-merged

- **WHEN** `omrg.jsonc` declares only `retrieval.top_k`
- **THEN** every other `retrieval` value MUST come from the lower sources

#### Scenario: YAML contains no secrets

- **WHEN** `config/defaults.yaml` or any file under `config/profiles/` is
  committed
- **THEN** it MUST NOT contain API keys, tokens, or absolute machine paths

#### Scenario: YAML resolves from installed package

- **WHEN** the server runs from an installed wheel (not the repository root)
- **THEN** `defaults.yaml` MUST be discoverable via `importlib.resources`
  regardless of the current working directory
