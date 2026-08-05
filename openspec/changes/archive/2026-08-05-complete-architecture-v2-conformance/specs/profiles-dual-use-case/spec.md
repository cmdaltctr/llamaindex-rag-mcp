## MODIFIED Requirements

### Requirement: Named profile bundles

The system SHALL provide three version-controlled YAML profile bundles under
`config/profiles/`: `documents.yaml` (document grounding), `codebase.yaml`
(codebase context), and `hybrid.yaml` (per-collection policy). Operational
bundles SHALL express their overrides as **nested blocks** keyed by subpackage
(`retrieval:`, `chunking:`, `metadata:`) using the same field names as the
subpackage Pydantic models, and SHALL be validated against those models.
Flat, environment-variable-style keys SHALL NOT be accepted. Bundles SHALL
contain no credentials.

#### Scenario: Bundles use the nested schema

- **WHEN** any file under `config/profiles/` is loaded
- **THEN** its retrieval, chunking, and metadata overrides MUST appear as
  nested mappings under `retrieval:`, `chunking:`, and `metadata:`
- **AND** a bundle using flat SCREAMING_SNAKE keys MUST be rejected with a
  validation error naming the offending key

#### Scenario: Documents profile values

- **WHEN** the `documents` profile is loaded
- **THEN** it MUST resolve to: markdown chunking fallback, reranker enabled,
  `top_k=10`, dense-only retrieval (no hybrid), category taxonomy

#### Scenario: Codebase profile values

- **WHEN** the `codebase` profile is loaded
- **THEN** it MUST resolve to: code chunking fallback, reranker disabled,
  `top_k=20`, hybrid retrieval (dense + BM25 + RRF), file_type taxonomy

#### Scenario: Hybrid selector carries no levers

- **WHEN** `hybrid.yaml` is loaded
- **THEN** it MUST declare only `default_profile`
- **AND** it MUST NOT declare `retrieval:`, `chunking:`, `ingestion:`, or
  `metadata:` blocks

#### Scenario: Malformed hybrid selector fails at construction, not first use

- **WHEN** `hybrid.yaml` declares a lever block
- **THEN** the failure MUST surface when the profile resolver is constructed
  (equivalently, at settings resolution)
- **AND** it MUST NOT be deferred to the first collection lookup or the first
  query, so a misconfigured deployment cannot start and appear healthy

#### Scenario: Invalid bundle rejected

- **WHEN** a profile bundle fails schema validation
- **THEN** the system MUST fail at resolution time with a clear validation
  error naming the offending key

---

### Requirement: Two-tier settings resolution

The system SHALL resolve settings in two tiers. Tier 1 components (embedder,
chunking and reader registries, vector store handle, reranker model) SHALL
be constructed once at startup in `compose.py` and shared across
collections. Tier 2 levers (reranker on/off, `top_k`, hybrid/RRF, chunking
fallback for ambiguous types, metadata taxonomy mode) SHALL be resolved per
operation by a `ProfileResolver` that returns a frozen `EffectiveSettings`,
which SHALL be passed as a parameter to `search()` and `ingest_path_async()`
and propagated to every module they call. Core operations SHALL NOT read
global state for any lever, Tier 1 or Tier 2. The `ProfileResolver` SHALL
receive the server-wide default profile name by injection and SHALL NOT read
it from a settings singleton.

#### Scenario: Per-query reranker decision

- **WHEN** a query targets a `documents`-profile collection and then a
  `codebase`-profile collection in the same process
- **THEN** the reranker model MUST be loaded at most once (Tier 1)
- **AND** the decision to apply it MUST differ per query according to each
  collection's resolved profile (Tier 2)

#### Scenario: Resolver falls back to server default

- **WHEN** `ProfileResolver.resolve()` is called for a collection with no
  profile tag
- **THEN** it MUST return the server-wide default profile's effective
  settings

#### Scenario: Resolver takes its default by injection

- **WHEN** `ProfileResolver` is constructed
- **THEN** the server-wide default profile name MUST be supplied by the caller
- **AND** `core/profiles/resolver.py` MUST NOT import a settings singleton

#### Scenario: Resolved settings reach the leaves

- **WHEN** an operation runs with an `EffectiveSettings` produced by the
  resolver
- **THEN** every module in the call chain — chunker, dense retriever, fusion,
  policy, reranker, metadata extractor, vector store — MUST read its knobs from
  that instance
- **AND** none MUST consult a process-wide settings object
