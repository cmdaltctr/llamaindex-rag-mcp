# Spec Delta

## MODIFIED Requirements

### Requirement: Embedding-provider selection is engine scoped

An engine SHALL use its own embedding provider and model. Two engines in one
process SHALL be able to use different providers or models simultaneously.

This retires the process-scoped limit recorded in ADR-047 decision 7, which
existed because the underlying library exposes one process-global embedding
model. The engine SHALL NOT depend on that global for its own operations.

#### Scenario: Two engines, two embedding models

- **GIVEN** engine A configured with one embedding model and engine B with
  another
- **WHEN** each ingests into its own collection in one process
- **THEN** each collection's vectors SHALL be produced by that engine's model
- **AND** neither engine's embeddings SHALL be produced by the other's model

#### Scenario: Interleaved operations stay correct

- **GIVEN** two engines with different embedding models
- **WHEN** their ingest and search operations interleave in one process
- **THEN** each operation SHALL use its own engine's model
- **AND** no operation SHALL observe a model swapped in by the other

#### Scenario: Embedding identity still guards the collection

- **WHEN** an engine queries a collection stamped with a different embedding
  identity
- **THEN** the existing embedding-identity guard SHALL reject the operation
- **AND** the rejection SHALL name the mismatch

#### Scenario: Different engines may target different providers

- **GIVEN** two collections requiring different embedding providers
- **WHEN** the caller constructs one explicitly configured Engine for each
- **THEN** both SHALL operate concurrently in one process
- **AND** one Engine MAY also serve both collections when their profiles name
  the two providers (see "One Engine routes embedding models by collection
  profile")

## ADDED Requirements

### Requirement: One Engine routes embedding models by collection profile

One Engine SHALL be able to serve collections whose profiles use different embedding models at the same time. The Engine SHALL choose the embedder for each operation from the collection's profile. The provider connection settings (URLs and keys) SHALL stay host configuration. A profile SHALL choose only the provider and the model name.

#### Scenario: Two collections with two models in one Engine

- **GIVEN** collection `papers` uses model A and collection `notes` uses model B
- **WHEN** one Engine ingests into both collections and searches both
- **THEN** each collection's vectors and queries SHALL come from its own model
- **AND** no operation SHALL use the other collection's model

#### Scenario: Interleaved operations keep their models

- **GIVEN** collection `papers` uses model A and collection `notes` uses model B
- **WHEN** a search of `papers` and an ingest into `notes` run at the same time in one Engine
- **THEN** the search SHALL use model A
- **AND** the ingest SHALL use model B

#### Scenario: A profile cannot change the provider URL

- **GIVEN** a user profile that chooses provider `ollama`
- **WHEN** the Engine builds the embedder for that profile
- **THEN** the embedder SHALL use the host's `OLLAMA_BASE_URL`
