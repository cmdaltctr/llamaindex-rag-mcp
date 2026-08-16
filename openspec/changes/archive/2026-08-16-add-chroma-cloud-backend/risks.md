# Security Assessment: Chroma Cloud error redaction

## Summary

- **Date**: 2026-08-15
- **Scope**: `identity.py`, Chroma cloud factory errors, MCP runtime and startup errors, smoke operation and cleanup errors
- **Auditor**: a-security
- **Verdict**: APPROVED
- **Follow-up review**: a second delegate pass closed three gaps (OpenRouter key redaction, smoke tenant/database masking, `_error_detail` settings-failure hardening) — see Follow-up Review below

## Findings

### [RESOLVED] The factory retained the unredacted SDK exception as its cause

**Location**: `src/rag_mcp/core/vectordb/chroma.py:391-406`

**Resolution**: `_construct_cloud_client` now raises the redacted `RuntimeError` with `from None`. Formatted tracebacks suppress the raw SDK exception context. Construction and heartbeat regression tests confirm that the API key, tenant, database, and every prefix of six or more characters remain absent.

**Former attack vector**: A construction or heartbeat failure reached code that logged traceback information, such as `logger.exception` or `exc_info=True`.

**Current impact**: No reviewed output path exposes the configured values. MCP envelopes, MCP warning logs, startup stderr, smoke operation logs, cleanup logs, and formatted factory tracebacks are redacted.

**Applied mitigation**:

1. Redact the API key, tenant, and database before constructing the wrapper error.
2. Raise the wrapper with `from None` to suppress the sensitive exception context.
3. Test `traceback.format_exception` for construction and heartbeat failures.
4. Assert that full values and every prefix of six or more characters are absent.

## Resolved Checks

- `redact_secret` removes complete values of any length.
- It removes every configured prefix of six or more characters, longest first.
- The cloud factory redacts API key, tenant, and database from the wrapper message.
- MCP warning logs and client error envelopes use the shared three-value redactor.
- MCP startup stderr uses the redacted error helper.
- Smoke operation and cleanup handlers redact all three configured values.
- Factory construction and heartbeat wrapper tests cover tenant and database prefixes.

## Dependency CVE Audit

`uv pip check`: 200 packages checked. All installed packages are compatible. No CVE identifier or actionable dependency issue surfaced.

## OWASP Top 10 Coverage

| ID | Category | Status |
|---|---|---|
| A01 | Broken Access Control | N/A — targeted error-redaction audit |
| A02 | Cryptographic Failures | ✓ — sensitive exception context is suppressed |
| A03 | Injection | ✓ — no SQL or shell construction in scope |
| A04 | Insecure Design | ✓ — shared redaction policy covers reviewed output boundaries |
| A05 | Security Misconfiguration | ✓ — cloud mode fails closed without local fallback |
| A06 | Vulnerable Components | ✓ — dependency compatibility check passed |
| A07 | Identification and Authentication Failures | N/A — no authentication boundary changed |
| A08 | Software and Data Integrity Failures | N/A — targeted error-redaction audit |
| A09 | Security Logging and Monitoring Failures | ✓ — reviewed error and traceback paths redact configured values |
| A10 | Server-Side Request Forgery | N/A — no user-supplied URL fetch in scope |

## Other Checklist Categories

- **Secrets and credentials**: No production credential pattern found in the reviewed Python source. Test-only fake values were identified.
- **Input validation**: Cloud mode requires an API key and enforces the tenant/database pair.
- **Authentication and authorisation**: N/A for this change.
- **Injection risks**: No string-interpolated SQL found in the reviewed vector-store module.
- **Data exposure**: No remaining finding in the reviewed error paths.
- **Cloudflare Workers**: N/A — this is a Python MCP server.

## Verification

- Final targeted redaction tests and file-size gate: 10 passed.
- File-size ceiling: 1 passed.
- `uv pip check`: passed for 200 packages.
- `git diff --check`: passed.
- Dynamic full-value and prefix probe: wrapper strings removed API key, tenant, and database values.
- Dynamic short-value probe: complete one-to-five-character values were removed.
- Formatted traceback tests: construction and heartbeat paths suppress the raw SDK context and expose no six-plus-character secret prefix.

## Follow-up Review (final delegate, 2026-08-15)

A second delegate pass found three gaps in the initial verdict, all fixed
with regression coverage in this change:

### [RESOLVED] OpenRouter API key outside the redaction contract

`_error_detail` (MCP) and the smoke script redacted Chroma Cloud values
only. An OpenRouter-side failure (the most likely real-world failure for
the Qwen smoke path) would have logged `OPENROUTER_API_KEY` unredacted.

- `_error_detail` now chains `redact_secret(..., settings.openrouter_api_key)`
  after the Chroma redactor.
- The smoke script wraps `build_embed_model` in a protected block and
  redacts the OpenRouter key in its operation and cleanup handlers.
- Regression tests: `test_ingest_error_envelope_redacts_openrouter_key`
  (MCP), `test_operation_failure_log_redacts_openrouter_key` and
  `test_embed_construction_failure_redacts_openrouter_key` (smoke).

### [RESOLVED] Smoke success log printed tenant and database verbatim

The `Storage mode: cloud (tenant=%r database=%r)` line echoed the
configured identifiers, contradicting the "no reviewed output path exposes
configured values" claim. It now prints `set`/`unset` presence only.
Regression: `test_success_log_masks_tenant_and_database`.

### [RESOLVED] `_error_detail` could raise from a non-`ValueError` settings failure

`Settings()` construction can raise `yaml.YAMLError` or `OSError`, which
the previous `except ValueError` did not catch — the redaction helper could
raise out of a tool handler (gotcha #1). It now catches `Exception` and
returns a placeholder, never unredacted detail.

## Verdict Justification

**APPROVED**. The cloud factory suppresses the raw SDK exception context. Reviewed formatted tracebacks, MCP paths, and smoke logs redact the full API key, tenant, database, OpenRouter API key, and every configured prefix of six or more characters. The three follow-up findings are resolved with dedicated regression tests. No actionable defect remains in scope.
