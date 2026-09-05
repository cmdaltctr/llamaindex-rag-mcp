# config-composition-root Specification

## Purpose
Defines the three-layer configuration architecture — packaged defaults,
environment overrides, and per-collection profile overlays — and the
resolution precedence between them. ``compose.py`` is the single
construction surface: it resolves settings once, fails fast on
construction and provider-selection errors, and hands every operation a
frozen effective-settings object. No layer below the composition root
reads configuration on its own.

## Requirements
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

### Requirement: Composition root fails fast on construction and provider-selection errors

`compose.py::ensure_runtime_setup` SHALL raise instead of logging a warning
and continuing when `build_embed_model` or `build_vector_store` fails. A
process that reports successful startup MUST have a working embed model and
a registered default vector store — leaving either unset and continuing
turns a construction failure into a confusing downstream error (or silent
misbehaviour) instead of a clear startup failure.

Entry points call `ensure_runtime_setup()` explicitly during startup, so
this failure surfaces when the startup path runs, not at import time.
Importing `compose.py` has no runtime side effects. A traceback plus a
non-zero exit is loud, which is the point.

`config/__init__.py`'s provider-selection validation SHALL raise
`ValueError` — which pydantic surfaces as a `ValidationError` subclassing
`ValueError` when raised inside a model validator — naming the offending
value and the accepted values, instead of
logging a warning and clamping to a default, for: `EMBED_PROVIDER`,
`METADATA_LLM_PROVIDER`, `LOCAL_BACKEND`, `CLOUD_BACKEND`,
`RETRIEVAL__HYBRID_SPARSE_BACKEND`, and an unrecognised `DOCUMENT_BACKEND`
value. This matches the existing `VECTOR_STORE` unknown-value contract
(`vectordb-abstraction`, ADR-034) and closes the gap left by ADR-029: an
unrecognised provider selection is a misconfiguration a user should see
immediately, not a warning buried in a log stream the MCP transport makes
invisible.

This requirement does NOT apply to the two settings that degrade
deliberately by design: `DOCUMENT_BACKEND=azure` with missing Azure
credentials SHALL still fall back to local processing (required by the
cloud-opt-in-with-local-fallback hard boundary), and an unrecognised
`RAG_PROFILE` SHALL still fall back to `documents` (required by the profile
system's own degrade-gracefully design). `PDF_READER`'s unknown-value
handling is unchanged — it is governed by the `pdf-reader` capability.

#### Scenario: Embed model construction failure fails startup

- **GIVEN** `build_embed_model` raises `ImportError` or `ValueError`
- **WHEN** `ensure_runtime_setup` runs
- **THEN** the exception SHALL propagate and startup SHALL fail
- **THEN** no warning-and-continue path SHALL leave `LlamaIndexSettings.embed_model` unset while reporting success

#### Scenario: Vector store construction failure fails startup

- **GIVEN** `build_vector_store` raises `ImportError` or `ValueError`
- **WHEN** `ensure_runtime_setup` runs
- **THEN** the exception SHALL propagate and startup SHALL fail
- **THEN** no warning-and-continue path SHALL leave the default vector store unregistered while reporting success

#### Scenario: Provider validation runs before dependent validation

- **GIVEN** `EMBED_PROVIDER` is set to an unrecognised value
- **AND** `EMBED_MODEL` is unset, so the `EMBED_MODEL`-required validator would also fail
- **WHEN** settings resolution runs
- **THEN** the raised error SHALL name `EMBED_PROVIDER` as the offending setting, not `EMBED_MODEL`

#### Scenario: Unknown METADATA_LLM_PROVIDER fails startup

- **WHEN** `METADATA_LLM_PROVIDER` is set to a value other than `local` or `cloud`
- **THEN** settings resolution SHALL raise `ValueError` naming the offending value
- **THEN** the system SHALL NOT fall back to `local`

#### Scenario: Unknown LOCAL_BACKEND fails startup

- **WHEN** `LOCAL_BACKEND` is set to a value other than `llamacpp` or `ollama`
- **THEN** settings resolution SHALL raise `ValueError` naming the offending value
- **THEN** the system SHALL NOT fall back to `llamacpp`

#### Scenario: Unknown CLOUD_BACKEND fails startup

- **WHEN** `CLOUD_BACKEND` is set to a value other than `openrouter`
- **THEN** settings resolution SHALL raise `ValueError` naming the offending value
- **THEN** the system SHALL NOT fall back to `openrouter`

#### Scenario: Unknown RETRIEVAL__HYBRID_SPARSE_BACKEND fails startup

- **WHEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND` is set to a non-empty value other than `auto`, `native`, or `bm25`
- **THEN** settings resolution SHALL raise `ValueError` naming the offending value
- **THEN** the system SHALL NOT fall back to `bm25`
- **AND** this is distinct from the `native`-requested-but-unsupported capability fallback, which is unchanged (`hybrid-retrieval`)

#### Scenario: Empty or whitespace-only RETRIEVAL__HYBRID_SPARSE_BACKEND uses the default

- **WHEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND` is set to an empty string or whitespace-only value
- **THEN** settings resolution SHALL reset the field to its declared default (`bm25`)
- **THEN** settings resolution SHALL NOT raise
- **AND** this rule applies to all six provider-selection settings uniformly (task 6.9)

#### Scenario: Unrecognised DOCUMENT_BACKEND value fails startup

- **WHEN** `DOCUMENT_BACKEND` is set to a value other than `local` or `azure`
- **THEN** settings resolution SHALL raise `ValueError` naming the offending value
- **THEN** the system SHALL NOT fall back to `local`

#### Scenario: DOCUMENT_BACKEND=azure with missing credentials still degrades to local

- **GIVEN** `DOCUMENT_BACKEND=azure` is set
- **WHEN** `AZURE_DOC_INTELLIGENCE_ENDPOINT` or `AZURE_DOC_INTELLIGENCE_KEY` is missing
- **THEN** the system SHALL log a WARNING and fall back to local processing
- **THEN** this scenario SHALL NOT raise, unlike an unrecognised `DOCUMENT_BACKEND` value

#### Scenario: Unrecognised RAG_PROFILE still degrades to documents

- **GIVEN** `RAG_PROFILE` is set to a value outside `documents`, `codebase`, `hybrid`
- **WHEN** settings resolution runs
- **THEN** the system SHALL log a WARNING and fall back to `documents`
- **THEN** this scenario SHALL NOT raise

### Requirement: Storage mode SHALL be resolved at the composition root

Configuration SHALL parse and validate Chroma mode and connection values as
pure data. `compose.build_vector_store(settings)` SHALL pass the resolved
mode and connection values to the registered Chroma factory. The config
package SHALL NOT import ChromaDB or construct a client.

#### Scenario: Local store construction

- **WHEN** resolved settings select local mode
- **THEN** the composition root SHALL pass the configured persist directory
  to the Chroma factory

#### Scenario: Cloud store construction

- **WHEN** resolved settings select cloud mode
- **THEN** the composition root SHALL pass the API key and optional
  tenant/database identifiers to the Chroma factory
- **AND** it SHALL NOT pass the local persist directory as an active storage target

#### Scenario: No credentials in effective operation settings

- **WHEN** the composition root builds `EffectiveSettings` for core operations
- **THEN** cloud API credentials SHALL NOT be copied into that value object
- **AND** credentials SHALL remain confined to construction-time settings

### Requirement: Runtime setup SHALL validate explicit cloud selection

Runtime setup SHALL construct and validate the selected cloud connection
before registering the default vector store. Failure SHALL leave no partially
registered default store.

#### Scenario: Cloud validation fails during startup

- **WHEN** cloud client construction or its connection check raises
- **THEN** runtime setup SHALL return or raise an actionable startup failure
- **AND** the process default store SHALL remain unset

### Requirement: Settings SHALL resolve one LanceDB default with source provenance

After the qualification pause gate passes, every executable default surface
SHALL agree on `lancedb`, including the typed settings resolver, YAML defaults
and `EffectiveSettings`. Resolution SHALL retain whether the backend came from
explicit user input or shipped defaults.

#### Scenario: Default resolution

- **GIVEN** no backend is supplied by constructor/CLI, environment or `.env`
- **WHEN** settings are resolved
- **THEN** the effective selector MUST be `lancedb`
- **AND** its provenance MUST be recorded as a shipped default

#### Scenario: Explicit selection is preserved

- **GIVEN** the user explicitly supplies a supported backend
- **WHEN** settings are resolved
- **THEN** the effective selector MUST equal that backend
- **AND** its provenance MUST be explicit

#### Scenario: Default surfaces agree

- **WHEN** the typed settings model, YAML defaults, effective-settings model and environment example are inspected by the drift test
- **THEN** all MUST identify LanceDB as the default

### Requirement: compose.py SHALL remain the sole vector-store constructor

Only `compose.py` SHALL resolve the selected registry entry and instantiate a
vector store. Core accessors and consumers SHALL receive or return injected
instances and SHALL not construct fallback stores.

#### Scenario: Uncomposed process-wide access

- **GIVEN** composition has not installed a process-wide store
- **WHEN** an accessor is called
- **THEN** it MUST fail clearly
- **AND** it MUST NOT import settings, compose or a concrete backend

### Requirement: Chroma compatibility SHALL be validated before credentials

Chroma settings SHALL be cross-validated against the selected backend before
credential completeness. Credential values SHALL never appear in errors.

#### Scenario: Cloud mode and LanceDB with missing API key

- **GIVEN** `VECTOR_STORE=lancedb`
- **AND** `CHROMA_MODE=cloud`
- **AND** no Chroma API key is supplied
- **WHEN** settings are validated
- **THEN** the error MUST state that Chroma settings require `VECTOR_STORE=chroma`
- **AND** it MUST NOT report the missing-key error first

#### Scenario: Partial or whitespace credentials with LanceDB

- **GIVEN** LanceDB is selected
- **AND** any Chroma credential remains non-empty after trimming
- **WHEN** settings are validated
- **THEN** backend mismatch MUST be reported without exposing the value

### Requirement: Configuration documentation SHALL reflect installation and rollback

Current documentation SHALL state LanceDB as the qualified default, Chroma as
an optional explicit backend, recognised-legacy fail-closed behaviour, and the
data-aware rollback procedure.

#### Scenario: Operator documentation is inspected

- **WHEN** active configuration, migration and rollback guidance is read
- **THEN** it MUST provide source-checkout and packaged-extra Chroma installation forms
- **AND** rollback MUST require pinning and verifying LanceDB before reverting software
- **AND** historical ADRs MUST be marked superseded by link rather than rewritten

