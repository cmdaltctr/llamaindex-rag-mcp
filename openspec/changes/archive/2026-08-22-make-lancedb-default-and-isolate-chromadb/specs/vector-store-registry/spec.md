## ADDED Requirements

### Requirement: Process-wide store access SHALL require prior composition

The process-wide accessor SHALL return only a store installed by the
composition root. It SHALL NOT import settings, composition or concrete store
modules and SHALL NOT construct a fallback.

#### Scenario: Access before composition

- **GIVEN** no process-wide store has been installed
- **WHEN** a core caller requests it
- **THEN** the accessor MUST raise a controlled error instructing the caller to compose or inject a store
- **AND** no backend module MUST be imported or constructed

#### Scenario: Access after composition

- **GIVEN** `compose.py` installed a resolved store
- **WHEN** a legacy process-wide caller requests it
- **THEN** the exact installed instance MUST be returned

### Requirement: Optional backend availability SHALL be registry metadata

A lazy registry entry MAY declare its required modules/distributions, optional
extra and installation guidance. Resolution SHALL generically distinguish
unknown, absent, partial and broken backends without branching over store names.

#### Scenario: Optional backend is absent

- **GIVEN** a selected registry entry has one or more absent required packages
- **WHEN** composition resolves it
- **THEN** startup MUST fail naming the selected backend, missing packages, required extra and supported default
- **AND** the dispatch path MUST contain no backend-name branch

#### Scenario: Optional backend is partially installed

- **GIVEN** only some packages declared by an optional backend are installed
- **WHEN** composition resolves it
- **THEN** startup MUST identify a partial/broken optional installation
- **AND** it MUST name the backend-specific repair guidance

#### Scenario: Factory import fails

- **GIVEN** all declared packages are present
- **AND** the registered factory cannot import
- **WHEN** resolution occurs
- **THEN** the error MUST identify a broken installation
- **AND** retain the original exception as diagnostic context

### Requirement: Sparse capability SHALL follow the selected store

Sparse/native capability SHALL be resolved from the selected store instance or
its registry metadata. Installed but unselected backends SHALL not affect it.

#### Scenario: LanceDB selected while Chroma extra is installed

- **GIVEN** `VECTOR_STORE=lancedb`
- **AND** the Chroma extra is installed
- **WHEN** sparse capability is resolved
- **THEN** the effective capability MUST be identical to a Chroma-free LanceDB installation
- **AND** the BM25 path MUST be used unless LanceDB itself advertises another supported capability

#### Scenario: Chroma-only native mode is requested for LanceDB

- **GIVEN** LanceDB is selected
- **AND** a Chroma-only native sparse mode is requested
- **WHEN** capability is validated
- **THEN** the system MUST use the documented BM25 fallback or reject the incompatible request according to the existing policy
- **AND** it MUST NOT probe Chroma by import
