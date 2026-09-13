# Security Assessment: Experiment 25 spend authorisation

## Summary

- **Date**: 2026-09-10
- **Scope**: The seven operator-listed Experiment 25 scripts and tests only
- **Auditor**: a-security
- **Scanner**: File-scoped Aikido SAST over the seven listed paths
- **Scanner verdict before triage**: NEEDS FIXES
- **Final verdict**: NEEDS FIXES
- **Operator constraints**: No broad scans, dependency audits, CVE feeds, or `.env` access
- **Protocol deviations**: The full scanner suite and dependency audit were forbidden. These categories are DEGRADED.

## High Findings

### [HIGH] Retry-blind token guard can exceed the approved ceiling

**Source**: [LLM-judged]

**Evidence**:

- `estimate_gate.py:195-213` counts a batch once, increments once, then calls the inner adapter.
- `build_index.py:203-214` wraps `build_embed_model()` without enforcing a retry limit.
- An offline runtime probe reported `adapter_max_retries 10` for the installed `OpenAILikeEmbedding` default.

**Vulnerability**: SDK retries happen inside the one inner call. The wrapper cannot count each transport attempt.

**Impact**: A transient failure can send the same paid batch up to eleven times. The approved token and currency ceilings can be exceeded.

**Remediation**:

1. Set the paid adapter retry count to zero for this build path.
2. Require a new operator approval before a failed request is retried.
3. Bind the retry policy into the request identity.
4. Add a test that proves the paid adapter has zero automatic retries.

**Status**: UNRESOLVED

### [HIGH] Approval documents are reusable across paid attempts

**Source**: [LLM-judged]

**Evidence**:

- `build_index.py:279` ignores an existing destination marker when `--force` is present.
- `build_index.py:297-313` re-runs the recount and accepts the same valid documents before another build.
- `estimate_gate.py:301-302` only logs that approval remains required.
- `estimate_gate.py:389-427` checks document fields but has no nonce, consumption record, attempt lock, or cumulative ledger.

**Vulnerability**: One valid approval can authorise repeated or concurrent attempts. Each process receives a fresh in-memory ceiling.

**Impact**: Parallel runs, a cleared destination, or retries after a partial failure can multiply authorised spend.

**Remediation**:

1. Add a unique approval identifier and one-attempt policy.
2. Atomically consume the approval before constructing the paid embedder.
3. Use an exclusive attempt record so only one concurrent process proceeds.
4. Require a new approval after any attempted paid request, including failed builds.
5. Add replay and concurrent-start regression tests.

**Status**: UNRESOLVED

## Medium Findings

### [MEDIUM] The recounted corpus is not frozen for ingestion

**Source**: [LLM-judged]

**Evidence**:

- `build_index.py:277` hashes the corpus before the recount.
- `build_index.py:297` recounts the live path.
- `build_index.py:306-313` gates and then ingests the same mutable path.
- `estimate_requests.py:145-196` reads files before the later corpus digest at `estimate_requests.py:260`.

**Vulnerability**: A writer can change files or symlink targets between hashing, recounting, and ingestion.

**Impact**: The paid build can embed content outside the approved identity. The token guard limits logical batches but does not preserve data identity.

**Remediation**:

1. Create a content-addressed, read-only corpus snapshot.
2. Run both recount sides and ingestion against that snapshot.
3. Reject destination paths that overlap the source snapshot.
4. Add a mutation-during-recount regression test.

**Status**: UNRESOLVED

### [MEDIUM] Approval and pricing documents provide integrity without provenance

**Source**: [LLM-judged]

**Evidence**:

- `estimate_gate.py:389-416` accepts a schema string, matching digest, destination, and non-empty `approved_by`.
- `approved_at` is not validated.
- `estimate_gate.py:344-350` accepts any non-empty pricing date and source.
- `build_index.py:96-105` uses standard `json.loads`, which accepts duplicate keys and keeps the last value.

**Vulnerability**: The hash is unkeyed and recomputable. The parser accepts ambiguous duplicate-key documents. Pricing age and source syntax are unrestricted.

**Impact**: A writable document can impersonate approval or present a misleading price basis. The independent token cap reduces the spend impact.

**Remediation**:

1. Reject duplicate JSON keys and unknown security-sensitive fields.
2. Validate strict field types, ISO dates, and an approval expiry.
3. Protect approval provenance with a detached signature or trusted file ownership and permissions.
4. Show the approval identifier and expiry in the pre-spend summary.

**Status**: UNRESOLVED

## Low Finding

### [LOW] The documented standalone baseline command does not force legacy chunking

**Source**: [LLM-judged]

**Evidence**:

- `build_index.py:120-125` correctly assigns empty tokenizer variables for baseline recounts.
- `estimate_requests.py:375` dispatches using the ambient environment.
- `estimate_requests.py:17` and `overnight.sh:29-32` show standalone side commands without side-specific environment values.
- Tests force the correct values at `test_exp25_estimate_requests.py:60-82` and `test_exp25_build_authorisation.py:120-144`.

**Impact**: The packaged Qwen default can make a manual baseline fragment use candidate chunking. The fresh recount then refuses, so this fails safely before spend.

**Remediation**:

1. Make `run_side()` set the side-specific tokenizer variables itself.
2. Add a subprocess test that starts from the packaged defaults.

**Status**: UNRESOLVED

### [LOW] Security-control documentation still says the live gate is inactive

**Source**: [LLM-judged]

**Evidence**:

- `estimate_gate.py:1-17` says the module is an unverified scaffold and is unreachable.
- `estimate_gate.py:282-296` repeats that `_preflight_cost_gate` is not reachable.
- `test_exp25_build_authorisation.py:1-8` says every rebuild refuses unconditionally.
- `build_index.py:306-313` calls the gate and then starts an approved build.

**Impact**: Reviewers can misclassify a live paid path as dead code and miss control regressions.

**Remediation**:

1. Update the module and test descriptions to identify the gate as live.
2. Keep the limitation text that explains which guarantees remain approximate.

**Status**: UNRESOLVED

## Manual Review Answers

### Q1. Reachable embedding requests

No direct bypass was found. Plain invocation only skips the historical marker or refuses. `--force` alone refuses. A destination-marker match skips without a request. The paid path starts only after documents load, fresh recount matches, and the full gate passes at `build_index.py:291-313`.

The approval replay and concurrency finding still permits repeated paid attempts with the same valid authorisation.

### Q2. Recount integrity

Fragment or estimate confusion fails before paid work. Four count fields and candidate identity are compared at `build_index.py:159-179`. The estimator runs from a fixed sibling path with argument-list subprocess calls in a private temporary directory at `build_index.py:128-156`.

The mutable-corpus race remains. Baseline and candidate fragments are also not compared to each other during the fresh recount.

### Q3. Estimator integrity

The socket guard is installed only inside each side subprocess at `estimate_requests.py:63-72` and `estimate_requests.py:216`. Merge mode performs local JSON work only. Baseline recounts correctly use empty tokenizer variables. Candidate recounts use the pinned Qwen identity. Clearing those variables would select the packaged candidate default.

Parity is exact and order-sensitive at `estimate_requests.py:53-60`. Both adapter client getters are replaced before the sync batch call at `estimate_requests.py:247-250`. Tokenizer load failure exits before a fragment is written.

### Q4. Dotenv and `.env`

The three scripts contain no `dotenv` import, `load_dotenv` call, or `.env` file read. They use inherited process environment values. Transitive modules were outside this audit scope.

### Q5. Recount tests

Yes. `_tamper_counts` changes a candidate count, recomputes the estimate digest, and updates the approval digest at `test_exp25_build_authorisation.py:207-225`. The tests at lines 261-291 and 384-408 prove fresh recount refusal and zero embedding calls.

Yes. `_approved_recount_documents` launches the real estimator subprocess for both sides and merge mode at lines 147-205. The approved-build test at lines 313-347 uses those real estimator outputs. Only the final paid embedder and storage are faked.

### Q6. Document attacks

Wrong schemas, digest stripping, digest mismatch, missing pricing, destination mismatch, and forged counts without a matching recount fail closed. Merge mode ignores fragment pricing and inserts explicit CLI pricing at `estimate_requests.py:294-329`.

Duplicate-key ambiguity, approval provenance, expiry, and pricing freshness remain unresolved. A recomputed digest is tamper evidence only when the approval document is trusted.

## Aikido Triage

1. `build_index.py:244` `[scanner: Aikido AIK_py_LFI]`: **False positive**. The sink writes a marker after the destination guard. It does not read or include a file. Mutable-path and symlink races remain covered by the corpus and document findings.
2. `estimate_requests.py:212` `[scanner: Aikido AIK_py_LFI]`: **False positive**. The sink writes an atomic JSON fragment to the local operator-supplied `--out` path. Arbitrary output location is intended for this CLI.
3. `estimate_gate.py:38` `[scanner: Aikido generic-api-key]`: **False positive**. The value is the pinned public Hugging Face tokenizer revision, not a credential.

No Aikido issue was ignored or marked accepted.

## Verification

- File-scoped Aikido: 3 findings, all triaged above.
- Five-file pytest command: **42 passed in 62.06 seconds**.
- `build_index.py --force`: expected refusal, exit 1.
- Plain `build_index.py`: expected historical-marker skip, exit 0.
- `bash -n overnight.sh`: passed.
- Installed adapter probe: OpenAI default retries 2; `OpenAILikeEmbedding.max_retries` 10.
- Dependency and CVE audit: **DEGRADED, operator-forbidden**.
- Peer regression-test delegation: **BLOCKED by subagent depth limit**. No tests were edited.

## Eight-Category Checklist

| Category | Status |
|---|---|
| Secrets | PASS within scope; tokenizer revision is not a secret |
| Input validation | NEEDS FIXES; strict document parsing and date validation missing |
| Authentication and authorisation | NEEDS FIXES; approval replay and provenance gaps |
| Injection | PASS within scope; subprocess arguments are arrays and shell arguments are quoted |
| Data exposure | NEEDS FIXES; mutable corpus can break approved identity |
| Dependency CVEs | DEGRADED; operator-forbidden |
| OWASP Top 10 | NEEDS FIXES; A01 and A04 findings above |
| Cloudflare Workers | N/A; no Worker code in scope |

## Verdict

**NEEDS FIXES**

The normal entry paths fail closed and the recount detects fabricated counts. Automatic retries and reusable approval state can exceed the intended spend authority. The mutable-corpus race can also break the approved data identity.
