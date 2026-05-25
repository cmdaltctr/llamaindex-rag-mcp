## Why

Several verified findings are low-risk maintainability issues: an unreachable unsupported-file branch, an internal benchmark importing a private chunking helper, a cosmetic watcher lock name, and a theoretically racy metadata ChromaDB client initializer. Grouping these small cleanups keeps functional changes separate from hygiene work.

## What Changes

- Remove or correct the unreachable `_gather_supported_files` unsupported-single-file branch and its misleading comment/test wording.
- Add a public/internal-supported chunking helper for benchmark use, or clearly document the private helper usage.
- Rename watcher `_timers_lock` to a clearer state lock if it protects both timers and hash cache.
- Protect `_chroma_client` lazy initialization with a small lock.
- Optionally replace the hardcoded test persist path with `tmp_path` for clarity, despite current EphemeralClient isolation.

## Capabilities

### New Capabilities
- `internal-maintainability`: Internal helper boundaries, lock naming, and test isolation SHALL be clear and low-risk.

### Modified Capabilities

## Impact

- Affected code: `src/rag_mcp/ingestion.py`, `src/rag_mcp/cli.py`, `src/rag_mcp/watcher.py`, `src/rag_mcp/metadata_extractor.py`, `tests/conftest.py`, related tests.
- No user-facing feature changes expected.
- No storage or dependency changes.
