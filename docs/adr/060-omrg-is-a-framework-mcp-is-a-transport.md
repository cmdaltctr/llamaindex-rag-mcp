# ADR-060: omrg Is a Framework; MCP Is a Transport

**Date:** 2026-09-08
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The project was built as an MCP server in v1 and carried that shape into
v2. The package was named `rag-mcp`, the import path was `rag_mcp`, and
the public entry point was the MCP stdio server. CLI and watcher
transports existed but were framed as secondary surfaces.

This framing created two problems:

1. **Library users could not import the retrieval engine without starting
   the MCP server.** The `ensure_runtime_setup()` path installed a
   process-global embedder, store and settings singleton. Any code that
   imported `rag_mcp` inherited those side effects, making embedding or
   testing in a library context fragile.

2. **One embedding model per process.**
   `EMBEDDING_PROVIDER_SCOPE = "process"` meant two collections with
   different embedding providers could not coexist. Mixing models is
   unsafe with ChromaDB (dimension lock), but even with LanceDB the
   process-global assignment prevented multi-tenant usage.

The rename to `omrg` (change `make-omrg-a-standalone-framework-4`) is the
moment to reframe the product: `omrg` is a standalone retrieval
framework; MCP is one transport among CLI and watcher.

## Decision

1. **D1 — The rename lands as its own commit.** The mechanical
   `rag_mcp` → `omrg` rename is content-neutral and committed separately
   from the behavioural work. This preserves bisect clarity: a
   content-neutral rename commit cannot hide a behavioural regression.

2. **D2 — `compose` constructs; `Engine` owns and operates.**
   `compose.build_engine()` is the single construction path. It resolves
   settings, constructs the embedder, store, reranker and profile
   resolver, and returns an `Engine` that owns those dependencies.
   `Engine(...)` accepts already-composed dependencies and constructs
   nothing itself. No module-level default engine exists.

3. **D3 — The embedder and store are injected through every seam.**
   `retrieval/dense.py::_embed_query`, `ingestion/replacement.py::
   _embed_missing_nodes`, and `VectorStore.write_nodes()` all accept an
   injected `embed_model`. `ingest_path_async()` accepts an injected
   `store`. The LlamaIndex global remains only as a legacy fallback when
   dependencies are omitted.

4. **D5 — `ensure_runtime_setup()` is reimplemented, not removed.** It
   calls `build_engine()`, then installs the result as the process
   default for legacy transport compatibility. Direct `Engine`
   construction never installs process globals. MCP, CLI and watcher
   transports continue to work unchanged.

5. **D7 — No Python import shim; keep the installed command surface via
   a one-major alias.** The `rag-mcp` console-script entry point is kept
   as a deprecated alias for one major version. No `rag_mcp` import shim
   is provided — Python imports are not redirectable without side
   effects, and a shim would re-introduce the import-time construction
   the framework change removes.

## Consequences

- The public API is `omrg.Engine`, `omrg.EffectiveSettings` and
  `omrg.__version__`, exported via PEP 562 lazy imports. Importing the
  package constructs nothing.
- Multiple engines with different stores and embedding models coexist
  safely in one process. `EMBEDDING_PROVIDER_SCOPE` is now `"engine"`.
- Stored vector data is unaffected. No migration or re-ingestion is
  required — the embedding identity fingerprint is identical for a
  single-engine process.
- The `rag-mcp` console alias is deprecated and will be removed in the
  next major version.
- `ensure_runtime_setup()` remains the legacy installer. New code should
  use `Engine.from_environment()` or direct construction.

## References

- OpenSpec change: `make-omrg-a-standalone-framework-4`
- ADR-047: Semantic Vector-Store Swappability (superseded decision 7 by
  ADR-061)
- ADR-037: Settings Dependency Injection
