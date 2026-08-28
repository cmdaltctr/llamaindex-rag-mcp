# Security Audit: `validate-embedding-write-contract` (commit `ebc934b`)

## Summary

- **Date**: 2026-08-28
- **Scope**: commit range `1bbeaf8..ebc934b` (single commit `ebc934b`, "feat(vectordb): enforce fail-closed embedding write contract"), 25 files, +1383/−142
- **Auditor**: a-security (read-only audit; no source, tests, or builds executed)
- **Scanner verdict (deterministic floor)**: clean on changed code (semgrep OWASP ruleset 0 findings; gitleaks 1 hit on an untracked local `.env`; `uv pip check` clean)
- **Final verdict**: APPROVED
- **Verdict raised above floor?**: no

## Methodology

1. Verified worktree: `git rev-parse --show-toplevel` and branch `feat/validate-embedding-write-contract` match the intended checkout; working tree clean.
2. Read the full diff (`git diff 1bbeaf8..ebc934b`) and the current source of every changed `src/` module.
3. Ran the deterministic scanners in **stdout-only mode** because this audit is READ-ONLY and must write exactly one file. The skill's `run-scan.sh` writes `<target>/.security/*.sarif`, so it was not used; this is a recorded deviation, not a silent skip. Substitutes:
   - `check-tools.sh`: all five scanners present (gitleaks 8.30.1, semgrep 1.174.0, osv-scanner 2.5.1, trivy 0.74.0, bandit 1.9.4).
   - `gitleaks detect --no-git` over the worktree (secrets layer).
   - `semgrep` with the skill's vendored OWASP Top-10 ruleset over `src/rag_mcp/core/vectordb/` plus the two changed experiment harness files (input-validation/injection layer).
   - `osv-scanner --lockfile uv.lock` (live CVE feed) and `uv pip check` (dependency consistency).
   - Aikido MCP in-memory scan on the three new modules: **secrets layer clean; SAST engine DEGRADED** (local Opengrep rules cache missing, environment issue). Semgrep + gitleaks cover that layer.
4. Manual threat-model triage on top of the scanner output, per the checklist below, with file:line evidence.

## Deterministic Scan Results

| Tool | Scope | Result |
| --- | --- | --- |
| gitleaks 8.30.1 | whole worktree, `--no-git` | 1 finding: `huggingface-access-token` in `.env:30`. **`.env` is untracked** (`git ls-files .env` empty; `.gitignore:13`; `git check-ignore` confirms). Local dev file, out of scope. |
| semgrep 1.174.0 (OWASP ruleset) | `src/rag_mcp/core/vectordb/`, exp 14 builder, `experiments/_lib/storage.py` | **0 findings** |
| osv-scanner 2.5.1 | `uv.lock` (253 packages) | chromadb 1.5.9: 4 advisories (2 Critical, 2 High), **no fixed version available**. Pre-existing; see OUT-OF-SCOPE. |
| `uv pip check` | installed environment | clean, 182 packages compatible |
| Aikido MCP | new modules (validation, chroma_cloud, lance_node_schema) | secrets: clean; SAST: DEGRADED (tool-side rules cache missing) |

No new dependency was introduced: `pyproject.toml` and `uv.lock` are untouched by the range; `validation.py` uses stdlib plus existing `llama_index` imports, `chroma_cloud.py` lazy-imports the existing `chromadb`, `lance_node_schema.py` imports existing `pyarrow` and local modules.

## Checklist Review (evidence)

### 1. Input validation at new boundaries — PASS

- `upsert_precomputed` validates first in both adapters: `chroma.py:234` (before `get_or_create_collection` at 237, `collection.upsert` at 244, `bump_generation` at 251) and `lancedb.py:276` (before `_check_or_stamp_identity`, `create_table`, `merge_insert`, `_flush_after_write`/`bump_generation` at 320-321).
- `embedding_identity` is keyword-only and required (`base.py:65-67`); omitting it raises `TypeError` before any store call — regression-tested at `tests/test_embedding_write_contract.py:306` (`test_missing_explicit_diagnostic_is_rejected`).
- `write_nodes` validates via `materialise_and_validate_node_embeddings` (`chroma.py:181-189`, `lancedb.py:217-225`) before `get_or_create_collection`, identity stamping, schema evolution, or index construction.
- Production callers are only `core/ingestion/writer.py:77` and `core/ingestion/replacement.py:234`; `writer.py:56` (`if not nodes: return 0`) means empty ingestion batches never reach the (now raising) empty-batch rejection. No bypass path found: every mutation in both adapters sits downstream of `validate_embedding_batch`.
- Read-only dimension probe: chroma `_get_collection` returns `None` when absent (it backs `collection_exists`, `chroma.py:152`) — `get_collection_dimension` creates no state.

### 2. Secrets and PII — PASS

- `EmbeddingIdentity` (`identity.py:30-44`) carries `provider`, `model`, `index_identity` strings only — no credentials. Validator diagnostics (`validation.py:44-47`) interpolate exactly those plus collection name and row ids.
- `chroma_cloud.py` extraction preserved the redaction wrapper verbatim: the moved `construct_cloud_client` body (diff-verified identical to the deleted `chroma.py::_construct_cloud_client`) wraps every exception message in `redact_cloud_secrets`, and `redact_secret` (`identity.py:79-98`) strips the full value and every prefix of six or more characters.
- gitleaks over the worktree: only the untracked local `.env`. Nothing in the committed range.

### 3. Fail-closed correctness — PASS (two LOW residuals, see Findings)

- Every adapter mutation follows validation; generation counters bump only after successful writes (`chroma.py` upsert tail; `lancedb.py:249,321`).
- Experiment 14 (`experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py:444-459`): `validate_embedding_batch` runs strictly before `delete_collection`/`create_collection`/`upsert_precomputed`. A malformed embedder batch can no longer destroy an existing index. Regression-tested at `tests/test_experiment_14_harness.py:501` (`test_malformed_embedder_batch_fails_before_destructive_rebuild`).
- Atomicity: `test_invalid_batch_rejected_before_collection_creation` (line 318), `test_invalid_batch_rejected_leaves_existing_collection_unchanged` (333), `test_atomicity_mixed_valid_invalid_persists_nothing` (371), plus ingestion/replacement equivalents (393-526).
- The removed Lance empty-batch no-op guard (`lancedb.py` old `if not ids or not embeddings: return`) is superseded by the validator's empty-batch rejection — intentional per the method docstring (an empty upsert would lock a zero-dimension vector column).

### 4. Injection — PASS

- All identifiers and collection names enter error strings through `!r` (`validation.py:51,57,67,70,76,82,97`), so control characters are escaped and cannot inject raw newlines into logs. Format strings are static f-string literals; no caller-controlled format text. The lancedb missing-keys error (`lancedb.py:307-310`) uses `sorted(missing)` in an f-string.

### 5. Dependency changes — PASS

- No new imports add a dependency (see Deterministic Scan Results). `uv pip check` clean.

### 6. DoS — PASS (one INFO note)

- The validator is a single O(n·d) pass with per-vector early break; nothing egregious.

## Findings

> Source labels: `[scanner: tool rule_id]` = machine-proven; `[LLM-judged]` = reasoning-layer.

### [LOW] Dimension-discovery TOCTOU between probe and write
**Source**: [LLM-judged]
**Location**: `src/rag_mcp/core/vectordb/chroma.py:164-171,234-236`; `src/rag_mcp/core/vectordb/lancedb.py:193-199,276-278`
**Evidence**: `get_collection_dimension` is read, then the batch validates, then the SDK mutates. A concurrent writer creating the collection with a different dimension between probe and write wins the race.
**Impact**: Minimal. Both backends enforce dimension at write time independently (LanceDB fixed-size-list schema; Chroma per-collection dimension), and the identity guard is a second check. This is a defence-in-depth residual, not a bypass.
**Recommended fix**: none required; optionally re-read the dimension inside a store-level write lock if cross-process writers ever become a supported deployment.

### [LOW] Non-embedding batch fields unvalidated; late SDK failure can leave a freshly created empty collection
**Source**: [LLM-judged]
**Location**: `src/rag_mcp/core/vectordb/chroma.py:234-251`; `src/rag_mcp/core/vectordb/lancedb.py:276-321`
**Evidence**: `validate_embedding_batch` checks ids/embeddings only. A batch with mismatched `documents` or `metadatas` lengths passes validation, then `get_or_create_collection`/`create_table` runs, then the SDK (Chroma `collection.upsert`) or `rows_to_arrow` (Lance) fails on the length mismatch — leaving behind a created, identity-stamped, empty collection/table.
**Impact**: No data corruption; a later valid write succeeds into the empty collection. Availability/cleanliness issue only.
**Recommended fix**: extend the validator (or a thin wrapper at the `upsert_precomputed` boundary) to assert `len(documents) == len(metadatas) == len(ids)` before any store call.

### [INFO] Failure diagnostics embed the complete identifier list
**Source**: [LLM-judged]
**Location**: `src/rag_mcp/core/vectordb/validation.py:51,57,97`
**Evidence**: error strings interpolate `list(identifiers)!r` for the whole batch. On a very large failed batch the exception message (and any log line carrying it) becomes very large.
**Impact**: log/memory bloat on hostile or very large batches; local-first tool, operator-facing.
**Recommended fix**: cap the identifier sample (for example first 10 plus count) in the message.

## OUT-OF-SCOPE (pre-existing or unrelated; not introduced by `ebc934b`)

- **chromadb 1.5.9 dependency CVEs** [scanner: osv-scanner]: PYSEC-2026-311 (9.3), GHSA-36p7-vc44-83pf (9.4), GHSA-2wm9-hf6c-p5cr (8.8), GHSA-xph7-9rjv-w5fr (8.8); **no fixed version published upstream**. The lockfile is unchanged by this commit, so this is a pre-existing carry-over already dispositioned in the prior audit of this change. Continue monitoring; reassess reachability when a fix ships. (Default deployment is embedded local mode; cloud mode is opt-in per ADR-024.)
- **Local `.env` contains a HuggingFace token** [scanner: gitleaks `huggingface-access-token`]: untracked and gitignored by design. Keep worktree archives and dotfile copies out of shared artefacts.
- **Aikido SAST engine unavailable** (missing local Opengrep rules cache): environment limitation, recorded as DEGRADED; covered by semgrep + gitleaks here.
- **Archived documentation drift**: prose references to `upsert_precomputed` in `openspec/changes/archive/2026-08-17-add-lancedb-vectordb-backend/`, `docs/adr/046`, and `docs/tdr/` predate the new keyword. Documentation only; no executable code outside `experiments/` and `src/` calls the method, and every live caller (8 files) passes `embedding_identity`.

## OWASP Coverage (condensed)

| ID | Status | Note |
| --- | --- | --- |
| A01/A03/A04 | ✓ | validation boundary now enforced before mutation; no injection (repr-interpolated diagnostics) |
| A02 | N/A | no new cryptography in range |
| A05 | ✓ | no new configuration surface |
| A06 | ⚠ out-of-scope | chromadb advisories, pre-existing, see above |
| A07/A09 | N/A | no auth/session surface in range; logging adds no PII |
| A08 | ✓ | dependency set unchanged; contract is an integrity control itself |
| A10 | N/A | no new outbound fetch; cloud client is opt-in and redacted |
| Workers | N/A | not a Cloudflare Workers project |

## Verdict Justification

All four adapter write paths and the Experiment 14 rebuild validate the complete batch before any persistent mutation, the required-keyword signature makes silent bypass impossible, redaction survived the `chroma_cloud.py` extraction intact, and no secret or dependency entered the range. The deterministic scanners returned nothing against the changed code. Remaining findings are two LOW defence-in-depth residuals and one INFO hardening note; none blocks ship.

VERDICT: APPROVED
