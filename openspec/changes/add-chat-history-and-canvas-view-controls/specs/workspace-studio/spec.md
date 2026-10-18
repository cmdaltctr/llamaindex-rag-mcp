# Spec Delta

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

The toolbar SHALL hold a full screen button. Full screen SHALL hide the navigation, the top bar, the profile header, the notices and the panel, and SHALL show only the canvas, the toolbar and an "X" button over the whole window. Entering full screen SHALL move focus to the "X" button. The "X" button and the Escape key SHALL leave full screen; Escape SHALL be ignored while focus is in a text field. Leaving SHALL restore the page as it was, with the same selection and viewport, and SHALL return focus to the full screen button. Full screen SHALL end when the user leaves the canvas sub-page.

#### Scenario: Enter and leave full screen

- **WHEN** the user presses the full screen button and then the "X" button
- **THEN** only the canvas MUST be visible while in full screen, and the normal page MUST return after the "X" with the same step selected

#### Scenario: Escape leaves full screen

- **WHEN** the canvas is in full screen and the user presses Escape
- **THEN** the canvas MUST leave full screen and focus MUST return to the full screen button
