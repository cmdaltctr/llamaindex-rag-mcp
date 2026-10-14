# workspace-chat delta

## Purpose

A chat view that answers each question from a selected knowledge base, with citations, verification status and evidence.

## ADDED Requirements

### Requirement: The user chats with a selected knowledge base

The Chat view SHALL present a transcript column and a composer, and a right-hand knowledge base panel listing collections with their counts. The selected collection SHALL be the collection segment of the `#/chat/<collection>` route; selecting another collection SHALL rewrite the route. Opening `#/chat` without a collection SHALL select the last-used collection when the server still lists it, and otherwise SHALL ask the user to choose one. Sending a message SHALL append the user message and call `answerCollection` on the selected collection with the message text, then append the assistant turn. The view SHALL state that each question answers on its own.

#### Scenario: Ask a question

- **WHEN** a knowledge base is selected and the user sends a question
- **THEN** the transcript MUST show the user message followed by the assistant answer for that question

#### Scenario: Switch knowledge base mid-conversation

- **WHEN** the user selects a different collection after two turns
- **THEN** the next turn MUST query the newly selected collection, the route MUST name it, and the transcript MUST keep earlier turns

### Requirement: Assistant turns cite their evidence

Each assistant turn SHALL render the answer's verification status as text with its status colour, the citations as chips, and the evidence rows in a collapsible section. Opening a citation or evidence row SHALL show the chunk in the chunk viewer.

#### Scenario: Answer with citations

- **WHEN** an answer returns two citations and verified status
- **THEN** the turn MUST show the status as text, two citation chips, and an evidence section listing both rows

#### Scenario: Open a citation

- **WHEN** the user opens a citation chip
- **THEN** the chunk viewer MUST show that chunk's text and source

### Requirement: Answer failures stay friendly

When `answerCollection` fails or the engine reports an error status, the turn SHALL show one friendly line naming the failure plus a Retry action, and MUST NOT render parser or stack text. The raw message SHALL be logged to the console only.

#### Scenario: Engine failure on a turn

- **WHEN** the answer call returns an error status
- **THEN** the turn MUST show a short failure line with a Retry action and no parser text

### Requirement: New chat clears the transcript

The Chat view SHALL offer a New chat action that clears the transcript of the active conversation. Transcripts SHALL NOT be stored server-side.

#### Scenario: Start a new chat

- **WHEN** the user chooses New chat after three turns
- **THEN** the transcript MUST be empty and the selected knowledge base MUST remain unchanged
