## Purpose

Define deterministic, configurable community partitioning shared by codebase and document graphs while keeping optional algorithms outside the base installation.

## ADDED Requirements

### Requirement: Community algorithm is configurable
The system SHALL support `louvain` and `leiden` as community-detection strategy names. The default SHALL remain `louvain` so existing installations require no new dependency.

#### Scenario: Default installation builds communities
- **WHEN** no community algorithm is configured
- **THEN** the system SHALL select Louvain
- **AND** the operation SHALL require only base-install dependencies

#### Scenario: Leiden is selected explicitly
- **WHEN** the configured community algorithm is `leiden`
- **THEN** both codebase and document graphs SHALL use the registered Leiden strategy

#### Scenario: Unknown strategy is configured
- **WHEN** the configured community algorithm is not a registered name
- **THEN** startup SHALL fail before graph construction
- **AND** the error SHALL list the available community strategies

### Requirement: Community partitions are deterministic
Every registered community strategy SHALL accept the configured integer seed and use it for algorithm randomness.

#### Scenario: Same graph and seed are repeated
- **WHEN** the same graph is partitioned repeatedly with the same algorithm, settings, and seed
- **THEN** every run SHALL return equivalent node memberships

#### Scenario: Louvain uses the default seed
- **WHEN** Louvain runs without an operator-supplied seed
- **THEN** it SHALL use seed `0`

### Requirement: Community strategies share one partition contract
Every community strategy SHALL return a flat partition in which each input node appears in exactly one non-empty community. Algorithm-specific result objects SHALL not escape the strategy boundary.

#### Scenario: A graph is partitioned successfully
- **WHEN** a registered strategy partitions a graph with at least five nodes
- **THEN** the union of returned communities SHALL equal the input node set
- **AND** no node SHALL appear in more than one returned community

#### Scenario: A small graph bypasses partitioning
- **WHEN** a graph contains fewer than five nodes
- **THEN** the existing single-community behaviour SHALL remain unchanged

### Requirement: Leiden remains an optional capability
The base installation SHALL not install Leiden-specific packages. An explicit Leiden selection SHALL require the optional Leiden extra and SHALL not silently fall back to Louvain when the dependency is absent.

#### Scenario: Leiden dependency is installed
- **WHEN** Leiden is configured and its optional dependency is available
- **THEN** startup SHALL validate the strategy successfully
- **AND** graph construction SHALL use Leiden

#### Scenario: Leiden dependency is absent
- **WHEN** Leiden is configured and its optional dependency is unavailable
- **THEN** startup SHALL fail with an actionable installation instruction
- **AND** no graph SHALL be built using a different algorithm

### Requirement: Graph consumer behaviour is preserved
Changing the partition strategy SHALL not change community labels, community output models, hub detection, bridge detection, cross-link calculation, cache policy, or the no-LLM graph-construction rule.

#### Scenario: Codebase graph uses either strategy
- **WHEN** the codebase graph receives a valid flat partition
- **THEN** it SHALL produce the existing `Community` output structure and deterministic labels

#### Scenario: Document graph uses either strategy
- **WHEN** the document graph receives a valid flat partition
- **THEN** it SHALL produce the existing `DocCommunity` output structure and category labels

#### Scenario: Community detection executes
- **WHEN** either registered strategy partitions a graph
- **THEN** the partition stage SHALL make no LLM call
