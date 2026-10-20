## MODIFIED Requirements

### Requirement: The canvas panel groups the controls in icon accordion sections

The canvas panel SHALL be one card with these accordion sections in this order: Pipeline settings (Base profile, Collection, Hybrid retrieval on the Search and Answer pipelines, and pipeline-wide settings), Operations, Steps and connections, Connect ports, Revision and run, Step settings. Pipeline settings SHALL show the base profile as read-only text and SHALL NOT offer a title or a profile choice. Each section SHALL have its own icon, shown before its title in the section header. Each section header SHALL be a button that shows whether the section is open. Several sections MAY be open at the same time. When the sub-page loads, Pipeline settings SHALL be open, and Step settings SHALL also be open if the restored draft already has a selected step. After load, selecting a step SHALL open Step settings, and starting a run from the panel SHALL open Revision and run. A run record that already exists when the sub-page loads SHALL NOT open Revision and run. Each section's content SHALL be a region named by its section title, and section headers SHALL sit one level below the page heading. Opening or closing a section SHALL NOT change the draft, the selection or the run identity.

#### Scenario: Pipeline settings sit above Operations

- **WHEN** the user opens the canvas sub-page
- **THEN** the Pipeline settings section header MUST come before the Operations section header in the panel

#### Scenario: Base profile is shown, not chosen

- **WHEN** the user opens Pipeline settings on a pipeline whose graph names the base profile `documents`
- **THEN** the section MUST show the text "Base profile: documents" and no title field and no profile list

#### Scenario: Every section has an icon

- **WHEN** the panel is expanded
- **THEN** each of the six section headers MUST show an icon, and no two sections MUST share the same icon

#### Scenario: Default open state

- **WHEN** the canvas sub-page loads with no selected step
- **THEN** Pipeline settings MUST be open and the other sections MUST be closed

#### Scenario: Restored selection

- **WHEN** the canvas sub-page loads a draft that has a selected step
- **THEN** Pipeline settings and Step settings MUST be open and the other sections MUST be closed

#### Scenario: Sections use the word step

- **WHEN** the panel is expanded
- **THEN** the section titles MUST read "Pipeline settings", "Operations", "Steps and connections", "Connect ports", "Revision and run" and "Step settings", in this order
- **AND** no section title MUST contain the word "node"

#### Scenario: Earlier run does not open its section

- **WHEN** the canvas sub-page loads a pipeline whose latest run finished before the visit
- **THEN** Revision and run MUST be closed

#### Scenario: Regions and headings

- **WHEN** the Operations section is open
- **THEN** its content MUST be a region named "Operations"
- **AND** its header MUST be a level-2 heading under the level-1 page heading

#### Scenario: Several sections open

- **WHEN** the user opens Pipeline settings while Operations is open
- **THEN** both sections MUST stay open

#### Scenario: Selection opens node settings

- **WHEN** the user selects a step while Step settings is closed
- **THEN** Step settings MUST open and show that step's parameters

#### Scenario: Run opens its section

- **WHEN** the user starts a run while Revision and run is closed
- **THEN** Revision and run MUST open and show the run progress

#### Scenario: Closing keeps work

- **WHEN** the user closes Pipeline settings after editing the collection
- **THEN** the edited collection MUST remain in the draft and reappear when the section opens again

#### Scenario: Keyboard use

- **WHEN** a keyboard user moves focus to a section header and presses Enter or Space
- **THEN** the section MUST toggle and its content MUST be reachable by Tab when open

## ADDED Requirements

### Requirement: Pipeline settings switch hybrid retrieval

On the Search and Answer pipelines, Pipeline settings SHALL show a "Hybrid retrieval" switch with the line "Adds keyword (sparse) search and merges it with vector search." The switch SHALL be on when the graph holds an enabled Sparse retrieval step, and off otherwise. Turning the switch on SHALL add a Sparse retrieval step and a Reciprocal rank fusion step with the connections of the canonical hybrid template: Prepare query to Sparse retrieval, Dense retrieval to fusion, Sparse retrieval to fusion, and fusion to every step that Dense retrieval fed before. Turning it off SHALL remove those two steps and connect Dense retrieval to every step that fusion fed. The switch SHALL keep the settings and positions of every other step, and SHALL change only the draft, so the user saves the change as a revision. The switch SHALL be disabled with a reason when the graph is read-only, when Sparse retrieval or Reciprocal rank fusion is unavailable on the host, or when the retrieval steps do not match the shape that the switch knows. The Ingest pipeline SHALL NOT show the switch.

#### Scenario: Hybrid is turned on

- **WHEN** a user profile's Search pipeline holds Prepare query, Dense retrieval, Cross-encoder rerank, Threshold and Assemble context, and the user turns "Hybrid retrieval" on
- **THEN** the draft MUST hold a Sparse retrieval step and a Reciprocal rank fusion step
- **AND** the draft MUST connect Prepare query to Sparse retrieval, Dense retrieval and Sparse retrieval to fusion, and fusion to Cross-encoder rerank
- **AND** the draft MUST NOT connect Dense retrieval to Cross-encoder rerank
- **AND** the draft MUST pass the draft check with no issue

#### Scenario: Hybrid is turned off

- **WHEN** the user turns "Hybrid retrieval" off on a pipeline that the switch turned on
- **THEN** the draft MUST equal the graph before the switch was turned on, apart from the layout of the removed steps

#### Scenario: Step settings survive the switch

- **WHEN** Prepare query holds `top_k: 20` and Dense retrieval holds `collection: papers`, and the user turns hybrid on
- **THEN** Prepare query MUST still hold `top_k: 20`
- **AND** Sparse retrieval MUST hold `collection: papers`
- **AND** every step that was on the canvas before MUST keep its position

#### Scenario: The switch reads the saved shape

- **WHEN** a user opens an Answer pipeline whose saved graph holds an enabled Sparse retrieval step
- **THEN** the "Hybrid retrieval" switch MUST show on

#### Scenario: A custom shape is left alone

- **WHEN** the Search graph holds two Dense retrieval steps
- **THEN** the switch MUST be disabled
- **AND** the section MUST show "This pipeline has a custom retrieval shape. Change it with the steps on the canvas."

#### Scenario: The host cannot run sparse retrieval

- **WHEN** the operation catalogue marks Sparse retrieval as unavailable
- **THEN** the switch MUST be disabled
- **AND** the section MUST show the catalogue reason

#### Scenario: A built-in profile shows the state only

- **WHEN** a user opens the Search pipeline of the built-in `documents` profile
- **THEN** the switch MUST show the state of the standard graph and MUST be disabled

### Requirement: Pipeline settings show pipeline-wide settings

Pipeline settings SHALL list each pipeline-wide override that the graph holds, with its plain label, its value and a Remove button. Remove SHALL delete the override from the draft. On the Search and Answer pipelines, Pipeline settings SHALL also show a "Rerank candidate factor" control with Inherit and Set value. Set value SHALL take a whole number of at least 1 and SHALL write the pipeline-wide override `retrieval.rerank_fetch_multiplier`. Inherit SHALL remove that override. The setting path SHALL show only in a collapsed Details area. On a read-only graph the list and the control SHALL be disabled.

#### Scenario: An override from the API is visible

- **WHEN** a pipeline was saved through the API with the override `retrieval.top_k: 25`
- **THEN** Pipeline settings MUST show "Number of results: 25" with a Remove button

#### Scenario: An override is removed

- **WHEN** the user selects Remove on "Number of results: 25"
- **THEN** the draft MUST hold no `retrieval.top_k` override
- **AND** the step cards MUST stop showing "(from pipeline settings)" for that setting after the next check

#### Scenario: The rerank candidate factor is set

- **WHEN** the user sets "Rerank candidate factor" to 5 on a Search pipeline
- **THEN** the draft MUST hold the override `retrieval.rerank_fetch_multiplier: 5`

#### Scenario: A bad factor is refused

- **WHEN** the user types 0 in "Rerank candidate factor"
- **THEN** the field MUST show "Enter a value of at least 1."
- **AND** the draft MUST NOT change

### Requirement: User profiles can be described in place

A pencil next to the description of a user profile in the canvas header SHALL open an inline description field. Enter or "Save" SHALL send `PATCH /v1/profiles/{id}` with the trimmed description. Escape or "Cancel" SHALL close the field with no request. A description longer than 1000 characters SHALL be refused in the field with "Use at most 1000 characters." and no request. A built-in profile SHALL show its description with no pencil.

#### Scenario: Describe from the canvas

- **WHEN** the user types "Papers for the fellowship review" in the description field of `papers-search` and presses Enter
- **THEN** the client MUST send `{description: "Papers for the fellowship review"}` to `PATCH /v1/profiles/papers-search`
- **AND** the gallery card MUST show the new description

#### Scenario: The description save fails

- **WHEN** the server refuses the description change
- **THEN** the old description MUST stay and one friendly failure line with a Retry action MUST show
