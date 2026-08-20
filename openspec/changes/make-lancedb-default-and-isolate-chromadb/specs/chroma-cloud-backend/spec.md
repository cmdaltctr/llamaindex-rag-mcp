## ADDED Requirements

### Requirement: Chroma modes SHALL require explicit backend selection and the optional extra

Local and cloud Chroma operation SHALL be available only when `VECTOR_STORE=chroma` and the `chroma` optional extra is installed. Chroma-specific settings SHALL NOT change the LanceDB runtime path.

#### Scenario: Chroma Cloud selected correctly

- **GIVEN** `VECTOR_STORE=chroma`
- **AND** `CHROMA_MODE=cloud`
- **AND** the `chroma` extra and valid cloud credentials are present
- **WHEN** runtime setup completes
- **THEN** the Chroma Cloud client MUST serve every collection operation

#### Scenario: Cloud mode with LanceDB selected

- **GIVEN** `VECTOR_STORE=lancedb`
- **AND** `CHROMA_MODE=cloud` or any Chroma cloud credential is explicitly set
- **WHEN** settings are validated
- **THEN** startup MUST fail with an error explaining that Chroma settings require `VECTOR_STORE=chroma`
- **AND** no cloud credential value MUST appear in the error

#### Scenario: Chroma backend without the extra

- **GIVEN** `VECTOR_STORE=chroma`
- **AND** the optional `chroma` extra is absent
- **WHEN** runtime setup begins
- **THEN** startup MUST fail with the documented installation instruction
- **AND** it MUST NOT fall back to LanceDB silently

### Requirement: Chroma SHALL remain quarantined until a patched release exists

The base installation SHALL exclude ChromaDB while CVE-2026-45829 has no official patched release. Reintroducing ChromaDB into base dependencies SHALL require a separate decision based on an official patched version and renewed security review.

#### Scenario: No patched release exists

- **WHEN** dependency policy is evaluated
- **THEN** Chroma packages MUST remain confined to the optional extra
- **AND** LanceDB MUST remain the base default

#### Scenario: Patched release becomes available

- **WHEN** an official release is outside the advisory's affected range
- **THEN** the project MAY open a separate OpenSpec change to reassess Chroma
- **AND** no automatic default reversal MUST occur
