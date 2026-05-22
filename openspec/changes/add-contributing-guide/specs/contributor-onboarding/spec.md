## ADDED Requirements

### Requirement: Repository has a CONTRIBUTING.md at the root
The repository SHALL contain a `CONTRIBUTING.md` file at the root that
serves as the single entry point for new contributors, linking to the
deeper docs without duplicating their content.

#### Scenario: CONTRIBUTING.md exists and is discoverable from GitHub
- **WHEN** a contributor visits the repository on GitHub
- **THEN** GitHub's "Contribute" sidebar and PR creation flow link to `CONTRIBUTING.md` at the repo root
- **THEN** the file is present and non-empty

#### Scenario: CONTRIBUTING.md is referenced from README
- **WHEN** a contributor reads `README.md`
- **THEN** the documentation table includes a row pointing at `CONTRIBUTING.md`

---

### Requirement: CONTRIBUTING.md describes the end-to-end contribution loop
`CONTRIBUTING.md` SHALL describe the contribution workflow from "I have an
idea" to "my PR is open" covering: setup, branching, OpenSpec proposal
(when non-trivial), implementation, testing, optional experiment, ADR
(when architectural), conventional commit, push, and PR.

#### Scenario: Workflow is summarised in a flow diagram
- **WHEN** a contributor opens `CONTRIBUTING.md`
- **THEN** a Mermaid `flowchart TD` block summarises the full workflow on a single page

#### Scenario: Each workflow step links to the deeper doc
- **WHEN** a contributor reads any step in the workflow
- **THEN** the step links to the existing canonical document for that step (`getting-started.md`, `AGENTS.md`, `EXP_TEMPLATE.md`, `ADR_README.md`, `tests/TEST_README.md`, etc.)
- **THEN** the step does not duplicate the linked doc's content

#### Scenario: Trivial fixes have an explicit shortcut
- **WHEN** a contributor reads the workflow
- **THEN** the diagram includes a `Trivial fix?` decision node that routes typos and one-line bug fixes directly to implementation, bypassing OpenSpec

---

### Requirement: CONTRIBUTING.md includes a where-to-find-things reference table
`CONTRIBUTING.md` SHALL include a reference table mapping common
"I am looking for X" questions to file paths within the repo.

#### Scenario: Reference table covers core docs
- **WHEN** a contributor reads the reference table
- **THEN** the table includes rows for setup, conventions, ADRs, OpenSpec, experiments, tests, configuration, CLI reference, MCP tool reference, and architecture

---

### Requirement: tests/ has a TEST_README.md front door
The `tests/` directory SHALL contain a `TEST_README.md` file that surfaces
quick-start commands, the conftest autouse patches, the per-module
coverage floors, the test-file inventory, and the non-obvious gotchas
(reranker singleton, EphemeralClient state, METADATA_EXTRACTION_MODE
module-level patching, slow marker exclusion).

#### Scenario: TEST_README.md exists in tests/
- **WHEN** a contributor opens the `tests/` directory
- **THEN** a `TEST_README.md` file is present and visible alongside the test files

#### Scenario: Quick-start commands run the fast suite
- **WHEN** a contributor copies the quick-start command from `tests/TEST_README.md`
- **THEN** the command is `uv run pytest -m "not slow" -v` or its coverage variant

#### Scenario: Gotchas are explicitly documented
- **WHEN** a contributor reads `tests/TEST_README.md`
- **THEN** the reranker singleton reset, EphemeralClient state-leak warning, METADATA_EXTRACTION_MODE module-level patching note, and `@pytest.mark.slow` exclusion are each documented

#### Scenario: Cross-references resolve
- **WHEN** a contributor follows a link from `tests/TEST_README.md`
- **THEN** the link navigates to `docs/guides/testing.md`, `AGENTS.md`, `CONTRIBUTING.md`, or `pyproject.toml`

---

### Requirement: README.md links to CONTRIBUTING.md
`README.md` SHALL include a row in its documentation table linking to
`CONTRIBUTING.md` so the front door is discoverable from the repo
landing page.

#### Scenario: README documentation table includes the contributing link
- **WHEN** a contributor reads the documentation table in `README.md`
- **THEN** a row labelled "Contributing" links to `CONTRIBUTING.md`
