## Why

The `--workers` CLI option and `INGEST_WORKERS` configuration still imply parallel file readers, but the current async ingestion path processes files sequentially and the `workers` parameter is explicitly unused. This mismatch erodes trust in the CLI and reports.

## What Changes

- Declare the contract explicitly: ingestion is sequential at the file-reading level. Embedding batching and concurrency are the only effective throughput controls.
- **Hard-remove** the `--workers/-w` CLI option from `rag-mcp ingest`. No hidden alias, no deprecation shim.
- Remove `INGEST_WORKERS` from `config.py` and `.env.example`.
- Remove the `workers` parameter from `ingest_path_async()` and all internal callers.
- Stop emitting `workers` in the ingest report.
- Keep `EMBED_BATCH_SIZE` and `EMBED_CONCURRENCY` as the documented, supported throughput controls. Update `.env.example` and any docs to point users to them.
- The implementing commit SHALL carry a `BREAKING CHANGE:` trailer so `python-semantic-release` cuts an appropriate version bump and the release notes call out the removal.

## Capabilities

### New Capabilities

### Modified Capabilities
- `async-ingestion`: CLI ingest flags and reports SHALL describe only effective ingestion controls.

## Impact

- Affected code: `src/rag_mcp/config.py`, `src/rag_mcp/cli.py`, `src/rag_mcp/ingestion.py`, `.env.example`, documentation/tests around CLI help and reports.
- **Breaking change**: removes the user-visible `--workers/-w` CLI option. Any script, shell alias, or CI job passing `--workers` will fail with "no such option" after release.
- **Breaking change**: removes the `workers` parameter from `ingest_path_async()`. Any external caller (none known) must update.
- Stale `.env` files containing `INGEST_WORKERS` will continue to load without error (the variable is simply ignored), so no migration step is required for end users beyond reading the release notes.
- Release notes SHALL direct users to `EMBED_CONCURRENCY` and `EMBED_BATCH_SIZE` as the supported throughput controls.
