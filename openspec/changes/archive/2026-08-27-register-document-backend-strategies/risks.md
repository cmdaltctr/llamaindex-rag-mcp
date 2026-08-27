# Security Assessment: register-document-backend-strategies

## Summary

- **Date**: 2026-08-26
- **Scope**: `src/rag_mcp/core/ingestion/backends/` (registry, orchestrator, local, contract), `src/rag_mcp/capabilities.py`, and diffs to `compose.py`, `integrations/azure.py`, `core/ingestion/chunker.py`, `config/__init__.py`, `tests/test_document_backends.py` on branch `feat/register-document-backend-strategies`
- **Auditor**: a-security (s-agent-security skill)
- **Scanner verdict (deterministic floor)**: BLOCKED — {'CRITICAL': 76, 'HIGH': 4, 'MEDIUM': 2}
- **Final verdict**: APPROVED (2026-08-27) — the chromadb acceptance condition (Decision 1) is now recorded by the maintainer. Original verdict at scan time: NEEDS FIXES, pending that acceptance.
- **Verdict lowered below floor?**: Yes — BLOCKED → NEEDS FIXES → APPROVED. Rationale: all 72 gitleaks CRITICALs are disproven false positives (content inspected); the 4 chromadb CRITICAL/HIGH CVEs are pre-existing, carry no patched version, and are unreachable in this codebase's embedded-only chromadb usage (source-proven below). This follows the unreachable-CVE precedent. The drop to APPROVED is authorised by the recorded maintainer acceptance in Decision 1.

## Deterministic Scan Results

- **Tools**: gitleaks 8.30.1, semgrep 1.174.0 (vendored rules), osv-scanner 2.5.1, trivy 0.74.0, bandit 1.9.4
- **Counts (merged findings.json)**: 3,093 total — gitleaks 72, semgrep 2, osv-scanner 4, trivy 4, bandit 3,011 (LOW/INFO, test-code noise: S101 asserts and similar)
- **Findings inside the change surface (all tools, all severities): 0**
- **Scope deviations (recorded)**: semgrep/bandit scoped to `src/ tests/ scripts/`; trivy/osv scoped to root lockfiles — `experiments/` (368 MB of research artefacts) excluded after the full-repo run exceeded the 10-minute budget twice. gitleaks history scan stopped after 20 minutes: every change-surface file is uncommitted (absent from history by definition), the working-tree scan completed, and the repo's own pre-commit hook runs gitleaks 8.30.1 on every commit.
- Raw evidence: `.security/findings.json` (scan artefacts reviewed, then deleted from disk after acceptance; the directory is gitignored for future scans)

## Findings

### [MEDIUM] chromadb 1.5.9 carries four unpatched CVEs (2 CRITICAL, 2 HIGH) — ACCEPTED, see Decision 1
**Source**: [scanner: osv-scanner + trivy CVE-2026-45829/45830/45831/45833], reachability [LLM-judged]
**Location**: `uv.lock` (chromadb==1.5.9; not modified by this change)
**Evidence**:

| CVE | Severity | Class | Patched | Reachable here? |
|---|---|---|---|---|
| CVE-2026-45829 | Critical | Pre-auth code injection via `trust_remote_code` on `/api/v2/tenants/{t}/databases/{d}/collections` | None | No |
| CVE-2026-45833 | Critical | Authenticated code injection, needs UPDATE_COLLECTION permission, v2 API | None | No |
| CVE-2026-45830 | High | Cross-tenant read/write by any authenticated user | None | No |
| CVE-2026-45831 | High | SimpleRBACAuthorizationProvider never scopes permissions to tenant/db/collection | None | No |

All four exploit a **network-exposed chroma server** (CVSS AV:N; tenant/RBAC/v2-endpoint prerequisites). This project constructs chromadb exclusively as an embedded client: `chromadb.PersistentClient(path=...)` at `src/rag_mcp/core/vectordb/chroma.py:113` and `:465`. No `HttpClient`, no `chroma run`, no listening port exists anywhere in `src/`. The vulnerable server component never executes. `CHROMA_MODE=cloud` uses `CloudClient` against Chroma's operated service, whose server side is the vendor's responsibility.
**Impact**: Not exploitable in the shipped configuration. Becomes relevant only if a future change exposes a chroma server or points an HttpClient at untrusted infrastructure.

**Decision 1 — recorded 2026-08-27, maintainer Dr Muhammad Aizat Bin Md Hawari: ACCEPTED (option 1).**
chromadb stays behind the `chroma` extra (ADR-049 quarantine). The four
CVEs are unreachable in this codebase's embedded-only usage:
`PersistentClient` (`chroma.py:113,465`) and `CloudClient` only — no
`chroma run`, no `HttpClient`, no listening port, ever. Standing
constraint: **never deploy a chroma server from this codebase.** If a
future change needs chroma server mode, this acceptance is void and the
exposure must be re-assessed. Re-scan when upstream publishes a patch
(chroma-core/chroma#6717, #7588, #7602 tracked for awareness).

### [LOW] Per-file retry delay amplifies ingest latency (accepted)
**Source**: [LLM-judged]
**Location**: `src/rag_mcp/core/ingestion/backends/orchestrator.py:24-25` (`MAX_RETRIES = 1`, `RETRY_DELAY_S = 5.0`)
**Evidence**: Under `DOCUMENT_BACKEND=azure` with the service unreachable, each failing `.pdf`/`.docx`/`.doc` costs 2 attempts + 5 s sleep before the local fallback. A directory of N such files adds roughly N×5 s wall time. The budget is bounded, `asyncio.CancelledError` inherits from `BaseException` so cancellation propagates, and the constants replicate the deleted `read_with_azure_fallback` behaviour exactly.
**Fix**: None required. If ingest latency ever matters at scale, make `RETRY_DELAY_S` a settings field — separate concern, not a security fix.

### [LOW] `AzureDocReader` retains a default-settings fallback constructor (accepted)
**Source**: [LLM-judged]
**Location**: `src/rag_mcp/integrations/azure.py:53-70`
**Evidence**: Constructing `AzureDocReader()` without arguments still reads `get_default_effective_settings()`. The registered path never does this — `read_documents` (azure.py:316-326) always injects endpoint/key/model from the frozen `EffectiveSettings`. Pre-existing signature, unchanged by this diff; noted because ADR-037 prefers injection-only adapters.
**Fix**: None required this change. Candidate cleanup when the class is next touched: drop the default-args branch.

### [INFO] Gitleaks 72 CRITICAL hits — false positives (no action)
**Source**: [scanner: gitleaks generic-api-key], disproven by content inspection
**Location**: `experiments/5b-persistent-mps-reranker-worker-2026-08-20/output*/preflight/*.json`
**Evidence**: Flagged lines are SHA-256 integrity hashes of HuggingFace model files (`"config.json": "380e02c9…"`, `"model.safetensors": "821d1aa6…"`) recorded by a benchmark preflight. 64-char hex strings trip the entropy rule. The files are tracked in git and their fingerprints are already curated in the committed `.gitleaksignore` (74 preflight entries). No credential material exists in these files.

### [INFO] semgrep 2 MEDIUM logger hits — pre-existing, outside scope (no action)
**Location**: `src/rag_mcp/core/retrieval/_model_config.py` (not modified by this change). The flagged messages log pad-token config values, not credentials.

## Checklist Verdicts (PASS evidence, one line each)

1. **Secrets in logs** — PASS: orchestrator warnings interpolate SDK exception strings (status + service message; the key travels in the `Ocp-Apim-Subscription-Key` header and never appears in `str(exc)`); `config/__init__.py:280-291` logs the NAMES of missing env vars, never values; `capabilities.py:59-64` names the missing dependency only; `azure.py:333-336` logs filename + chunk count only.
2. **Secrets in error propagation** — PASS: KeyError/ValueError list registered backend names; ImportError names the module and install instruction. No credential-bearing settings field is interpolated into any raised message.
3. **Credential handling** — PASS: `azure.py:316-326` reads endpoint/key/model solely from the injected frozen `EffectiveSettings`; nothing mutates them; `BackendRead` is a NamedTuple.
4. **Input validation** — PASS: `file_path` crosses no new trust boundary (same operator-configured ingest path the old code passed to the same readers); the azure suffix gate (`registry.py:150-157`) narrows reach to `.pdf/.docx/.doc`.
5. **Registry integrity** — PASS: `register()` is called only from code at the module bottom (`registry.py:150,151`); user-controlled `DOCUMENT_BACKEND` reaches only read paths (`get`/`describe`/`verify_available`), which raise KeyError on unknown names BEFORE any `importlib` call; import strings are code-declared, never configuration-derived.
6. **Replay/state races** — PASS: retry loop holds no state between attempts; per-file scope; `_cache` maps name→callable (code identity); `BackendRead` immutable.
7. **DoS surface** — PASS: bounded budget (2 attempts + 1 fallback, then propagate); see LOW latency note above.
8. **Dependency chain** — PASS: `uv.lock` unmodified in the working tree (no new dependencies); azure stays optional behind `require_azure_installed`; `uv run lint-imports` reports 8 kept, 0 broken (incl. `config-is-leaf`, `integrations-are-leaves`).
9. **Regression guard** — PASS: terminal exception surface is unchanged — both-fail case propagates to `pipeline.py:302` per-source catch (`error=str(exc)`, ingest continues) and MCP handlers return `{"status": "error", ...}` per invariant #1; unknown backend names moved from config-tuple rejection to a STRICTER compose-startup ValueError that lists registered names and fail-fasts bad import strings (`capabilities.py:69-89`, called at `compose.py:370`).
10. **OWASP quick pass** — PASS: A01/A07 no auth surface change; A02 no crypto; A03 no new sinks (argv-free, no SQL, no shell); A04 strengthened (startup validation of dispatch target); A05 `.env.example` diff is comments only; A06 unchanged deps (chromadb pre-existing, Decision 1); A08 registry write paths unreachable from untrusted input; A09 logs reviewed clean; A10 the Azure endpoint is operator-configured and never user input — no SSRF surface.

**Ruff (flake8-bandit S rules enabled, `pyproject.toml:349-376`)**: `uv run ruff check src tests` — All checks passed. Zero S-rule hits in the changed files.

**Test honesty**: `tests/test_document_backends.py` (35 tests) asserts real behaviour — e.g. `test_runtime_failure_retries_then_single_local_fallback` patches both readers and asserts `azure.await_count == MAX_RETRIES + 1`, `local.await_count == 1`, structured-flag preservation, and visible diagnostics.

## Verdict Justification

The change surface itself is clean: zero scanner findings across five tools, zero S-rule hits, all ten checklist items pass, import contracts intact, and the 35-test suite pins the retry/fallback/propagation contract. The deterministic floor of BLOCKED rests entirely on two groups outside the change: 72 disproven gitleaks false positives (SHA-256 model hashes, curated in `.gitleaksignore`) and four chromadb advisories that are pre-existing, unpatchable today, and unreachable while chromadb stays embedded (`PersistentClient` only — proven at `chroma.py:113,465`). NEEDS FIXES rather than APPROVED because the chromadb exposure needs a recorded maintainer decision (accept-with-mitigation or upstream tracking); the verdict must not fall to APPROVED until that acceptance is recorded.

**Post-scan update (2026-08-27):** the maintainer acceptance is recorded in Decision 1 (accepted with the embedded-only constraint), satisfying the condition above — the final verdict is APPROVED. Separately, the LOW note about `AzureDocReader`'s default-args fallback was resolved after the scan: the a-refactor step removed the constructor's settings-singleton fallback, so `azure.py` now takes explicit endpoint/key/model only.
