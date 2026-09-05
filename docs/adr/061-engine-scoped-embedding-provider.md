# ADR-061: Engine-Scoped Embedding Provider

**Date:** 2026-09-08
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

ADR-047 decision 7 recorded that embedding-provider selection is
process-scoped: `EMBEDDING_PROVIDER_SCOPE = "process"`. The rationale
was that LlamaIndex exposes one process-global
`Settings.embed_model`, and provider registries made embedding providers
look runtime-swappable even though they were not.

This constraint prevented:

- **Multi-tenant usage:** two engines with different embedding models
  operating in one process.
- **Library usage:** importing the package installed a process-global
  embedder, making test isolation fragile.
- **Safe coexistence:** a test engine and a production engine in the
  same process would share (and overwrite) the global embedder.

The `make-omrg-a-standalone-framework-4` change introduces `Engine` as
the public API, where each engine owns its embedder, store and settings.
The process-global assignment is now a legacy compatibility path, not
the construction default.

## Decision

Supersede ADR-047 decision 7. Embedding-provider selection is
**engine-scoped**: `EMBEDDING_PROVIDER_SCOPE = "engine"`.

1. **Each `Engine` owns its embedder.** `compose.build_engine()`
   constructs the embedder from settings and passes it to the `Engine`
   constructor. The engine holds the reference for its lifetime.

2. **The embedder is injected through every seam.**
   `retrieval/dense.py::_embed_query`,
   `ingestion/replacement.py::_embed_missing_nodes`, and
   `VectorStore.write_nodes()` all accept an injected `embed_model`.
   No core or integration module reads `Settings.embed_model` directly.

3. **The LlamaIndex global is a legacy fallback only.**
   `ensure_runtime_setup()` installs one engine's embedder as the
   process default for MCP, CLI and watcher transport compatibility.
   Direct `Engine` construction never assigns the global.

4. **The embedding identity fingerprint is unchanged for a single-engine
   process.** `_runtime_embedding_identity()` fingerprints the injected
   embedder using the same class/model attributes as the global path.
   Existing collections do not reprocess.

5. **`Engine.close()` releases the embedder reference** and evicts
   BM25 cache entries scoped to the engine's store identity. Closing
   one engine does not affect another.

## Consequences

- Two engines with different embedding models coexist safely in one
  process. ChromaDB's dimension lock still applies within a single
  store, but two LanceDB stores with different models are now possible.
- `EMBEDDING_PROVIDER_SCOPE = "engine"` is the new invariant.
  ADR-047 decision 7 is superseded.
- The no-global-settings-reads guard is widened to scan the full
  production package, permitting only `compose.py`,
  `compose_answer.py` and `compose_engine.py`.
- Stored vector data is unaffected. The identity fingerprint is
  byte-identical for a single-engine process.

## References

- ADR-047: Semantic Vector-Store Swappability (decision 7 superseded)
- ADR-060: omrg Is a Framework; MCP Is a Transport
- OpenSpec change: `make-omrg-a-standalone-framework-4`
