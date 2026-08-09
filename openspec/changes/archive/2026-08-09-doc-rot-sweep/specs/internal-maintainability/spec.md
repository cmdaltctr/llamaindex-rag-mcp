## ADDED Requirements

### Requirement: Documented source paths resolve

Documentation that cites a source file path SHALL cite a path that exists.
Every `src/rag_mcp/**/*.py` path referenced in `docs/guides/` or
`tests/TEST_README.md` SHALL resolve to a file on disk. Records under
`docs/adr/` are EXCLUDED: an ADR legitimately cites paths that were correct
when the decision was taken and have since moved.

#### Scenario: A guide cites a path deleted by a refactor

- **WHEN** a guide references `src/rag_mcp/config.py` after the v2 split moved it to `src/rag_mcp/config/__init__.py`
- **THEN** the documentation reference check SHALL fail
- **THEN** the failure SHALL name the citing file, its line, and the unresolved path

#### Scenario: A historical ADR cites a since-deleted path

- **WHEN** `docs/adr/026-provider-registry-and-openrouter.md` references `src/rag_mcp/metadata_extractor.py`, a v1 module deleted in v2.0.0
- **THEN** the check SHALL NOT fail
- **THEN** the ADR SHALL remain unmodified, its accuracy carried by a dated forward note instead

### Requirement: Documented provider names match the live registries

The provider names listed in `docs/guides/providers.md` SHALL match the names
registered in the embedding and LLM provider registries exactly. The guide
SHALL delimit these names in a machine-readable block so the check reads a
declared list rather than inferring one from prose.

#### Scenario: A provider is added without updating the guide

- **WHEN** a new provider is registered in `core/providers/embeddings/registry.py` via `register()`
- **AND** `docs/guides/providers.md` is not updated to list it
- **THEN** the registry contract test SHALL fail
- **THEN** the failure SHALL name the provider present in the registry but absent from the guide

#### Scenario: The guide names a provider that no longer exists

- **WHEN** `docs/guides/providers.md` lists a provider name absent from `available()`
- **THEN** the registry contract test SHALL fail
- **THEN** the failure SHALL name the provider documented but unregistered

#### Scenario: Guide and registries agree

- **WHEN** the documented names equal `embed_registry.available()` for embeddings and `llm_registry.available()` for LLMs
- **THEN** the check SHALL pass without requiring any suppression or allowlist entry
