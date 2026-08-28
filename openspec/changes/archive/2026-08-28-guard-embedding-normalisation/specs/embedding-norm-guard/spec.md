## ADDED Requirements

### Requirement: Ingest rejects non-unit embedding vectors

The system SHALL compute the L2 norm of every embedding vector produced for
storage and SHALL reject the file replacement when any vector norm deviates
from 1.0 by more than the configured tolerance. Rejection SHALL occur before
any node write, so the failure-safe replacement ordering keeps the previous
searchable version intact. The error SHALL name the embedding model, the
observed norm, the tolerance, and the controlling setting.

#### Scenario: Unit-norm vectors ingest normally
- **WHEN** a file is ingested and every produced vector has a norm within tolerance of 1.0
- **THEN** ingestion SHALL proceed unchanged and SHALL record the observed norm band in the file's ingest report

#### Scenario: Off-norm vector aborts the write
- **WHEN** an embedding vector with norm 0.7 or 1.4 is produced for storage and the tolerance is the default
- **THEN** the replacement SHALL abort before any node write
- **THEN** the previously indexed version SHALL remain searchable
- **THEN** the error message SHALL contain the model name, the observed norm, and the tolerance

### Requirement: Query path warns and diagnoses on non-unit vectors

The system SHALL compute the L2 norm of the query embedding before dense
search. When the norm deviates beyond tolerance, the system SHALL log a
warning at most once per process per model, SHALL continue to return search
results, and SHALL attach a norm-guard diagnostic to results when diagnostics
are enabled.

#### Scenario: Off-norm query still returns results
- **WHEN** a query embedding with norm outside tolerance is produced
- **THEN** search SHALL return results normally
- **THEN** a warning SHALL be logged once per process for that model
- **THEN** with diagnostics enabled, each result SHALL carry a norm-guard field showing the observed norm

#### Scenario: Unit-norm query is silent
- **WHEN** a query embedding within tolerance is produced
- **THEN** no warning SHALL be logged and no norm-guard diagnostic SHALL be attached

### Requirement: Guard configuration is explicit

The guard SHALL be controlled by nested settings providing an enable flag
(default enabled) and a tolerance (default 0.001). Disabling the guard SHALL
be an explicit operator action and SHALL be logged at startup.

#### Scenario: Tolerance is configurable
- **WHEN** the operator sets the tolerance to 0.05 and a vector of norm 0.97 is embedded for storage
- **THEN** ingestion SHALL proceed and record the norm band

#### Scenario: Disable is explicit and visible
- **WHEN** the operator disables the guard via settings
- **THEN** startup SHALL log that the embedding norm guard is disabled
- **THEN** no norm rejection or query diagnostic SHALL occur

### Requirement: Guard state is observable

The system SHALL expose the guard's effective state (enabled, tolerance) and
the last observed norm band in search diagnostics and ingestion reports, so
operators can verify which provider contract is being enforced.

#### Scenario: Diagnostics expose guard state
- **WHEN** a search is run with diagnostics enabled
- **THEN** the response SHALL include the guard enable flag, the tolerance, and the observed query-vector norm

### Requirement: Local provider paths are norm-validated

The acceptance of this capability SHALL include an empirical norm record for
each locally supported embedding backend in use (Ollama recorded by the 2026
investigation; llama.cpp recorded by this change), so no production index is
built on an unverified provider path.

#### Scenario: llama.cpp path is probed
- **WHEN** the acceptance task embeds one query through a local llama-server with the production GGUF
- **THEN** the observed norm SHALL be recorded in the experiment note or ADR accompanying this change
