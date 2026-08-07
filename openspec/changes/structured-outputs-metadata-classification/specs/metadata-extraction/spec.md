## ADDED Requirements

### Requirement: Serving-layer JSON enforcement for LLM classification

When `METADATA_EXTRACTION_MODE` is `"local"`, the classification request SHALL instruct the backend to
constrain generation to valid JSON, in addition to the existing prompt-level instruction. The system
SHALL use each backend's native mechanism:

- `METADATA_LLM_PROVIDER=ollama` — the request to `/api/generate` SHALL set the JSON output format flag.
- `METADATA_LLM_PROVIDER=llamacpp` — the request to `/v1/chat/completions` SHALL set the OpenAI-compatible
  JSON-object response format.
- `METADATA_LLM_PROVIDER=openrouter` — the request SHALL set a JSON Schema response format describing the
  three-key classification object (`category` as a string, `keywords` as an array of strings, `summary` as
  a string), with all three required. Because structured-output support on OpenRouter is determined per
  serving endpoint rather than per model, the request SHALL additionally instruct provider routing to
  select only endpoints that honour the supplied parameters.

Enforcement SHALL be additive and SHALL NOT replace existing response handling: the system SHALL continue
to strip a surrounding markdown code fence and SHALL continue to fall back to
`{"category": "uncategorised", "keywords": [], "summary": ""}` when a response cannot be parsed. The
metadata dict returned to callers SHALL be unchanged in shape.

No new configuration setting SHALL be introduced; enforcement SHALL be unconditional for these backends.

#### Scenario: Ollama request constrains output format

- **WHEN** `METADATA_EXTRACTION_MODE=local` and `METADATA_LLM_PROVIDER=ollama`
- **THEN** the request body sent to `/api/generate` SHALL include the JSON output format flag
- **THEN** the request body SHALL still include the classification prompt and the existing category list

#### Scenario: llama.cpp request constrains output format

- **WHEN** `METADATA_EXTRACTION_MODE=local` and `METADATA_LLM_PROVIDER=llamacpp`
- **THEN** the request body sent to `/v1/chat/completions` SHALL include a JSON-object response format

#### Scenario: OpenRouter request carries the classification schema

- **WHEN** `METADATA_EXTRACTION_MODE=local` and `METADATA_LLM_PROVIDER=openrouter`
- **THEN** the request body SHALL include a JSON Schema response format requiring `category`, `keywords`
  and `summary`
- **THEN** the request body SHALL instruct provider routing to require parameter support

#### Scenario: Fence stripping still applies when enforcement is ignored

- **WHEN** a backend ignores the enforcement flag and returns JSON wrapped in a markdown code fence
- **THEN** the system SHALL strip the fence and parse the JSON as before
- **THEN** the returned metadata SHALL NOT be `uncategorised`

#### Scenario: Returned metadata shape is unchanged

- **WHEN** classification succeeds under enforcement
- **THEN** the returned dict SHALL contain exactly the keys `category`, `keywords` and `summary`

### Requirement: Graceful downgrade when a backend rejects structured output

A backend MAY reject a request whose structured-output parameters it cannot satisfy. When the OpenRouter
backend receives an HTTP 400, 404 or 422 response, the system SHALL treat it as a parameter fault rather
than a transient fault: it SHALL remove the response-format and provider-routing parameters from the
request, SHALL log at INFO that structured outputs were rejected, and SHALL retry immediately without
backoff on the prompt-only path. The downgrade SHALL be attempted at most once per classification call.

The downgraded retry SHALL consume one attempt from the configured retry budget rather than exceeding it.
Where that budget leaves no attempt remaining — notably when it is configured to a single attempt — no
downgraded request SHALL be sent. A single-attempt budget is an explicit instruction to issue one request
per classification, and the downgrade SHALL NOT override it; the system SHALL fall back to
`uncategorised` exactly as it would for any other exhausted budget.

Statuses that indicate a transient or unrelated fault SHALL NOT trigger a downgrade. In particular, HTTP
429 SHALL follow the existing retry-with-backoff path, and HTTP 401 or 403 SHALL NOT be downgraded because
dropping structured outputs cannot resolve an authentication failure.

The overall retry budget SHALL be unchanged; when it is exhausted the system SHALL fall back to
`{"category": "uncategorised", "keywords": [], "summary": ""}` and log a WARNING, as today.

#### Scenario: No schema-capable endpoint available

- **WHEN** the OpenRouter request is rejected with HTTP 404 because provider routing found no endpoint
  supporting the supplied parameters
- **THEN** the system SHALL retry without the response-format and provider-routing parameters
- **THEN** the retry SHALL be issued without backoff delay
- **THEN** a successful retry SHALL return normal metadata rather than `uncategorised`

#### Scenario: Schema rejected as invalid by the upstream provider

- **WHEN** the OpenRouter request is rejected with HTTP 400 or 422
- **THEN** the system SHALL retry once without the structured-output parameters

#### Scenario: Rate limiting does not trigger downgrade

- **WHEN** the OpenRouter request is rejected with HTTP 429
- **THEN** the request SHALL be retried with the structured-output parameters still present
- **THEN** the retry SHALL observe the existing exponential backoff

#### Scenario: Authentication failure does not trigger downgrade

- **WHEN** the OpenRouter request is rejected with HTTP 401 or 403
- **THEN** the structured-output parameters SHALL remain on the request
- **THEN** the system SHALL follow the existing retry-and-fallback path

#### Scenario: Downgrade is attempted at most once

- **WHEN** a downgraded request is itself rejected with HTTP 400
- **THEN** the system SHALL NOT attempt a further downgrade
- **THEN** it SHALL follow the existing retry-and-fallback path

#### Scenario: Downgrade cannot exceed a single-attempt retry budget

- **WHEN** the retry budget is configured to a single attempt
- **AND** the OpenRouter request is rejected with HTTP 400
- **THEN** no downgraded request SHALL be sent
- **THEN** exactly one request SHALL have been issued for that classification
- **THEN** the system SHALL return `{"category": "uncategorised", "keywords": [], "summary": ""}`

#### Scenario: Downgrade path exhausts the retry budget

- **WHEN** every attempt fails, including the downgraded one
- **THEN** the system SHALL return `{"category": "uncategorised", "keywords": [], "summary": ""}`
- **THEN** the system SHALL log a WARNING
