# strategy-registration-governance Specification

## Purpose
Define when configurable implementations require registry dispatch and distinguish those strategies from external capability adapters, factories, and single implementations.
## Requirements
### Requirement: Registry eligibility is explicit
An implementation family SHALL use a registry when configuration selects by name between two or more interchangeable implementations that satisfy one shared contract. A single external capability adapter, availability probe, or ordered fallback factory SHALL not require registration solely because it lives under `integrations/`.

Whether an implementation is `native` SHALL describe dependency availability only. It SHALL NOT decide registry eligibility. Native and optional implementations in the same configured strategy family SHALL use the same registry contract.

#### Scenario: Multiple interchangeable algorithms exist
- **WHEN** configuration selects between Louvain and Leiden using one community partition contract
- **THEN** both implementations SHALL be exposed through the community strategy registry

#### Scenario: A single capability adapter exists
- **WHEN** an integration provides one optional external capability without a configured interchangeable implementation
- **THEN** it SHALL remain a direct integration or factory
- **AND** the audit SHALL record why registry dispatch is not applicable

#### Scenario: A native implementation belongs to a configured family
- **WHEN** a base-install implementation and optional implementations are selected by the same configuration field
- **THEN** the native implementation SHALL be registered alongside the optional implementations
- **AND** its base-install status SHALL remain visible in the inventory

### Requirement: Strategy dispatch has no inline name branching
Registered strategy consumers SHALL resolve configured names through the relevant registry. Consumer modules SHALL not import concrete strategy modules at module scope or branch over strategy names.

#### Scenario: A new community strategy is added
- **WHEN** a maintainer adds another community algorithm
- **THEN** the consumer SHALL require no algorithm-specific branch
- **AND** registration SHALL make the strategy discoverable through the registry

### Requirement: Existing modules receive a registration audit
The change SHALL audit every Python module recursively under `src/omrg/integrations/`, plus current factories and name-dispatched implementation families elsewhere. The audit SHALL include package facades, Azure, Magika, every PDF module, sparse retrieval backends, metadata extraction, embedding providers, LLM providers, chunking, reranking, and community detection. No integration module SHALL remain unclassified.

For each module, the audit SHALL record whether it is native or optional, whether configuration selects it by name, its shared contract if any, its fallback owner, and its disposition as registry strategy, capability integration, factory, facade, or direct implementation.

#### Scenario: Audit finds an unregistered strategy family
- **WHEN** multiple interchangeable implementations are selected by a configuration name without registry dispatch
- **THEN** the audit SHALL identify the family and affected call sites
- **AND** the implementation SHALL be registered in this change when migration preserves behaviour and dependency boundaries

#### Scenario: Audit finds a behaviour-changing migration
- **WHEN** correcting dispatch would alter public behaviour, dependency defaults, or persisted data
- **THEN** the audit SHALL record a follow-up OpenSpec change rather than expand this implementation silently

#### Scenario: Magika is assessed
- **WHEN** the audit evaluates the Magika integration
- **THEN** it SHALL classify Magika according to the same eligibility rule
- **AND** it SHALL remain unregistered unless configuration selects it among interchangeable file-detection implementations with one shared contract

#### Scenario: Integrations directory changes
- **WHEN** a Python module is added beneath `src/omrg/integrations/`
- **THEN** the maintained inventory SHALL classify it using the registry eligibility rule
- **AND** the audit check SHALL fail while the module is absent from the inventory

#### Scenario: PDF adapters are assessed
- **WHEN** the audit evaluates the configured PDF implementations and their `auto` factory
- **THEN** it SHALL distinguish automatic capability resolution from concrete backend selection
- **AND** it SHALL state whether the concrete native and optional readers require registry dispatch behind the existing factory API

### Requirement: Registry inventory is testable
The audit SHALL produce a maintained inventory that names every integration module and implementation family, its native or optional status, its classification, its selection mechanism, and its registry, factory, facade, or adapter location. Contract tests SHALL cover registered names that are also documented configuration values and SHALL detect unclassified integration modules.

#### Scenario: A configurable registered name changes
- **WHEN** a registered strategy is added, removed, or renamed without updating its documented inventory
- **THEN** the registry contract test SHALL fail and identify the mismatch

