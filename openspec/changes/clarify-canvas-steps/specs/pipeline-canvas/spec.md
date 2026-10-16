# pipeline-canvas delta

## MODIFIED Requirements

### Requirement: Node controls show effective behaviour
Node controls SHALL derive from operation schemas and show effective values, inherited defaults, and allowed overrides. Each pipeline SHALL inherit settings from its profile's base profile, and a step setting SHALL override the inherited value. Reranker and hybrid controls SHALL support inherit/on/off where applicable. Disabling a node in the graph (bypass) SHALL remain a separate mechanism from an operation control such as the reranker `enabled` control. Each control SHALL use a plain label and SHALL state where its value comes from. The canvas SHALL run the draft check by itself when a pipeline opens and after each change to the graph document, after a short pause, and SHALL show the effective values that the check returns without run inputs. An effective value SHALL show only while the draft matches the graph that was checked or validated. Technical identifiers SHALL sit in a collapsed Details area. Choice options SHALL show readable labels where one exists, and the saved value SHALL not change.

#### Scenario: Reranker is disabled with a click
- **WHEN** a user sets the reranker node's `enabled` control to off and submits a new run
- **THEN** the admitted node control SHALL explicitly disable inference
- **AND** the node SHALL run, pass its evidence through without inference, and record the reason in its summary
- **AND** the inspector SHALL show that inference was skipped and that reason

#### Scenario: Node is disabled in the graph
- **WHEN** a user disables a node in the graph (the node bypass toggle) and submits a new run
- **THEN** core SHALL emit a bypassed event for that node instead of running its operation
- **AND** the node SHALL pass its declared input through unchanged when that input is available
- **AND** the canvas SHALL show the node as bypassed

#### Scenario: Profile default is restored
- **WHEN** a user resets a control to inheritance
- **THEN** the next run SHALL use profile resolution and record its effective value

#### Scenario: Active run has an edited toggle
- **WHEN** a toggle changes while a run is active
- **THEN** the draft SHALL change for a later run
- **AND** the current run's snapshot SHALL remain unchanged

#### Scenario: A step setting overrides the base profile
- **WHEN** a pipeline's graph names the base profile `documents` and the user sets "Number of results" to 20 on its Prepare query step
- **THEN** that step SHALL use 20
- **AND** every other inherited setting SHALL keep its `documents` value

#### Scenario: Values show without Validate
- **WHEN** a user opens a Search pipeline whose base profile sets `retrieval.top_k` to 10, and has not pressed Validate
- **THEN** after the draft check returns, the Prepare query card SHALL show "Number of results: 10 (from profile)"
- **AND** Step settings for that step SHALL show "Value in use: 10 (from profile)"

#### Scenario: Settings use plain labels and name their source
- **WHEN** a user opens Step settings for a Prepare query step after a check reported `retrieval.top_k` as 10 from the profile
- **THEN** the control SHALL be labelled "Number of results"
- **AND** the value note SHALL read "Value in use: 10 (from profile)"
- **AND** the setting path `retrieval.top_k` SHALL not show outside the Details area

#### Scenario: An edit starts a new check
- **WHEN** a check reported effective values and the user then changes the draft graph
- **THEN** Step settings and the step cards SHALL stop showing the earlier values
- **AND** each inherited control SHALL name its source without a value until the new check returns
- **AND** the canvas SHALL send one new draft check after the user stops editing for the pause

#### Scenario: Layout edits keep the values
- **WHEN** a check reported effective values and the user then moves a step or changes the selection
- **THEN** the values SHALL stay
- **AND** the canvas SHALL NOT send a new draft check

#### Scenario: The automatic check leaves the issue list alone
- **WHEN** the automatic draft check finds issues in an incomplete draft
- **THEN** the cards and Step settings SHALL show the values that the check returned for the other steps
- **AND** the issue list and the issue badges SHALL change only when the user selects Validate

#### Scenario: Technical identifiers are in Details
- **WHEN** a user opens Step settings for a step
- **THEN** the heading SHALL be the step name
- **AND** a collapsed Details area SHALL hold the node id, the operation id and version, the full description, each setting path, the port types and the issue codes
- **AND** issue messages SHALL stay visible outside the Details area

#### Scenario: A choice option has a readable label
- **WHEN** a user opens the fallback chunking control of a Read document step
- **THEN** the options SHALL read "Markdown", "Code" and "Sentences"
- **AND** choosing "Sentences" SHALL save the parameter value `sentence`

## ADDED Requirements

### Requirement: Step cards show what each step does
Each step card on the canvas SHALL show the step name, a one-line summary of what the step does, up to three main settings with their values and sources, and its port names. A step without parameters SHALL show "No settings". The card SHALL not show the operation id, the node id or the port type kinds. The node id SHALL show only when another step in the graph has the same name.

#### Scenario: A step with settings is on the canvas
- **WHEN** the graph holds a Split into chunks step whose chunk size is not set on the step, and the last check still matches the draft and reported a chunk size of 1024 from the profile
- **THEN** the card SHALL show "Chunk size: 1024 (from profile)"
- **AND** the card SHALL show the first sentence of the catalogue description on one line

#### Scenario: A setting is set on the step
- **WHEN** a Cross-encoder rerank step has its `enabled` parameter set to off
- **THEN** the card SHALL show "Reranker: Off (set here)"

#### Scenario: A value is not known yet
- **WHEN** a setting comes from the profile and the draft check has not returned a value for it
- **THEN** the card SHALL show the setting with the text "From profile" and no number
- **AND** the card SHALL show the value as soon as the check returns it

#### Scenario: Main settings are chosen
- **WHEN** a Prepare query step is on the canvas
- **THEN** the card SHALL show "Number of results", "Minimum similarity" and "Reranker", because the card takes settings in catalogue order and puts the collection setting last
- **AND** the card SHALL say how many more settings Step settings holds
- **AND** a setting that the canvas cannot edit SHALL not be one of the three

#### Scenario: A step has no settings
- **WHEN** a Discover sources step is on the canvas
- **THEN** the card SHALL show "No settings"

#### Scenario: Internal codes are absent
- **WHEN** any step card is on the canvas
- **THEN** the card SHALL show port names such as "sources"
- **AND** the card SHALL not show the operation id, the port type kinds or the node id

#### Scenario: Two steps have the same name
- **WHEN** the graph holds two Dense retrieval steps with node ids `dense` and `dense_2`
- **THEN** each of the two cards SHALL show its node id in muted text under the step name
- **AND** the accessible name of each card SHALL include its node id

#### Scenario: Status badges stay
- **WHEN** a step is bypassed, unavailable, has validation issues, or is part of a shown run
- **THEN** the card SHALL show the Bypassed, Unavailable or issue text and the run state as before

### Requirement: The Embed chunks card names the embedding model
The Embed chunks step card SHALL show a read-only line with the model that the server uses for embeddings: "Model: <model> (fixed for collections that already hold vectors)". The model name SHALL come from the existing connection summary. The canvas SHALL not offer a control to change it.

#### Scenario: The server reports the embedding model
- **WHEN** the connection summary names `nomic-embed-text` as the embeddings model of the provider that holds the embeddings role
- **THEN** the Embed chunks card SHALL show "Model: nomic-embed-text (fixed for collections that already hold vectors)"
- **AND** the card SHALL not show "No settings"

#### Scenario: The connection summary is not available
- **WHEN** the connection summary fails to load or no provider holds the embeddings role
- **THEN** the card SHALL show "Model: unknown (fixed for collections that already hold vectors)"
- **AND** the rest of the canvas SHALL keep working

### Requirement: Step cards open their settings
Each step card SHALL show that it opens its settings. The card SHALL show a settings icon and a hover state, and SHALL show the shared focus outline when it has keyboard focus. The card SHALL have the accessible name "<step name> step". Selecting the card with a click, Enter or Space SHALL open Step settings for that step.

#### Scenario: A user clicks a step card
- **WHEN** a user clicks the Discover sources card
- **THEN** Step settings SHALL open and show the Discover sources step

#### Scenario: A keyboard user selects a step card
- **WHEN** a keyboard user moves focus to a step card and presses Enter
- **THEN** the card SHALL show the focus outline
- **AND** Step settings SHALL open and show that step

#### Scenario: Assistive technology names the card
- **WHEN** a screen reader reaches the Discover sources card
- **THEN** it SHALL announce the name "Discover sources step"

### Requirement: The canvas explains how to edit it
The canvas page SHALL show one intro line under the page heading: "Build your own profile. Click a step to change it in Step settings. Drag from one port to another to connect steps, or use Connect ports." The line SHALL show for an empty graph and for a graph with steps. It SHALL not cover any step.

#### Scenario: The graph is empty
- **WHEN** a user opens a pipeline with no steps
- **THEN** the intro line SHALL show under the page heading
- **AND** the empty state SHALL read "The graph is empty. Add a step from Operations to start."

#### Scenario: The graph has steps
- **WHEN** a user opens a pipeline with steps
- **THEN** the intro line SHALL show under the page heading
- **AND** the line SHALL sit outside the flow surface, so it covers no step
