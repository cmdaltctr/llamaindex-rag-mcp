# pipeline-canvas Specification

## Purpose
Let users create and execute compatible RAG graphs, edit node settings, and inspect actual execution and evidence through an accessible local interface.

## Requirements

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

### Requirement: Execution display follows real events
The canvas SHALL show the queued, running, completed, skipped, bypassed, failed, and cancelled node states, and the cancelling run status, from core events. Active-edge animation SHALL follow those states and respect reduced motion. Trace replay SHALL be labelled as replay.

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
Navigation between workspace views, theme changes, and detail-panel interactions SHALL preserve the current Studio canvas draft and admitted run identity. The set and order of views is defined by the `workspace-presentation` capability. Stored-profile changes SHALL remain separate from saving a graph preset.

#### Scenario: User opens evidence and returns
- **WHEN** a user navigates from a Studio canvas result to citation evidence and back
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

### Requirement: A read-only canvas shows a graph without changing it
The canvas SHALL be able to open a graph read-only. The user SHALL be able to pan, zoom, select steps, read step settings and run Validate. The canvas SHALL NOT offer adding, removing, moving or connecting steps, editing a setting, "Save layout", "Save revision" or "Run". A read-only canvas SHALL NOT write a browser draft.

#### Scenario: Editing controls are absent or disabled
- **WHEN** the user opens a graph read-only
- **THEN** the operations in the catalogue SHALL be disabled with the reason "Read-only profile"
- **AND** every setting field in Step settings SHALL be disabled
- **AND** "Remove step" SHALL NOT be shown
- **AND** "Save layout", "Save revision" and "Run" SHALL NOT be shown
- **AND** "Validate" SHALL be enabled

#### Scenario: Steps cannot be moved, removed or connected
- **WHEN** a pointer or keyboard user tries to drag a step, delete a step or connect two ports on a read-only canvas
- **THEN** the graph SHALL stay unchanged
- **AND** the Connect ports section SHALL show "This pipeline is read-only." in place of the connection controls

#### Scenario: Selection still shows settings
- **WHEN** the user selects a step on a read-only canvas
- **THEN** Step settings SHALL open and show that step's values

#### Scenario: No draft is stored
- **WHEN** the user pans or selects steps on a read-only canvas and then reloads the page
- **THEN** browser storage SHALL hold no draft for that graph

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
- **AND** the card SHALL say how many settings are left, on the button "+N more settings"
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

#### Scenario: Connected ports are green
- **WHEN** a step has a port with at least one connection
- **THEN** the handle of that port SHALL show in the success colour
- **AND** a port with no connection SHALL keep the neutral handle colour
- **AND** an input and an output with the same name SHALL show their own state

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
The canvas page SHALL show this intro as one visible line with a little vertical padding, above the pipeline tabs: "Build your own profile. Click a step to change it in Step settings. Drag from one port to another to connect steps, or use Connect ports." Each pipeline tab SHALL also have an info button with an "i" icon and no chevron. A click on the button SHALL open a popover that holds the description of that pipeline and, for a built-in profile, the read-only note. The popover SHALL close on Escape, on a click elsewhere and on a second click on the button. The intro line SHALL show once and SHALL not repeat inside any popover. The intro line and the info buttons SHALL show for an empty graph and for a graph with steps. They SHALL not cover any step.

#### Scenario: The graph is empty
- **WHEN** a user opens a pipeline with no steps
- **THEN** the intro line SHALL show above the pipeline tabs without a click
- **AND** an info button SHALL show on each pipeline tab
- **AND** no popover SHALL hold the intro line
- **AND** the empty state SHALL read "The graph is empty. Add a step from Operations to start."

#### Scenario: The graph has steps
- **WHEN** a user opens a pipeline with steps
- **THEN** the intro line SHALL show above the pipeline tabs without a click
- **AND** an info button SHALL show on each pipeline tab
- **AND** no popover SHALL hold the intro line
- **AND** the intro line and the info buttons SHALL sit outside the flow surface, so they cover no step

### Requirement: The edge into a step that just finished animates
While a run is live, the canvas SHALL animate the edge into a step for 1.5 seconds after that step finishes with success, so the user sees data move one step ahead. The canvas SHALL keep animating the edge into a step while that step runs. The canvas SHALL not animate any edge for a run that had finished before the canvas began to watch it. With reduced motion, the canvas SHALL show a static highlight and no movement.

#### Scenario: A step finishes in a live run
- **WHEN** a live run reports that the Dense retrieval step finished with success
- **THEN** the edge into Dense retrieval SHALL animate and show the success colour
- **AND** the animation SHALL stop 1.5 seconds later

#### Scenario: A step runs
- **WHEN** a live run reports that a step runs
- **THEN** the edge into that step SHALL animate for as long as the step runs

#### Scenario: A finished run is opened
- **WHEN** the user opens a pipeline whose latest run had finished before the canvas began to watch it
- **THEN** no edge SHALL animate

#### Scenario: A step fails
- **WHEN** a live run reports that a step failed
- **THEN** the edge into that step SHALL not show the finished animation

#### Scenario: Motion is reduced
- **WHEN** the system asks for reduced motion and a live step finishes
- **THEN** the edge into that step SHALL show the success colour for 1.5 seconds
- **AND** the edge SHALL not move

### Requirement: Connections are drawn as smooth-step lines
The canvas SHALL draw each connection as a smooth-step line, with right-angle bends and rounded corners, and not as a diagonal curve. The line shape SHALL be presentation only: it SHALL not change the saved graph, the saved layout or the execution identity.

#### Scenario: A connection runs back across the canvas
- **WHEN** a connection joins a step in the first row to a step in the second row, so that its target lies to the left of its source
- **THEN** the line SHALL be a smooth-step line
- **AND** the line SHALL not be the default curve

#### Scenario: Line shape does not touch the saved graph
- **WHEN** a user saves a revision or a layout
- **THEN** the saved document and the saved layout SHALL hold no line type

### Requirement: The step summary expands in place
The one-line summary on a step card SHALL be a button. A click or Enter or Space on it SHALL show the whole first sentence of the catalogue description on the card, and a second one SHALL return it to one line. The card SHALL grow to fit the text, and the summary SHALL show no chevron. Using the summary SHALL not select the card, open Step settings or start a drag.

#### Scenario: A long summary is read in full
- **WHEN** a card shows "List the eligible files under a path…" cut to one line and the user clicks the summary
- **THEN** the card SHALL show the whole sentence
- **AND** the summary button SHALL report that it is expanded

#### Scenario: The summary is collapsed again
- **WHEN** the user clicks an expanded summary
- **THEN** the card SHALL show the summary on one line again

#### Scenario: The summary does not select the card
- **WHEN** the user clicks the summary, or presses Enter on it
- **THEN** the card SHALL not become selected
- **AND** Step settings SHALL not change

### Requirement: Step settings sit in a mini card that expands in place
A step card SHALL show its settings inside a mini card nested in the card: the main settings with their values, the Embed chunks model line, or "No settings". When the step has more editable settings than the card shows, the mini card SHALL end with a button "+N more settings", where N is the number left over. A click or Enter or Space on that button SHALL show the other settings, with their values and sources, inside the mini card, and the button SHALL then read "Show fewer settings". Using the button SHALL not select the card, open Step settings or start a drag. A step with no more settings SHALL show no such button.

#### Scenario: A step has more settings
- **WHEN** the Prepare query card shows three settings and has two more
- **THEN** the mini card SHALL end with a button "+2 more settings" that reports `aria-expanded` false

#### Scenario: The user expands the settings
- **WHEN** the user clicks "+2 more settings"
- **THEN** the mini card SHALL show five settings, each with its value
- **AND** the button SHALL read "Show fewer settings" and report `aria-expanded` true
- **AND** the card SHALL not be selected

#### Scenario: The user folds the settings
- **WHEN** the user clicks "Show fewer settings"
- **THEN** the mini card SHALL show the three main settings again

#### Scenario: A step has no more settings
- **WHEN** a card shows all the editable settings of its step
- **THEN** the mini card SHALL show no "more settings" button

### Requirement: The canvas header slides up to give the canvas more room
The canvas header SHALL have a toggle button with a panel-top icon, at the right end of the title row. Its name SHALL be "Hide header" while the header is shown and "Show header" while it is hidden. A click on "Hide header" SHALL slide the intro line and the pipeline tabs up. The title row SHALL stay in place: the profile name, its badges, the profile ID, "Duplicate to edit", "All profiles" and the toggle. The hidden intro line and tabs SHALL not take focus, and the toggle SHALL keep focus. A click on "Show header" SHALL slide them down again. Notices SHALL stay visible while the header is hidden. The header SHALL start shown on every visit, and the canvas SHALL fill the room that the hidden part leaves. With reduced motion, the header SHALL change without a slide.

#### Scenario: The user hides the header
- **WHEN** the user clicks "Hide header"
- **THEN** the intro line and the pipeline tabs SHALL be hidden and SHALL not take focus
- **AND** the title row, "Duplicate to edit" and "All profiles" SHALL stay visible
- **AND** the toggle SHALL read "Show header" and SHALL keep focus

#### Scenario: The user shows the header again
- **WHEN** the user clicks "Show header"
- **THEN** the intro line and the pipeline tabs SHALL show again
- **AND** the toggle SHALL read "Hide header" and SHALL keep focus

#### Scenario: A notice appears while the header is hidden
- **WHEN** the header is hidden and a notice appears, for example a refused connection
- **THEN** the notice SHALL show

#### Scenario: A new visit
- **WHEN** the user opens the canvas again
- **THEN** the header SHALL be shown
