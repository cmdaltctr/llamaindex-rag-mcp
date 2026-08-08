## ADDED Requirements

### Requirement: Every LLM sub-provider is reachable through the provider registry

Selecting an LLM sub-provider SHALL resolve through the LLM provider registry.
No selection path SHALL construct a provider client inline with a hardcoded
endpoint.

This applies uniformly to local and cloud sub-providers. A sub-provider that is
selectable by configuration but absent from the registry is a defect, regardless
of whether the selection currently works.

#### Scenario: Cloud sub-provider is selected

- **WHEN** configuration selects the `openrouter` cloud backend for metadata
  extraction
- **THEN** the client is obtained from the LLM provider registry
- **AND** the endpoint comes from configuration rather than a literal in the
  calling module

#### Scenario: A selectable sub-provider is missing from the registry

- **WHEN** a sub-provider name is accepted by configuration validation
- **AND** that name is not registered in the LLM provider registry
- **THEN** the backend symmetry check fails

### Requirement: Metadata backends are symmetric across registries

Every metadata extraction backend that delegates to an LLM sub-provider SHALL be
registered in both the metadata extraction registry and the LLM provider
registry, under the same name.

#### Scenario: Symmetry holds for all LLM-backed backends

- **WHEN** the backend symmetry check runs
- **THEN** `ollama`, `llamacpp`, and `openrouter` are each present in both
  registries under the same name

#### Scenario: A backend is added to one registry only

- **WHEN** a new LLM-backed backend is registered in the metadata registry
- **AND** it is not registered in the LLM provider registry
- **THEN** the backend symmetry check fails, naming the missing registration
