## 1. Path-component safety (both adapters)

> `core/vectordb/lancedb.py` (497 lines) and `core/vectordb/chroma.py`
> (499 lines) are at the 500-line ceiling. Task 1.1 lands validation in a
> small shared focused module both adapters call — not inline growth, and
> no broad refactor.

- [ ] 1.1 Add path-component validation for collection names (non-empty, single component, no separators/`.`/`..`/absolute) in a small shared helper, invoked at both adapters' filesystem boundaries before any disk-touching store operation, with unit tests for every rejection case.
- [ ] 1.2 Verify the validation rejects bad names on the real store paths (LanceDB table open, Chroma collection use) without creating filesystem artefacts.

## 2. LanceDB layout pin (default path)

- [ ] 2.1 Add regression tests pinning the LanceDB native layout: two distinct collections resolve to distinct `.lance` table paths under `LANCEDB_URI` against a real temporary store. The tests pin layout only — they assert nothing about concurrency.
- [ ] 2.2 Confirm no `compose.py` changes are needed for the default path (one store serves all tables); if any become necessary, they must arrive as a small focused module given the 497-line ceiling.

## 3. Documentation

- [ ] 3.1 Document the layout and safety contract per backend in `docs/guides/configuration.md` and `docs/guides/architecture.md`, stating explicitly that cross-process concurrent writes are unverified and that the process-global ingestion mutation lock serialises mutations across collections within one process.
- [ ] 3.2 Record the deferred Chroma scope and its two blockers (operator demand; two-process/two-collection write experiment for any contention claim) in the proposal and design (done in this refresh) and reference them from the documentation where the Chroma extra is described.

## 4. Validation

- [ ] 4.1 Run `openspec validate add-per-collection-persist-dirs --strict`, targeted store tests, Ruff, and `uv run lint-imports`.
- [ ] 4.2 Ask for approval, then run the full fast suite with branch coverage at the repository floors.

## Deferred (not tasks of this change)

- Chroma per-collection persist directories, grouping map, per-collection
  resolution in `compose.py`, and the `rag-mcp migrate-storage` CLI.
- The `vectordb-abstraction` per-collection persist-resolution amendment.
- Any backend-split watcher-warning rewording.
