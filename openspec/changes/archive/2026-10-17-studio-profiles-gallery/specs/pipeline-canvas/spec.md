## ADDED Requirements

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
