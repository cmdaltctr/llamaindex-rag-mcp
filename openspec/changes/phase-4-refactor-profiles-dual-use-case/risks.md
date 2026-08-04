# Security & Code Review: phase-4-refactor-profiles-dual-use-case (v2)

## Summary
- **Date**: 2026-08-04
- **Scope**: PR #16 (`feat/phase-4-refactor-profiles-dual-use-case-v2`, 33b2c64) — profiles system: `core/profiles/resolver.py`, `core/profiles/contract.py`, `config/__init__.py` (`_ProfileYamlSettingsSource`, `_load_profile_bundle`), `core/retrieval/policy.py` + `pipeline.py`, `core/ingestion/pipeline.py` + `chunker.py`, `server.py` (`change_collection_profile`, resolver wiring), `cli.py` (`set-profile`, ingest/search transports), `config/profiles/*.yaml`, `tests/test_profiles.py`. Full review: security, spec compliance, architecture, test quality, code quality.
- **Auditor**: a-security
- **Verdict**: NEEDS CHANGES

## Prior-Finding Verification (PR #15 review)

| # | Prior finding | Status |
|---|---|---|
| 1 | HIGH: `change_collection_profile` could raise from MCP handler | **FIXED** — both preview and confirm paths wrap in `except Exception` (`server.py:376-390`); invalid profile short-circuits before any store access |
| 2 | MEDIUM: invalid profile tags silently swallowed | **FIXED** — `ingest_documents` (`server.py:64-67`) and `search_documents` (`server.py:129-136`) return `{"status": "error", ...}` on resolver `ValueError` |
| 3 | MEDIUM: `metadata_taxonomy_mode` dead lever | **NOT FIXED** — see Finding 1 below |
| 4 | MEDIUM: `apply_profile_change` creates missing collections | **FIXED** — `collection_exists` guard (`contract.py:210-214`); regression test `test_apply_profile_change_rejects_nonexistent_collection` present |
| 5 | MEDIUM: operation-time bundle validation gap | **PARTIALLY FIXED** — `yaml.YAMLError` now caught (`config/__init__.py:127-131`); the remaining gaps are Finding 2 below |

## Findings

### [MEDIUM] Finding 1 (prior #3, unfixed): `metadata_taxonomy_mode` is resolved, documented, and diffed — but has zero consumers

**Location**: `src/rag_mcp/core/ingestion/pipeline.py:44-48,151-155`; `src/rag_mcp/core/metadata/extractor.py:172`; `src/rag_mcp/core/metadata/settings.py:39`
**Defect**: `EffectiveSettings.metadata_taxonomy_mode` (`category` vs `file_type`) is resolved per operation, compared in the safety contract, exposed as a Settings field, and claimed by the `ingest_path_async` docstring to "supply the defaults for … metadata classification". Grep confirms no consumer outside resolver/contract/settings: `extract_metadata_async(file_text, file_name)` has no taxonomy parameter and the ingest pipeline never passes the lever anywhere. The codebase profile's headline `file_type` taxonomy is a no-op — ingests into a codebase-tagged collection classify with the category taxonomy regardless of profile. Task 4.4 ("Thread resolved levers … chunking fallback + taxonomy mode") is checked off with the taxonomy half unimplemented, and the `ingest_path_async` docstring actively misdescribes the code.
**Impact**: Spec non-compliance — the spec's Tier 2 lever list ("metadata taxonomy mode") and the codebase bundle's `METADATA_TAXONOMY_MODE: file_type` are inert. The safety contract shows users a `metadata_taxonomy_mode: category → file_type` "impact" that never takes effect, which is worse than absent: it promises a behaviour change that does not happen.
**Mitigation**: Either (a) thread `effective_settings.metadata_taxonomy_mode` from `ingest_path_async` into the metadata extraction stage and implement the `file_type` classification path, or (b) formally descope the lever: remove it from `EffectiveSettings`, the bundles, the safety-contract diff, the spec lever list, and the docstring. Silence is not an option — the current state is a checked-off task over unimplemented behaviour.

---

### [MEDIUM] Finding 2 (prior #5, residual): operation-time bundle validation still fails open and never names the offending key

**Location**: `src/rag_mcp/config/__init__.py:103-143`; `src/rag_mcp/core/profiles/resolver.py:86-131,317-340`
**Defect**: Three residual gaps against the spec scenario "Invalid bundle rejected … the system MUST fail at resolution time with a clear validation error naming the offending key":
1. **Malformed YAML now fails open.** The `yaml.YAMLError` catch returns `{}`, and `_load_effective` degrades to field defaults with a log warning. A syntax-corrupted bundle silently runs operations under defaults — the opposite of the spec's MUST-fail requirement. (The catch is correct for gotcha #1; the degradation is the problem.)
2. **Bare coercion.** `int(os.environ.get("TOP_K", bundle.get("TOP_K", 10)))` raises `ValueError: invalid literal for int() with base 10: 'abc'` — no bundle name, no key name. Surfaced to MCP clients as an opaque validation error.
3. **No model validation at operation time.** The spec requires bundles to be "validated against the same Pydantic settings models as global configuration". Only the startup `RAG_PROFILE` bundle passes through `Settings`; per-collection bundles loaded by `ProfileResolver._load_effective` are raw-dict coerced, and unknown keys are silently ignored.

**Impact**: A mistyped bundle edit (the intended user-facing configuration surface for this phase) either silently degrades retrieval behaviour or crashes resolution with an error that gives the user no path to the offending key.
**Mitigation**: Validate the loaded bundle dict against the `Settings` model inside `_load_profile_bundle` (e.g. `Settings.model_validate` over the mapped keys) and raise `ValueError(f"profile bundle {name!r}: field {key}: {err}")` on failure; let the resolver propagate that `ValueError` so the MCP transports return a named, actionable error instead of degrading.

---

### [MEDIUM] Finding 3 (new): CLI and watcher transports bypass profile resolution — every Tier 2 lever resolves wrong for non-default collections

**Location**: `src/rag_mcp/cli.py:657-664` (search), `src/rag_mcp/cli.py:568,577` (ingest), `src/rag_mcp/watcher.py:301-305`
**Defect**: Only the MCP transport constructs `EffectiveSettings`. `cli.py search` calls `do_search(...)` with no `effective_settings` and hardcodes `hybrid=False` via the typer flag default; `cli.py ingest` and the watcher call `ingest_path_async` with no `effective_settings`. Against a `codebase`-tagged collection, the CLI therefore applies: `top_k=10` (not 20), reranker ON (not off — see below), hybrid OFF (not on), and never applies the `code` chunking fallback. Every Tier 2 lever inverts for the codebase use case on the CLI path. The spec requires Tier 2 levers to be "resolved per operation by a `ProfileResolver` and passed as parameters to `search()` and `ingest_path_async()`" without a transport carve-out, and the content-type dispatch scenarios ("ingested into a `codebase`-profile collection") are transport-agnostic.
**Compounding factor**: the default `RAG_PROFILE=documents` bundle now sits above field defaults in the startup precedence chain, so `settings.rerank_enabled` resolves **True** globally (pinned by the changed expectation in `tests/test_settings_resolver.py:53-57`). Pre-Phase-4, CLI search defaulted to reranker OFF (Experiment 10). CLI search against a codebase-tagged collection now reranks — the exact behaviour Experiment 10 showed degrades technical workloads by 19–27%.
**Impact**: The dual-use-case feature works only over MCP. CLI users (and the watcher's auto-ingest) get documents-profile behaviour on codebase collections: slower queries, worse technical retrieval, wrong chunking fallback, wrong taxonomy (Finding 1) — while the collection tag suggests otherwise.
**Mitigation**: Resolve `EffectiveSettings` in the CLI search/ingest commands and the watcher dispatch (mirroring `server.py`), and change the CLI `--hybrid` flag default from `False` to `None` so the profile/global default can apply. If CLI profile support is deliberately out of scope, the spec and `docs/guides/configuration.md` must say so explicitly, and the CLI should warn when operating on a non-default-tagged collection.

---

### [LOW] Finding 4: dead code and uncached file re-read in `_resolve_hybrid_default`

**Location**: `src/rag_mcp/core/profiles/resolver.py:266-286`
`bundle = _load_profile_bundle("hybrid")` (line 268) is assigned and never used — the comment explains why, but the call itself is dead work. The method then re-reads and re-parses `hybrid.yaml` from disk on every untagged resolve under `RAG_PROFILE=hybrid`, bypassing the resolver's bundle cache. Remove the dead call and cache the resolved default.

### [LOW] Finding 5: signature-only tests for content-type dispatch (carried over, unfixed)

**Location**: `tests/test_profiles.py:305-331`
`TestContentTypeDispatch` asserts only that `read_and_chunk_file_async` has a `fallback_strategy` parameter. The test passes even if the dispatch logic in `chunker.py:87-96` is deleted or inverted — spec scenarios "Known types ignore profile strategy" and "Ambiguous types use profile fallback" have no functional verification, yet task 5.5 is checked off. Similarly `test_invalid_bundle_key_rejected_at_validation` (line 122-131) patches the `TOP_K` **env var**, not a bundle — the bundle-rejection path is untested (and currently fails open, per Finding 2). These tests do not satisfy the "fails when the code is broken" bar.

### [LOW] Finding 6: CLI `set-profile` leaks raw tracebacks on store errors

**Location**: `src/rag_mcp/cli.py:1272,1276,1314`
`generate_safety_contract` and `apply_profile_change` are called with no `try/except`. The new `collection_exists` guard raises `ValueError` for a typo'd collection — the MCP tool converts this to an error dict, but the CLI shows an uncaught traceback. Not gotcha #1 (CLI, not an MCP handler), but the two transports now diverge in error behaviour.

### [LOW] Finding 7: sync store I/O in async MCP handlers (carried over, unfixed)

**Location**: `src/rag_mcp/server.py:65,130`
`_profile_resolver.resolve()` performs a synchronous ChromaDB metadata read inside the async handler body, before `asyncio.to_thread`. A slow store blocks the event loop for all concurrent tool calls. Wrap the resolve in `asyncio.to_thread`.

### [LOW] Finding 8: minor code-quality items

- `src/rag_mcp/core/profiles/__init__.py:1` — docstring still cites "ADR-030"; line 13 correctly references ADR-035.
- `src/rag_mcp/core/profiles/contract.py:76,81` — calls the resolver's private `_load_effective`; either make it public or inject pre-loaded `EffectiveSettings`.
- `search()` / `ingest_path_async()` type `effective_settings` as `Any` — `EffectiveSettings` is importable without a cycle (profiles does not import retrieval/ingestion), so the type safety loss is unnecessary.
- `ProfileResolver._cache` never invalidates: mid-process bundle edits or env changes are invisible until restart. Acceptable for a server process; noted.

### [INFO] Finding 9: env-var path interpolation in `_load_profile_bundle`

`RAG_PROFILE` interpolates into `profiles/{name}.yaml` before the Settings validator clamps it (`config/__init__.py:122,165`). Env vars are trusted local config, so not exploitable today; noted for Phase 5 if profile selection is ever exposed over a network transport. Collection tags are allowlist-validated before bundle load, so the untrusted-input path is closed.

### [INFO] Finding 10: global `settings.rerank_enabled` now resolves True by default

By design (documents profile above field defaults), the startup singleton's `rerank_enabled` is now `True`. Only `core/retrieval/policy.py:246` reads it at runtime, and the profile path overrides it correctly on the MCP transport. Recorded so future consumers of `settings.rerank_enabled` do not assume the Experiment-10 default; the interaction with the un-resolved CLI path is Finding 3.

## Dependency CVE Audit

```
uv pip check:  Checked 197 packages — all compatible
uvx pip-audit: No known vulnerabilities found
```

**CVEs requiring action**: none.

## OWASP Top 10 Coverage

| ID | Category | Status |
|---|---|---|
| A01 | Broken Access Control | N/A — local stdio MCP server, no auth boundary introduced |
| A02 | Cryptographic Failures | N/A — no new crypto/credential handling; bundles contain no credentials (test-pinned) |
| A03 | Injection | ✓ — profile names allowlist-validated at resolver, contract, and both transports; `yaml.safe_load`; no SQL/shell interpolation; CLI `--metadata` JSON-parsed with type check |
| A04 | Insecure Design | ✗ — fail-open bundle degradation (Finding 2); dead spec lever advertised in the safety contract (Finding 1); transport-split behaviour (Finding 3) |
| A05 | Security Misconfiguration | ✗ — invalid bundles degrade silently to defaults instead of failing closed (Finding 2) |
| A06 | Vulnerable Components | ✓ — pip-audit clean, uv pip check clean |
| A07 | Identification & Auth Failures | N/A |
| A08 | Software & Data Integrity | ✓ — create-on-tag side effect fixed via `collection_exists` guard; read-modify-write metadata merge race remains theoretical (single-process local ChromaDB) |
| A09 | Security Logging & Monitoring | ✓ — degraded paths logged at warning/error; MCP error returns carry no stack traces or internals beyond exception type/message |
| A10 | SSRF | N/A — no server-side URL fetching in the change |

## Cloudflare Workers Specific

N/A — not a Workers project.

## Secrets Scan

`sk-`/`AKIA`/`xoxb-`/`ghp_`/key/password/secret patterns over all changed files: no hits. Profile bundles and `defaults.yaml` carry no credentials (also test-pinned in `test_profiles.py:112-120`).

## Spec Compliance Matrix (profiles-dual-use-case)

| Requirement / Scenario | Status |
|---|---|
| Three version-controlled bundles under `config/profiles/` | ✓ |
| Bundles contain no credentials | ✓ (test-pinned) |
| Bundles validated against the same Pydantic models as global config | ✗ — startup path only; operation-time bundles raw-coerced (Finding 2) |
| Documents / codebase profile values | ✓ (test-pinned) |
| Invalid bundle rejected with key-named error at resolution time | ✗ — fails open on YAML errors; bare `int()` coercion names no key (Finding 2) |
| `RAG_PROFILE` selection + collection metadata binding + inheritance | ✓ (test-pinned) |
| Hybrid mode selector: untagged → `default_profile`; `hybrid` tag rejected; invalid tag rejected listing available profiles | ✓ (test-pinned) |
| Existing untagged collections unaffected (no migration) | ✓ |
| Two-tier resolution; Tier 2 resolved per operation and passed as parameters | ✗ — MCP path only; CLI/watcher bypass (Finding 3); taxonomy lever inert (Finding 1) |
| Reranker model loaded at most once (Tier 1) | ✓ (process-wide ONNX cache; test-pinned) |
| Content-type dispatch precedence over profile fallback | ✓ implemented (`chunker.py:87-96`); ✗ tests are signature-only (Finding 5) |
| Non-destructive O(1) profile change; metadata-only mutation | ✓ — `collection_exists` guard + metadata-only `modify` |
| Safety contract surfaced; CLI prompts; MCP preview/confirm | ✓ (contract, CLI prompt, and MCP flow test-pinned) — with the caveat that the contract advertises an inert lever (Finding 1) |
| M1 revalidation recorded; AGENTS.md invariant #5 corrected | ✓ — ADR-035 §M1 records the outcome; AGENTS.md updated |

## Reranking Spec (MODIFIED requirements)

| Scenario | Status |
|---|---|
| Env-var defaults table | ✓ |
| Profile-resolved enablement takes precedence over global default; explicit flags bypass both | ✓ implemented and test-pinned (`policy.py:240-243`; `test_profiles.py:273-302`) |
| Per-operation per-collection reranker decisions in one process | ✓ on the MCP path; ✗ CLI path resolves global defaults (Finding 3) |

## Gates Run

| Gate | Result |
|---|---|
| `uv run pytest tests/test_profiles.py` | 37 passed |
| `uv run pytest -m "not slow"` (full suite) | 900 passed, 8 deselected |
| `openspec validate --all --strict` | 24 passed, 0 failed |
| `uv pip check` / `pip-audit` | clean / no known vulnerabilities |
| Secrets pattern scan (changed files) | no hits |

## Verdict Justification

**NEEDS CHANGES.** No CRITICAL findings: no secrets, no injection vectors, no dependency CVEs, profile-name input is allowlist-validated at every boundary, the MCP never-raise invariant now holds on the new tool, and the two-tier resolution itself is architecturally correct on the MCP path (verified: per-profile reranker/top_k/hybrid resolution, hybrid-mode fallback, tag rejection, cache behaviour, non-destructive O(1) mutation with existence guard). The prior review's HIGH and two of its MEDIUMs are genuinely fixed with regression tests.

Three MEDIUMs remain open. Finding 1 is a checked-off spec task over an inert lever whose safety contract misleads users. Finding 2 leaves the spec's invalid-bundle MUST scenario unmet and now fails open. Finding 3 (new) means the feature's headline use case — different behaviour per collection — silently does not apply on the CLI and watcher transports, with every Tier 2 lever inverted for codebase collections there. All three fixes are small and localised; none require redesign. The verdict upgrades to APPROVED once: (1) `metadata_taxonomy_mode` is wired or formally descoped, (2) bundle validation fails closed with key-named errors, (3) CLI/watcher resolve profiles or the spec explicitly scopes them out. Per the project's merge-gate rule, this verdict is a hard gate independent of CI green.
