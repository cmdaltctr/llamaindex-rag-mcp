## ADDED Requirements

### Requirement: Every experiment directory uses slug-date naming
Each experiment directory SHALL be named `<descriptive-slug>-<YYYY-MM-DD>` where the slug
describes what was tested and the date is when the experiment was first run.

#### Scenario: Directory name is human-readable
- **WHEN** a contributor lists the `experiments/` directory
- **THEN** each experiment directory name describes what was tested and when, without needing to open any file

#### Scenario: Existing experiments are renamed
- **WHEN** the change is applied
- **THEN** `experiment-1` is renamed to `reranker-threshold-calibration-2026-05-12`
- **THEN** `experiment-2` is renamed to `embedding-model-comparison-2026-05-19`
- **THEN** `experiment-3` is renamed to `e2e-smoke-test-metadata-2026-05-20`

---

### Requirement: Every experiment has a separate protocol.md
Each experiment directory SHALL contain a `protocol.md` file that covers hypothesis,
variables, environment, corpus, method, success criteria, and artefacts — structured
according to `experiments/TEMPLATE.md`.

#### Scenario: protocol.md exists in every experiment
- **WHEN** a contributor opens any experiment directory
- **THEN** a `protocol.md` file is present at the root of that directory

#### Scenario: experiment-1 protocol is split from merged file
- **WHEN** the change is applied to experiment-1
- **THEN** `experiments.md` is removed
- **THEN** `protocol.md` contains the Hypothesis, Variables, Environment, Method, and Success Criteria sections
- **THEN** no content from the original `experiments.md` is lost

---

### Requirement: Every experiment has a separate results.md
Each experiment directory SHALL contain a `results.md` file with the operator, status,
findings, score tables, and conclusion — separate from the protocol.

#### Scenario: results.md exists in every experiment
- **WHEN** a contributor opens any experiment directory
- **THEN** a `results.md` file is present at the root of that directory

#### Scenario: experiment-1 results are split from merged file
- **WHEN** the change is applied to experiment-1
- **THEN** `results.md` contains the Results Summary, Key Findings, and Practical Recommendations sections
- **THEN** all original result tables and data are preserved verbatim

---

### Requirement: Every protocol.md includes an operator field
Each `protocol.md` SHALL include an **Operator** field identifying who ran the experiment
(human name or "AI agent (automated)").

#### Scenario: Operator is recorded
- **WHEN** a contributor reads any experiment's protocol.md
- **THEN** the Operator field is present and non-empty

---

### Requirement: Every protocol.md includes a variables table
Each `protocol.md` SHALL include a Variables table with three rows: Independent (what
was changed), Dependent (what was measured), and Controlled (what was held constant).

#### Scenario: Variables table is present
- **WHEN** a contributor reads any experiment's protocol.md
- **THEN** a Variables table with Independent, Dependent, and Controlled rows is present

#### Scenario: Variables table isolates the tested variable
- **WHEN** a contributor reads the variables table
- **THEN** it is clear which single variable was changed and which were held constant

---

### Requirement: Every protocol.md includes an artefacts section
Each `protocol.md` SHALL include an Artefacts section listing every file in the experiment
directory with a one-line description of its purpose.

#### Scenario: Artefacts section is present
- **WHEN** a contributor reads any experiment's protocol.md
- **THEN** an Artefacts section lists all files in the directory

#### Scenario: Artefacts section is accurate
- **WHEN** a file exists in the experiment directory
- **THEN** it appears in the Artefacts table

---

### Requirement: README.md index reflects renamed directories
The `experiments/README.md` index table SHALL link to the renamed experiment directories
after the change is applied.

#### Scenario: Index links resolve correctly
- **WHEN** a contributor clicks an experiment link in experiments/README.md
- **THEN** the link navigates to the correct renamed directory

#### Scenario: No stale references remain
- **WHEN** the repo is searched for references to `experiment-1`, `experiment-2`, `experiment-3`
- **THEN** no references to the old directory names remain (except in git history)
