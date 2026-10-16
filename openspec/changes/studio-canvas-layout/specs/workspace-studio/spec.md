## MODIFIED Requirements

### Requirement: The canvas sub-page gives the graph the full width

Editing or creating a pipeline SHALL open the `#/studio/<pipeline-id>` sub-page. From the `lg` breakpoint up, the flow surface SHALL fill the whole main area from the top bar to the bottom of the window, with no page padding, and one panel SHALL float over its right side. The panel SHALL hold every other control of the sub-page (see "The canvas panel groups the controls in icon accordion sections"). A slim bar above the surface SHALL show the pipeline title as the page heading, the "All pipelines" link and the notices. Selecting a node SHALL open that node's settings in the panel. Adding a box from the catalogue SHALL add the operation node; removing a node SHALL remove it with its connections. Below the `lg` breakpoint the panel SHALL stack under the flow surface instead of floating.

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
- **THEN** the pipeline settings, operation catalogue, node outline, connection menu, revision and run controls and node settings MUST all be inside one right-hand panel
- **AND** no other card MUST render outside that panel

#### Scenario: Node settings on selection

- **WHEN** the user selects a node on the canvas
- **THEN** the node's parameters MUST open in the panel without leaving the sub-page

#### Scenario: Empty graph

- **WHEN** the pipeline has no nodes
- **THEN** the main area MUST show the empty-graph message and the operation catalogue MUST be available in the panel

#### Scenario: Narrow window

- **WHEN** the window is narrower than 1024 px
- **THEN** the panel MUST stack below the flow surface, MUST NOT offer the icon rail, and every control MUST stay reachable

## ADDED Requirements

### Requirement: The canvas panel groups the controls in icon accordion sections

The canvas panel SHALL be one card with these accordion sections in this order: Pipeline settings (Title, Profile, Collection), Operations, Nodes and connections, Connect ports, Revision and run, Node settings. Each section SHALL have its own icon, shown before its title in the section header. Each section header SHALL be a button that shows whether the section is open. Several sections MAY be open at the same time. When the sub-page loads, Operations SHALL be open, and Node settings SHALL also be open if the restored draft already has a selected node. After load, selecting a node SHALL open Node settings, and starting a run from the panel SHALL open Revision and run. A run record that already exists when the sub-page loads SHALL NOT open Revision and run. Each section's content SHALL be a region named by its section title, and section headers SHALL sit one level below the page heading. Opening or closing a section SHALL NOT change the draft, the selection or the run identity.

#### Scenario: Pipeline settings sit above Operations

- **WHEN** the user opens the canvas sub-page
- **THEN** the Pipeline settings section header MUST come before the Operations section header in the panel

#### Scenario: Every section has an icon

- **WHEN** the panel is expanded
- **THEN** each of the six section headers MUST show an icon, and no two sections MUST share the same icon

#### Scenario: Default open state

- **WHEN** the canvas sub-page loads with no selected node
- **THEN** Operations MUST be open and the other sections MUST be closed

#### Scenario: Restored selection

- **WHEN** the canvas sub-page loads a draft that has a selected node
- **THEN** Operations and Node settings MUST be open and the other sections MUST be closed

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

- **WHEN** the user selects a node while Node settings is closed
- **THEN** Node settings MUST open and show that node's parameters

#### Scenario: Run opens its section

- **WHEN** the user starts a run while Revision and run is closed
- **THEN** Revision and run MUST open and show the run progress

#### Scenario: Closing keeps work

- **WHEN** the user closes Pipeline settings after editing the title
- **THEN** the edited title MUST remain in the draft and reappear when the section opens again

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

- **WHEN** the panel is collapsed and the user selects a node
- **THEN** the panel MUST stay collapsed
- **AND** the Node settings rail button MUST show the highlight
- **AND** pressing it MUST expand the panel with that node's parameters

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
