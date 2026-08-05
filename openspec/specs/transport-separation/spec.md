## Purpose

Define the transport layer separation (MCP, CLI, API), the daemon layer for background processes, the integrations layer for external-tool wrappers, the uniform MCP error contract, FastMCP forward-compatibility, and the versioned OpenAPI 3.1 contract for the future REST transport.
## Requirements
### Requirement: Thin transports over a shared core

The system SHALL organise all delivery mechanisms under `transports/`:
`transports/mcp.py` (MCP server), `transports/cli/` (CLI split by command
group), and `transports/api/` (design contract only). Every transport SHALL
validate input, delegate to `core/`, and format output; no transport file
SHALL contain business logic. The `core/` layer SHALL NOT import from `mcp`
or any transport and SHALL NOT receive transport-specific objects (e.g. a
FastMCP `Context`).

#### Scenario: CLI split by command group

- **WHEN** the CLI is inspected after the move
- **THEN** `transports/cli/` MUST contain separate modules per command group
  (`ingest.py`, `search.py`, `list.py`, `watch.py`)
- **AND** every `rag-mcp` subcommand MUST behave identically to the
  pre-refactor CLI

#### Scenario: MCP server entry unchanged

- **WHEN** `rag-mcp` is run with no arguments
- **THEN** the MCP server MUST start identically to the pre-refactor server
  with all tool signatures unchanged

#### Scenario: Core stays transport-agnostic

- **WHEN** the codebase is searched for transport imports in `core/`
- **THEN** no `core/` module MUST import from `transports/`, `mcp`, or any
  CLI framework

---

### Requirement: Uniform MCP error contract

Every MCP tool handler SHALL return an error dictionary
(`{"status": "error", "message": "..."}`) on failure and SHALL NOT raise
from a tool handler (AGENTS.md gotcha #1), including `ingest_documents`.

#### Scenario: ingest_documents failure returns dict

- **WHEN** `ingest_documents` is invoked with an input that fails during
  ingestion
- **THEN** the handler MUST catch the failure and return an error dict
- **AND** MUST NOT propagate an exception to the MCP runtime

#### Scenario: All tools audited

- **WHEN** every tool handler in `transports/mcp.py` is reviewed
- **THEN** each MUST have failure handling that produces an error dict

---

### Requirement: FastMCP lifespan and context forward-compatibility

`transports/mcp.py` SHALL preserve the ability to pass a `lifespan=`
parameter to the `FastMCP` constructor, and tool handler signatures SHALL
NOT prevent adding a `ctx: Context` parameter in future. Lifespan/context
usage itself is out of scope for this phase.

#### Scenario: Lifespan slot preserved

- **WHEN** the `FastMCP` constructor call is inspected
- **THEN** it MUST accept a `lifespan=` argument (passed as `None` or a
  context manager) without structural changes to the module

#### Scenario: Context parameter not precluded

- **WHEN** tool handler signatures are inspected
- **THEN** adding `ctx: Context` as a parameter MUST NOT require
  restructuring the handler module

---

### Requirement: Integrations consolidation

All wrappers around external tools and libraries SHALL live under
`integrations/`: local PDF parsers in `integrations/pdf/`, Azure Document
Intelligence in `integrations/azure.py`, and Magika file-type detection in
`integrations/magika.py` (extracted from `codebase_map.py`). The PDF factory
SHALL continue to dispatch to the Azure reader by importing from
`integrations.azure`.

#### Scenario: Azure at integrations root

- **WHEN** the integrations tree is inspected
- **THEN** `integrations/azure.py` MUST sit at the `integrations/` root
  (cloud intelligence service), not inside `pdf/`
- **AND** the lazy-import discipline (ADR-024 — no top-level Azure SDK
  import) MUST be preserved

#### Scenario: Magika extraction

- **WHEN** `codebase_map.py` needs file-type detection
- **THEN** it MUST import from `integrations/magika.py`
- **AND** detection behaviour MUST be unchanged

---

### Requirement: Watcher as daemon

The file watcher SHALL live at `daemon/watcher.py` as the home for
long-running background processes, distinct from request-response
transports.

#### Scenario: Watch behaviour unchanged

- **WHEN** `rag-mcp watch` runs after the move
- **THEN** debouncing, hashing, and ingestion triggering MUST behave
  identically to the pre-refactor watcher

---

### Requirement: Versioned OpenAPI 3.1 contract for the future REST transport

The system SHALL ship `transports/api/README.md` (design and implementation
boundary) and `transports/api/openapi.yaml` — a valid OpenAPI 3.1 document
mapping REST endpoints to existing core operations, with explicit request,
response, and error schemas and the destructive-operation preview/confirm
contract. The folder SHALL contain NO runtime HTTP code; the REST
implementation is a separate follow-up change.

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

---

### Requirement: Agent-facing documentation reflects the final tree

The refactor SHALL update `AGENTS.md` (architecture invariants #1–#6,
gotchas, and the module list) and `docs/guides/architecture.md` to the
post-refactor structure, and SHALL refresh the graphify knowledge graph, in
the same change. In addition, every architecture decision record and
reference document SHALL be corrected wherever it asserts a property the code
does not have. A decision record SHALL NOT claim conformance that is not
enforced by a test or an import-linter contract.

#### Scenario: AGENTS.md invariants rewritten

- **WHEN** `AGENTS.md` is read after the change
- **THEN** every invariant and gotcha MUST reference the current module paths
  (e.g. `core/retrieval/reranker.py`, `core/codebase/`, `core/documents/`,
  `compose.py`, the `config/` resolver)
- **AND** no invariant MUST describe a superseded layout as current

#### Scenario: Falsified ADR claims corrected

- **WHEN** the ADR set is read after the change
- **THEN** ADR-032's claim that dispatch runs through the strategy registries,
  ADR-033's claim that no import-time settings snapshots remain, ADR-034's
  claim that no consumer reaches ChromaDB APIs directly, ADR-036 §1's claim
  that import-linter contracts already cover the boundaries, and ADR-036 §3's
  claim about the Magika extraction MUST each be either true of the code or
  amended with a correction note
- **AND** ADR-033's reference to `src/rag_mcp/server.py` for reranker wiring
  MUST point at `transports/mcp.py`

#### Scenario: Reference documents match the shipped tree

- **WHEN** `docs/brainstorm/refactor-proposal/PROPOSAL.md` is read
- **THEN** §8 Phase 2's "572 → ~150 lines" statement MUST reflect the achieved
  size
- **AND** §12's recorded deviation about top-level graph modules MUST be
  updated to record that the relocation has been completed

#### Scenario: A new decision record captures this change

- **WHEN** the ADR index is read after the change
- **THEN** a new ADR MUST record the conformance work, the nested
  configuration schema, the deletion of the v1 compatibility surface, the
  environment variable migration table, and the v2.0.0 release implication

