## ADDED Requirements

### Requirement: The accordion primitive keeps the Radix accessibility contract

`web/src/components/ui/` SHALL provide an accordion primitive that allows several sections open at once. It SHALL keep the Radix behaviour: each header is a button with `aria-expanded` and `aria-controls`, Enter and Space toggle a section, the arrow keys, Home and End move focus between headers, and closed content is hidden from assistive technology. It SHALL let a header show a leading icon that is hidden from assistive technology, so the title stays the accessible name. It SHALL use the shared semantic tokens, show a visible focus ring and carry the open state as text or an icon that changes with the state.

#### Scenario: Header state

- **WHEN** a section is closed and the user opens it
- **THEN** its header MUST report `aria-expanded="true"` and its content MUST be visible

#### Scenario: Arrow keys move between headers

- **WHEN** focus is on a section header and the user presses the Down arrow
- **THEN** focus MUST move to the next section header

#### Scenario: Closed content is hidden

- **WHEN** a section is closed
- **THEN** its content MUST NOT be reachable by Tab or exposed to a screen reader

#### Scenario: Header icon does not change the name

- **WHEN** a section header shows a leading icon and the title "Operations"
- **THEN** the header's accessible name MUST be "Operations"
