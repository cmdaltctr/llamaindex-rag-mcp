## ADDED Requirements

### Requirement: Base and Chroma-extra dependency contracts SHALL be tested separately

The base dependency set SHALL resolve and pass without ChromaDB packages. The optional `chroma` dependency group SHALL retain declared floors and SHALL be tested in its own continuous-integration job.

#### Scenario: Base install excludes Chroma

- **WHEN** the base dependency set is installed from `pyproject.toml`
- **THEN** `chromadb` and `llama-index-vector-stores-chroma` MUST be absent
- **AND** the fast LanceDB-default suite MUST pass

#### Scenario: Chroma extra resolves at declared floors

- **WHEN** the `chroma` optional dependency group is resolved at lowest direct versions
- **THEN** the Chroma-specific contract and cloud tests MUST run
- **AND** dependency-floor drift checks MUST include both optional packages

#### Scenario: Lockfile retains optional packages

- **GIVEN** the lockfile records all optional groups
- **WHEN** security scanning reports CVE-2026-45829 from the optional Chroma group
- **THEN** the result MUST be dispositioned with the optional, unreachable-server rationale
- **AND** the advisory MUST remain tracked until an official patch exists
