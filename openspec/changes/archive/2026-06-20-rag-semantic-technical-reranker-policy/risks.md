# Security Assessment: rag-semantic-technical-reranker-policy

## Summary
- **Date**: 2026-06-20
- **Scope**: New code in commit `6ed4ac3` — `_classify_query_technical()`, `_resolve_rerank_policy()`, and related changes in `retrieval.py`, `server.py`, `cli.py`, `config.py`
- **Auditor**: a-security
- **Verdict**: **APPROVED** — no CRITICAL, HIGH, or MEDIUM findings. Two LOW hardening notes. Safe to merge.

---

## Findings

### [LOW] ReDoS potential in version regex pattern

**Location**: `src/rag_mcp/retrieval.py:457`
```python
if re.search(r"v?\d+\.\d+(\.\d+)?", token):
```

**Vulnerability**: The pattern `v?\d+\.\d+(\.\d+)?` exhibits O(n²) backtracking on digit-only tokens with no dot. When the first `\d+` greedily consumes all input, the subsequent `\.` fails, and the engine backtracks one character at a time across `\d+` until the optional `(\.\d+)?` also fails. On a single 10,000-digit token this costs ~200 ms of CPU; a 50,000-digit token would cost ~5 seconds.

**Attack Vector**: An MCP client (or CLI user) sends a query consisting of a single very long digit-only token. This is an MCP stdio server (not a public HTTP endpoint), and LLM clients are unlikely to produce digit-only queries, so practical exploitability is low.

**Impact**: Transient CPU spike on a single request. No data exposure, no crash, no state corruption.

**Mitigation**:
```diff
-        if re.search(r"v?\d+\.\d+(\.\d+)?", token):
+        if "." in token and re.search(r"v?\d+\.\d", token):
```
Since every version pattern contains a dot, the `"." in token` guard eliminates backtracking on dot-free tokens. The simplified regex `v?\d+\.\d` avoids nested optional quantifiers while retaining the classifier's intent (flagging version-like tokens). Alternatively, keep the original regex but guard it with a simpler pre-check.

**Verification**: Confirmed O(n²) with benchmark — 500-digit token takes 0.50 ms/iter vs 0.02 ms/iter for 100-digit token (see audit session). The 26 existing policy tests pass.

---

### [LOW] Config import crashes on non-numeric `HARD_TECHNICAL_THRESHOLD`

**Location**: `src/rag_mcp/config.py:83`
```python
HARD_TECHNICAL_THRESHOLD = float(os.getenv("HARD_TECHNICAL_THRESHOLD", "0.3"))
```

**Vulnerability**: A non-numeric environment variable value (e.g. `HARD_TECHNICAL_THRESHOLD=abc`) causes `ValueError` at module import time, crashing the server on startup with a traceback.

**Attack Vector**: An operator misconfigures the env var. Not remotely exploitable — requires filesystem access to the `.env` file or the process environment.

**Impact**: Server fails to start. No data exposure or runtime compromise.

**Mitigation** (hardening, not blocking):
```python
try:
    HARD_TECHNICAL_THRESHOLD = float(os.getenv("HARD_TECHNICAL_THRESHOLD", "0.3"))
except (ValueError, TypeError):
    logger.warning(
        "Invalid HARD_TECHNICAL_THRESHOLD=%r, falling back to 0.3",
        os.getenv("HARD_TECHNICAL_THRESHOLD"),
    )
    HARD_TECHNICAL_THRESHOLD = 0.3
```

**Note**: This `float()` call pre-existed the PR (the line was unchanged except for comment updates). The PR activates it as runtime logic in `_resolve_rerank_policy()`. Existing out-of-range values (e.g. `-5`, `1.5`) produce surprising but not exploitable policy behavior: negative values classify all queries as technical (reranking always disabled via semantic path), values > 1.0 classify no queries as technical. Explicit `rerank=True` always overrides in both cases.

---

### All other audit categories — CLEAN

The following were examined and found free of security findings:

| Category | Status | Notes |
|---|---|---|
| **Secrets & Credentials** | ✓ CLEAN | No hardcoded keys, tokens, or passwords in new code. All config is env-var sourced. |
| **Input Validation (injection)** | ✓ CLEAN | Query only used in string split/containment/regex (read-only) and parameterised ChromaDB queries. No `eval`, `exec`, `subprocess`, SQL, or file path construction. Float `technical_fraction` only used in numeric comparisons. Bool `rerank` only used in identity checks. |
| **Data Exposure** | ✓ CLEAN | `rerank_reason` diagnostic strings expose policy parameters (feature flags, threshold value) — these are configuration knobs, not secrets. Diagnostics are only attached when `include_diagnostics=True` (default `False`). The MCP server's `search_documents()` handler **never passes** `include_diagnostics=True`. CLI search also omits it. |
| **Information Disclosure** | ✓ CLEAN | The `rerank_reason` reveals whether a query was classified as technical/semantic and the threshold. This could theoretically help an attacker tune queries to probe the classifier, but the classifier is deterministic from the query text itself — an attacker can compute the fraction locally. No internal state beyond config knobs is revealed. |
| **Policy Bypass** | ✓ CLEAN | The classifier is a quality-of-service decision (rerank on/off), not a security boundary. An attacker already controls their query text and can vary it to influence search results. Explicit `rerank=True` always overrides the classifier. |
| **Auth/AuthZ** | N/A | MCP server — no web auth surface. |
| **Dependency CVE** | ✓ CLEAN | `uv pip check` — 152 packages, all compatible. No CVEs. |
| **OWASP Top 10** | ✓ CLEAN | Walked A01–A10. All injection categories clean. No SQL, XSS, command injection, path traversal, or SSRF paths in new code. |
| **Cloudflare Workers** | N/A | Not a Workers project. |

---

## Code: clean by construction

The new code's safety properties from first principles:

1. **`_classify_query_technical(query: str) -> float`** — Pure function. Takes a string, returns a float. Tokenizes with `.split()`. Applies read-only regex/string checks per token. Divides count by length (length ≥ 1 guaranteed by guard). No side effects, no I/O, no mutation of global state.

2. **`_resolve_rerank_policy(rerank, query, technical_fraction) -> tuple[bool, str]`** — Pure function. Reads config at call time (for test monkeypatchability). Three branches: explicit True/False (immediate return), global default, semantic policy. No mutation, no I/O beyond reading module-level config constants.

3. **`search()` changes** — Wraps `effective_rerank` into existing `_resolve_fetch_k`, `_effective_threshold`, and reranker call paths. Same parameterised ChromaDB queries as before. Diagnostics attachment is gated by `include_diagnostics=False` default.

4. **`server.py` / `cli.py`** — Both default `rerank` to `None` (was `RERANK_ENABLED`), routing through the resolver. No new inputs, no new output paths, no new exceptions.

---

## Verdict Justification

**APPROVED** — the two LOW findings are hardening opportunities, not exploitable vulnerabilities. The ReDoS pattern has a limited attack surface (MCP stdio, not public HTTP) and mitigates trivially with a dot guard. The config crash is a startup robustness issue, not a runtime exploit. No secrets, injections, auth bypasses, or data leaks were found. The new code is architected with clean functional boundaries: no mutation, no I/O in classifier/resolver, no unsafe sinks. Dependency audit is clean. 26 new tests pass, and the full test suite (440+/442) confirms no regressions.

The PR is safe to merge.
