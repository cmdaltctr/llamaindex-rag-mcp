## MODIFIED Requirements

### Requirement: Three-layer configuration architecture

The system SHALL separate configuration into three layers: a typed settings
resolver (`config.py`), a composition root (`compose.py`), and dependency
injection in every other module. `config.py` SHALL contain only settings
data, parsing, and validation — zero object construction (no `_build_*()`
methods) and zero runtime capability probing. `config.py` SHALL NOT import
from any `core/` module other than the pure-data subpackage `settings`
models, and SHALL remain at or below approximately 150 lines. `compose.py`
SHALL be the only module that instantiates provider and pipeline objects and
the only module that resolves capability probes. All other modules SHALL
receive their dependencies and their settings as parameters and SHALL NOT
import concrete provider classes or a settings singleton.

#### Scenario: config.py is construction-free

- **WHEN** `config.py` is inspected after the refactor
- **THEN** it MUST NOT contain any provider or pipeline object construction
- **AND** it MUST expose a validated, immutable resolved `Settings` object via
  `get_settings()` with no module-level instantiation

#### Scenario: config.py is business-logic-free

- **WHEN** `config.py` imports are inspected
- **THEN** the only `core/` imports MUST be the subpackage `settings` models
- **AND** capability probes such as native-sparse detection or PDF backend
  probing MUST NOT appear

#### Scenario: config.py meets its size target

- **WHEN** `src/rag_mcp/config/__init__.py` is measured
- **THEN** it MUST be at or below approximately 150 lines

#### Scenario: compose.py is the single construction site

- **WHEN** the codebase is searched for provider instantiation
- **THEN** all instantiation MUST occur in `compose.py`
- **AND** `compose.py` MUST build objects by resolving registries against the
  resolved `Settings`

#### Scenario: Components receive dependencies

- **WHEN** any `core/` component that consumes a constructed object (provider,
  reranker, vector store) is instantiated in a test
- **THEN** the test MUST pass that object as a parameter, without mocking the
  global config and without constructing it inside the component
- **AND** effective settings MUST be passed as an `EffectiveSettings`
  parameter, so tests override knobs by constructing that object rather than
  by patching a settings singleton

---

### Requirement: Settings resolution precedence

The system SHALL resolve the effective `Settings` by layering sources in a
documented precedence order: subpackage model defaults (lowest),
`config/defaults.yaml`, the selected YAML profile bundle when present,
environment variables and `.env`, then explicit per-operation options
(highest). `config/defaults.yaml` and profile bundles SHALL be expressed as
nested mappings keyed by subpackage block (`chunking:`, `retrieval:`,
`metadata:`) plus top-level cross-cutting keys, and SHALL be deep-merged
rather than flattened. They SHALL contain no secrets, provider keys, or
machine-specific absolute paths. YAML files SHALL be loaded via
`importlib.resources` so they resolve correctly in both development
(repository root) and installed (site-packages) contexts, and SHALL be
declared as package data in `pyproject.toml`.

#### Scenario: Environment overrides YAML

- **WHEN** a setting is present in both `config/defaults.yaml` and the
  process environment
- **THEN** the environment value MUST win

#### Scenario: Nested YAML is deep-merged

- **WHEN** `config/defaults.yaml` declares `retrieval.top_k` and the selected
  profile declares only `retrieval.rerank_enabled`
- **THEN** the resolved settings MUST carry both values
- **AND** the profile MUST NOT replace the whole `retrieval` block

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
`config.py`, `compose.py`, or any other `core/` module. The root `Settings`
model SHALL compose these models as **nested fields** (`chunking:`,
`retrieval:`, `metadata:`) rather than by multiple inheritance, and SHALL
declare `env_nested_delimiter` so each nested field is addressable from the
environment.

#### Scenario: No upward imports

- **WHEN** the import-linter CI check runs
- **THEN** it MUST fail if any subpackage `settings.py` imports from
  `config.py`, `compose.py`, or a sibling `core/` module

#### Scenario: Root settings composes by nesting

- **WHEN** the root `Settings` model is inspected
- **THEN** `chunking`, `retrieval`, and `metadata` MUST be nested model fields
- **AND** the class MUST NOT inherit from the subpackage settings models

#### Scenario: Defaults live near their code

- **WHEN** a new configuration knob is added for a subpackage
- **THEN** its default MUST be declared in that subpackage's `settings.py`
  and surfaced through the root `Settings` model's nested field

---

### Requirement: Shared registry contract

Every strategy folder SHALL implement its `registry.py` as a lazy registry
and SHALL be the **only** dispatch mechanism used by production code for that
concern. This applies to `chunking/`, `retrieval/`, `metadata/`,
`providers/embeddings/`, and `providers/llm/`. Each `registry.py` SHALL map
strategy names to lazy `"module:attr"` import strings, resolved and cached on
first `get()`, and SHALL expose `register(name, import_path)`, `get(name)`,
and `available()` as its public API. The underlying mapping SHALL be private.
Registration at module level SHALL record import strings, not live objects,
so importing a registry does not eagerly import strategy modules.

#### Scenario: Lazy resolution

- **WHEN** a registry module is imported
- **THEN** no strategy module MUST be imported as a side effect

#### Scenario: Registries are the production dispatch path

- **WHEN** the chunking dispatcher, the metadata extractor orchestrator, or the
  retrieval pipeline selects a strategy
- **THEN** it MUST resolve the strategy through `registry.get(name)`
- **AND** it MUST NOT use eager top-level imports of concrete strategy modules
  or an if/elif chain over strategy names

#### Scenario: Registration goes through the helper

- **WHEN** a strategy is registered
- **THEN** it MUST be registered by calling `register(name, import_path)`
- **AND** no module MUST mutate a registry's mapping directly

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

## ADDED Requirements

### Requirement: Structured environment variable interface

Environment variables for subpackage settings SHALL be addressed through the
nested delimiter (`CHUNKING__*`, `INGESTION__*`, `RETRIEVAL__*`, `METADATA__*`).
Cross-cutting settings that are not owned by a subpackage (for example
`EMBED_MODEL`, `CHROMA_PERSIST_DIR`, `COLLECTION_NAME`, `VECTOR_STORE`,
`PDF_READER`, `DOCUMENT_BACKEND`, `RAG_PROFILE`, and provider credentials)
SHALL keep their existing flat names. This is a **breaking change** to the
configuration surface: the pre-v2 flat subpackage names SHALL NOT be accepted
as aliases.

Unrecognised configuration MUST NOT be silently discarded. Two guards SHALL
enforce this, with distinct scopes:

1. Each subpackage settings model SHALL reject unknown fields
   (`extra="forbid"`), so any unexpected key under a nested prefix — including
   a typo or a name nobody enumerated — fails at settings resolution naming the
   offending field. The root settings model SHALL remain permissive, because it
   legitimately coexists with unrelated process environment entries.
2. Startup SHALL additionally fail with an actionable error when a known
   pre-v2 flat subpackage name is present in the environment, naming its nested
   replacement. This guard is required because a bare flat name never reaches a
   subpackage model and therefore cannot be caught by guard 1.

#### Scenario: Nested env var applies

- **WHEN** `RETRIEVAL__TOP_K=20` is set
- **THEN** the resolved settings MUST report `retrieval.top_k == 20`

#### Scenario: Legacy flat name is rejected loudly

- **WHEN** the pre-v2 `TOP_K=20` is set and `RETRIEVAL__TOP_K` is not
- **THEN** startup MUST fail with an error naming `RETRIEVAL__TOP_K` as the
  replacement
- **AND** the legacy value MUST NOT be silently applied or silently ignored

#### Scenario: Unknown nested key is rejected loudly

- **WHEN** an unrecognised key under a nested prefix is set, such as
  `RETRIEVAL__TOPK=20` or `CHUNKING__NOT_A_FIELD=1`
- **THEN** settings resolution MUST fail with an error naming the offending
  field
- **AND** the value MUST NOT be silently discarded, even though the name is
  absent from the known-legacy enumeration

#### Scenario: Unrelated process environment entries are tolerated

- **WHEN** the process environment contains variables unrelated to this
  application, such as `PATH` or `HOME`
- **THEN** settings resolution MUST succeed
- **AND** the root settings model MUST NOT reject them

#### Scenario: Ingestion concurrency is addressed under its own prefix

- **WHEN** `INGESTION__EMBED_CONCURRENCY=4` is set
- **THEN** the resolved settings MUST report `ingestion.embed_concurrency == 4`
- **AND** `CHUNKING__EMBED_CONCURRENCY` MUST be rejected as an unknown field

#### Scenario: Cross-cutting names unchanged

- **WHEN** `EMBED_MODEL`, `CHROMA_PERSIST_DIR`, or `RAG_PROFILE` is set
- **THEN** the resolved settings MUST reflect the value under the same name as
  before v2.0.0

#### Scenario: Documentation matches the surface

- **WHEN** `.env.example` and the configuration guide are read
- **THEN** every documented variable name MUST match the name the resolver
  actually accepts

## REMOVED Requirements

### Requirement: Legacy constant deprecation shim

**Reason**: The PEP 562 `__getattr__` alias table on `rag_mcp.config` was a
migration aid for the Phase 2 config surface change. It has no remaining
production consumers, it keeps a second live configuration path alongside the
structured `Settings` object, and the nested schema in v2.0.0 makes a flat
constant surface meaningless. Retaining it would preserve exactly the
"documented target plus live legacy path" pattern this change exists to end.

**Migration**: Replace `from rag_mcp.config import <CONSTANT>` with the
injected `EffectiveSettings` parameter for `core/` code, or with
`get_settings()` in `compose.py`. For each removed constant the replacement is
the corresponding nested field: `TOP_K` → `settings.retrieval.top_k`,
`CHUNK_SIZE` → `settings.chunking.chunk_size`, `METADATA_EXTRACTION_MODE` →
`settings.metadata.extraction_mode`, and so on. ADR-037 carries the complete
mapping table. Environment-variable users migrate per the structured
environment variable interface requirement above.

### Requirement: Same environment variable interface

**Reason**: Superseded by "Structured environment variable interface". The
nested `Settings` composition mandated by the agreed architecture
(`env_nested_delimiter`) necessarily renames every subpackage-owned variable,
so a requirement that no documented variable is renamed can no longer hold.

**Migration**: Rename subpackage variables in `.env` and deployment
configuration to their `CHUNKING__*`, `RETRIEVAL__*`, `METADATA__*` forms.
Cross-cutting variable names and every effective default value are unchanged,
so the only migration action is renaming. The startup tripwire names the
replacement for any legacy key it finds.
