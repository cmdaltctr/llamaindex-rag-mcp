# Spec Delta

## MODIFIED Requirements

### Requirement: The canvas panel groups the controls in icon accordion sections

The canvas panel SHALL be one card with these accordion sections in this order: Pipeline settings (Base profile, Collection), Operations, Steps and connections, Connect ports, Revision and run, Step settings. Pipeline settings SHALL show the base profile as read-only text and SHALL NOT offer a title or a profile choice. Each section SHALL have its own icon, shown before its title in the section header. Each section header SHALL be a button that shows whether the section is open. Several sections MAY be open at the same time. When the sub-page loads, Pipeline settings SHALL be open, and Step settings SHALL also be open if the restored draft already has a selected step. After load, selecting a step SHALL open Step settings, and starting a run from the panel SHALL open Revision and run. A run record that already exists when the sub-page loads SHALL NOT open Revision and run. Each section's content SHALL be a region named by its section title, and section headers SHALL sit one level below the page heading. Opening or closing a section SHALL NOT change the draft, the selection or the run identity.

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
