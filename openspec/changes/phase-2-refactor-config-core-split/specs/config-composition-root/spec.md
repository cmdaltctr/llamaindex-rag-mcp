## ADDED Requirements

### Requirement: Three-layer configuration architecture

The system SHALL separate configuration into three layers: a typed settings
resolver (`config.py`), a composition root (`compose.py`), and dependency
injection in every other module. `config.py` SHALL contain only settings
data, parsing, and validation — zero object construction (no `_build_*()`
methods). `compose.py` SHALL be the only module that instantiates provider
and pipeline objects. All other modules SHALL receive their dependencies as
parameters and SHALL NOT import concrete provider classes.

#### Scenario: config.py is construction-free

- **WHEN** `config.py` is inspected after the refactor
- **THEN** it MUST NOT contain any provider or pipeline object construction
- **AND** it MUST expose a validated, immutable resolved `Settings` object

#### Scenario: compose.py is the single construction site

- **WHEN** the codebase is searched for provider instantiation
- **THEN** all instantiation MUST occur in `compose.py`
- **AND** `compose.py` MUST build objects by resolving registries against the
  resolved `Settings`

#### Scenario: Components receive dependencies

- **WHEN** any `core/` component that consumes a constructed object (provider,
  reranker) is instantiated in a test
- **THEN** the test MUST pass that object as a parameter, without mocking the
  global config and without constructing it inside the component
- **AND** resolved settings SHALL be read from the `settings` singleton at
  call time, so tests override individual knobs by patching singleton
  attributes rather than mocking the config module

---

### Requirement: Settings resolution precedence

The system SHALL resolve the effective `Settings` by layering sources in a
documented precedence order: subpackage model defaults (lowest),
`config/defaults.yaml`, the selected YAML profile bundle when present
(Phase 4), environment variables and `.env`, then explicit per-operation
options (highest). `config/defaults.yaml` and profile bundles SHALL contain
no secrets, provider keys, or machine-specific absolute paths. YAML files
SHALL be loaded via `importlib.resources` so they resolve correctly in both
development (repository root) and installed (site-packages) contexts, and
SHALL be declared as package data in `pyproject.toml`.

#### Scenario: Environment overrides YAML

- **WHEN** a setting is present in both `config/defaults.yaml` and the
  process environment
- **THEN** the environment value MUST win

#### Scenario: YAML contains no secrets

- **WHEN** `config/defaults.yaml` or any file under `config/profiles/` is
  committed
- **THEN** it MUST NOT contain API keys, tokens, or absolute machine paths

#### Scenario: YAML resolves from installed package

- **WHEN** the server runs from an installed wheel (not the repository root)
- **THEN** `defaults.yaml` MUST be discoverable via `importlib.resources`
  regardless of the current working directory

---

### Requirement: Subpackage settings models

Each subpackage (chunking, retrieval, metadata) SHALL declare a
`settings.py` containing a Pydantic model of its configuration knobs and
defaults. These models SHALL be pure data and SHALL NOT import from
`config.py`, `compose.py`, or any other `core/` module.

#### Scenario: No upward imports

- **WHEN** the import-linter CI check runs
- **THEN** it MUST fail if any subpackage `settings.py` imports from
  `config.py`, `compose.py`, or a sibling `core/` module

#### Scenario: Defaults live near their code

- **WHEN** a new configuration knob is added for a subpackage
- **THEN** its default MUST be declared in that subpackage's `settings.py`
  and surfaced through the root `Settings` model

---

### Requirement: Shared registry contract

Every strategy folder SHALL implement its `registry.py` as a lazy registry.
This applies to `chunking/`, `retrieval/`, `metadata/`,
`providers/embeddings/`, and `providers/llm/`. Each `registry.py` SHALL be a
`Dict[str, str]` mapping strategy names to lazy `"module:attr"` import
strings, resolved and cached on first `get()`. Registration at module level
SHALL record import strings, not live objects, so importing a registry does
not eagerly import strategy modules.

#### Scenario: Lazy resolution

- **WHEN** a registry module is imported
- **THEN** no strategy module MUST be imported as a side effect

#### Scenario: Unknown strategy error

- **WHEN** `get()` is called with an unregistered name
- **THEN** it MUST raise `KeyError` listing the available strategy names

#### Scenario: Missing optional dependency degrades gracefully

- **WHEN** a strategy whose optional dependency is not installed is resolved
  via `get()`
- **THEN** it MUST raise an `ImportError` naming the strategy and the missing
  dependency context, without breaking other strategies

#### Scenario: Adding a strategy touches one file

- **WHEN** a new strategy is added
- **THEN** it MUST require only a new strategy file plus one `register()`
  line in that folder's `registry.py`, with no other file modified

---

### Requirement: Legacy constant deprecation shim

The system SHALL provide a PEP 562 module-level `__getattr__` on the legacy
`rag_mcp.config` module so that pre-refactor constant reads (`TOP_K`,
`CHUNK_SIZE`, `RERANK_ENABLED`, `EMBED_MODEL`, and the other module-level
constants) resolve to the structured `Settings` values with a
`DeprecationWarning`. After the migration, no module-level constant read
SHALL remain outside `config.py` and `compose.py`.

#### Scenario: Legacy constant reads keep working

- **WHEN** code executes `from rag_mcp.config import TOP_K` (or another
  legacy constant)
- **THEN** the import MUST succeed and return the value from the structured
  settings
- **AND** a `DeprecationWarning` MUST be emitted naming the structured access
  path

#### Scenario: Constant surface fully migrated

- **WHEN** the codebase is searched for legacy constant imports at phase
  acceptance
- **THEN** no constant read MUST exist outside `config.py`/`compose.py`
  except through the deprecation shim in third-party or experimental code
  awaiting migration

---

### Requirement: Same environment variable interface

The refactor SHALL preserve every existing environment variable name and its
effective default. Migration to structured settings SHALL NOT rename,
remove, or change the meaning of any documented env var.

#### Scenario: Env vars behave identically

- **WHEN** any previously supported environment variable (e.g. `EMBED_MODEL`,
  `CHUNK_SIZE`, `RERANK_ENABLED`, `TOP_K`) is set
- **THEN** the resolved settings MUST reflect the same value and default as
  before the refactor
