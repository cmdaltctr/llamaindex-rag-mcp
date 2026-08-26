## 1. Layout contract and safety (both backends)

- [ ] 1.1 Add path-component validation for collection and group names (non-empty, single component, no separators/`.`/`..`/absolute) at both adapters' filesystem boundaries, with unit tests for every rejection case.
- [ ] 1.2 Add regression tests pinning the LanceDB native layout: two distinct collections resolve to distinct `.lance` table paths under `LANCEDB_URI` against a real temporary store.
- [ ] 1.3 Specify the per-backend resolution rules in `config/` data + `compose.py` (LanceDB: no-op resolution; Chroma local: default per-collection directory + grouping map), no `if/elif` over collection names.

## 2. Chroma per-collection persistence (opt-in extra path)

- [ ] 2.1 Add the `collection_group_map` setting (flat JSON) to `config/` and `core/settings.py`, mirrored for injection.
- [ ] 2.2 Implement the directory-keyed Chroma store provider in `compose.py`: build-or-reuse per resolved directory; inject into MCP, CLI, watcher, ingestion, retrieval, deletion, listing, profile, and codebase-map paths.
- [ ] 2.3 Replace the Chroma `_get_client()` lazy flat-default read with the injected resolved directory; missing injection fails clearly.
- [ ] 2.4 Startup log line listing any groups whose members share a directory.

## 3. Migration (Chroma extra only)

- [ ] 3.1 Implement `rag-mcp migrate-storage`: stopped-server check, source backup, per-collection API export/import into staging, verification, atomic swap, resumable exact imports, conflict abort, rollback restore.
- [ ] 3.2 Guard: the command refuses to run unless the `chroma` extra is installed and `VECTOR_STORE=chroma`; it MUST NOT touch LanceDB stores.
- [ ] 3.3 Document the migration and the re-ingest fallback in the CLI reference.

## 4. Watcher warning accuracy

- [ ] 4.1 Split the daemon warning by backend: same-collection writes contend everywhere; different-collection writes contend only under Chroma co-location (shared group or flat legacy dir).

## 5. Validation and documentation

- [ ] 5.1 Update `docs/guides/configuration.md` and `docs/guides/architecture.md` with the layout contract per backend.
- [ ] 5.2 Run `openspec validate add-per-collection-persist-dirs --strict`, targeted store/compose/daemon tests, Ruff, and `uv run lint-imports`.
- [ ] 5.3 Ask for approval, then run the full fast suite with branch coverage at the repository floors.
