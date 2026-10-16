## MODIFIED Requirements

### Requirement: Documented source paths resolve

Documentation that cites a source file path SHALL cite a path that exists.
Every `src/omrg/**/*.py` path referenced in `docs/guides/`,
`tests/TEST_README.md`, the root `AGENTS.md` or a folder guidance file SHALL
resolve to a file on disk. A short citation that starts at a top-level
package folder (`core/`, `transports/`, `integrations/`, `config/` or
`daemon/`) and omits `src/omrg/` SHALL resolve below `src/omrg/` in the same
way. Records under `docs/adr/` are EXCLUDED: an ADR legitimately cites paths
that were correct when the decision was taken and have since moved.

#### Scenario: A guide cites a path deleted by a refactor

- **WHEN** a guide references `src/omrg/config.py` after the v2 split moved it to `src/omrg/config/__init__.py`
- **THEN** the documentation reference check SHALL fail
- **THEN** the failure SHALL name the citing file, its line, and the unresolved path

#### Scenario: A guide cites a moved file without the package prefix

- **WHEN** a guide references `core/vectordb/lancedb.py` after the file moved to `core/vectordb/lancedb/store.py`
- **THEN** the documentation reference check SHALL fail
- **THEN** the failure SHALL name the citing file, its line, and the unresolved path

#### Scenario: A folder guidance file cites a moved file

- **WHEN** `src/omrg/core/vectordb/AGENTS.md` cites a module path that no longer exists
- **THEN** the documentation reference check SHALL fail and name that file and line

#### Scenario: A historical ADR cites a since-deleted path

- **WHEN** `docs/adr/026-provider-registry-and-openrouter.md` references `src/omrg/metadata_extractor.py`, a v1 module deleted in v2.0.0
- **THEN** the check SHALL NOT fail
- **THEN** the ADR SHALL remain unmodified, its accuracy carried by a dated forward note instead

## ADDED Requirements

### Requirement: Key source folders carry agent guidance files

Each of these folders SHALL contain an `AGENTS.md` file and a `CLAUDE.md`
symbolic link that points to it: `src/omrg/`, `src/omrg/core/`,
`src/omrg/core/vectordb/`, `src/omrg/core/retrieval/`,
`src/omrg/core/ingestion/`, `src/omrg/core/pipelines/`,
`src/omrg/transports/`, `src/omrg/integrations/`, `web/src/` and `tests/`.
Each guidance file SHALL be at most 40 lines and SHALL link to the root
`AGENTS.md`. An automated check SHALL enforce these rules.

#### Scenario: Guidance file missing

- **WHEN** one of the listed folders has no `AGENTS.md`
- **THEN** the check SHALL fail and name the folder

#### Scenario: Claude link points elsewhere

- **WHEN** a listed folder has a `CLAUDE.md` that is a regular file, or a link whose target is not `AGENTS.md`
- **THEN** the check SHALL fail and name the folder

#### Scenario: Guidance file grows too long

- **WHEN** a guidance file has more than 40 lines
- **THEN** the check SHALL fail and name the file and its line count

#### Scenario: Guidance file does not link back

- **WHEN** a guidance file contains no link to the root `AGENTS.md`
- **THEN** the check SHALL fail and name the file

### Requirement: Agent guidance files stay out of the wheel

The built wheel SHALL contain no `AGENTS.md` and no `CLAUDE.md` file at any
depth. The release wheel check SHALL report each such file it finds.

#### Scenario: Wheel built from the source tree

- **WHEN** a wheel is built from a tree that holds folder guidance files under `src/omrg/`
- **THEN** no `AGENTS.md` or `CLAUDE.md` entry SHALL appear in the wheel

#### Scenario: A guidance file leaks into a wheel

- **WHEN** the release wheel check reads a wheel that contains `omrg/core/AGENTS.md`
- **THEN** the check SHALL fail and name that entry
