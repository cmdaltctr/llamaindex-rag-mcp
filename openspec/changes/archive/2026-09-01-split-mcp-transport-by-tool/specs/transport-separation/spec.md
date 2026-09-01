## MODIFIED Requirements

### Requirement: Thin transports over a shared core

The system SHALL organise all delivery mechanisms under `transports/`:
`transports/mcp/` (MCP server, split by tool), `transports/cli/` (CLI split by
command group), and `transports/api/` (design contract only). Every transport
SHALL validate input, delegate to `core/`, and format output; no transport file
SHALL contain business logic. The `core/` layer SHALL NOT import from `mcp`
or any transport and SHALL NOT receive transport-specific objects (e.g. a
FastMCP `Context`).

Where a transport is split across modules, the package entry point SHALL own
the shared server or application object and SHALL import every handler module
so that registration decorators run on import. A handler module that is not
imported is a defect, because its handler disappears from the running transport
without any error.

The package entry point SHALL also re-export every handler by name, so that a
handler remains importable from the package root exactly as it was before the
split. Importing a module for its decorator side effect alone does not satisfy
this: it registers the handler with the server without binding its name on the
package.

#### Scenario: CLI split by command group

- **WHEN** the CLI is inspected after the move
- **THEN** `transports/cli/` MUST contain separate modules per command group
  (`ingest.py`, `search.py`, `list.py`, `watch.py`)
- **AND** every `rag-mcp` subcommand MUST behave identically to the
  pre-refactor CLI

#### Scenario: MCP split by tool

- **WHEN** `transports/mcp/` is inspected
- **THEN** it MUST contain separate modules per tool group
  (`ingest.py`, `search.py`, `list.py`, `delete.py`, `codebase.py`,
  `profile.py`)
- **AND** `__init__.py` MUST own the server instance and import every tool
  module

#### Scenario: MCP server entry unchanged

- **WHEN** `rag-mcp` is run with no arguments
- **THEN** the MCP server MUST start identically to the pre-refactor server
  with all tool signatures unchanged

#### Scenario: Tool set stays complete after a transport split

- **WHEN** the running MCP server is asked to list its tools
- **THEN** every tool available before the split MUST still be present
- **AND** each MUST keep its name, parameters, defaults, and annotations

#### Scenario: Handlers stay importable from the package root

- **WHEN** a handler is imported from the transport package root after the
  split
- **THEN** the import MUST succeed and MUST yield the same callable the server
  registered
- **AND** this MUST hold for every handler the transport exposes

#### Scenario: Core stays transport-agnostic

- **WHEN** the codebase is searched for transport imports in `core/`
- **THEN** no `core/` module MUST import from `transports/`, `mcp`, or any
  CLI framework

---

### Requirement: Uniform MCP error contract

Every MCP tool handler SHALL catch its failures and return an error payload
carrying `{"status": "error", "message": "..."}`, and SHALL NOT raise from a
tool handler (AGENTS.md gotcha #1), including `ingest_documents`.

The error payload SHALL be carried in the handler's own declared return type,
not coerced into a dictionary. A handler returning a mapping returns the error
mapping directly. A handler returning a list returns a single-element list
containing it. A handler returning a string returns its JSON encoding. What is
uniform is that a failure is caught, reported with that status and message, and
never raised — not the outer container.

#### Scenario: ingest_documents failure returns dict

- **WHEN** `ingest_documents` is invoked with an input that fails during
  ingestion
- **THEN** the handler MUST catch the failure and return an error dict
- **AND** MUST NOT propagate an exception to the MCP runtime

#### Scenario: A list-returning handler reports an error

- **WHEN** `search_documents` fails
- **THEN** it MUST return a single-element list whose element carries the error
  status and message
- **AND** MUST NOT raise, and MUST NOT change its declared list return type

#### Scenario: A string-returning handler reports an error

- **WHEN** `get_codebase_map` fails
- **THEN** it MUST return a JSON-encoded string carrying the error status and
  message
- **AND** MUST NOT raise, and MUST NOT change its declared string return type

#### Scenario: All tools audited

- **WHEN** every tool handler under `transports/mcp/` is reviewed
- **THEN** each MUST have failure handling that produces an error payload in
  its own return type

---

### Requirement: FastMCP lifespan and context forward-compatibility

`transports/mcp/` SHALL preserve the ability to pass a `lifespan=`
parameter to the `FastMCP` constructor, and tool handler signatures SHALL
NOT prevent adding a `ctx: Context` parameter in future. Lifespan/context
usage itself is out of scope for this phase.

#### Scenario: Lifespan slot preserved

- **WHEN** the `FastMCP` constructor call is inspected
- **THEN** it MUST accept a `lifespan=` argument (passed as `None` or a
  context manager) without structural changes to the package entry point

#### Scenario: Context parameter not precluded

- **WHEN** tool handler signatures are inspected
- **THEN** adding `ctx: Context` as a parameter MUST NOT require
  restructuring the handler module

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
  MUST point at `transports/mcp/`

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
