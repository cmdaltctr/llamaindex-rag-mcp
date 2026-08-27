## Purpose

Define configurable local and Azure document-reading backends that share one async contract while preserving local-first fallback and optional cloud dependencies.

## ADDED Requirements

### Requirement: Document backends use one configured contract
The system SHALL expose `local` and `azure` as interchangeable document-backend names through one async reading contract.

#### Scenario: Local backend is selected
- **WHEN** `DOCUMENT_BACKEND=local`
- **THEN** supported documents SHALL be read without cloud credentials
- **AND** no Azure SDK SHALL be imported

#### Scenario: Azure backend is selected
- **WHEN** `DOCUMENT_BACKEND=azure` and valid credentials are available
- **THEN** supported documents SHALL be read through Azure Document Intelligence
- **AND** emitted document metadata SHALL remain compatible with the ingestion pipeline

### Requirement: Cloud selection remains local-first on failure
The system SHALL retain the existing local fallback when Azure credentials, dependencies, or runtime calls are unavailable, and SHALL emit a visible diagnostic naming the reason.

#### Scenario: Credentials are missing
- **WHEN** Azure is selected without its required endpoint or key
- **THEN** the effective backend SHALL resolve to local before document reading
- **AND** startup SHALL report the degradation naming the missing credential

#### Scenario: Azure SDK dependency is missing
- **WHEN** Azure is selected and the optional Azure SDK dependency is not installed
- **THEN** the effective backend SHALL resolve to local before document reading
- **AND** the diagnostic SHALL name the missing dependency

#### Scenario: Azure fails at runtime
- **WHEN** Azure reading fails after the configured retry budget
- **THEN** the same document SHALL be attempted through the local backend
- **AND** the caller SHALL receive the local result when fallback succeeds
- **AND** the diagnostic SHALL name the Azure runtime failure as the fallback reason

### Requirement: Backend dispatch is lazy and extensible
Configured backend names SHALL resolve lazily without importing optional SDKs at module load time. Adding another backend SHALL not require strategy-specific branching in the ingestion consumer.

#### Scenario: Base installation starts
- **WHEN** the Azure extra is absent and the local backend is selected
- **THEN** startup and local ingestion SHALL succeed

#### Scenario: Unknown backend is configured
- **WHEN** `DOCUMENT_BACKEND` contains an unregistered name
- **THEN** startup SHALL fail and list the available backend names
