## ADDED Requirements

### Requirement: Each extraction backend is implemented outside the dispatch module

Every registered metadata extraction backend SHALL be implemented in its own
module. The module that dispatches between backends SHALL NOT contain any
backend's implementation, and SHALL NOT import a concrete backend module at
import time.

Adding a backend SHALL therefore require one new module and one registration,
with no edit to the dispatch module's logic.

#### Scenario: Every registered backend resolves outside the dispatch module

- **WHEN** the extraction registry is enumerated
- **THEN** no registered backend resolves to the dispatch module

#### Scenario: A backend is added

- **WHEN** a new extraction backend is introduced
- **THEN** it is added as a new module plus one registration
- **AND** the dispatch module gains no branch naming that backend

#### Scenario: Backend selection is unchanged by the module move

- **WHEN** configuration selects the `openrouter` extraction backend
- **THEN** extraction behaviour, including structured-output downgrade handling,
  is identical to before the backend was moved out of the dispatch module
