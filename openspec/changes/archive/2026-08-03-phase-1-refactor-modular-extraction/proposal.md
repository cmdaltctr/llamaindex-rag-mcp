## Why

Nine files in `src/rag_mcp/` exceed the 500-line ceiling documented in AGENTS.md, and the three worst offenders (`metadata_extractor.py` at 1164 lines, `ingestion.py` at 991, `retrieval.py` at 719) bury multiple strategies inside monoliths. Adding a new chunking strategy or metadata backend today means editing a thousand-line file and hoping nothing breaks. This is Phase 1 of the five-phase modular RAG framework refactor defined in `docs/brainstorm/refactor-proposal/PROPOSAL.md`: a pure mechanical extraction that splits the worst offenders into subpackages with zero behaviour change, so every later phase builds on a navigable layout.

## What Changes

- Split `metadata_extractor.py` (1164 lines) into `core/metadata/`: `extractor.py` (orchestrator), `keyword.py`, `ollama.py`, `llamaindex.py`, `llamacpp.py` (four extraction backends), `taxonomy.py` (ADR-013 hybrid category logic). OpenRouter is NOT a backend — it routes through the llamaindex/local mode via the provider registry and has no file here.
- Split `ingestion.py` (991 lines) into `core/ingestion/` (`loader.py`, `chunker.py`, `writer.py`, `__init__.py` exposing `ingest_path_async()`) plus `core/chunking/` with the four EXISTING strategies only: `code.py`, `markdown.py`, `sentence.py`, `config_file.py`. The `structural.py` and `evidence_md.py` strategies are net-new work, not extractions, and are explicitly deferred (PROPOSAL §5.2 H5 note).
- Group `retrieval.py` (719) + `sparse_retriever.py` (221) + `reranker.py` (241) into `core/retrieval/`: `pipeline.py` (the `search()` orchestrator — required, otherwise the registry cannot dispatch an end-to-end query), `policy.py` (the `HARD_TECHNICAL_THRESHOLD = 0.3` ÷30 rerank threshold policy, currently in `retrieval.py` NOT `reranker.py`), `dense.py`, `sparse.py`, `fusion.py` (RRF), `reranker.py`.
- Add re-export compat shims at every old module path (`metadata_extractor.py`, `ingestion.py`, `retrieval.py`, `sparse_retriever.py`, `reranker.py`) carrying a `DeprecationWarning` naming the new import path. Shims are removed in v2.0.0 after all five phases land (PROPOSAL §11, Decision 2).
- No public function signature changes. No CLI command changes. No MCP tool signature changes. No changes to `config.py`, `server.py`, `cli.py`, `watcher.py`, or the `readers/` package (those are Phases 2 and 5).

## Capabilities

### New Capabilities

- `modular-core-extraction`: Structural requirements for the Phase 1 split — subpackage layout, mechanical-extraction fidelity (behaviour preservation), re-export shim contract, and per-phase test-continuity guarantees.

### Modified Capabilities

None. Phase 1 is a behaviour-preserving mechanical extraction. Existing capability requirements (`metadata-extraction`, `async-ingestion`, `hybrid-retrieval`, `reranking`, `semantic-technical-reranker-policy`, `markdown-aware-chunking`) are unchanged — only the physical location of their implementations moves.

## Impact

- **Code**: `metadata_extractor.py`, `ingestion.py`, `retrieval.py`, `sparse_retriever.py`, `reranker.py` are converted to compat shims; logic moves to `core/metadata/`, `core/ingestion/`, `core/chunking/`, `core/retrieval/`.
- **Tests**: Test files may update imports to new public paths, but no test assertion changes. All ~30 test files must pass unmodified in behaviour at the phase boundary.
- **Dependencies**: None added or removed.
- **Downstream phases**: Phases 2–5 build on this layout. Phase 1 is independently shippable and revertible — the shims mean a stalled refactor is not a broken codebase.
- **Risk**: Low. Mechanical refactoring with no logic change.
