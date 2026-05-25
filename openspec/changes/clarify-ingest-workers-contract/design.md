## Context

`ingest_path_async(..., workers=1)` documents `workers` as unused. The CLI still exposes `--workers/-w`, reads `INGEST_WORKERS`, clamps it, passes it through, and includes it in reports. `.env.example` says `INGEST_WORKERS` controls parallel file-level reading, which is no longer true.

## Goals / Non-Goals

**Goals:**
- Remove misleading user-facing references to file-reader workers.
- Keep actual performance knobs clear: embedding batch size and embedding concurrency.
- Avoid surprising breakage where reasonable.

**Non-Goals:**
- Reintroducing parallel file reading.
- Changing embedding concurrency behavior.
- Redesigning ingestion scheduling.

## Decisions

- **Compatibility mode (resolved 2026-05-25): hard remove. No deprecation window.** Rationale: `--workers` and `INGEST_WORKERS` have been no-ops since the async ingestion refactor. `EMBED_CONCURRENCY` is the documented and effective control. The project is pre-1.0 with no known external consumers depending on the flag.
- Remove `--workers/-w` from the `rag-mcp ingest` CLI entirely (no hidden alias, no warning shim).
- Remove `INGEST_WORKERS` from `config.py` and `.env.example`.
- Remove the `workers` parameter from `ingest_path_async()` and any internal callers.
- Remove `workers` from the report configuration output.
- The commit message SHALL include a `BREAKING CHANGE:` trailer so `python-semantic-release` triggers an appropriate version bump and the release notes call out the removal.
- Release notes SHALL direct users to `EMBED_CONCURRENCY` (and `EMBED_BATCH_SIZE`) as the supported throughput controls.

## Risks / Trade-offs

- Removing `--workers` breaks any script or shell alias that passes it → accepted risk. Pre-1.0, no public consumers known. The breaking-change release note is the mitigation.
- Removing `workers` from `ingest_path_async()` is an API change for any external caller of the module → accepted; the module is not a published library surface.
- Users with stale `.env` files containing `INGEST_WORKERS` will see no error (env vars are ignored if undefined in `config.py`) → acceptable silent no-op; release notes cover migration.
