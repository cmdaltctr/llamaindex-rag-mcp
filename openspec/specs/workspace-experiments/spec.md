# workspace-experiments Specification

## Purpose
Experiments as the research area: named experiment folders holding sub-experiments, marimo notebook loading through plugin approval, and the pipeline runs list.

## Requirements

### Requirement: Experiment contexts group under named folders

The Experiments view SHALL group experiment contexts under their parent directories below the approved experiment roots, showing named main folders that each list their sub-experiments. A main folder with no contexts SHALL still be listed. When no root is approved, the view SHALL say so and name the `--experiment-root` server flag.

#### Scenario: Grouped listing

- **WHEN** two contexts exist under `reranker-calibration` and one under `input-quality`
- **THEN** the view MUST show both folders with their contexts listed beneath them

#### Scenario: Empty folder

- **WHEN** a main folder exists on disk with no registered context
- **THEN** the folder MUST appear with an empty indication

### Requirement: Folders are created from the view

The user SHALL create a main folder by name, which creates a directory below an approved experiment root through a session-scoped endpoint, and SHALL create a sub-experiment inside a folder by registering an experiment context in that directory with its declared factors. Path validation SHALL reject relative escapes and paths outside approved roots.

#### Scenario: Create a main folder

- **WHEN** the user creates a folder named `hybrid-search` under the approved root
- **THEN** the directory MUST be created and the folder MUST appear in the listing

#### Scenario: Create a sub-experiment

- **WHEN** the user registers an experiment named `run-1` inside `hybrid-search`
- **THEN** a context MUST be approved for that workspace and listed under the folder with its factors

#### Scenario: Rejected path

- **WHEN** a folder name containing path traversal is submitted
- **THEN** the request MUST fail with a validation error and no directory MUST be created

### Requirement: Marimo loads through plugin approval

The Experiments view SHALL keep the notebook tool registration, trust notice, one-time credentials and editor launch panels. Opening a notebook editor for an experiment workspace SHALL launch the registered marimo tool, and stopping it SHALL end the launch.

#### Scenario: Open the marimo editor

- **WHEN** marimo is registered and the user opens the editor for an experiment workspace
- **THEN** an editor launch MUST start and its status MUST be shown with a stop action

### Requirement: Pipeline runs live in Experiments

The Experiments view SHALL include the pipeline runs list with its status filter and refresh. Selecting a run SHALL open `#/experiments/runs/<run-id>`, showing its snapshot, node outcomes and evidence, following the `pipeline-canvas` and `pipeline-run-records` requirements.

#### Scenario: Runs are available

- **WHEN** the user opens the runs section of Experiments
- **THEN** the run list, status filter and run detail with snapshot, node outcomes and evidence MUST be available

#### Scenario: Run detail has its own address

- **WHEN** the user reloads the page at `#/experiments/runs/<run-id>`
- **THEN** the detail for that run MUST be shown
