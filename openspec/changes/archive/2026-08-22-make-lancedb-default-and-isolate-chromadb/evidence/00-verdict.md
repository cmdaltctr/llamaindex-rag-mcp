# Security verdict: make-lancedb-default-and-isolate-chromadb

- **Date:** 2026-08-21
- **Auditor:** a-security
- **Scope:** OpenSpec tasks 1.3–1.6, design D8/D9, base wheel, fresh base installation, dependency scans, Chroma server reachability, and a focused secret-leakage review
- **Verdict:** **BLOCKED**

## What's wrong

The base wheel and base installation pass every requested packaging check. The universal lock still resolves affected `chromadb==1.5.9`, and no named policy owner has signed the D9 disposition.

## What to do

1. Assign a named release-policy owner.
2. Complete and sign the dated template in [`04-residual-lock-finding.md`](04-residual-lock-finding.md).
3. If the owner rejects the residual risk, execute task 1.7 before release.
4. Re-run the advisory review when any D10 patch or advisory trigger occurs.

## Severity-ranked findings

### [GATE BLOCKER] D9 policy-owner disposition is missing

- **Location:** [`04-residual-lock-finding.md`](04-residual-lock-finding.md)
- **Evidence:** The all-extras scan found `PYSEC-2026-311`, with aliases `GHSA-f4j7-r4q5-qw2c` and `CVE-2026-45829`, in `chromadb==1.5.9`.
- **Fix versions reported by scanner:** None.
- **Exposure controls:** The base wheel excludes both Chroma distributions. The fresh base install contains neither. Project source starts no Chroma FastAPI server.
- **Gate impact:** Design D9 still requires a named, dated approval or rejection. No risk acceptance is recorded.
- **Required resolution:** Signed policy-owner disposition, or task 1.7 isolation/removal.

This is a release-policy blocker. The audit did not establish a newly reachable base-install exploit.

### [INFO] Direct wheel-path mode is unsupported by pip-audit 2.10.1

The scanner rejected the wheel as a positional project path. Two separate `--path` scans over isolated installations of the built wheel completed successfully. Their full JSON results were byte-identical.

## Requested evidence results

| Evidence | Result | Key proof |
|---|---:|---|
| [`01-wheel-metadata.md`](01-wheel-metadata.md) | PASS | Zero unconditional Chroma `Requires-Dist` entries; wheel SHA-256 recorded |
| [`02-fresh-install.md`](02-fresh-install.md) | PASS | Both imports absent; both distributions absent; default LanceDB search returned `[]`; no Chroma module loaded |
| [`03-base-sbom.json`](03-base-sbom.json) and [summary](03-base-sbom-summary.md) | PASS | 133 dependencies scanned twice; zero known vulnerabilities; no Chroma distribution |
| [`04-residual-lock-finding.md`](04-residual-lock-finding.md) | BLOCKED | 179 all-extras dependencies; one Chroma advisory; owner remains `TBD` |
| [`05-no-server-entrypoint.md`](05-no-server-entrypoint.md) | PASS | Zero FastAPI/uvicorn/`chromadb.app` launch paths; only `PersistentClient` and `CloudClient` constructors |

## Focused code review

- `core/vectordb/legacy.py`: no credential leakage. Operator errors name the legacy directory and required choices only.
- `core/vectordb/registry.py`: no credential values. Errors expose package names and install guidance only.
- Chroma cloud connection errors pass through `redact_cloud_secrets(...)`.

## Security checklist coverage

| Category | Status | Scope result |
|---|---:|---|
| 1. Secrets and credentials | PASS | Focused review found no leaked secret values |
| 2. Input validation | N/A | No input-boundary change in the requested packaging scope |
| 3. Authentication and authorisation | N/A | No auth surface in scope |
| 4. Injection risks | N/A | No query or command construction change in scope |
| 5. Data exposure | PASS | Legacy diagnostic exposes a configured directory path only; cloud errors are redacted |
| 6. Dependency CVE audit | PARTIAL / BLOCKED | Base closure clean; universal all-extras lock retains the Chroma advisory |
| 7. OWASP Top 10 | PARTIAL | A06 is recorded above; other categories have no changed surface in this audit |
| 8. Cloudflare Workers | N/A | This is not a Cloudflare Workers change |

Peer CVE validation was attempted, but the environment rejected nested delegation at its depth limit. The user prohibited external network research beyond `pip-audit`. The CVE identity, aliases, affected installed version, and empty fix-version list therefore come directly from the current `pip-audit 2.10.1` PyPI advisory response.

The audit created evidence files only. Other working-tree changes appeared concurrently and remain outside this audit.

## Verdict justification

**BLOCKED.** Tasks 1.3, 1.4, 1.5, and the D9 source-entry check pass. Task 1.6 cannot clear until a real named policy owner supplies a dated decision and signature. This audit does not accept the residual risk.

---

## Addendum 2026-08-22 (dated, append-only)

The D9 blocker recorded above was resolved the next day: the named policy
owner (Dr Muhammad Aizat Bin Md Hawari) signed an APPROVE-with-quarantine
disposition dated 2026-08-22 with expiry 2026-11-22 or earlier on the first
ADR-049 D10 trigger. See `04-residual-lock-finding.md` (Signed policy-owner
disposition). The audit's original BLOCKED verdict stands as recorded at
2026-08-21; this addendum records the subsequent approval without rewriting
it.
