# Tasks: add-per-collection-persist-dirs

## 1. Settings and resolver data

- [ ] 1.1 Add `collection_group_map: dict[str, str]` (collection name → group directory name, default empty) to `config/__init__.py` and mirror in `core/settings.py`, following the nested env-var convention (ADR-037); choose the encoding (JSON dict env var) and document it in `.env.example`
- [ ] 1.2 Confirm `chroma_persist_dir` semantics become "parent root of all collection directories" in docstrings and `.env.example` (no code change to the field itself)

## 2. Composition-root resolution

- [ ] 2.1 Add a `resolve_persist_dir(collection_name, settings) -> str` function in `compose.py`: mapped group name → `{parent}/{group}/`; else `{parent}/{collection_name}/`; pure lookup, no filesystem touch, no `if/elif` chains over collection names
- [ ] 2.2 Route all `ChromaVectorStore` construction through the resolved directory; retire the production-path lazy flat-default read in `_get_client()` (`core/vectordb/chroma.py`) so the store always receives an injected directory (keep constructor override for tests)
- [ ] 2.3 Add a startup log line listing any group directories shared by multiple collections (contentment visibility)

## 3. Migration command

- [ ] 3.1 Add `rag-mcp migrate-storage` CLI command: with the server stopped, move each collection found in the flat `./chroma_db` layout to its resolved per-collection subdirectory (directory moves only, no embedding recomputation); refuse to run if target directories already exist
- [ ] 3.2 Include `--dry-run` output listing source → destination moves; document the manual alternative (move directories yourself, or re-ingest) in the command help

## 4. Tests

- [ ] 4.1 Unit test: unmapped collection resolves to `{parent}/{collection}/`; mapped collection resolves to `{parent}/{group}/` — verify resolver tests fail before task 2.1 lands
- [ ] 4.2 Unit test: store constructed for different unmapped collections receives different directories (two `PersistentClient` paths never equal)
- [ ] 4.3 Unit test: two mapped collections in one group receive the same directory (opt-in co-location works)
- [ ] 4.4 Integration test: ingest into collection A and collection B in separate processes (or simulated via two store instances) — no database-locked errors, data lands in separate files
- [ ] 4.5 Integration test: migration command moves a flat-layout collection; collection readable and queryable afterwards with identical chunk counts
- [ ] 4.6 Regression: full fast suite passes (`uv run pytest -m "not slow" --cov=rag_mcp`); coverage floors hold for `config/`, `core/vectordb`, `transports/cli`

## 5. Documentation and ADR

- [ ] 5.1 Write `docs/adr/ADR-0XX-per-collection-persist-dirs.md`: decision (directory-per-collection subdirectories over filename namespacing and over HTTP server mode), prior art (LlamaIndex namespacing pattern and its inapplicability to embedded Chroma), static-table decision with the middle-path rationale
- [ ] 5.2 In the same ADR, record future work as first-class deferred paths: (1) Option 2 — runtime-mutable grouping via MCP tool writing a state file, additive on this layout contract, triggered when the agentic loop creates collections dynamically; (2) agentic retrieval loop — multi-query fan-out, self-correcting retrieval, per-session namespaces (the workload that justifies Option 2); (3) cloud evolution — `PersistentClient` → `HttpClient` swap at the single `compose.py` seam (self-hosted `chroma run` or managed cloud), noting that embedding compute, not Chroma, is the likely experiment bottleneck on the current Mac
- [ ] 5.3 Update `docs/guides/configuration.md` (new mapping var, parent-dir semantics) and `docs/guides/architecture.md` if the storage-layout invariant table needs the new rule
- [ ] 5.4 Update `transports/cli/watch.py` and README guidance that warned "two processes do not share the internal write lock": now qualified — safe for different collections, still unsafe for the same collection or shared group
- [ ] 5.5 Run `ruff check`, `ruff format --check`, import contracts, and file-size ceiling test; fix any violations
