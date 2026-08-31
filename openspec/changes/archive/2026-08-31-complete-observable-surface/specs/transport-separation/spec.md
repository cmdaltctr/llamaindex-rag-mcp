## MODIFIED Requirements

### Requirement: Versioned OpenAPI 3.1 contract for the future REST transport

The system SHALL ship `transports/api/README.md` (design and implementation
boundary) and `transports/api/openapi.yaml` — a valid OpenAPI 3.1 document
mapping REST endpoints to existing core operations, with explicit request,
response, and error schemas and the destructive-operation preview/confirm
contract. The folder SHALL contain NO runtime HTTP code; the REST
implementation is a separate follow-up change.

The contract SHALL describe the surface the shipped transports actually
expose. Every parameter accepted by an MCP search operation, every key present
in a core listing result, and every key present in a core search result SHALL
appear in the corresponding request or response schema. Validity of the
document is necessary but not sufficient: a well-formed document that omits an
implemented field does not satisfy this requirement.

A field that appears only when diagnostics are enabled SHALL be declared and
SHALL NOT be marked required. A field present on every response SHALL be
declared and required.

Declared defaults SHALL match the implementation exactly. A parameter with no
implementation default SHALL be declared required without a default. A
parameter whose default is resolved from the collection profile SHALL declare
no default, and its description SHALL NOT assert a concrete one.

Conformance SHALL be enforced by an automated check that derives the
implemented surface from the code rather than from a maintained list, so a
future field addition fails the check by default instead of relying on an
author remembering the contract.

#### Scenario: Contract covers the core operations

- **WHEN** `openapi.yaml` is inspected
- **THEN** it MUST define operations for: ingest path
  (`POST /v1/ingestions`), search collection
  (`POST /v1/collections/{collection}/search`), list documents
  (`GET /v1/collections/{collection}/documents`), list collections
  (`GET /v1/collections`), delete documents
  (`DELETE /v1/collections/{collection}/documents`), generate codebase
  map (`POST /v1/codebase-maps`), and change collection profile
  (`PATCH /v1/collections/{collection}/profile`)

#### Scenario: Profile change endpoint carries preview/confirm

- **WHEN** the `PATCH /v1/collections/{collection}/profile` operation is
  inspected
- **THEN** a request without `confirm: true` MUST be declared as returning
  a preview response (HTTP 200 with impact details and `confirm_required: true`)
- **AND** a request with `confirm: true` MUST be declared as returning the
  updated collection metadata (HTTP 200)
- **AND** the error schema MUST cover the case of an invalid profile name

#### Scenario: Explicit success and error schemas

- **WHEN** any operation in `openapi.yaml` is inspected
- **THEN** it MUST declare both success and error response schemas, with the
  error envelope matching the MCP error-dict shape

#### Scenario: Authentication schemes declared

- **WHEN** `openapi.yaml` is inspected
- **THEN** it MUST declare at least one `securitySchemes` entry under
  `components`
- **AND** every operation MUST reference a security requirement (or
  explicitly mark itself as unauthenticated)

#### Scenario: Long-running operations declared

- **WHEN** operations that may exceed a synchronous response window
  (`POST /v1/ingestions`, `POST /v1/codebase-maps`) are inspected
- **THEN** the contract MUST document whether the operation is synchronous
  or asynchronous
- **AND** if asynchronous, it MUST declare `202 Accepted` semantics with a
  job-resource schema containing at minimum a job identifier and a status
  field
- **AND** if asynchronous, it MUST declare a status-polling endpoint or
  document the polling mechanism

#### Scenario: No runtime code

- **WHEN** `transports/api/` is inspected
- **THEN** it MUST contain only `README.md` and `openapi.yaml` — no `.py`
  files

#### Scenario: Contract validated in CI

- **WHEN** CI runs
- **THEN** an OpenAPI validation step MUST pass against `openapi.yaml`

#### Scenario: Search request schema covers every optional search parameter

- **WHEN** the search request schema is compared against the MCP
  `search_documents` operation
- **THEN** every optional parameter that operation accepts MUST be declared
  in the schema, including the diagnostics control
- **AND** each declared parameter MUST carry the same default as the
  operation

#### Scenario: Document listing schema covers every listing result key

- **WHEN** the document-listing response schema is compared against the keys
  a core document listing returns
- **THEN** every returned key MUST be declared, including the stable source
  identifier and the tri-state orphan status
- **AND** a key whose value may be absent MUST be declared as nullable

#### Scenario: Search result schema covers every default result key

- **WHEN** the search-result response schema is compared against the keys a
  core search result carries without diagnostics
- **THEN** every returned key MUST be declared and required, including the
  per-chunk metadata mapping and every lineage field

#### Scenario: Search result schema covers diagnostic keys as optional

- **WHEN** the search-result response schema is compared against the keys a
  core search result carries with diagnostics enabled
- **THEN** every additional key MUST be declared
- **AND** each MUST be declared as not required, because it is absent from a
  default response

#### Scenario: A parameter default disagrees with the implementation

- **WHEN** a declared default differs from the implementation default
- **THEN** the conformance check MUST fail
- **AND** a parameter whose implementation default is resolved from the
  collection profile MUST fail the check if the contract declares any default
  for it

#### Scenario: An implemented field is missing from the contract

- **WHEN** the conformance check runs
- **AND** the implemented surface exposes a field the contract does not
  declare
- **THEN** the check MUST fail
- **AND** the failure MUST name the missing field and the schema expected to
  carry it

#### Scenario: A new field is added to an implemented surface

- **GIVEN** the contract and the implementation currently agree
- **WHEN** a field is added to a search parameter list or a listing result
- **AND** `openapi.yaml` is not updated in the same change
- **THEN** the conformance check MUST fail without any edit to the check
  itself
