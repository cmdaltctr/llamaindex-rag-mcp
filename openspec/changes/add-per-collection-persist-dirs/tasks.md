# Tasks: add-per-collection-persist-dirs

## 1. Settings and resolver data

- [ ] 1.1 Add `collection_group_map: dict[str, str]` (collection name → group directory name, default empty) to the cross-cutting Storage section in `config/__init__.py` and mirror it in `core/settings.py`; use a flat `COLLECTION_GROUP_MAP` environment variable containing a JSON object, consistent with `CHROMA_PERSIST_DIR` and `VECTOR_STORE`, and document it in `.env.example`
- [ ] 1.2 Confirm `chroma_persist_dir` semantics become "parent root of all collection directories" in docstrings and `.env.example` (no code change to the field itself)

## 2. Composition-root resolution

- [ ] 2.1 Add a pure `resolve_persist_dir(collection_name, settings) -> str` function in `compose.py`: mapped group name → `{parent}/{group}/`; else `{parent}/{collection_name}/`; reject empty names, absolute paths, `/`, `\\`, `.`, and `..` for both collection and group names before path construction; perform no filesystem touch and use no `if/elif` chains over collection names
- [ ] 2.2 Add a directory-keyed store provider in `compose.py` that resolves each operation's `collection_name`, builds or reuses its `ChromaVectorStore`, and injects that selected store through MCP, CLI, watcher, ingestion, retrieval, deletion, listing, profile, and codebase-map paths; prevent `ensure_runtime_setup`, `set_default_store`, and `get_default_store` from bypassing per-collection resolution; make production `_get_client()` reject a missing `persist_dir` instead of reading the flat global default (keep an explicit constructor override for tests)
- [ ] 2.3 Add a startup log line listing any group directories shared by multiple collections (contention visibility)

## 3. Migration command

- [ ] 3.1 Add `rag-mcp migrate-storage`: with the server stopped, read the source root from `chroma_persist_dir` or `--root`; back it up; export each collection through the ChromaDB API with IDs, embeddings, documents, and metadata in API-sized batches; import those supplied embeddings into its resolved staging directory without invoking the embedding provider; verify records before an atomic destination swap; permit an existing group directory only when no collection or record conflicts; skip exact prior imports; preserve backups and report partial failures for safe rollback and idempotent re-runs
- [ ] 3.2 Include `--dry-run` output listing each collection, source root, and resolved destination without writing; document backup restoration and re-ingestion as the manual fallback in command help

## 4. Tests

- [ ] 4.1 Unit test: unmapped collection resolves to `{parent}/{collection}/`; mapped collection resolves to `{parent}/{group}/`; empty names, absolute paths, separators, `.`, and `..` are rejected for collection and group inputs; verify resolver tests fail before task 2.1 lands
- [ ] 4.2 Unit test through the composition-root provider: operation paths for two different unmapped collections receive different resolved directories and different store instances; MCP, CLI, watcher, and codebase-map paths MUST NOT fall back to one unresolved default store
- [ ] 4.3 Unit test through the composition-root provider: two mapped collections in one group receive the same directory and reuse the same store instance
- [ ] 4.4 Unit test: production client access without an injected `persist_dir` raises a clear error; assert `_get_client()` never calls `get_default_effective_settings()` and the default-store wiring cannot bypass collection resolution
- [ ] 4.5 Integration test with real process boundaries: synchronise two operating-system processes so writes overlap, then ingest collections A and B under one shared parent root through real ChromaDB clients; neither process reports a database-lock error and both collections contain the expected data; keep the same-process two-store case only as a fast supplement
- [ ] 4.6 Integration test: migrate a flat-layout collection and verify identical IDs, embeddings, documents, metadata, and chunk counts afterwards; configure the embedding provider to fail if migration attempts recomputation; exercise non-default roots through both `chroma_persist_dir` and `--root`, grouped destinations, conflict rejection, and an exact idempotent re-run matched on all copied fields; inject a failure after one collection imports, then verify source integrity, retained destinations, duplicate-free resume, and rollback
- [ ] 4.7 Regression: full fast suite passes (`uv run pytest -m "not slow" --cov=rag_mcp`); coverage floors hold for `config/`, `core/vectordb`, `transports/cli`; migration tests pass with the locked ChromaDB version and the `--resolution lowest-direct` floor job

## 5. Documentation and ADR

- [ ] 5.1 Write `docs/adr/ADR-0XX-per-collection-persist-dirs.md`: decision (directory-per-collection subdirectories over filename namespacing and over HTTP server mode), prior art (LlamaIndex namespacing pattern and its inapplicability to embedded Chroma), static-table decision with the middle-path rationale
- [ ] 5.2 In the same ADR, record future work as first-class deferred paths: (1) Option 2 — runtime-mutable grouping via MCP tool writing a state file, additive on this layout contract, triggered when the agentic loop creates collections dynamically; (2) agentic retrieval loop — multi-query fan-out, self-correcting retrieval, per-session namespaces (the workload that justifies Option 2); (3) cloud evolution — selecting an `HttpClient`-backed store at the `compose.py` store-selection seam while ChromaDB client construction remains in `core/vectordb/chroma.py` (self-hosted `chroma run` or managed cloud), noting that embedding compute, not Chroma, is the likely experiment bottleneck on the current Mac
- [ ] 5.3 Update `docs/guides/configuration.md` (new mapping var, parent-dir semantics) and `docs/guides/architecture.md` if the storage-layout invariant table needs the new rule
- [ ] 5.4 Update `transports/cli/watch.py` and the matching warning in `docs/guides/cli-reference.md` that said "two processes do not share the internal write lock": qualify it as safe for different collection directories, while the same collection or shared group still contends
- [ ] 5.5 Run `ruff check`, `ruff format --check`, import contracts, and file-size ceiling test; fix any violations
