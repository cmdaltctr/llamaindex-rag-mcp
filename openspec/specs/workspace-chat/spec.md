# workspace-chat Specification

## Purpose
A chat view that answers each question from a selected knowledge base, with citations, verification status and evidence.

## Requirements

### Requirement: The user chats with a selected knowledge base

The Chat view SHALL present a history list, a transcript column with the composer docked at its bottom edge, and a knowledge base panel listing collections with their counts. On wide screens the history list SHALL sit to the left of the transcript and the knowledge base panel to its right. On narrow screens the knowledge base panel SHALL sit above the transcript, and a History button SHALL open the history list. The selected collection SHALL be the collection segment of the `#/chat/<collection>` or `#/chat/<collection>/<chat-id>` route; selecting another collection SHALL rewrite the route and keep the open chat. Opening `#/chat` without a collection SHALL select the last-used collection when the server still lists it, and otherwise SHALL ask the user to choose one. Sending a message SHALL append the user message and call `answerCollection` on the selected collection with the message text, then append the assistant turn. The view SHALL state that each question answers on its own.

#### Scenario: Ask a question

- **WHEN** a knowledge base is selected and the user sends a question
- **THEN** the transcript MUST show the user message followed by the assistant answer for that question

#### Scenario: Composer stays docked

- **WHEN** the transcript is shorter than the screen, or long enough to scroll
- **THEN** the composer MUST stay at the bottom edge of the view, and on a narrow screen the knowledge base panel MUST appear above the transcript

#### Scenario: Switch knowledge base mid-conversation

- **WHEN** the user selects a different collection after two turns
- **THEN** the next turn MUST query the newly selected collection, the route MUST name it, and the transcript MUST keep earlier turns

#### Scenario: History list placement

- **WHEN** the Chat view is open at a window width of 1024 px or more
- **THEN** the history list MUST sit to the left of the transcript
- **AND** at a width of 390 px a History button MUST open the list and the page MUST NOT scroll sideways

### Requirement: Assistant turns cite their evidence

Each assistant turn SHALL render the answer's verification status as text with its status colour, the citations as chips, and the evidence rows in a collapsible section. A `[n]` marker in the answer text SHALL be a button only when `n` is the ordinal of a returned citation; any other marker SHALL stay plain text. Pressing a citation chip or a marker button SHALL open a citation popover next to it (see "A citation popover shows the evidence and its metadata"). Opening an evidence row, or the full chunk from the popover, SHALL show the chunk in the chunk viewer.

#### Scenario: Answer with citations

- **WHEN** an answer returns two citations and verified status
- **THEN** the turn MUST show the status as text, two citation chips, and an evidence section listing both rows

#### Scenario: Open a citation

- **WHEN** the user opens a citation chip and then chooses to open the full chunk
- **THEN** the chunk viewer MUST show that chunk's text and source

#### Scenario: Marker in the answer text

- **WHEN** the answer text contains `[1]` and `[7]` and only ordinal 1 is a returned citation
- **THEN** `[1]` MUST be a button that opens the popover for citation 1 and `[7]` MUST stay plain text

### Requirement: Answer failures stay friendly

When `answerCollection` fails or the engine reports an error status, the turn SHALL show one friendly line naming the failure plus a Retry action, and MUST NOT render parser or stack text. The raw message SHALL be logged to the console only.

#### Scenario: Engine failure on a turn

- **WHEN** the answer call returns an error status
- **THEN** the turn MUST show a short failure line with a Retry action and no parser text

### Requirement: New chat clears the transcript

The Chat view SHALL offer a New chat action that shows a new, empty chat. The previous chat SHALL stay in the history list unchanged. The selected knowledge base SHALL stay unchanged. A new chat SHALL appear in the history list when its first answer is stored.

#### Scenario: Start a new chat

- **WHEN** the user chooses New chat after three turns
- **THEN** the transcript MUST be empty, the selected knowledge base MUST remain unchanged, and the previous chat MUST still be listed with its three turns

### Requirement: A citation popover shows the evidence and its metadata

The citation popover SHALL show the citation ordinal, the source name, the score with its kind when present, and the evidence text sent to the model. It SHALL show a Lineage section with the source id, the source version, the chunk position ("Chunk i of n"), the page label when present, and every chunk id the citation spans when it covers more than one chunk. It SHALL show a Metadata section that lists every other stored metadata key of the chunk with its value, read from the stored index. Long values SHALL be cut, with an action to show the full value. The popover SHALL offer an action to open the full chunk in the chunk viewer. Escape, a click outside it, or a second press SHALL close the popover and return focus to its button. When the chunk is no longer stored, the popover SHALL keep the evidence text and SHALL state that the stored chunk is not available, without an error page. The chunk viewer SHALL show the same Lineage and Metadata sections.

#### Scenario: Popover content

- **WHEN** the user presses citation chip `[2]` of an answer whose citation 2 spans two chunks of `paper.pdf`
- **THEN** the popover MUST show the source `paper.pdf`, the evidence text, the chunk position, both chunk ids and the stored metadata keys with their values

#### Scenario: Close the popover

- **WHEN** the popover is open and the user presses Escape
- **THEN** the popover MUST close and focus MUST return to the chip

#### Scenario: Source deleted after the chat was saved

- **WHEN** the user opens a stored chat whose cited source was deleted, and presses a citation chip
- **THEN** the popover MUST show the saved evidence text and a line saying the stored chunk is not available

### Requirement: Chats are stored in the workspace

Each chat SHALL be stored in the workspace database with its turns. A turn SHALL keep the question, the collection it was sent to and the answer result. A turn SHALL be stored when a usable answer arrives. A failed call, or an answer with an error status, SHALL NOT be stored; a Retry that then succeeds SHALL store the turn. Opening a stored chat SHALL show its saved turns in order and MUST NOT call `answerCollection` for them. A chat title SHALL come from the first question, cut to 60 characters. Chats SHALL survive a page reload and a server restart. Only the browser session of `omrs web` SHALL read, change or delete chats; a bearer token MUST be refused.

#### Scenario: Reload keeps the chat

- **WHEN** the user asks two questions, then reloads the page and opens the chat from the history list
- **THEN** the transcript MUST show both questions with their saved answers and no answer call MUST be made

#### Scenario: Failed answer is not stored

- **WHEN** an answer returns an error status and the user reloads the page without a Retry
- **THEN** the history MUST NOT contain that question

#### Scenario: Bearer token is refused

- **WHEN** a client with a bearer token that holds the `read` scope requests the chat list
- **THEN** the server MUST refuse the request and return no chat

### Requirement: Chats can be grouped in folders

The user SHALL be able to create, rename and delete folders in the history list. A folder holds chats and no other folder. A chat sits in one folder or in none. The user SHALL be able to drag a chat onto a folder to move it, and onto the "No folder" row to take it out. Each chat SHALL also have a "Move to" menu that does the same move by keyboard or touch.

#### Scenario: Drag a chat into a folder

- **WHEN** the user drags a chat onto a folder
- **THEN** the chat MUST appear under that folder and MUST stay there after a reload

#### Scenario: Move without a pointer

- **WHEN** the user opens the "Move to" menu of a chat with the keyboard and picks a folder
- **THEN** the chat MUST move to that folder

### Requirement: The user can delete chats and folders

The user SHALL be able to delete one chat, and to select several chats and delete them in one action. Deleting a folder SHALL delete every chat inside it. Each delete SHALL ask for confirmation first and SHALL state how many chats it removes. A confirmed delete SHALL remove the chats and their turns for good. A bulk delete SHALL remove all the selected chats or none of them. If the open chat is deleted, the view SHALL show a new empty chat.

#### Scenario: Delete several chats

- **WHEN** the user selects three chats and confirms the delete
- **THEN** the three chats MUST leave the history list and the server MUST no longer return them

#### Scenario: Delete a folder with chats

- **WHEN** the user deletes a folder that holds four chats and confirms a prompt that says four chats will be deleted
- **THEN** the folder and its four chats MUST be removed

#### Scenario: Delete the open chat

- **WHEN** the user deletes the chat that is open in the transcript
- **THEN** the view MUST show a new empty chat

#### Scenario: Cancel a delete

- **WHEN** the user cancels the confirmation
- **THEN** nothing MUST be deleted

### Requirement: Chat says when no model is connected

The Chat view SHALL read `GET /v1/settings/chat`. When Chat is not ready, the view SHALL show one plain line that names the reason and a link to `#/settings/chat`, and SHALL disable the Send action. When an answer fails at the generation stage, the failure line SHALL also link to `#/settings/chat`. The view SHALL NOT show the server's configuration text.

#### Scenario: No model connected

- **WHEN** `GET /v1/settings/chat` reports ready false with the reason `not-configured`
- **THEN** the Chat view MUST show one line saying that Chat has no model connected, with a link to `#/settings/chat`, and the Send action MUST be disabled

#### Scenario: Answering turned off

- **WHEN** `GET /v1/settings/chat` reports ready false with the reason `disabled`
- **THEN** the line MUST say that answering is turned off on the server, and MUST NOT show the text of the server error

#### Scenario: Model fails during an answer

- **WHEN** Chat is ready and an answer returns an error status with the failure stage `generation`
- **THEN** the turn MUST show the friendly failure line with a Retry action and a link to `#/settings/chat`

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
