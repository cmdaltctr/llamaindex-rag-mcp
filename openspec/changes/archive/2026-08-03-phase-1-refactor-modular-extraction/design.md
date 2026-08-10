## Context

Phase 1 of the five-phase modular RAG framework refactor (`docs/brainstorm/refactor-proposal/PROPOSAL.md` §8). The codebase is flat modules under `src/rag_mcp/`; the three worst offenders (`metadata_extractor.py` 1164 lines, `ingestion.py` 991, `retrieval.py` 719) bury strategies inside monoliths. Phase 1 is deliberately mechanical: it moves code, changes nothing else, so every subsequent phase has a clean foundation and a safe revert point.

## Goals / Non-Goals

**Goals:**

- Split the three worst files into subpackages under `src/rag_mcp/core/` (metadata, ingestion, chunking, retrieval).
- Preserve every public function signature, CLI command, and MCP tool signature exactly.
- Keep every old import path resolving via compat shims with `DeprecationWarning`.
- Leave no file in `core/` exceeding 500 lines.

**Non-Goals:**

- No new chunking strategies (`structural.py`, `evidence_md.py` are deferred — they are net-new work, not extractions; PROPOSAL §5.2 H5).
- No registry/settings/compose machinery (Phase 2).
- No `VectorStore` abstraction (Phase 3).
- No profiles (Phase 4).
- No transport moves, `readers/` relocation, or watcher relocation (Phase 5).
- No behaviour change of any kind — including no "improvements while we're here".

## Decisions

### D1: Extraction targets and file mapping

| Current file (lines) | New location | Contents |
|---|---|---|
| `metadata_extractor.py` (1164) | `core/metadata/` | `extractor.py` orchestrator + `keyword.py`, `ollama.py`, `llamaindex.py`, `llamacpp.py` backends + `taxonomy.py` (ADR-013) |
| `ingestion.py` (991) | `core/ingestion/` | `loader.py` (file gathering + reader dispatch), `chunker.py` (content_type → strategy dispatch), `writer.py` (embed + ChromaDB write); `__init__.py` exposes `ingest_path_async()` |
| chunking functions inside `ingestion.py` | `core/chunking/` | `code.py`, `markdown.py`, `sentence.py`, `config_file.py` — the four existing strategies only |
| `retrieval.py` (719) | `core/retrieval/` | `pipeline.py` (`search()` orchestrator), `policy.py` (rerank threshold policy), `dense.py` |
| `sparse_retriever.py` (221) | `core/retrieval/sparse.py` + `fusion.py` | BM25 retrieval and RRF merge |
| `reranker.py` (241) | `core/retrieval/reranker.py` | CrossEncoder ONNX reranker, unchanged |

Rationale: `pipeline.py` and `policy.py` are mandatory inclusions (PROPOSAL §5.2 H5). The `search()` orchestrator and the ÷30 threshold policy live in `retrieval.py` today; splitting dense/sparse/fusion/reranker without them leaves orchestration homeless. Alternative considered (leave orchestration in a top-level `retrieval.py` shim) was rejected because it would keep a 719-line file in disguise.

### D2: Compat shims, not rewrites of call sites

Old modules become thin shims that re-export from the new paths and emit `DeprecationWarning` naming the new path:

```python
# src/rag_mcp/metadata_extractor.py — COMPAT SHIM (deprecated, removal in v2.0.0)
"""Backward-compatible re-export. Import from rag_mcp.core.metadata instead."""

from rag_mcp.core.metadata.extractor import *  # noqa: F401,F403
```

Rationale: external MCP clients, experiments, and ~30 test files import the old paths. Rewriting every call site in Phase 1 would balloon the diff and the review risk. Shims are removed in a single `refactor!:` major bump to v2.0.0 after Phase 5 (PROPOSAL §11, Decision 2).

### D3: Reranker singleton preserved as-is

`CrossEncoderReranker`'s `__new__` singleton, module-level `RERANK_MODEL`, and the independent `load_dotenv()` (AGENTS.md gotcha #4) move to `core/retrieval/reranker.py` unchanged. The DI conversion is Phase 2 (M3). The test reset hook (`CrossEncoderReranker._instance = None`) keeps working because the class object is the same object re-exported through the shim.

### D4: Import boundaries stay as they are

`core/ingestion/` and `core/retrieval/` share only `config.py` (AGENTS.md invariant #2). Phase 1 does not introduce imports between the new subpackages; if extraction reveals a hidden cross-import, it is surfaced as a finding, not silently fixed.

## Risks / Trade-offs

- Hidden cross-imports surface during extraction → surfacing them is the point; fix by keeping the shim re-exporting from both directions temporarily and recording the finding for Phase 2, never by merging the subpackages.
- Test suite breaks on import paths → shims preserve old paths; tests are updated incrementally to the new public paths with no assertion changes.
- A file in `core/` still exceeds 500 lines after the split → re-split by responsibility before accepting the phase; the 500-line ceiling is an acceptance criterion.
- Scope creep into "improvements" → any behaviour change discovered as desirable is recorded as a follow-up note in the change, not implemented.

## Migration Plan

1. Create `core/` subpackage skeletons.
2. Move code file-by-file (metadata → ingestion+chunking → retrieval), adding the shim at the old path immediately after each move.
3. Run `uv run pytest -m "not slow" --cov=rag_mcp` after each move; a red suite stops the phase.
4. Update test imports to new public paths last, as a separate commit.
5. Rollback: revert the branch. Each move is its own commit, so partial rollback is possible.
