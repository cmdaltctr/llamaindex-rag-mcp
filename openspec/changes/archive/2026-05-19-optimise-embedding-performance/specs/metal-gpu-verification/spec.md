## ADDED Requirements

### Requirement: GPU back-end detection at start-up
When `LOG_LEVEL=DEBUG` is set, the system SHALL inspect Ollama's running model list to detect whether the embedding model is using Metal GPU acceleration.

#### Scenario: Metal GPU is active (DEBUG logging)
- **WHEN** the system starts with `LOG_LEVEL=DEBUG`
- **AND** Ollama reports a Metal runner for the current `EMBED_MODEL`
- **THEN** a log message SHALL be emitted: `"Ollama running <model> on Metal GPU — VRAM: <value>"`

#### Scenario: CPU-only fallback detected
- **WHEN** the system starts with `LOG_LEVEL=DEBUG`
- **AND** Ollama reports a CPU-only runner for the current `EMBED_MODEL`
- **THEN** a warning SHALL be logged: `"Ollama running <model> on CPU — consider enabling Metal for faster embeddings"`

#### Scenario: Ollama not reachable
- **WHEN** the system starts with `LOG_LEVEL=DEBUG`
- **AND** `ollama ps` fails or returns no results
- **THEN** a debug log SHALL be emitted: `"Could not determine Ollama runner — <reason>"`

### Requirement: No crash on failure
The GPU check SHALL never block start-up or crash the application.

#### Scenario: Graceful degradation
- **WHEN** `ollama ps` raises an exception
- **THEN** the system SHALL log a warning and continue without GPU info
- **THEN** the system SHALL NOT exit or raise an unhandled error
