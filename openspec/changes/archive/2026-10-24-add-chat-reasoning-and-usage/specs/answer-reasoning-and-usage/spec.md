## ADDED Requirements

### Requirement: A reasoning level is sent only when one is set

The `answer` settings block SHALL hold `reasoning` for the Chat model and `verify_reasoning` for the claim judge. Each SHALL be empty or a level of 1 to 32 characters from letters, digits, `-` and `_`. An empty level SHALL send no reasoning field, so the provider uses its own default. A set level SHALL go to the provider on every call for that role. The provider SHALL map it to its own request field. A provider with no mapping SHALL send nothing and SHALL report that it ignores the level.

#### Scenario: Empty level keeps current behaviour

- **WHEN** `answer.reasoning` is empty and an answer runs on OpenRouter
- **THEN** the request MUST NOT contain a `reasoning` field

#### Scenario: Level sent to OpenRouter

- **WHEN** `answer.reasoning` is `low` and an answer runs on OpenRouter
- **THEN** every completion request for that answer MUST contain `reasoning: {"effort": "low"}`

#### Scenario: Judge level is separate

- **WHEN** `answer.reasoning` is `high` and `answer.verify_reasoning` is empty
- **THEN** judge requests MUST NOT contain a reasoning field, and answer requests MUST contain the level `high`

#### Scenario: Invalid level refused

- **WHEN** a save sets `answer.reasoning` to `high; drop`
- **THEN** the server MUST refuse the save with 400 and MUST NOT change the setting

#### Scenario: Provider without a mapping

- **WHEN** the Chat provider is `llamacpp` and `answer.reasoning` is `low`
- **THEN** the request MUST NOT contain a reasoning field, and `GET /v1/settings/chat` MUST report that the provider ignores the level

### Requirement: Reasoning text is kept apart from the answer

When the provider returns reasoning text in a field apart from the answer, the answer result SHALL carry that text in a `reasoning` field. The `answer` field SHALL hold only the answer content. Citation parsing and claim checks SHALL read only the `answer` field. The MCP answering tool SHALL include `reasoning` only when the caller asks for it. The web answer route SHALL always include it.

#### Scenario: Reasoning returned separately

- **WHEN** the provider reply has the content `The sky is blue [1].` and the reasoning `The user asks about colour.`
- **THEN** the result `answer` MUST be `The sky is blue [1].` and the result `reasoning` MUST be `The user asks about colour.`

#### Scenario: No reasoning returned

- **WHEN** the provider reply has no reasoning field
- **THEN** the result MUST NOT contain a `reasoning` field

#### Scenario: Several model calls

- **WHEN** one answer needs two completion calls and both return reasoning
- **THEN** the result `reasoning` MUST hold both texts in call order, with a blank line between them

#### Scenario: MCP caller does not ask

- **WHEN** an MCP client calls the answering tool without asking for reasoning
- **THEN** the tool result MUST NOT contain a `reasoning` field

### Requirement: Each answer records its tokens and cost

The answer result SHALL carry a `usage` object whenever the server's own model wrote the answer. It SHALL hold `input_tokens`, `output_tokens`, `reasoning_tokens`, `cost_usd` and `calls`, summed over every completion call for that answer, judge calls included. A figure the provider did not report SHALL be `null`, never `0`. An answer written through client sampling SHALL carry no `usage` object.

#### Scenario: OpenRouter reports usage

- **WHEN** an answer makes one OpenRouter call that reports 25 input tokens, 11 output tokens, 2 reasoning tokens and a cost of 0.00000925
- **THEN** the result `usage` MUST be `{"input_tokens": 25, "output_tokens": 11, "reasoning_tokens": 2, "cost_usd": 0.00000925, "calls": 1}`

#### Scenario: Judge calls are added

- **WHEN** the answer call costs 0.001 and two judge calls cost 0.0002 each
- **THEN** `usage.cost_usd` MUST be 0.0014 and `usage.calls` MUST be 3

#### Scenario: Provider reports no cost

- **WHEN** the Chat provider is Ollama, which reports tokens but no cost
- **THEN** `usage.cost_usd` MUST be `null`

#### Scenario: Usage is saved with the turn

- **WHEN** a finished answer is saved to Chat history and the chat is opened later
- **THEN** the saved turn MUST carry the same `usage` object, and opening it MUST NOT call the model

### Requirement: Remaining credit is read only on request

`GET /v1/usage/credit` SHALL return the remaining credit for the Chat provider when the provider publishes it, else `{"available": false}`. For OpenRouter it SHALL read the key's spending limit and SHALL return `limit_usd` and `remaining_usd`. A key with no limit SHALL return `available: false`. The server SHALL send no provider request for this until the route is called. The API key SHALL NOT appear in the response or the log.

#### Scenario: Key with a limit

- **WHEN** the OpenRouter key has a limit of 10 dollars and 2.81 dollars left
- **THEN** the route MUST return `{"available": true, "limit_usd": 10, "remaining_usd": 2.81}`

#### Scenario: Provider without credit data

- **WHEN** the Chat provider is Ollama
- **THEN** the route MUST return `{"available": false}` and MUST send no request

### Requirement: The level list comes from the provider catalogue

`GET /v1/settings/chat/reasoning-levels?provider=&model=` SHALL return the levels a model supports when the provider publishes them. For OpenRouter it SHALL read the public model catalogue and SHALL return the supported levels, the default level and whether reasoning is mandatory. When the provider publishes no list, or the model is not in the list, it SHALL return `{"known": false}`. The route SHALL run only on request and SHALL send no API key.

#### Scenario: Mandatory reasoning model

- **WHEN** the catalogue lists `z-ai/glm-5.3-flash` with levels `max, high, low`, default `max` and mandatory true
- **THEN** the route MUST return `{"known": true, "levels": ["max", "high", "low"], "default": "max", "mandatory": true}`

#### Scenario: Model that can turn reasoning off

- **WHEN** the catalogue lists `deepseek/deepseek-v4.1-flash` with levels `max, high, low, none`
- **THEN** the returned levels MUST include `none`

#### Scenario: Provider without a catalogue

- **WHEN** the provider is `llamacpp`
- **THEN** the route MUST return `{"known": false}` and MUST send no request
