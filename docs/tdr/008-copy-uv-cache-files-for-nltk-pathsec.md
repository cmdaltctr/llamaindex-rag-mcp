# TDR-008: Copy uv cache files for NLTK Pathsec in Linux CI

**Date:** 2026-08-13
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Tags:** ci | uv | nltk | dependency-floors | security

## Context

The Linux CI test and floor-resolution jobs failed while LlamaIndex loaded
its bundled NLTK stopwords. The failure occurred before the affected tests
could run. macOS did not show the same failure.

The project must retain the floor-resolution matrix. It proves that declared
dependency minima still work. The project must also retain NLTK Pathsec,
which protects file access from unsafe path changes.

### Root Cause Analysis

The floor-resolution job selected NLTK 3.10.3. Its Pathsec hardened file
open rejects files with more than one hard link. uv materialised package files
from its Linux cache with hard links. LlamaIndex's bundled file
`_static/nltk_cache/corpora/stopwords/english` therefore had link count two,
and Pathsec raised an error.

The error is a package-installation interaction. It is not an application
path traversal issue and does not indicate corrupt stopwords data.

## Decision

Set `UV_LINK_MODE: copy` on CI `uv sync` steps that install the base or
floor-resolution environments:

```yaml
env:
  UV_LINK_MODE: copy
run: uv sync --frozen
```

The floor matrix uses the same environment value with
`uv sync --resolution lowest-direct`. Copying prevents package files in the
environment from sharing hard links with uv's cache. Keep NLTK Pathsec and
the floor-resolution checks enabled.

## Consequences

### Positive

- Linux CI runs NLTK Pathsec without false failures from uv cache links.
- Floor-resolution coverage remains active.
- NLTK's hard-link security check remains active.

### Negative

- Dependency installation copies files and uses more temporary disk space.
- CI dependency installation can take slightly longer.

### Neutral

- Local developers can continue to use uv's default link mode.
- The lockfile and declared dependency floors are unchanged.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| Disable NLTK Pathsec | Removes a security check to hide an installation artefact. |
| Pin NLTK below 3.10.3 | Avoids the symptom and leaves the cache-link behaviour unresolved. |
| Remove floor-resolution CI | Removes the dependency compatibility contract that detected the issue. |
| Use `UV_LINK_MODE=copy` in affected CI installs | Accepted because it isolates installed files from the cache. |

## How to Recognise / Handle This Again

1. CI fails while NLTK opens a bundled LlamaIndex corpus file.
2. Check the error for a Pathsec hard-link rejection and inspect the file link count with `stat`.
3. Confirm the job has `UV_LINK_MODE: copy` on its `uv sync` step.
4. Re-run the failed CI job. Do not disable Pathsec or the floor matrix.

## Revisit Triggers

- NLTK changes Pathsec hard-link handling.
- uv stops using hard links by default in Linux CI.
- LlamaIndex removes the bundled NLTK cache.
- CI disk or install-time cost becomes material.

## References

- [PR #49](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/49)
- `.github/workflows/ci.yml` — dependency-install steps
- `tests/test_dependency_floors.py` — declared floor contract
- [TDR-004](004-uv-no-build-incompatible-with-editable-installs.md) — earlier uv CI compatibility record
