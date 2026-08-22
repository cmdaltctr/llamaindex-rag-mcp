# Task 1.6: Residual universal-lock and all-extras finding

## Finding

- **Date:** 2026-08-21
- **Lock:** `uv.lock`
- **Lock SHA-256:** `4ce24a2da4e349130a33292d108d7d2d74d7893dbe2585427d8f50c1c9b6fa70`
- **Scanner:** `pip-audit 2.10.1`
- **Resolution scope:** `uv export --frozen --all-extras --no-dev --no-emit-project`
- **Audited dependencies:** 179
- **Vulnerabilities:** 1 vulnerability in 1 package

`uv.lock` continues to contain every declared optional extra. The all-extras resolution includes:

```text
chromadb==1.5.9
llama-index-vector-stores-chroma==0.5.5
```

The universal-lock scan reported:

```text
package=chromadb
version=1.5.9
id=PYSEC-2026-311
aliases=['GHSA-f4j7-r4q5-qw2c', 'CVE-2026-45829']
fix_versions=[]
```

The adapter package had no separate advisory in this scan. Its presence pulls the affected Chroma package into the all-extras resolution.

## Commands and scanner output

The project environment does not include `pip-audit`:

```console
$ uv run --no-sync pip-audit 2>&1 | tail -30
error: Failed to spawn: `pip-audit`
  Caused by: No such file or directory (os error 2)
```

`pip-audit 2.10.1 --locked` did not recognise `uv.lock` directly. The lock was therefore exported with every extra, without changing it. The scanner audited the exact pinned export without dependency re-resolution:

```console
$ uv export --frozen --all-extras --no-dev --no-emit-project --no-hashes \
    --format requirements-txt \
    --output-file /tmp/ragmcp-security-evidence-20260821/universal-lock-requirements.txt

$ uvx pip-audit \
    --requirement /tmp/ragmcp-security-evidence-20260821/universal-lock-requirements.txt \
    --no-deps --disable-pip --format json --progress-spinner off
exit_code=1
dependency_count=179
vulnerability_count=1
package=chromadb version=1.5.9 id=PYSEC-2026-311 fixes=[] aliases=['GHSA-f4j7-r4q5-qw2c', 'CVE-2026-45829']
Found 1 known vulnerability in 1 package
```

The exported requirements SHA-256 was `98c5ec696003a8332b1aabc34f167f7ca27b3748bfb4401b06b93f613c6e63e7`. The complete scanner JSON SHA-256 was `cfd123cbdfe574087dc89b3125df6356e38d83f360f8697afe7db0b395c7fb47`.

## Disposition status

The base wheel and fresh base installation exclude both Chroma distributions. The residual advisory still exists in the universal lock and the opt-in `chroma` extra. Optional placement does not clear the finding.

Design decision D9 requires a named, dated policy-owner decision. **Signed 2026-08-22** — see the "Signed policy-owner disposition" section below.

## DRAFT policy-owner disposition template

> **DRAFT ONLY. This section is not an approval or acceptance.**
>
> A named policy owner must complete every field and provide a dated signature. The release remains blocked until that happens.

| Field | Required value |
|---|---|
| Owner | **TBD. A real named policy owner is required.** |
| Decision | **APPROVE / REJECT** |
| Decision date | **TBD, ISO 8601 date** |
| Scope | **TBD. Identify the release, `uv.lock`, the `chroma` extra, and affected distribution versions.** |
| Rationale | **TBD. Explain the policy basis, exposure analysis, and compensating controls.** |
| Expiry or review date | **TBD, ISO 8601 date** |
| Official release trigger | Reassess only after an official maintainer PyPI release. |
| Linked-fix trigger | Require a linked fixing commit or release note. |
| Advisory trigger | Require exclusion of the candidate version by the named authoritative advisory source. |
| Renewed-review trigger | Require a new security review, preferably with an isolated regression or proof-of-concept check. |
| Named owner's dated signature | **TBD. Required to clear the D9 release gate.** |

**Policy-owner decision:** PENDING.

**Result:** BLOCKED pending the named owner's completed, dated disposition. If policy rejects the residual risk, task 1.7 requires a separately locked and distributed plugin or temporary removal of Chroma support.

---

## Signed policy-owner disposition

> **SIGNED 2026-08-22.** This section records the named owner's dated approval and clears the D9 release gate for the residual finding described above. The DRAFT template above is superseded by this record.

| Field | Value |
|---|---|
| Owner | Dr Muhammad Aizat Bin Md Hawari |
| Decision | **APPROVE** (with quarantine) |
| Decision date | 2026-08-22 |
| Scope | This release (`rag_mcp` on `feat/make-lancedb-default-and-isolate-chromadb`), `uv.lock` (SHA-256 `4ce24a2da4e349130a33292d108d7d2d74d7893dbe2585427d8f50c1c9b6fa70`), the opt-in `chroma` extra, and the affected distributions `chromadb==1.5.9` / `llama-index-vector-stores-chroma==0.5.5` (PYSEC-2026-311 / GHSA-f4j7-r4q5-qw2c / CVE-2026-45829, no fix versions reported by pip-audit 2.10.1). |
| Rationale | The base wheel and a fresh base installation contain neither Chroma distribution; the vulnerable package exists only in the universal lock and the opt-in `chroma` extra, which no base path installs or imports. The project never launches Chroma's Python FastAPI server — the vulnerable surface — and uses only `PersistentClient`/`CloudClient`. Exposure is therefore confined to operators who explicitly install the extra and select `VECTOR_STORE=chroma`; the fail-closed legacy gate and explicit-selection provenance require that explicit choice. Optionalisation does not make the package safe; it bounds the exposure to opt-in use pending a patched release. Quarantine and patch-reconsideration triggers are recorded in ADR-049 (decision D10): official maintainer PyPI release, linked fixing commit or release note, exclusion of the candidate version by the named authoritative advisory source, and a renewed review (preferably with an isolated regression or proof-of-concept check). Disagreement between authoritative sources keeps quarantine in force. |
| Expiry or review date | 2026-11-22 (90 days), or earlier on the first of the ADR-049 D10 triggers (official PyPI release with a linked fix), whichever comes first. |
| Official release trigger | Reassess only after an official maintainer PyPI release. |
| Linked-fix trigger | Require a linked fixing commit or release note. |
| Advisory trigger | Require exclusion of the candidate version by the named authoritative advisory source. |
| Renewed-review trigger | Require a new security review, preferably with an isolated regression or proof-of-concept check. |
| Named owner's dated signature | **Dr Muhammad Aizat Bin Md Hawari, 2026-08-22** |

**Policy-owner decision:** APPROVED with quarantine, dated 2026-08-22.

**Result:** The D9 release gate is cleared for this residual finding under the recorded scope, expiry, and triggers. If the extra is used beyond the expiry or review date without a patched release, or if any trigger fires, the disposition must be re-reviewed before further release. If policy later rejects the residual risk, task 1.7 (separately locked/distributed plugin or temporary removal of Chroma support) applies.
