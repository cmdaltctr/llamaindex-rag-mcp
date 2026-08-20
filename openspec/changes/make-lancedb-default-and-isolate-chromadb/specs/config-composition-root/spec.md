## ADDED Requirements

### Requirement: Settings SHALL resolve a LanceDB default and validate Chroma selection

The resolved default for the vector-store selector SHALL be `lancedb`. Settings validation SHALL cross-validate Chroma-specific configuration against the selected backend so misconfiguration fails at startup instead of being ignored.

#### Scenario: Default resolution

- **GIVEN** no `VECTOR_STORE` value is provided by the user or environment
- **WHEN** settings are resolved
- **THEN** the effective vector-store selector MUST be `lancedb`
- **AND** the resolved value MUST remain overridable by explicit user configuration

#### Scenario: Explicit Chroma selection is preserved

- **GIVEN** the `chroma` optional extra is installed
- **AND** `VECTOR_STORE=chroma` is explicitly set
- **WHEN** settings are resolved
- **THEN** the effective selector MUST be `chroma`
- **AND** runtime setup MUST construct the Chroma store through the registry

#### Scenario: Chroma cloud credentials without Chroma selection

- **GIVEN** `CHROMA_MODE=cloud` or any `CHROMA_CLOUD_*` credential is set
- **AND** `VECTOR_STORE` resolves to `lancedb`
- **WHEN** settings are validated
- **THEN** validation MUST fail with an actionable error naming both settings
- **AND** the error MUST NOT echo any credential value

#### Scenario: Configuration documentation reflects the default

- **WHEN** the environment example, defaults file, and configuration guides are inspected
- **THEN** they MUST state `lancedb` as the default vector store
- **AND** Chroma usage MUST document the optional-extra installation step
