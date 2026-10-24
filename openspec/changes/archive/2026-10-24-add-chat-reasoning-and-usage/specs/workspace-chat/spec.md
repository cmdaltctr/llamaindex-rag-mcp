## ADDED Requirements

### Requirement: An answer shows its reasoning in a collapsed box

When an assistant turn carries reasoning text, the turn SHALL show a "Reasoning" box above the answer. The box SHALL start collapsed. Its text SHALL be smaller than the answer text and use the muted colour. Opening the box SHALL show the reasoning as plain text, with no citation buttons. A turn without reasoning SHALL show no box.

#### Scenario: Answer with reasoning

- **WHEN** an answer arrives with a `reasoning` field
- **THEN** the turn MUST show a collapsed "Reasoning" control above the answer, and the reasoning text MUST NOT be visible until the user opens it

#### Scenario: Old saved turn

- **WHEN** the user opens a chat saved before this change
- **THEN** its turns MUST show no Reasoning control

#### Scenario: Keyboard use

- **WHEN** the user focuses the Reasoning control and presses Enter
- **THEN** the box MUST open, and the control MUST report its open state to screen readers

### Requirement: The question box shows tokens and cost of the latest answer

The question box SHALL show one line of small muted text at its top right. The line SHALL give the tokens and cost of the latest answer in the open chat, for example `1,240 in · 380 out · 210 reasoning · $0.0012`. It SHALL omit a figure that is `null`. When the remaining credit is available, the line SHALL end with it, for example `· $2.81 left`. The line SHALL show nothing when the latest answer has no `usage`. Hovering or focusing the line SHALL show the full figures, including the number of model calls.

#### Scenario: Latest answer with usage

- **WHEN** the latest answer carries `usage` with 1240 input tokens, 380 output tokens, 210 reasoning tokens and a cost of 0.0012
- **THEN** the line MUST read `1,240 in · 380 out · 210 reasoning · $0.0012`

#### Scenario: Remaining credit known

- **WHEN** `GET /v1/usage/credit` returns `remaining_usd` 2.81
- **THEN** the line MUST end with `· $2.81 left`

#### Scenario: Cost unknown

- **WHEN** the latest answer has `cost_usd` null
- **THEN** the line MUST show the tokens and MUST NOT show a dollar figure

#### Scenario: Credit is read after an answer, not on every render

- **WHEN** a new answer finishes
- **THEN** Chat MUST request `GET /v1/usage/credit` once, and MUST NOT request it while the user types

#### Scenario: Phone width

- **WHEN** the page is 390 px wide
- **THEN** the line MUST stay on one row above the question box, cut with an ellipsis if needed, and the page MUST NOT scroll sideways
