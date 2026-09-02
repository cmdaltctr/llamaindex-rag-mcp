# Security Review: `add-grounded-answer-synthesis-3`

## Summary

- **Date**: 2026-09-02
- **Branch**: `feat/add-grounded-answer-synthesis-3`
- **Scope**: Grounded-answer core, MCP and CLI transports, composition, configuration, and OpenAPI contract.
- **Audit mode**: Read-only. No production or test code was changed.
- **Final verdict**: **BLOCKED** (first round, 2026-09-02) → **REMEDIATION COMPLETE — CONDITIONAL** after the second review round (same day; see the remediation record below). Two user approvals still gate the ship decision.
- **Most important reason**: The new `metadata_filter` boundary reaches a string-built LanceDB SQL predicate. Project policy requires parameterised queries only and classifies any interpolated SQL as CRITICAL.
- **Scanner verdict (deterministic floor)**: **BLOCKED**. The final verdict was not lowered.

## Remediation record (second review round, 2026-09-02)

A second review round (1 CRITICAL, 7 HIGH, 6 MEDIUM) was remediated in full; the first-round findings below were re-verified against the remediated code. Per-finding status:

| Finding | Severity | Status | Evidence |
|---|---|---|---|
| F1 SQL construction policy | CRITICAL | **Remediated to the engine maximum — pending a user policy decision.** Research on the locked lancedb 0.37.1 (Context7 docs.lancedb.com, DeepWiki lancedb/lancedb, live probes): no bind-parameter API exists; expression objects also serialise to SQL internally and cannot address `metadata.<field>` struct paths, so a full expression-tree refactor is impossible without a schema redesign the spec forbids. Landed instead: fail-closed literal verification in `lance_filter.py` — every engine-quoted fragment is checked against a closed form per type and strings are re-decoded through the SQL literal grammar and compared to the original value; unfaithful output is refused with an actionable `ValueError`. This converted two real, previously unknown engine mis-serialisation classes (apostrophe runs; backslash-before-apostrophe — proven to match the wrong row on a real table) from silent wrong-row hazards into clean rejections. Structural bounds: depth 10, clause count 50, `$in`/`$nin` list 100, serialised length 8192. Evidence: `tests/test_lance_filter_security.py` — 48 tests: 26-payload corpus (×2), 300-string seeded fuzz with an independent literal scanner, 200-name field fuzz, five engine round-trips, bounds, and a sabotage test that proves a regressed unparser is refused. Red run before the fix: 23 failures across the suites. | `lance_filter.py:171-206`, `tests/test_lance_filter_security.py` |
| F2 Unbounded requests | HIGH | **Remediated.** Core-entry limits inherited by every transport: query ≤ 4096 chars, `top_k` 1..100, `expand_window` 0..10, `similarity_threshold` finite 0.0..1.0 (NaN/Infinity explicitly rejected). Synthesis hard prompt ceiling 262,144 chars independent of the context window, lowest-ranked-first truncation with an in-prompt notice. Filter structural bounds (above). OpenAPI `AnswerRequest` now declares the same constraints, pinned to the core constants by `test_answer_request_limits_mirror_core`. | `pipeline.py:88-133`, `synthesis.py:56`, `openapi.yaml` AnswerRequest |
| F3 Redaction bypass | MEDIUM | **Remediated** by the error-path restructure: retrieval, generation, and citation failures route through `_safe_error_detail`, which applies the transport's `redact_cloud_secrets`/`redact_secret` helpers before the text enters a result. | `pipeline.py:145-162, 353-354, 427, 457-459` |
| F4 Referential-only `ok` | MEDIUM | **Open — accepted design limit.** The citation guarantee is referential (ordinal → stored lineage), never semantic entailment; the docs state this and task 7.2 records claim-level verification as the follow-up experiment. | `docs/guides/mcp-tools.md` statuses |
| F5 MRTR cache lifecycle | MEDIUM | **Remediated.** Cache re-keyed to a stable per-connection identity (`id(request_context.lifespan_context)`, verified stable across all MRTR rounds) plus `(query, collection)`; the tool body evicts in `finally`; process-wide FIFO bound 32 remains for abandoned flows. Residual: abandoned flows are reclaimed by the bound, not a finaliser; collision semantics (same connection, same query, different args) documented in the module docstring. | `transports/mcp/answer_mrtr.py`, `test_answer_transport_mrtr.py` |
| F6 Event-loop blocking | MEDIUM | **Remediated.** Retrieval runs through `asyncio.to_thread` in both the resolver chain and the core pipeline; a concurrency regression test proves two 0.2 s retrievals complete in < 0.35 s. | `pipeline.py`, `test_answer_core.py` |
| F7 pypdf CVE (ingestion path) | MEDIUM | **Remediated 2026-09-02 (user-directed).** `pypdf>=6.16.1` declared directly in base dependencies (transitive-but-floored, `pylance>=10` precedent) with the CVE named in the comment; lock upgraded 6.15.0 → 6.16.2; floors and PDF-path suites green. | `pyproject.toml`, `uv.lock` |

Second-round findings (all remediated, red-first where feasible): MRTR cache identity and single-search guarantee; resolver/sampling failures now return the structured error contract with `failure_stage`; `ANSWER__ENABLED` gates every completion source (modern, legacy, server) before any sample or model call; client rounds capped at the four-resolver chain with exhaustion mapped to a structured generation failure (settings bound 1..8); optional-provider `ModuleNotFoundError` returns the graceful `None` while credential `ImportError` stays loud; CLI `--json` (success and failure) on stderr with one result schema and stdout asserted empty; CLI `--hybrid` tri-state deferring to the profile and empty collections short-circuiting to `no_evidence`; honest `retrieval_ms`/`generation_ms`/`completion_calls` including client sampling time and real call counts; oversized citation ordinals rejected before `int()` and citation failures retained as generation errors with evidence; OpenAPI `failure_stage` accepts JSON null.

Gate re-verification (2026-09-02, post-remediation): `ruff check` clean; `ruff format` clean; `lint-imports` 8 kept / 0 broken with no new ignores; file-size ceiling green; `openspec validate --all --strict` 50/50; full fast suite green (`2368 passed, 127 skipped`, base manifest re-baselined at 2364) with branch coverage 90% overall.

Local Aikido MCP re-scan: **attempted, blocked, then deferred by user decision** — `~/Library/Caches/aikido-mcp/opengrep_rules` does not exist and no `opengrep_rules.zip` archive is present to extract (the documented workaround does not apply); the MCP exposes no re-fetch action. Remediation (deferred): restart the Aikido MCP host to trigger the rules download, then re-run `aikido_aikido_full_scan` on the changed files. Scanner evidence therefore rests on the first-round gate recorded above plus the adversarial suite added in this round.

### Remaining ship gates (user decision required)

1. **F1 policy exception.** The engine offers no parameterised path; values are engine-quoted, independently verified, and fail closed. Options: (a) approve a documented exception to the parameterised-query invariant for the LanceDB filter adapter; (b) drop `metadata_filter` from the answer path only; (c) schedule a metadata schema redesign as its own change. **Status: RESOLVED IN PRINCIPLE, DEFERRED 2026-09-02 — the user chose option (a); the acceptance proposal `openspec/changes/accept-lancedb-filter-policy-exception/` is drafted and validates strict. Implementation and archiving happen later per user decision.**
2. **Scanner false-positive ratification.** ~~No user-approved rationale exists to lower that floor.~~ **RESOLVED 2026-09-02: the user accepted the triage — the 73 gitleaks records (72 SHA-256 model-file hashes, one process-lock UUID) are approved false positives. The deterministic floor no longer blocks this change.**
3. **Local Aikido re-scan.** ~~Restart the Aikido MCP host to trigger the rules download, then re-run.~~ **DEFERRED by user decision 2026-09-02 — to be fixed and re-run later; not a release gate for this change.**

### Scan gate

The mandatory scan gate ran before manual review.

| Layer | Result |
|---|---|
| Deterministic core | 79 merged findings: 73 gitleaks and 6 Semgrep. No merged finding targeted the reviewed answer files. |
| Live feed | 26 merged OSV/Trivy records. These represent 17 distinct dependency advisories after duplicate reports are collapsed. |
| LLM-judged | One CRITICAL, one HIGH, and four MEDIUM findings in the answering attack surface. |

Scanner versions: gitleaks 8.30.1, Semgrep 1.174.0, osv-scanner 2.5.1, Trivy 0.74.0, Bandit 1.9.4.

`findings.json` contains 105 merged findings: 80 CRITICAL, 11 HIGH, and 14 MEDIUM. Its `verdict_from_scanners` is `BLOCKED`.

Bandit's SARIF formatter failed with an internal `IndexError`. A JSON-format fallback scan completed with 22 findings. None targeted files in this review. `uv pip check` checked 182 packages and found no incompatible installs.

The 73 gitleaks records were triaged as 72 SHA-256 model-file hashes and one process-lock UUID. Git-history scanning found no leak. These are scanner false positives, not accepted security issues. No user-approved rationale exists to lower the deterministic floor.

### Dependency feed triage

| Package | Advisories | Answer-path reachability | Action |
|---|---|---|---|
| ChromaDB 1.5.9 | CVE-2026-45829, CVE-2026-45830, CVE-2026-45831, CVE-2026-45833 | Not reachable. The advisories require a network-exposed Chroma server. This project uses embedded `PersistentClient` or managed Chroma Cloud. | Do not run `chroma serve` from this environment. Track an upstream fix. |
| NLTK 3.10.2 | Ten CVEs reported by OSV | Not reachable. The project does not call the affected pickle, Java wrapper, downloader, corpus, draw, stemmer, or model-artifact APIs. | Upgrade to 3.10.3 when dependency constraints permit. |
| pypdf 6.15.0 | CVE-2026-84309, CVE-2026-84310, CVE-2026-84311 | No answer-path reachability. CVE-2026-84311 is reachable through the separate PDF ingestion path. | Upgrade to pypdf 6.16.1 or later. |

### Eight-category checklist

| Category | Status |
|---|---|
| Secrets and credentials | Scoped scan clean. Core error results can disclose configured secrets through exception text. See F3. |
| Input validation | Failed. Caller-controlled sizes and ranges have no runtime caps. See F2. |
| Authentication and authorisation | N/A for the current local stdio MCP transport. The OpenAPI contract declares global bearer authentication but has no runtime HTTP implementation. |
| Injection | Blocked by project policy. LanceDB filtering produces interpolated SQL text. See F1. |
| Data exposure | Failed. Provider and retrieval exception text bypasses the established redactor. See F3. |
| Dependency CVEs | Answer path has no reachable CVE. CVE-2026-84311 remains reachable in PDF ingestion. |
| OWASP review | LLM01 remains applicable, LLM02 maps to F3, and LLM06 is mitigated by the read-only, non-agentic design. |
| Cloudflare Workers | N/A. This is not a Workers deployment. |

### OWASP Top 10 coverage

| ID | Category | Status |
|---|---|---|
| A01 | Broken Access Control | N/A for local stdio. Future REST runtime must implement the declared bearer boundary. |
| A02 | Cryptographic Failures | N/A to this change. No cryptography was added. |
| A03 | Injection | Failed by policy. See F1. |
| A04 | Insecure Design | Failed for resource bounds and semantic trust labelling. See F2 and F4. |
| A05 | Security Misconfiguration | Partial. Positive values are enforced, but upper bounds and cross-field limits are absent. |
| A06 | Vulnerable Components | Partial. No answer-reachable CVE; pypdf ingestion needs an upgrade. |
| A07 | Identification and Authentication Failures | N/A for local stdio. |
| A08 | Software and Data Integrity Failures | No new package or model-download mechanism was added. |
| A09 | Security Logging and Monitoring Failures | Partial. Outer MCP logging redacts credentials; core-returned errors bypass that control. |
| A10 | SSRF | No caller-supplied URL fetch was added. Provider endpoints are operator configuration. |

## Findings

### F1. CRITICAL: Attacker-controlled metadata filters reach string-built SQL

**Source**: [LLM-judged]

**Location**: `src/rag_mcp/transports/mcp/answer.py:375`, `src/rag_mcp/core/vectordb/lance_filter.py:81`, `src/rag_mcp/core/vectordb/lance_filter.py:138-159`, `src/rag_mcp/core/vectordb/lancedb.py:356-361`

**Vulnerability**: `answer_documents` accepts an attacker-controlled dictionary. The LanceDB adapter converts it into a SQL string and passes that string to `builder.where()`. Values use `lancedb.expr.lit(...).to_sql()`, fields use a strict grammar, and operators come from a fixed set. Those controls prevent the tested quote and identifier attacks. They do not make the query parameterised. This violates the project's mandatory parameterised-query invariant.

**Attack scenario**: A malicious client supplies crafted field names, operators, or values through `metadata_filter`. Current validation rejects unsafe field syntax and engine-quotes values. A future literal-builder regression or newly accepted value type would place attacker-controlled text in the SQL predicate without a binding boundary.

**Impact**: The current implementation has no demonstrated SQL injection payload. The policy treats this construction as CRITICAL because the sink remains SQL text assembled from client input.

**Remediation**: Replace string predicates with bound parameters or a LanceDB expression tree. If that API cannot address struct fields, redesign the metadata schema or reject answer filters on LanceDB until a parameterised path exists.

**Regression test**: Add answer-path tests for quote, comment, union, and identifier payloads. Add a policy tripwire that fails while `translate_where()` returns executable SQL text.

### F2. HIGH: Unbounded request values can retrieve the full collection and create oversized prompts

**Source**: [LLM-judged]

**Location**: `src/rag_mcp/transports/mcp/answer.py:366-375`, `src/rag_mcp/core/retrieval/policy.py:76`, `src/rag_mcp/core/retrieval/pipeline.py:270`, `src/rag_mcp/core/retrieval/pipeline.py:378`, `src/rag_mcp/core/answer/synthesis.py:117-120`, `src/rag_mcp/transports/api/openapi.yaml:632-678`

**Vulnerability**: The MCP boundary has no length, range, or complexity checks for `query`, `top_k`, `similarity_threshold`, `expand_window`, or `metadata_filter`. The answer OpenAPI schema also omits the `top_k >= 1` and `0 <= similarity_threshold <= 1` constraints already present on `SearchRequest`. Retrieval clamps a large `top_k` only to collection size. Synthesis then widens the nominal context budget until all evidence fits within the round count.

**Attack scenario**: A client sends `top_k=1000000000` against a 500,000-chunk collection. `_resolve_fetch_k()` requests 500,000 rows. For 500 million evidence characters, `_widen_for_round_bound()` raises an 8,192-character configuration to a 125,000,000-character per-round budget. A deeply nested filter, huge `$in` list, oversized query, or extreme expansion window adds further CPU and memory pressure.

**Impact**: One read-only tool call can consume large amounts of memory, block retrieval, create oversized model requests, increase cloud-model cost, or terminate the process.

**Remediation**: Validate all boundaries before retrieval. Set hard caps for query length, `top_k`, expansion, filter depth, filter node count, and list size. Reject non-finite thresholds. Keep prompt size below a hard byte or token budget. Return a truncation diagnostic instead of widening past the configured context window.

**Verification**: A direct check returned `fetch_k=500000` and `per_round_budget=125000000` for the scenario above.

### F3. MEDIUM: Core failure results bypass credential redaction

**Source**: [LLM-judged]

**Location**: `src/rag_mcp/core/answer/pipeline.py:190`, `src/rag_mcp/core/answer/pipeline.py:247`, `src/rag_mcp/transports/mcp/__init__.py:67-88`, `src/rag_mcp/transports/cli/answer.py:110`, `src/rag_mcp/transports/cli/answer.py:129`

**Vulnerability**: Retrieval and generation exceptions are caught inside `answer()` and copied verbatim into result fields. The MCP handler therefore returns normally and never passes those strings through `_error_detail()`. The CLI also prints raw exception and result text.

**Attack scenario**: A provider raises an exception containing an OpenRouter key, authenticated URL, response body, or connection details. The MCP result exposes that text to the caller. Logs or CLI output can retain it.

**Impact**: Credential disclosure and internal infrastructure disclosure are possible when a dependency includes sensitive request details in its exception.

**Remediation**: Apply the established redactor to every error before it enters a result. Prefer stable public error codes and generic messages. Keep detailed, redacted diagnostics server-side.

**Verification**: An injected generation exception containing a fake OpenRouter-style secret returned that secret unchanged in `result["error"]`.

### F4. MEDIUM: A valid ordinal marks unsupported model output as `ok`

**Source**: [LLM-judged]

**Location**: `src/rag_mcp/core/answer/prompt.py:22-36`, `src/rag_mcp/core/answer/prompt.py:45-61`, `src/rag_mcp/core/answer/pipeline.py:260-267`

**Vulnerability**: Prompt instructions ask the model to ignore outside knowledge and cite sources. Retrieved text remains untrusted prompt content and is not isolated from instructions. The final `ok` decision checks only that answer text exists and at least one in-range ordinal appears. It does not verify that the cited source supports the claim.

**Attack scenario**: An ingested document instructs the model to output an attacker-chosen claim followed by `[1]`. The parser resolves ordinal 1 to genuine stored lineage. The result receives `status="ok"` even when the claim contradicts or is absent from that evidence. A malicious MCP sampling client can do the same through its reply.

**Impact**: Consumers can mistake referentially valid citations for semantic support. Prompt injection can corrupt answer integrity while preserving the citation shape.

**Remediation**: Rename the status to express the actual guarantee, such as `citations_resolved`, or add claim-to-evidence verification before `ok`. Keep an explicit `untrusted_generated_text` signal. Treat source text as quoted data with strong delimiters and repeat the instruction hierarchy after each source block.

**Verification**: An injected reply containing an unsupported claim plus `[1]` returned `status="ok"` and one citation.

### F5. MEDIUM: Abandoned MRTR resolver flows can leave unbounded cache entries

**Source**: [LLM-judged]

**Location**: `src/rag_mcp/transports/mcp/answer.py:67`, `src/rag_mcp/transports/mcp/answer.py:159-198`, `src/rag_mcp/transports/mcp/answer.py:476-478`

**Vulnerability**: MRTR resolvers populate the process-global `_request_cache` before the tool body runs. Cleanup exists only in the body's `finally`. If sampling fails, the client disconnects, or the continuation is abandoned before body entry, that cleanup cannot execute. Each entry retains rows and a second evidence copy. The key is only `str(request_id)`, with no session or argument binding.

**Attack scenario**: A client starts many modern sampling calls with unique request IDs, receives each sample request, and abandons every continuation. The dictionary grows until process memory is exhausted. Duplicate IDs across concurrent sessions could also return one request's evidence to another if the transport later supports multiple sessions.

**Impact**: Process memory exhaustion. Cross-request evidence confusion is a future multi-session risk.

**Remediation**: Store resolver state in framework request state, not a module global. Otherwise use a session-scoped composite key, bounded TTL/LRU storage, argument fingerprinting, and a resolver lifecycle finaliser that runs when the body never starts.

### F6. MEDIUM: Synchronous retrieval runs on the MCP event loop

**Source**: [LLM-judged]

**Location**: `src/rag_mcp/transports/mcp/answer.py:184`, `src/rag_mcp/core/answer/pipeline.py:183`, `src/rag_mcp/core/answer/retriever.py:99`, `src/rag_mcp/transports/mcp/search.py:94`

**Vulnerability**: Both the MRTR resolver and the uncached answer pipeline call synchronous search directly from async functions. The existing `search_documents` tool uses `asyncio.to_thread()` for this operation.

**Attack scenario**: A costly hybrid, rerank, expansion, or large-filter request blocks the event loop. Sampling continuations and unrelated MCP requests cannot progress until retrieval returns.

**Impact**: One client request amplifies the availability impact in F2 and can stall the MCP server.

**Remediation**: Run retrieval once through `asyncio.to_thread()` at the transport boundary, or provide a native async retrieval entry point. Pass the resulting rows to resolvers and core synthesis.

### F7. MEDIUM: Reachable pypdf denial of service exists outside the answer path

**Source**: [scanner: osv-scanner CVE-2026-84311] [scanner: trivy CVE-2026-84311]

**Location**: `uv.lock:1` (package record; scanner reports lock-file level)

**Vulnerability**: pypdf 6.15.0 has exponential Form XObject traversal during `extract_text()`.

**Attack scenario**: A crafted PDF is ingested through the pypdf backend or an automatic fallback that selects it.

**Impact**: The ingestion worker can hang or exhaust CPU and memory. The answer path consumes already-ingested rows and does not invoke pypdf.

**Remediation**: Upgrade to pypdf 6.16.1 or later. Prefer the other configured PDF readers until upgraded.

## Verified Mitigations

1. **Citation identifiers are system-owned**. `parse_citation_ordinals()` accepts only numeric bracket groups. It drops malformed groups and out-of-range ordinals (`citations.py:24-54`).
2. **Citation lineage comes only from supplied evidence**. `build_citations()` indexes the evidence list and copies stored lineage (`citations.py:72-86`). Model-invented chunk IDs, paths, or source versions never enter citation objects.
3. **The citation guarantee is referential**. It proves that an ordinal maps to supplied evidence. It does not prove semantic entailment. F4 records this limit.
4. **Empty retrieval avoids the model**. The pipeline returns `no_evidence` before provider selection or generation (`pipeline.py:204-214`).
5. **Modern sessions cannot select the legacy seam through normal negotiation**. Protocol versions at or above `2026-07-28` select MRTR (`answer.py:91-102`). `create_message()` is confined to `_legacy_complete()` (`answer.py:105-117`).
6. **Client sampling has bounded outward agency**. The hard-coded chain contains four `Sample` resolvers. Settings can reduce the number of required rounds. The model cannot call tools or mutate storage.
7. **Client replies cannot forge lineage**. A client controls generated text and later refine prompts. Citation construction still resolves only supplied ordinals.
8. **MRTR request-state echoes do not enter prompt construction**. The implementation consumes resolver results only. Deterministic `plan_next_prompt()` owns the query, evidence labels, and replay sequence.
9. **Tool annotations match runtime behaviour**. `read_only_hint=True` and `destructive_hint=False` are accurate (`answer.py:364`). Retrieval and completion have no storage mutation. Model calls still incur compute, network, and possible provider cost, which the tool description declares.
10. **The outer MCP error boundary redacts active Chroma and OpenRouter credentials**. `_error_detail()` is safe when it is reached. F3 identifies the core-returned path that bypasses it.
11. **Current LanceDB filter quoting blocks known payloads**. Field names use a conservative grammar, operators use an allowlist, and values pass through `lancedb.expr.lit()`. F1 remains a policy blocker because the final predicate is SQL text.
12. **Targeted functional tests pass**. `uv run pytest tests/test_answer_core.py tests/test_answer_transport_mcp.py tests/test_answer_compose.py -q` completed with 35 passing tests.

## Residual Risk

- Prompt injection remains inherent because ingested document text shares the model context with instructions. Fixed prompt wording reduces accidental drift. It cannot make untrusted source text authoritative.
- A malicious document or sampling client can steer answer text and cited ordinals. The system protects lineage integrity, not truth or claim support.
- The current result already returns every supplied evidence row, including text and source paths. Prompt-induced echoing does not cross an additional caller-visible confidentiality boundary. Sending evidence to a configured cloud model remains external data egress and must be an explicit operator choice.
- The MCP deployment is local stdio. It assumes the spawning client has collection-level read access. A future network transport needs authentication, collection authorisation, quotas, request-size limits, and per-tenant cache isolation.
- Client completion size is requested through `max_tokens`, but the server does not independently cap returned text. A malicious client can ignore the request and send an oversized reply.
- `parse_citation_ordinals()` converts matched digit strings with `int()`. An extremely long numeric group can raise under Python's integer-string limit. The MCP outer boundary catches it, but request-size controls should reject it earlier.
- `ANSWER__MAX_ROUNDS`, `ANSWER__CONTEXT_WINDOW`, and `ANSWER__MAX_OUTPUT_TOKENS` enforce only positive values (`settings.py:66-69`). Operator misconfiguration can create excessive cost or invalid provider requests. Add upper bounds and a cross-field validator.
- Scanner feed results change over time. Re-run OSV and Trivy before release, especially for ChromaDB, NLTK, and pypdf.

**Verdict: REMEDIATION COMPLETE — CONDITIONAL** (second round, 2026-09-02)

All code-level findings from both review rounds are remediated and verified (see the remediation record; F7's pypdf upgrade landed 2026-09-02 by user direction, and the CLI-wide `--json` stream fix — `search`, `list`, `list-collections`, `delete`, `benchmark`, `profile`, and the shared Ollama helper — landed the same day, closing the residual noted in the second round). Ship remains gated on one user decision recorded above: the F1 policy exception (LanceDB offers no parameterised filter API in 0.37.x — quoting is engine-owned, verified fail-closed). F4 (referential citations) remains open as a documented residual — experiment 20 (`experiments/20-citation-faithfulness-2026-09-02/`, PLANNED) pre-registers the gates for the claim-verification decision.
