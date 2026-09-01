## MODIFIED Requirements

### Requirement: Embedding-provider swappability scope is explicit

Embedding-provider selection SHALL be **engine scoped**. Each engine owns its
embedding provider and model, and two engines in one process MAY use different
providers or models simultaneously. The vector-store abstraction SHALL
document this scope accurately and MUST NOT imply guarantees the runtime does
not implement.

This supersedes the previous process-scoped model, which existed because the
underlying library exposes one process-global embed model and the composition
root assigned it at startup (ADR-047 decision 7). With composition owned by
the engine, that global is no longer the mechanism by which an operation's
embedder is selected.

#### Scenario: Different deployment provider
- **WHEN** a process starts with a different registered embedding provider
- **THEN** the composition root MAY construct the new provider and stores SHALL operate through the same contract

#### Scenario: Concurrent per-collection provider request

- **WHEN** two engines in one process are configured with different embedding
  providers or models
- **THEN** each engine's operations SHALL use its own model
- **AND** the previously documented unsupported boundary SHALL no longer
  apply, with documentation and tests updated to match

#### Scenario: Mismatched embedding identity is still rejected

- **WHEN** an engine operates on a collection stamped with a different
  embedding identity
- **THEN** the existing embedding-identity guard SHALL reject the operation
- **AND** engine scoping SHALL NOT weaken that guard
