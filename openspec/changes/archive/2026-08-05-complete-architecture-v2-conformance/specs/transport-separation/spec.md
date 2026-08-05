## MODIFIED Requirements

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
