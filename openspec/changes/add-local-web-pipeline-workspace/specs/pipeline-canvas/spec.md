# Pipeline canvas

## Purpose

Let users create and execute compatible RAG graphs, edit node settings, and inspect actual execution and evidence through an accessible local interface.

## ADDED Requirements

### Requirement: Canvas edits executable graphs
The canvas SHALL let users add registered nodes, create/remove compatible connections, choose graph inputs/outputs, configure parameters, and save revisions. Templates SHALL be editable. Server validation SHALL remain authoritative.

#### Scenario: Template is rewired
- **WHEN** a user changes a template's valid connections and runs the saved revision
- **THEN** the new connections SHALL determine execution
- **AND** the template's original fixed order SHALL not replace them

#### Scenario: Incompatible connection is attempted
- **WHEN** a user connects incompatible ports or creates a cycle
- **THEN** the canvas SHALL explain the invalid connection
- **AND** direct API submission SHALL still require server validation

#### Scenario: Draft differs from saved revision
- **WHEN** an edited draft has not been saved or validated
- **THEN** the canvas SHALL identify that state before run submission
- **AND** the admitted graph SHALL be an immutable validated revision

### Requirement: Node controls show effective behaviour
Node controls SHALL derive from operation schemas and show effective values, inherited defaults, and allowed overrides. Profile selection SHALL support documents/codebase or collection inheritance. Reranker and hybrid controls SHALL support inherit/on/off where applicable.

#### Scenario: Reranker is disabled with a click
- **WHEN** a user disables the reranker and submits a new run
- **THEN** the admitted node control SHALL explicitly disable inference
- **AND** the inspector SHALL show the bypass and its reason

#### Scenario: Profile default is restored
- **WHEN** a user resets a control to inheritance
- **THEN** the next run SHALL use profile resolution and record its effective value

#### Scenario: Active run has an edited toggle
- **WHEN** a toggle changes while a run is active
- **THEN** the draft SHALL change for a later run
- **AND** the current run's snapshot SHALL remain unchanged

### Requirement: Execution display follows real events
The canvas SHALL show queued, running, completed, skipped, failed, and cancelling states from core events. Active-edge animation SHALL follow those states and respect reduced motion. Trace replay SHALL be labelled as replay.

#### Scenario: A node has not started
- **WHEN** a downstream node waits for required inputs
- **THEN** it SHALL not be displayed as executing or completed

#### Scenario: Core reports fallback or failure
- **WHEN** an operation degrades, bypasses, or fails
- **THEN** the canvas SHALL show its actual outcome and explanation

#### Scenario: Motion is reduced
- **WHEN** reduced motion is enabled
- **THEN** status text and icons SHALL retain execution information without ongoing animation

#### Scenario: Replay is opened
- **WHEN** a historical trace is replayed
- **THEN** it SHALL be labelled as historical playback
- **AND** replay SHALL not execute operations

### Requirement: Inspectors expose useful bounded evidence
The inspector SHALL show node parameters, effective settings, safe input/output previews, timing, ranking provenance, and available source/citation references. It SHALL identify preview truncation and retain score-kind labels.

#### Scenario: Ranked rows are inspected
- **WHEN** a user inspects retrieval or reranker output
- **THEN** the inspector SHALL show rank changes and their score kinds
- **AND** scores SHALL not be labelled as a shared probability of correctness

#### Scenario: Large or sensitive payload is inspected
- **WHEN** output exceeds preview bounds or includes credential fields
- **THEN** the preview SHALL identify its bounds and exclude credentials and vector arrays

### Requirement: Application navigation preserves working state
The workspace SHALL provide Canvas, Library, Search, Ask, Runs, Experiments, and Settings views. Navigation, theme changes, and inspector interactions SHALL preserve the current draft and admitted run identity. Stored-profile changes SHALL remain separate from saving a graph preset.

#### Scenario: User opens evidence and returns
- **WHEN** a user navigates from a canvas result to citation evidence and back
- **THEN** the canvas draft, selection, and run identity SHALL remain available

#### Scenario: Graph preset is saved
- **WHEN** a graph preset is saved
- **THEN** collection profile metadata SHALL remain unchanged
- **AND** a stored-profile change SHALL require its own preview and confirmation

### Requirement: Controls are accessible and theme-aware
The interface SHALL use shared semantic styles, readable light/dark themes, visible focus, labelled controls, textual status, and responsive inspectors. Node and connection editing SHALL be available through keyboard controls. Technical identifiers SHALL retain readable direction and wrapping.

#### Scenario: Graph is edited using a keyboard
- **WHEN** a keyboard user selects nodes and opens connection controls
- **THEN** the user SHALL be able to create/remove connections, edit fields, and submit validation without dragging

#### Scenario: Theme or viewport changes
- **WHEN** the theme changes or the viewport narrows
- **THEN** labels, focus states, errors, and inspector actions SHALL remain readable and reachable
- **AND** current edits SHALL remain intact
