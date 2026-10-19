# Spec Delta

## ADDED Requirements

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
