# pipeline-canvas delta

## MODIFIED Requirements

### Requirement: Application navigation preserves working state
Navigation between workspace views, theme changes, and detail-panel interactions SHALL preserve the current Studio canvas draft and admitted run identity. The set and order of views is defined by the `workspace-presentation` capability. Stored-profile changes SHALL remain separate from saving a graph preset.

#### Scenario: User opens evidence and returns
- **WHEN** a user navigates from a Studio canvas result to citation evidence and back
- **THEN** the canvas draft, selection, and run identity SHALL remain available

#### Scenario: Graph preset is saved
- **WHEN** a graph preset is saved
- **THEN** collection profile metadata SHALL remain unchanged
- **AND** a stored-profile change SHALL require its own preview and confirmation
