## ADDED Requirements

### Requirement: Base and Chroma-extra dependency contracts SHALL be tested separately

The built base package and a fresh base installation SHALL exclude both Chroma
distributions. The optional `chroma` group SHALL retain supported floors and run
in a separate complete CI job.

#### Scenario: Built base wheel excludes Chroma

- **WHEN** base wheel metadata is inspected
- **THEN** neither Chroma package MUST be an unconditional `Requires-Dist`
- **AND** the Chroma extra markers MUST be represented accurately

#### Scenario: Fresh base installation excludes Chroma

- **WHEN** the base wheel is installed without extras in a fresh environment
- **THEN** both Chroma distributions MUST be absent from import metadata and installed-distribution inventory
- **AND** the full LanceDB-default fast suite and base import-lint contracts MUST pass

#### Scenario: Chroma extra resolves at floors

- **WHEN** the `chroma` group is resolved at lowest direct versions
- **THEN** every Chroma-skipped base case MUST run in the extra job
- **AND** contract, local, hybrid and cloud suites MUST pass
- **AND** floor drift checks MUST cover both packages

### Requirement: Residual advisory findings SHALL require explicit release-policy disposition

Optionalisation SHALL NOT by itself clear a release gate. Base-artifact and
universal-lock/all-extras findings SHALL be observed and recorded separately.

#### Scenario: Base artefact is scanned

- **WHEN** the base wheel or base-install SBOM is scanned
- **THEN** the actual result MUST be recorded with artefact identity and scanner version
- **AND** it MUST be distinguished from the universal-lock result

#### Scenario: Universal lock still reports the advisory

- **GIVEN** `uv.lock` contains the optional Chroma group
- **WHEN** security tooling reports CVE-2026-45829
- **THEN** the release MUST remain blocked until a named policy owner records acceptance or rejection
- **AND** any acceptance MUST include scope, rationale, date, expiry/review date and patch/advisory triggers
- **AND** the advisory MUST remain tracked

#### Scenario: Policy refuses the residual finding

- **WHEN** policy cannot waive the optional universal-lock finding
- **THEN** this change MUST NOT claim release clearance
- **AND** Chroma support MUST be separately locked/distributed or removed temporarily before release
