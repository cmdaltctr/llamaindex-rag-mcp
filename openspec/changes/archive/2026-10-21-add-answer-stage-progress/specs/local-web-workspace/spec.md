# Spec Delta

## ADDED Requirements

### Requirement: The answer route can stream its stage

The app SHALL offer `POST /v1/collections/{collection}/answer/stream`. It SHALL take the body of `POST /v1/collections/{collection}/answer`, SHALL need the `read` scope, and SHALL follow the same authentication, Host and Origin rules. A valid request SHALL get `text/event-stream` with `stage` frames, then exactly one `result` frame, then the end. The route SHALL open the stream only when the first stage or the result is ready. A request that fails before the stream opens SHALL get an ordinary HTTP error. A request the Engine rejects as invalid SHALL get the same 400 response as the blocking route.

#### Scenario: Stages then result

- **WHEN** a session posts a valid question to the stream route
- **THEN** the response MUST be `text/event-stream`
- **AND** it MUST hold `stage` frames in stage order, then one `result` frame, then end

#### Scenario: The result equals the blocking result

- **WHEN** the same question is posted to the stream route and to `POST .../answer`
- **THEN** the `result` frame MUST hold the same fields as the blocking response, with the same redaction of its `error` text

#### Scenario: The blocking route is unchanged

- **WHEN** a client posts to `POST /v1/collections/{collection}/answer`
- **THEN** the response MUST be the same JSON as before this change
- **AND** the status codes MUST be the same

#### Scenario: Authentication and Origin

- **WHEN** a request has no credential, or a session cookie with a foreign Origin, or a bearer credential without the `read` scope
- **THEN** the route MUST answer 401 or 403 before it admits any work
- **AND** a bearer credential with the `read` scope MUST be accepted

#### Scenario: Bad body

- **WHEN** the body has an unknown field or a question over 4,096 characters
- **THEN** the route MUST answer with the same error as the blocking route and MUST NOT open a stream

#### Scenario: Server is shutting down

- **WHEN** the server has stopped admitting work
- **THEN** the route MUST answer 503 and MUST NOT open a stream

#### Scenario: The Engine rejects the request

- **WHEN** the Engine raises a validation error, for example because the user profile has no saved Answer graph
- **THEN** the route MUST answer 400 with the same body as the blocking route
- **AND** it MUST NOT open a stream

### Requirement: Stage frames carry no content

A `stage` frame SHALL hold only a stage name, a sequence number that starts at 1 and rises by 1, and the elapsed milliseconds since the request was admitted. The frame schema SHALL be closed. A `stage` frame SHALL NOT hold question text, passage text, answer text, model names, provider names, keys, paths or error text. The `result` frame SHALL be the only frame that holds answer content.

#### Scenario: Question text does not leak into stage frames

- **WHEN** the question contains a marker string and the answer fails with an error text that contains a saved key
- **THEN** no `stage` frame MUST contain the marker or the key
- **AND** the `result` frame MUST hold the key-free error text of the blocking route

#### Scenario: Frames match the contract

- **WHEN** a stream is read in full
- **THEN** every frame MUST match the schema that `openapi.yaml` declares for its event name

#### Scenario: Sequence numbers

- **WHEN** a stream reports three stages
- **THEN** their sequence numbers MUST be 1, 2 and 3 and their elapsed times MUST not fall

### Requirement: A stream follows its client

The streaming answer SHALL hold runtime admission from before the first byte until the answer ends or is cancelled. When the client leaves before the `result` frame, the server SHALL cancel the answer and SHALL release admission. The route SHALL watch the client itself, so that a client that leaves while no frame is due is noticed whatever ASGI spec version the server reports. A cancelled answer SHALL write nothing. Each stream SHALL have its own frames. A stream SHALL keep no state after it ends.

#### Scenario: Browser tab closes mid-answer

- **WHEN** the client drops the connection while the answer runs
- **THEN** the server MUST cancel the answer
- **AND** the admission count MUST return to its value before the request

#### Scenario: Client leaves during a long model call

- **WHEN** the client drops the connection while the model call runs and no frame is due
- **THEN** the server MUST cancel the answer within a few seconds
- **AND** it MUST NOT wait for the next frame to notice

#### Scenario: Two answers at once

- **WHEN** two clients start streams at the same time
- **THEN** each stream MUST hold only the stages of its own answer
- **AND** each MUST end with its own `result` frame

#### Scenario: Shutdown while a stream runs

- **WHEN** graceful shutdown begins during a stream
- **THEN** the server MUST wait for the admitted answer as it does for the blocking route
- **AND** the Engine MUST stay open until the answer ends

#### Scenario: Unexpected Engine error

- **WHEN** the Engine raises an error other than a validation error during the stream
- **THEN** the stream MUST end with a `result` frame in the same error shape the blocking route returns for that case
