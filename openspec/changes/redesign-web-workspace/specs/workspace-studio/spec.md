# workspace-studio delta

## Purpose

Studio as the home of pipelines: a gallery of templates, profile presets and saved pipelines, plus the full-width canvas sub-page where graphs are edited and run.

## ADDED Requirements

### Requirement: Studio opens on a pipeline gallery

The Studio view SHALL list the engine pipeline templates from `listPipelineTemplates`, profile preset cards for the `documents` and `codebase` profiles, and the saved pipelines from `listPipelines`, each as a card with a title and description. Creating a pipeline from any card SHALL create the pipeline on the server and open its canvas sub-page at `#/studio/<pipeline-id>` with that starting graph as the draft.

#### Scenario: Gallery contents

- **WHEN** the engine offers the ingestion, search and answer templates and one saved pipeline exists
- **THEN** the gallery MUST show the three template cards, the documents and codebase preset cards, and the saved pipeline card

#### Scenario: Start from a profile preset

- **WHEN** the user creates a pipeline from the documents preset card
- **THEN** a new pipeline MUST exist on the server and its canvas sub-page MUST open seeded from the search template with the documents profile's retrieval defaults

### Requirement: The canvas sub-page gives the graph the full width

Editing or creating a pipeline SHALL open the `#/studio/<pipeline-id>` sub-page, where the flow surface takes the full main area, the operation catalogue palette is the right-hand column, and selecting a node opens that node's settings. Adding a box from the palette SHALL add the operation node; removing a node SHALL remove it with its connections.

#### Scenario: Palette on the right

- **WHEN** the user opens a pipeline in the canvas sub-page
- **THEN** the flow surface MUST occupy the main area and the operation catalogue MUST be the right-hand column

#### Scenario: Node settings on selection

- **WHEN** the user selects a node on the canvas
- **THEN** the node's parameters MUST open in a detail region without leaving the sub-page

### Requirement: Saved pipelines reopen from the gallery

Each saved pipeline card SHALL reopen the canvas sub-page at its latest revision. Revision, validation and run behaviour SHALL follow the `pipeline-canvas`, `pipeline-graphs` and `pipeline-run-records` requirements.

#### Scenario: Reopen a saved pipeline

- **WHEN** the user opens a saved pipeline card
- **THEN** the canvas sub-page MUST load that pipeline's latest revision and offer the validate and run actions
