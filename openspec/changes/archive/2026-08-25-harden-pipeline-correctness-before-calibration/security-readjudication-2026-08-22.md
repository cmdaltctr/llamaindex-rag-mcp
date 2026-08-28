# Security re-adjudication: ChromaDB CVE-2026-45829 release gate

**Date:** 2026-08-22
**Supersedes:** the BLOCKED release note in this change's Stage 5 security
review (2026-08-19).
**Advisory:** PYSEC-2026-311 / GHSA-f4j7-r4q5-qw2c / CVE-2026-45829 in
`chromadb==1.5.9` (no fixed release available at adjudication time).
**Disposing change:** `make-lancedb-default-and-isolate-chromadb` — PR #61,
merge commit `e0fa536`, ADR-049, archived with full evidence at
`openspec/changes/archive/2026-08-22-make-lancedb-default-and-isolate-chromadb/`.

## The 2026-08-19 conditions

The Stage 5 security review imposed two conditions before merging to `main`:

1. Track the dependency in a separate security change.
2. Do not merge to `main` until the release gate clears.

## Adjudication

Both conditions are satisfied as of the PR #61 merge.

1. **Separate security tracking exists.** The
   `make-lancedb-default-and-isolate-chromadb` change was created, reviewed,
   and merged for exactly this purpose. Its evidence directory records the
   wheel metadata audit, fresh base installation, base SBOM, residual
   all-extras lock finding, server-entrypoint scan, and risks register.

2. **The base-release gate clears.** Chain of evidence:
   - `pyproject.toml` places `chromadb` only under the optional `chroma`
     extra, with the CVE named in a comment block (ADR-049 quarantine).
   - Base SBOM (`evidence/03-base-sbom.json`): 133 dependencies scanned
     twice, zero known vulnerabilities, no Chroma distribution present.
   - Fresh base installation (`evidence/02-fresh-install.md`): contains
     neither `chromadb` nor `llama-index-vector-stores-chroma`.
   - No server entrypoint (`evidence/05-no-server-entrypoint.md`): zero
     FastAPI/uvicorn/`chromadb.app` launch paths in project source.
   - Import-linter contract `chromadb-confined-to-vectordb` fails the build
     if Chroma imports leak outside the vector-store adapter.
   - Fail-closed legacy guard (`tests/test_legacy_chroma_fail_closed.py`):
     a default-derived store cannot silently fall back to a legacy Chroma
     directory.

## Residual risk (accepted)

The universal `uv.lock` still resolves `chromadb==1.5.9` for users who
install the opt-in `chroma` extra. Exposure is limited to the
`PersistentClient`/`CloudClient` constructor paths; the vulnerable FastAPI
server is never launched by this project. This is an accepted-risk posture
documented in ADR-049 and the `pyproject.toml` quarantine comment.

**Ratified 2026-08-22 by Dr Muhammad Aizat Bin Md Hawari (policy owner):**
accepted-risk. Rationale: the extra is opt-in and retained deliberately for
experiment use; the quarantine note in `pyproject.toml` warns anyone who
enables it; downstream forks that choose to install the extra assume that
risk themselves. This signature also discharges the unsigned D9 disposition
flagged by the archived ADR-049 security verdict.

## Review triggers

- Re-audit on every `chromadb` release; lift the quarantine only when a
  fixed version clears PYSEC-2026-311 and the registry list-collections
  regression noted in ADR-049 is resolved.
- Re-open this gate if any change promotes `chromadb` toward the base
  dependency closure.
