# workspace-studio Specification

## Purpose
Studio as the home of pipelines: a gallery of templates, profile presets and saved pipelines, plus the full-width canvas sub-page where graphs are edited and run.

## Requirements

### Requirement: The canvas sub-page gives the graph the full width

Opening a profile SHALL open the `#/studio/<profile-id>` or `#/studio/<profile-id>/<purpose>` sub-page. From the `lg` breakpoint up, the flow surface SHALL fill the whole main area from the top bar to the bottom of the window, with no page padding, and one panel SHALL float over its right side. The panel SHALL hold every other control of the sub-page (see "The canvas panel groups the controls in icon accordion sections"). A slim bar above the surface SHALL show the profile header as the page heading (see "The canvas page shows the profile and its three pipelines"), the "All profiles" link and the notices. Selecting a step SHALL open that step's settings in the panel. Adding a box from the catalogue SHALL add the operation step; removing a step SHALL remove it with its connections. Below the `lg` breakpoint the panel SHALL stack under the flow surface instead of floating.

#### Scenario: Canvas fills the main area

- **WHEN** the user opens a pipeline in the canvas sub-page at a window width of 1024 px or more
- **THEN** the flow surface MUST occupy the whole main area, from the top bar down to the bottom of the window
- **AND** the page MUST NOT scroll

#### Scenario: Panel floats over the canvas

- **WHEN** the panel is expanded at a window width of 1024 px or more
- **THEN** the panel MUST sit over the right side of the flow surface with the floating-surface shadow
- **AND** the flow surface MUST keep its full width under the panel

#### Scenario: Palette on the right

- **WHEN** the user opens a pipeline in the canvas sub-page
- **THEN** the operation catalogue MUST be the Operations section of the right-hand panel and MUST be open

#### Scenario: One panel on the right

- **WHEN** the user opens a pipeline in the canvas sub-page
- **THEN** the pipeline settings, operation catalogue, step outline, connection menu, revision and run controls and step settings MUST all be inside one right-hand panel
- **AND** no other card MUST render outside that panel

#### Scenario: Node settings on selection

- **WHEN** the user selects a step on the canvas
- **THEN** the step's parameters MUST open in the panel without leaving the sub-page

#### Scenario: Empty graph

- **WHEN** the pipeline has no steps
- **THEN** the main area MUST show the empty-graph message and the operation catalogue MUST be available in the panel

#### Scenario: Narrow window

- **WHEN** the window is narrower than 1024 px
- **THEN** the panel MUST stack below the flow surface, MUST NOT offer the icon rail, and every control MUST stay reachable

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

### Requirement: The canvas panel collapses to an icon rail

From the `lg` breakpoint up, the panel header SHALL have a button that collapses the panel to a narrow floating rail on the right side of the canvas. The rail SHALL hold one icon button per section, in the same order and with the same icons as the section headers, plus a button that expands the panel. Each rail button SHALL show a tooltip with its section title. Its accessible name SHALL be the section title, followed by ", open" when that section is open. A rail button whose section is open SHALL have a filled rounded highlight. Pressing a rail button SHALL expand the panel, open that section and move focus to that section's header; it SHALL NOT close a section. Collapsing SHALL move focus to the expand button, and expanding with the expand button SHALL move focus to the collapse button. Collapsing and expanding SHALL NOT change which sections are open, the draft, the selection or the run identity. The panel SHALL start expanded. Below the `lg` breakpoint the panel SHALL show its sections whatever the collapsed state is.

#### Scenario: Collapse to the rail

- **WHEN** the panel is expanded and the user presses the collapse button
- **THEN** the panel content MUST be hidden and out of the tab order, and the rail MUST show six section buttons and an expand button
- **AND** the flow surface MUST stay at full width
- **AND** focus MUST move to the expand button

#### Scenario: Rail button opens its section

- **WHEN** the panel is collapsed and the user presses the Connect ports rail button
- **THEN** the panel MUST expand and the Connect ports section MUST be open

#### Scenario: Open sections are highlighted on the rail

- **WHEN** Operations is open and the panel is collapsed
- **THEN** the Operations rail button MUST show the filled highlight and have the accessible name "Operations, open"
- **AND** the other rail buttons MUST NOT show the highlight and MUST have only their section title as the accessible name

#### Scenario: Selection while collapsed

- **WHEN** the panel is collapsed and the user selects a step
- **THEN** the panel MUST stay collapsed
- **AND** the Step settings rail button MUST show the highlight and have the accessible name "Step settings, open"
- **AND** pressing it MUST expand the panel with that step's parameters

#### Scenario: State survives a round trip

- **WHEN** the user opens Pipeline settings, collapses the panel and expands it again
- **THEN** Pipeline settings MUST still be open and the draft MUST be unchanged

#### Scenario: Rail button on an open section

- **WHEN** Operations is open, the panel is collapsed and the user presses the Operations rail button
- **THEN** the panel MUST expand and Operations MUST stay open

#### Scenario: Collapsed state on a narrow window

- **WHEN** the user collapses the panel and the window then narrows below 1024 px
- **THEN** the stacked panel MUST show its sections and no rail

#### Scenario: Keyboard use of the rail

- **WHEN** a keyboard user tabs to a rail button and presses Enter or Space
- **THEN** the panel MUST expand with that section open and focus MUST move to that section's header

### Requirement: Studio explains what a profile is

The Studio page header SHALL show two sentences under the heading: "Profiles are groups of steps that you connect into pipelines to ingest files, search them and answer questions. Each collection uses one profile, and the profile decides how that collection works." Under the header, a closed disclosure named "How profiles work" SHALL hold four lines of plain text that explain built-in and user profiles, the three pipelines, where a collection picks its profile, and the embedding model lock.

#### Scenario: Header text

- **WHEN** the user opens `#/studio`
- **THEN** the text under the "Studio" heading MUST read "Profiles are groups of steps that you connect into pipelines to ingest files, search them and answer questions. Each collection uses one profile, and the profile decides how that collection works."
- **AND** the text "Build pipelines from templates and run them." MUST NOT appear

#### Scenario: Disclosure is closed at first

- **WHEN** the user opens `#/studio`
- **THEN** a disclosure named "How profiles work" MUST be present and closed

#### Scenario: Disclosure text

- **WHEN** the user opens "How profiles work"
- **THEN** it MUST show these four lines in this order:
  1. "Built-in profiles come with OMRG and are read-only. Your profiles are copies that you can rename, change and delete."
  2. "Each profile has three pipelines: Ingest reads files and splits them into chunks, Search finds the best chunks for a question, and Answer writes a cited answer."
  3. "To use a profile, pick it for a collection in Knowledge Base, under Profile."
  4. "When a collection holds vectors, the embedding model of its profile is locked, because the stored vectors were made with that model."

### Requirement: Studio opens on a profile gallery

The Studio view SHALL list the profiles from `GET /v1/profiles` in two sections: "Built-in profiles" and "Your profiles". Each card SHALL show the title, the profile ID in grey, the description and how many collections use it. A built-in card SHALL offer "Open profile" and "Duplicate". A user profile card SHALL also offer a rename pencil and "Delete". A profile that is not ready SHALL show a "Not ready" badge and its reasons as text. "Your profiles" SHALL end with a "New empty profile" card.

#### Scenario: Gallery contents

- **WHEN** the server lists the built-in profiles Documents and Codebase and one user profile "Papers search"
- **THEN** the "Built-in profiles" section MUST show the Documents and Codebase cards
- **AND** the "Your profiles" section MUST show the "Papers search" card and then the "New empty profile" card
- **AND** no "Templates", "Profile presets" or "Saved pipelines" section MUST appear

#### Scenario: Card details

- **WHEN** the user profile `papers-search` with the title "Papers search" is used by the collections `papers` and `notes`
- **THEN** its card MUST show "Papers search", the grey text `papers-search` and "Used by 2 collections"

#### Scenario: Unused profile

- **WHEN** no collection uses a profile
- **THEN** its card MUST show "Not used by any collection"

#### Scenario: Built-in card actions

- **WHEN** the gallery shows the Documents card
- **THEN** it MUST offer "Open profile" and "Duplicate"
- **AND** it MUST NOT offer a rename pencil or "Delete"

#### Scenario: Not ready profile

- **WHEN** the server marks a user profile not ready with the reason "The Answer pipeline has no `answer` output."
- **THEN** its card MUST show a "Not ready" status badge and the text "The Answer pipeline has no `answer` output."

#### Scenario: Open a profile

- **WHEN** the user selects "Open profile" on the card of `papers-search`
- **THEN** `#/studio/papers-search` MUST open on that profile's Ingest pipeline

#### Scenario: No user profiles yet

- **WHEN** the server lists no user profile
- **THEN** "Your profiles" MUST show the line "You have no profiles yet. Duplicate a built-in profile or start an empty one." and the "New empty profile" card

#### Scenario: Profiles cannot load

- **WHEN** the profile listing fails
- **THEN** the gallery MUST show one friendly failure line with a Retry action
- **AND** the "New empty profile" card MUST remain enabled

### Requirement: A new profile starts from a copy or from nothing

"Duplicate" and "New empty profile" SHALL open one dialog that asks for the title before anything is created, because the server makes the permanent profile ID from it. The dialog SHALL say "The profile ID is made from this title. It cannot change later." Creating SHALL call `POST /v1/profiles` with the source profile ID, or `null` for an empty profile, and the title. On success `#/studio/<new-profile-id>` SHALL open.

#### Scenario: Duplicate a built-in profile

- **WHEN** the user selects "Duplicate" on the Documents card, keeps the proposed title "Documents copy" and selects "Create profile", and the server returns the ID `documents-copy`
- **THEN** the client MUST send `{source: "documents", title: "Documents copy"}` to `POST /v1/profiles`
- **AND** `#/studio/documents-copy` MUST open on the Ingest pipeline of the copy

#### Scenario: Start an empty profile

- **WHEN** the user selects the "New empty profile" card, types "Notes" and selects "Create profile"
- **THEN** the client MUST send `{source: null, title: "Notes"}` to `POST /v1/profiles`

#### Scenario: Empty title is refused

- **WHEN** the title field holds only spaces and the user selects "Create profile"
- **THEN** the dialog MUST show "Enter a title." next to the field and MUST NOT send a request

#### Scenario: Server refuses the title

- **WHEN** the server refuses the create request
- **THEN** the dialog MUST stay open with the typed title and show one friendly failure line

#### Scenario: Cancel creates nothing

- **WHEN** the user selects "Cancel" or presses Escape in the dialog
- **THEN** no request MUST be sent and focus MUST return to the button that opened the dialog

### Requirement: User profiles can be renamed in place

A pencil next to a user profile title SHALL open an inline title field, on the gallery card and in the canvas header. Enter or "Save" SHALL send `PATCH /v1/profiles/{id}` with the trimmed title. Escape or "Cancel" SHALL close the field with no request. The profile ID SHALL stay shown in grey and SHALL NOT change. The profile title SHALL be the only title Studio shows for a profile; the web SHALL NOT read or write a title in the pipeline layout.

#### Scenario: Rename from the gallery

- **WHEN** the user renames "Papers search" to "Papers, strict" on its card and presses Enter
- **THEN** the client MUST send `{title: "Papers, strict"}` to `PATCH /v1/profiles/papers-search`
- **AND** the card MUST show "Papers, strict" with the grey ID `papers-search`

#### Scenario: Rename on the canvas shows in the gallery

- **WHEN** the user renames the profile from the canvas header and then selects "All profiles"
- **THEN** the gallery card MUST show the new title

#### Scenario: Layout title is ignored

- **WHEN** a pipeline layout from an earlier version holds the title "Old name" and the profile title is "Papers search"
- **THEN** the canvas heading MUST read "Papers search"
- **AND** a saved layout MUST NOT carry a title

#### Scenario: Empty title is refused

- **WHEN** the user clears the title and presses Enter
- **THEN** the field MUST show "Enter a title." and MUST NOT send a request

#### Scenario: Rename fails

- **WHEN** the server refuses the rename
- **THEN** the old title MUST stay and one friendly failure line with a Retry action MUST show

#### Scenario: Built-in profiles keep their title

- **WHEN** the gallery or the canvas header shows a built-in profile
- **THEN** no rename pencil MUST be offered

### Requirement: User profiles can be deleted when no collection uses them

"Delete" on a user profile card SHALL open a confirmation dialog titled "Delete <title>?" that says "Collections can no longer pick this profile. Past runs stay in Experiments." Confirming SHALL call `DELETE /v1/profiles/{id}` and remove the card. While any collection uses the profile, "Delete" SHALL be disabled and visible text SHALL give the reason and name the collections.

#### Scenario: Delete an unused profile

- **WHEN** the user deletes an unused profile and selects "Delete profile" in the dialog
- **THEN** the client MUST call `DELETE /v1/profiles/<id>` once
- **AND** the card MUST disappear and the status line "Profile deleted." MUST show

#### Scenario: Profile in use

- **WHEN** the collections `papers` and `notes` use a profile
- **THEN** its "Delete" button MUST be disabled
- **AND** the card MUST show "You cannot delete this profile while collections use it: papers, notes. Pick another profile for them in Knowledge Base first."

#### Scenario: Server refuses because the profile came into use

- **WHEN** the server answers the delete with status 409 and `used_by` `["papers"]`
- **THEN** the dialog MUST show "You cannot delete this profile while collections use it: papers." and MUST NOT remove the card

#### Scenario: Cancel keeps the profile

- **WHEN** the user selects "Cancel" in the dialog
- **THEN** no request MUST be sent and focus MUST return to the "Delete" button

### Requirement: The canvas page shows the profile and its three pipelines

`#/studio/<profile-id>/<purpose>` SHALL open the pipeline of that purpose on the canvas; `#/studio/<profile-id>` SHALL open Ingest. The slim bar SHALL show the profile title as the page heading, the profile ID in grey, a "Built-in" or "Your profile" badge, the "Not ready" badge with reasons when it applies, and a navigation named "Pipelines of this profile" with links Ingest, Search and Answer. The link of the open purpose SHALL be marked current. One line SHALL describe the open purpose.

#### Scenario: Tabs open the slot pipelines

- **WHEN** the user opens the Search link on the canvas page of `papers-search`
- **THEN** the address bar MUST read `#/studio/papers-search/search` and the canvas MUST load the profile's Search pipeline
- **AND** the Search link MUST have `aria-current="page"`

#### Scenario: No purpose in the route

- **WHEN** the user opens `#/studio/papers-search`
- **THEN** the Ingest pipeline MUST open and the Ingest link MUST have `aria-current="page"`

#### Scenario: Purpose line

- **WHEN** the Ingest, Search or Answer pipeline is open
- **THEN** the line under the links MUST read "Reads files, splits them into chunks and stores them in the collection.", "Finds the chunks that best match a question." or "Writes an answer from the best chunks and cites them." respectively

#### Scenario: Switching tabs keeps unsaved edits

- **WHEN** the user edits the Ingest pipeline, opens the Search link and then opens the Ingest link again
- **THEN** the unsaved Ingest draft MUST be shown again

#### Scenario: Unknown profile

- **WHEN** the user opens `#/studio/pl_1` and the server returns no profile with the ID `pl_1`
- **THEN** the page MUST show a not-found state for the profile with the link "Back to Studio" to `#/studio`

#### Scenario: Back to the gallery

- **WHEN** the user selects "All profiles"
- **THEN** the gallery at `#/studio` MUST open

### Requirement: Built-in profiles open read-only

A built-in profile SHALL show, for each purpose, the standard graph that a duplicate of it would get, from the `standard_graphs` field of `GET /v1/profiles/{id}`, on a read-only canvas (see the `pipeline-canvas` requirement "A read-only canvas shows a graph without changing it"). The slim bar SHALL show "Built-in profiles are read-only. Duplicate this profile to change it." with a "Duplicate to edit" button that opens the duplicate dialog for that profile.

#### Scenario: Read-only notice

- **WHEN** the user opens `#/studio/documents/search`
- **THEN** the canvas MUST show the graph from `standard_graphs.search` of `documents`
- **AND** the slim bar MUST show "Built-in profiles are read-only. Duplicate this profile to change it." and a "Duplicate to edit" button

#### Scenario: No run on a built-in

- **WHEN** the user opens Revision and run on a built-in profile
- **THEN** the section MUST show "Duplicate this profile to save and run its pipelines." and a Validate button, and no Run button

#### Scenario: Duplicate to edit

- **WHEN** the user selects "Duplicate to edit" and creates the copy
- **THEN** the canvas page of the copy MUST open on Ingest and allow editing

### Requirement: Saving a pipeline of a profile in use warns first

When the open pipeline belongs to a profile that one or more collections use, "Save revision" SHALL first open a dialog titled "Save this revision?" that names those collections. The text SHALL depend on the purpose. "Save revision" in the dialog SHALL save; "Cancel" SHALL save nothing. When no collection uses the profile, the save SHALL start with no dialog. After a save, the status line SHALL name the collections from the `affected_collections` field of the response.

#### Scenario: Search pipeline in use

- **WHEN** the collections `papers` and `notes` use the profile and the user selects "Save revision" on the Search pipeline
- **THEN** the dialog MUST say "Saving changes how 2 collections are searched: papers, notes."
- **AND** no revision MUST be sent until the user confirms

#### Scenario: Answer pipeline in use

- **WHEN** one collection `papers` uses the profile and the user saves the Answer pipeline
- **THEN** the dialog MUST say "Saving changes how 1 collection answers questions: papers."

#### Scenario: Ingest pipeline in use

- **WHEN** the collection `papers` uses the profile and the user saves the Ingest pipeline
- **THEN** the dialog MUST say "Saving changes how 1 collection ingests files: papers. Documents already in these collections keep their old chunks until you ingest them again."

#### Scenario: Profile not in use

- **WHEN** no collection uses the profile and the user selects "Save revision"
- **THEN** the revision MUST be sent with no dialog

#### Scenario: Status names the affected collections

- **WHEN** the server saves revision 4 and returns `affected_collections` `["papers", "notes"]`
- **THEN** the status line MUST read "Saved revision 4. It now applies to 2 collections: papers, notes."

#### Scenario: Cancel keeps the draft

- **WHEN** the user selects "Cancel" in the dialog
- **THEN** no revision MUST be sent and the draft MUST stay unchanged

### Requirement: The canvas arranges the pipeline horizontally or vertically

The canvas SHALL show a toolbar at its top left. The toolbar SHALL hold a button that switches the arrangement between horizontal (steps flow left to right) and vertical (steps flow top to bottom). The button SHALL name the arrangement it will apply. Applying an arrangement SHALL place each step in a layer by its connections, move the step positions, turn the connection points to match (left and right for horizontal, top and bottom for vertical), and fit the view to the graph. The arrangement SHALL be part of the presentation layout and SHALL be stored by the Save layout action like any position change. It MUST NOT create a revision or change the execution graph. A layout saved before this change SHALL open as horizontal. On a built-in profile's read-only canvas the button SHALL change the view for the visit only.

#### Scenario: Arrange vertically

- **WHEN** the user presses the arrange button on a horizontal three-step pipeline
- **THEN** the steps MUST sit in one column in connection order and the connection points MUST be at the top and bottom of each step

#### Scenario: No new revision

- **WHEN** the user changes the arrangement and saves the layout
- **THEN** the pipeline's current revision MUST be unchanged
- **AND** reopening the pipeline MUST show the vertical arrangement

#### Scenario: Read-only canvas

- **WHEN** the user arranges a built-in profile's standard graph
- **THEN** the steps MUST move and no layout MUST be sent to the server

### Requirement: The canvas has a full screen mode

The toolbar SHALL hold a full screen button. Full screen SHALL hide the navigation, the top bar, the profile header and the notices, and SHALL show the canvas, the toolbar, the canvas panel and an "X" button over the whole window. Entering full screen SHALL move focus to the "X" button. The "X" button and the Escape key SHALL leave full screen; Escape SHALL be ignored while focus is in a text field. Leaving SHALL restore the page as it was, with the same selection and viewport, and SHALL return focus to the full screen button. Full screen SHALL end when the user leaves the canvas sub-page.

#### Scenario: Enter and leave full screen

- **WHEN** the user presses the full screen button and then the "X" button
- **THEN** only the canvas, its toolbar and its panel MUST be visible while in full screen, and the normal page MUST return after the "X" with the same step selected

#### Scenario: Escape leaves full screen

- **WHEN** the canvas is in full screen and the user presses Escape
- **THEN** the canvas MUST leave full screen and focus MUST return to the full screen button

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
