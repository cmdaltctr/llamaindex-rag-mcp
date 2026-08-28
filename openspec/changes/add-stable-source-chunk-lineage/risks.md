# Security Assessment: add-stable-source-chunk-lineage

## Summary

- **Date**: 2026-08-28
- **Scope**: Diff from `6cddbab` under `src/` and `tests/`, plus the mandatory dependency audit
- **Threat model**: Single-user local MCP server; LanceDB is default; ChromaDB is optional and embedded
- **Auditor**: a-security
- **Changed-code scanner verdict**: APPROVED
- **Dependency scanner verdict**: BLOCKED
- **Final verdict**: BLOCKED
- **Verdict raised above changed-code floor?**: Yes. The dependency scan found four unpatched ChromaDB CVEs.
- **Verdict lowered below dependency floor?**: No. No user-approved rationale has been recorded.

The lineage implementation has no confirmed exploitable vulnerability in the stated local threat model. The final verdict remains BLOCKED because the deterministic verdict contract does not permit lowering the dependency scanner floor without explicit user approval.

## Deterministic Scan Results

The scanner suite ran against isolated copies of the scoped files. It did not modify the worktree.

- **Tools**: gitleaks 8.30.1, semgrep 1.174.0, osv-scanner 2.5.1, trivy 0.74.0, bandit 1.9.4
- **Semgrep ruleset snapshot**: 2026-08-26, 559 OWASP rules
- **Changed-code scan**: 450 LOW and 1 INFO Bandit observations; no gitleaks or semgrep finding
- **Changed-test triage**: 142 `B101` assertion observations and one `B108` temporary-path fixture observation
- **Live-feed scan**: eight raw reports, representing four unique ChromaDB CVEs
- **Dependency consistency**: `uv --directory <worktree> pip check` passed for 182 installed packages

`B101` reports normal pytest assertions. `B108` is a test-only canonical path fixture. `B112`, `B404`, and `B603` are unchanged or test-only code outside the lineage security surface. They require no change for this OpenSpec work.

## Findings

| ID | Severity | Source | Location | Description | Reachability |
| --- | --- | --- | --- | --- | --- |
| F-01 | CRITICAL | `[scanner: osv-scanner CVE-2026-45829]`, `[scanner: trivy CVE-2026-45829]` | `uv.lock:614-615` | ChromaDB FastAPI server permits pre-authentication remote code execution through a remote model reference. No fixed release exists. | Not reachable. This project does not start the Chroma HTTP server or accept remote model references. |
| F-02 | CRITICAL | `[scanner: osv-scanner CVE-2026-45833]`, `[scanner: trivy CVE-2026-45833]` | `uv.lock:614-615` | ChromaDB server collection updates can reach remote code execution through `trust_remote_code`. No fixed release exists. | Not reachable. The project uses embedded `PersistentClient`, without the affected server permission path. |
| F-03 | HIGH | `[scanner: osv-scanner CVE-2026-45830]`, `[scanner: trivy CVE-2026-45830]` | `uv.lock:614-615` | ChromaDB server collection lookup permits cross-tenant access. No fixed release exists. | Not reachable. The local embedded store has no multi-tenant authentication boundary. |
| F-04 | HIGH | `[scanner: osv-scanner CVE-2026-45831]`, `[scanner: trivy CVE-2026-45831]` | `uv.lock:614-615` | ChromaDB `SimpleRBACAuthorizationProvider` does not enforce resource scope. No fixed release exists. | Not reachable. This project does not configure that provider or run the Chroma server. |
| F-05 | LOW | `[LLM-judged]` | `tests/test_clean_base_tripwire.py:99-128` | Tests prove the clean base and default runtime avoid Chroma, but no source-level test bans future Chroma HTTP/server or RBAC paths. | Current code is safe. A future server import could make F-01 to F-04 reachable without a focused test failing. |

### Required action

1. Add a regression test that rejects Chroma HTTP/server, RBAC, and remote-client paths under `src/rag_mcp/`.
2. Monitor the four advisories and update ChromaDB when a fixed release exists.
3. Keep ChromaDB optional, embedded, and off untrusted networks.
4. Obtain explicit user approval before recording an unreachable-CVE rationale that lowers the scanner floor.

Authoritative advisory evidence:

- <https://github.com/advisories/GHSA-f4j7-r4q5-qw2c>
- <https://github.com/advisories/GHSA-36p7-vc44-83pf>
- <https://github.com/advisories/GHSA-2wm9-hf6c-p5cr>
- <https://github.com/advisories/GHSA-xph7-9rjv-w5fr>

## Threat Checklist

1. **Input validation and filter injection: PASS.** `canonical_source_path` normalises with `expanduser().resolve()` at `source_state.py:190-197`; deletion filters use a fixed `source_id` key at `writer.py:194-196`. LanceDB serialises values with `lit(value).to_sql()` at `lance_filter.py:67-83`.
2. **Tilde expansion and deletion scope: PASS for the stated threat model.** `remove_document` can select any indexed path the local caller names at `writer.py:194-202`. The unchanged MCP tool declares destructive behaviour at `transports/mcp.py:319-332`. There is no lower-privilege remote caller in scope.
3. **Hash manipulation: PASS.** `source_id`, `chunk_id`, and row IDs are deterministic identities at `source_state.py:199-243`. No changed code uses them for authentication or authorisation.
4. **Denial of service and regression: PASS with a known linear cost.** The compatibility guard makes two scoped `count_where` calls at `source_state.py:263-269`. Stale cleanup scans the collection at `replacement.py:124-129`; the base code already used the same full-collection iteration, now with safer `source_id` matching.
5. **Information disclosure: PASS.** The new top-level public fields are limited to the five stable lineage keys at `dense.py:81-91`. `source_attempt` is not one of them. Ordinary results remove the internal row `id` at `retrieval/pipeline.py:177-190`. `file_path` was already public through `source` and metadata.
6. **Error messages: PASS.** The incompatibility error contains the operator-supplied canonical path and row count at `source_state.py:271-276`. It includes no credential, token, content, or digest input beyond existing operational metadata.
7. **Metadata injection: PASS.** `stamp_source_lineage` persists the canonical path at `source_state.py:391-400`, while machine filters use constant keys and SHA-256 values. A filename containing `$and` remains a value, not a filter operator.
8. **OWASP and transport-adjacent behaviour: PASS for changed code.** `git diff 6cddbab -- src/rag_mcp/transports/` is empty. The existing deletion tool remains explicitly destructive and error-wrapped at `transports/mcp.py:319-377`.
9. **Test honesty: PASS.** The new tests contain active assertions and no skip or xfail markers. The only `# noqa` is `ANN001, ARG002` on a test stub at `test_lineage_retrieval.py:74`; it suppresses typing and unused-argument rules, not security rules.

## OWASP Top 10 Coverage

| ID | Category | Status | Evidence |
| --- | --- | --- | --- |
| A01 | Broken Access Control | N/A | Single-user local process; no changed authentication boundary. |
| A02 | Cryptographic Failures | PASS | SHA-256 is used for public identity, not secrecy or credentials. |
| A03 | Injection | PASS | Constant filter keys and type-safe LanceDB literal serialisation. |
| A04 | Insecure Design | PASS | Attempt-specific row IDs preserve write-verify-delete replacement safety. |
| A05 | Security Misconfiguration | PASS | Destructive MCP annotation remains present; no transport change. |
| A06 | Vulnerable Components | BLOCKED | F-01 to F-04 remain unpatched in optional ChromaDB 1.5.9. |
| A07 | Identification and Authentication Failures | N/A | No authentication flow changed. |
| A08 | Software and Data Integrity Failures | PASS | Deterministic identities and pre-mutation schema guard preserve store integrity. |
| A09 | Security Logging and Monitoring Failures | PASS | New errors contain path diagnostics but no secrets or document content. |
| A10 | Server-Side Request Forgery | N/A | Changed paths perform no network fetch from caller-supplied URLs. |

## Cloudflare Workers

N/A. This is a local Python MCP server and contains no Cloudflare Workers path in scope.

## Residual Risks

### Accepted

None. No risk has user approval for acceptance.

### Action required

- F-01 to F-04 stay open until a fixed ChromaDB release is available or the user explicitly approves the documented unreachable-path rationale.
- F-05 needs a regression test before any Chroma server, remote client, or RBAC support is introduced.
- Re-run this assessment if Chroma becomes the default, gains a network listener, or accepts remote model references.

## Verdict Justification

The changed lineage code passes the requested threat checklist. It uses fixed metadata keys, deterministic non-secret digests, canonical local paths, and unchanged failure-safe replacement ordering. The dependency feed reports two CRITICAL and two HIGH ChromaDB findings. Their vulnerable paths are not reachable in the current embedded local deployment, but the scanner floor remains BLOCKED until the user approves that rationale or a fixed dependency is locked.

**VERDICT: BLOCKED**
