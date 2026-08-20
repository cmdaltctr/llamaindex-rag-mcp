## Why

ChromaDB 1.5.9 is a critical direct dependency affected by CVE-2026-45829, and no patched release exists. Stage 5 proved LanceDB satisfies the shared retrieval, filter, score, cache, and ingestion contracts, so LanceDB can become the safe base default while Chroma remains an explicit optional backend.

## What Changes

- **BREAKING**: Change the default `VECTOR_STORE` from `chroma` to `lancedb`.
- Move `chromadb` and `llama-index-vector-stores-chroma` from base dependencies into a named `chroma` optional extra.
- Make all default construction and fallback paths resolve LanceDB without importing ChromaDB.
- Return an actionable installation message when `VECTOR_STORE=chroma` or `CHROMA_MODE=cloud` is selected without the extra.
- Reject incompatible `CHROMA_MODE` and `VECTOR_STORE` combinations during settings validation.
- Warn existing users when an unset store selector resolves to LanceDB while a non-empty legacy Chroma directory exists; explain how to retain Chroma or re-ingest.
- Run future experiments on LanceDB unless ChromaDB is the manipulated factor.
- Add base-install and `chroma`-extra CI jobs, with store-neutral test fixtures for the default suite.
- Write ADR-049 covering the default change, optional dependency boundary, security rationale, migration, and reconsideration trigger.
- Reconsider ChromaDB only after an official patched release exists and a separate decision validates it.

## Capabilities

### New Capabilities

- `experiment-vector-store-policy`: Defines LanceDB as the default store for future experiments unless the store backend is deliberately manipulated.

### Modified Capabilities

- `lancedb-vector-store`: Makes embedded LanceDB the base-install and runtime default.
- `vector-store-registry`: Requires default and missing-extra resolution through the lazy registry with actionable errors.
- `chroma-cloud-backend`: Makes local and cloud Chroma modes conditional on the optional `chroma` extra and compatible store selection.
- `dependency-floor-integrity`: Moves Chroma floors into an optional group while retaining lowest-direct testing.
- `config-composition-root`: Changes the resolved vector-store default and validates Chroma-specific settings against store selection.

## Impact

- Affects package dependencies, `uv.lock`, settings defaults, registry fallback, sparse capability probing, runtime summaries, CI, test fixtures, environment examples, and user documentation.
- Existing `./chroma_db/` data is not migrated automatically. Users must install the extra and select Chroma, or re-ingest into LanceDB.
- The lockfile may still contain optional Chroma packages; security tooling needs an explicit optional-and-unreachable disposition until a patch exists.
- Chroma Cloud remains available only through the optional extra.
