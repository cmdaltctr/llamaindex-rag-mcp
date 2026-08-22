## ADDED Requirements

### Requirement: Chroma modes SHALL require explicit backend selection and the optional extra

Local and cloud Chroma operation SHALL be available only when
`VECTOR_STORE=chroma` is explicitly selected and both optional packages are
installed. Chroma settings SHALL never alter an unselected LanceDB route.

#### Scenario: Chroma Cloud selected correctly

- **GIVEN** explicit `VECTOR_STORE=chroma`
- **AND** `CHROMA_MODE=cloud`
- **AND** both Chroma optional packages and valid credentials are present
- **WHEN** runtime setup completes
- **THEN** the Chroma Cloud client MUST serve every collection operation

#### Scenario: Chroma settings with LanceDB selected

- **GIVEN** `VECTOR_STORE=lancedb`
- **AND** `CHROMA_MODE=cloud` or any non-empty Chroma cloud credential is explicitly set
- **WHEN** settings are validated
- **THEN** backend mismatch MUST be reported before credential completeness
- **AND** the error MUST name the incompatible setting names without exposing values

#### Scenario: Chroma backend without the complete extra

- **GIVEN** explicit `VECTOR_STORE=chroma`
- **AND** either optional Chroma package is absent
- **WHEN** composition begins
- **THEN** startup MUST fail with backend-specific installation guidance
- **AND** it MUST NOT fall back to LanceDB

### Requirement: Chroma SHALL remain quarantined until authoritative patch evidence converges

Chroma packages SHALL remain optional and LanceDB SHALL remain the base default
until a separately reviewed official release has accepted fix and advisory
evidence. Upstream assertion alone SHALL not end quarantine.

#### Scenario: No accepted patched release exists

- **WHEN** dependency policy is evaluated
- **THEN** Chroma packages MUST remain confined to the optional extra
- **AND** LanceDB MUST remain the base default

#### Scenario: Candidate patched release appears

- **GIVEN** an official maintainer PyPI release exists
- **AND** a fixing commit or release note is linked
- **AND** the project's named authoritative advisory excludes that version
- **AND** renewed security review accepts the candidate, preferably with an isolated regression test
- **WHEN** all evidence agrees
- **THEN** the project MAY open a separate OpenSpec reassessment
- **AND** no automatic base-dependency or default reversal may occur

#### Scenario: Authorities disagree

- **WHEN** upstream, the authoritative advisory or renewed review disagree about the candidate
- **THEN** quarantine MUST remain in force
