# Spec Delta

## ADDED Requirements

### Requirement: A running answer shows its stage

While a turn waits for its answer, Chat SHALL show the current stage in plain words: "Searching", "Writing the answer", "Checking citations" or "Verifying claims". Finished stages SHALL stay in view with a tick. A seconds counter SHALL run from the moment the question is sent. The stage line SHALL be a polite live region, and the counter SHALL stay outside it. A stage that does not run SHALL NOT appear. When the answer arrives, the progress SHALL give way to the answer.

#### Scenario: Stages in order

- **WHEN** a question is sent and the server reports `searching`, then `writing`, then `citing`
- **THEN** the turn MUST show "Searching" with a tick, "Writing the answer" with a tick and "Checking citations" as the current stage
- **AND** the counter MUST show the seconds since the question was sent

#### Scenario: Verification is off

- **WHEN** an answer finishes without a `verifying` stage
- **THEN** the turn MUST NOT have shown "Verifying claims"

#### Scenario: No evidence

- **WHEN** the server reports `searching` and then the no-evidence result
- **THEN** the turn MUST NOT show "Writing the answer"
- **AND** the no-evidence answer MUST replace the progress

#### Scenario: A screen reader user

- **WHEN** the stage changes
- **THEN** the live region MUST announce the new stage once
- **AND** the counter MUST NOT be announced on each tick

#### Scenario: Narrow screen

- **WHEN** the progress shows at a width of 390 px in the light and the dark theme
- **THEN** it MUST fit the transcript column and the page MUST NOT scroll sideways

### Requirement: Chat answers when the stream is unavailable

Stage progress SHALL be a convenience and SHALL NOT be a dependency of the answer. When the browser cannot read a streamed body, or the server has no stream route, Chat SHALL ask `answerCollection` as before. When the stream opens but delivers no stage, the turn SHALL show "Waiting for the answer." with the seconds counter. A stream that ends with no result SHALL show the friendly failure line with a Retry action and SHALL NOT start a second answer by itself.

#### Scenario: Browser cannot stream

- **WHEN** the browser cannot read a streamed response body
- **THEN** Chat MUST call the blocking answer route and show "Waiting for the answer." with the counter
- **AND** the answer MUST appear when it arrives

#### Scenario: Server has no stream route

- **WHEN** the stream route answers 404 or 405 before any frame
- **THEN** Chat MUST call the blocking answer route once and show its result

#### Scenario: Stream delivers no stage

- **WHEN** the stream is open for 10 seconds with no frame
- **THEN** the turn MUST show "Waiting for the answer." and a counter that reads 10 s

#### Scenario: Stream drops mid-answer

- **WHEN** the connection closes after two stages and before the result
- **THEN** the turn MUST show one friendly failure line with a Retry action and no parser or network text
- **AND** Chat MUST NOT call the blocking route by itself

#### Scenario: Refusal is not a fallback

- **WHEN** the stream route answers 403 or 503
- **THEN** Chat MUST show the friendly failure line and MUST NOT call the blocking route

### Requirement: Leaving a turn stops its answer

When a turn that waits for its answer leaves the page, or the user presses Retry on it, Chat SHALL abort the request for the old answer. An aborted request SHALL NOT show an error.

#### Scenario: User leaves the chat mid-answer

- **WHEN** the user opens another chat while an answer runs
- **THEN** Chat MUST abort the stream request of the running answer
- **AND** no failure line MUST appear for it

#### Scenario: Retry replaces the running request

- **WHEN** the user presses Retry
- **THEN** Chat MUST abort any request still open for that turn before it sends the new one

### Requirement: Stage progress is never stored

A chat SHALL store the finished answer result only. Stage names, sequence numbers and timings SHALL NOT enter the workspace database, the chat list or an exported chat. A reopened chat SHALL show no progress.

#### Scenario: Reload after an answer

- **WHEN** the user asks a question, sees three stages, then reloads and opens the chat
- **THEN** the turn MUST show the saved answer with no stage line
- **AND** the stored turn MUST hold the question, the collection and the answer result only

#### Scenario: Failed answer

- **WHEN** an answer ends with an error status after two stages
- **THEN** the history MUST NOT contain that question, as before
