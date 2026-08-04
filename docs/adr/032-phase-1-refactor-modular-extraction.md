# ADR-032: Phase 1 Refactor — Modular Core Extraction

**Date:** 2026-08-03
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `phase-1-refactor-modular-extraction`
**Phase:** 1 of 5 (`docs/brainstorm/refactor-proposal/PROPOSAL.md`)
**Precedes:** [ADR-031](./031-three-layer-config-compose-di.md) (Phase 2)

## Context

Three files dominated `src/rag_mcp/` and blocked every subsequent improvement.
`metadata_extractor.py` (1164 lines), `ingestion.py` (991), and `retrieval.py`
(719) — plus its companions `sparse_retriever.py` (221) and `reranker.py`
(241) — each buried several strategies or backends behind a single import.
Adding a chunking strategy meant editing a thousand-line file; adding a
metadata backend meant touching the one orchestrator every extraction path
shared. Nine files in the package exceeded the 500-line ceiling documented in
AGENTS.md.

Phase 1 is the first of a five-phase behaviour-preserving refactor (PROPOSAL
§8). Its sole job is to give every later phase a navigable foundation: split
the monoliths into `core/` subpackages, keep every public surface identical,
and leave a safe revert point. The risk is deliberately Low — no logic
changes — so the architectural decision recorded here is about *layout and
migration policy*, not about runtime behaviour.

The forces in play:

- About thirty test files and external MCP clients import the old paths.
  Rewriting every call site in one phase would balloon review risk.
- The `search()` orchestrator and the ÷30 rerank threshold policy both live
  inside `retrieval.py`; splitting dense/sparse/fusion/reranker without moving
  them leaves orchestration homeless.
- Two would-be strategies (`structural.py`, `evidence_md.py`) are net-new, not
  extractions; including them turns Phase 1 into a behaviour change.
- `core/ingestion` and `core/retrieval` already share only `config.py`
  (AGENTS.md invariant #2); the split must not introduce new cross-imports.

## Decision

Adopt a domain-oriented `core/` subpackage layout with backward-compatibility
re-export shims, applied as a pure mechanical extraction.

### D1 — Split by domain responsibility into `core/`

| Former monolith (lines) | New subpackage | Contents |
|---|---|---|
| `metadata_extractor.py` (1164) | `core/metadata/` | `extractor.py` (orchestrator), `keyword.py`, `ollama.py`, `llamaindex.py`, `llamacpp.py` (four backends), `taxonomy.py` (ADR-013) |
| `ingestion.py` (991) | `core/ingestion/` + `core/chunking/` | `loader.py`, `chunker.py`, `writer.py`; chunking strategies `code.py`, `markdown.py`, `sentence.py`, `config_file.py` |
| `retrieval.py` (719) + `sparse_retriever.py` (221) + `reranker.py` (241) | `core/retrieval/` | `pipeline.py` (`search()`), `policy.py` (÷30 threshold), `dense.py`, `sparse.py`, `fusion.py`, `reranker.py` |

Grouping is by domain (metadata, ingestion, chunking, retrieval), not by layer
or by feature. Each subpackage owns exactly one pipeline stage. OpenRouter is
not a metadata backend — it routes through the llamaindex/local mode via the
provider registry, so it has no file in `core/metadata/`.

### D2 — `pipeline.py` and `policy.py` are mandatory inclusions

The `search()` orchestrator and the `HARD_TECHNICAL_THRESHOLD = 0.3` ÷30
rerank threshold policy both lived in `retrieval.py`. They move into
`core/retrieval/` as `pipeline.py` and `policy.py`. Without them the retrieval
registry cannot dispatch an end-to-end query (PROPOSAL §5.2, H5). Leaving
orchestration in a top-level `retrieval.py` shim was rejected because it would
preserve a 719-line file in disguise.

### D3 — Compat shims with `DeprecationWarning`, not call-site rewrites

Every old module path (`metadata_extractor.py`, `ingestion.py`,
`retrieval.py`, `sparse_retriever.py`, `reranker.py`) becomes a thin re-export
shim that emits a `DeprecationWarning` naming the new import path. Internal
callers and tests migrate to the new `rag_mcp.core.*` paths incrementally;
external callers keep working untouched. Shims are removed in a single
`refactor!:` major bump to v2.0.0 after Phase 5 (PROPOSAL §11, Decision 2).

### D4 — Reranker singleton preserved verbatim; DI deferred

`CrossEncoderReranker`'s `__new__` singleton, module-level `RERANK_MODEL`, and
the independent `load_dotenv()` (AGENTS.md gotcha #4) move to
`core/retrieval/reranker.py` unchanged. The DI conversion is Phase 2
(ADR-031). The test reset hook (`CrossEncoderReranker._instance = None`) keeps
working because the shim re-exports the same class object.

### D5 — Import boundaries unchanged; net-new strategies deferred

`core/ingestion/` and `core/retrieval/` continue to share only `config.py`.
Phase 1 introduces no imports between the new subpackages; a hidden
cross-import surfaced during extraction is recorded as a finding for Phase 2,
never silently fixed. `structural.py` and `evidence_md.py` are net-new
strategies (a reader return-type change and a non-existent chunker
respectively), so they are deferred to keep Phase 1 purely mechanical.

### Structural invariant

No file under `core/` exceeds 500 lines. This is an acceptance criterion, not
a guideline.

## Consequences

### Positive

- Each pipeline stage is now a navigable subpackage; adding a strategy or
  backend costs one file in the right folder, not an edit to a thousand-line
  monolith.
- The compat shims mean a stalled refactor is not a broken codebase — every
  old import path still resolves, so Phase 2 can proceed without coordinating
  a flag day.
- The split is a safe revert point: each move is its own commit, and the suite
  is green at every step.
- Later phases inherit a layout that matches their work: Phase 2 adds
  `settings.py` and `registry.py` beside the code that owns each knob; Phase 3
  adds `core/vectordb/`.

### Negative

- Five shim files sit at 0% coverage because no test imports from them by
  design — they exist for external and not-yet-migrated callers. This accounts
  for the 1% overall coverage dip (88% → 87%) recorded in the Phase 1
  acceptance record, and is why the coverage gate was amended from absolute
  floors to a no-regression baseline for this phase.
- Two physical locations exist for each module (shim plus real file) until
  v2.0.0; developers must learn to read the real path, not the shim.
- The reranker singleton and its `load_dotenv()` workaround survive into
  Phase 2, carrying the circular-import gotcha forward until ADR-031 removes
  them.

### Neutral

- The `core/` package coexists with the top-level modules during the shim
  window. The names do not collide because the shims are explicitly marked
  deprecated.
- `content_type` metadata continues to take precedence over file extension for
  chunking strategy selection (AGENTS.md gotcha #8); the move to
  `core/ingestion/chunker.py` preserves that dispatch unchanged.

## Alternatives Considered

| Option | Rejected Because |
|--------|------------------|
| **Rewrite every call site in Phase 1 (no shims)** | The diff would be too large to review safely and a single bad merge would break the whole tree at once. Shims let migration proceed file-by-file with the suite green at each step. |
| **Leave orchestration in a top-level `retrieval.py`** | Preserves a 719-line file in disguise; the registry cannot dispatch an end-to-end query without `pipeline.py` inside the subpackage. |
| **Include `structural.py` / `evidence_md.py` now** | Both are net-new work (a reader return-type change and a non-existent chunker), not extractions. Including them makes Phase 1 a behaviour change and breaks the "no assertion changes" acceptance criterion. |
| **Convert the reranker to DI in Phase 1** | Couples a Low-risk mechanical phase to the High-risk DI conversion. The singleton moves unchanged; DI is Phase 2 (ADR-031). |
| **Group by layer (all strategies together) instead of by domain** | Each strategy is consumed by exactly one pipeline stage; grouping it away from its consumer hides the dispatch path. Domain grouping keeps each strategy beside its dispatcher. |
| **Fix hidden cross-imports as they surface** | A silent fix during a "no behaviour change" phase defeats the point. Cross-imports are recorded as findings for Phase 2 and resolved there with the config/compose split. |

## References

- Proposal: [`openspec/changes/archive/2026-08-03-phase-1-refactor-modular-extraction/proposal.md`](../../openspec/changes/archive/2026-08-03-phase-1-refactor-modular-extraction/proposal.md)
- Design: [`openspec/changes/archive/2026-08-03-phase-1-refactor-modular-extraction/design.md`](../../openspec/changes/archive/2026-08-03-phase-1-refactor-modular-extraction/design.md) (decisions D1–D4)
- Refactor proposal: [`docs/brainstorm/refactor-proposal/PROPOSAL.md`](../brainstorm/refactor-proposal/PROPOSAL.md) (§5.2 H5, §8 Phase 1, §11 Decision 2)
- [ADR-013](./013-hybrid-category-taxonomy-for-ollama-metadata.md) — Hybrid Category Taxonomy (the `taxonomy.py` logic that moves)
- [ADR-031](./031-three-layer-config-compose-di.md) — Phase 2 Three-Layer Architecture (builds on this layout; removes the reranker singleton)
- `src/rag_mcp/core/metadata/`, `src/rag_mcp/core/ingestion/`, `src/rag_mcp/core/chunking/`, `src/rag_mcp/core/retrieval/` — the extracted subpackages
- PR #12 — `refactor: modular extraction — Phase 1 subpackage restructure`
