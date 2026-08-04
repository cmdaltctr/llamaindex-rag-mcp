# Security & Code Review: phase-4-refactor-profiles-dual-use-case

## Summary
- **Date**: 2026-08-04
- **Scope**: PR #15 (`feat/phase-4-refactor-profiles-dual-use-case`, c3bc5b7) — profiles system: `core/profiles/resolver.py`, `core/profiles/contract.py`, `config/__init__.py` (`_ProfileYamlSettingsSource`, `_load_profile_bundle`), `core/retrieval/policy.py` + `pipeline.py`, `core/ingestion/pipeline.py` + `chunker.py`, `server.py` (`change_collection_profile`), `cli.py` (`set-profile`), `config/profiles/*.yaml`, `tests/test_profiles.py`
- **Auditor**: a-security
- **Verdict**: NEEDS FIXES

## Findings

### [HIGH] MCP `change_collection_profile` confirm path can raise — violates "never raise from MCP tool handlers" (gotcha #1)

**Location**: `src/rag_mcp/server.py:380-386` (`change_collection_profile`)
**Vulnerability**: The `confirm=True` path wraps `apply_profile_change` in `except ValueError` only. `apply_profile_change` calls `store.update_collection_metadata()` → ChromaDB `collection.modify()` and `store.count()`, which raise ChromaDB/runtime exceptions (not `ValueError`) on store failure. Any such exception propagates out of the tool handler. The preview path (`confirm=False`) calls `generate_safety_contract` with no guard at all — it survives store errors only by accident of its internal try/excepts; `get_default_store()` outside those guards can still raise.
**Attack Vector**: MCP client invokes the tool against a corrupted/locked ChromaDB persist dir or a collection name ChromaDB rejects at `modify()` time — handler raises instead of returning `{"status": "error"}`.
**Impact**: Broken MCP protocol contract; unhandled exception surfaces to the client as a transport-level failure. Violates the project's explicit critical invariant.
**Mitigation**:

```diff
     if not confirm:
-        contract = generate_safety_contract(collection, profile)
-        return {"status": "preview", "contract": contract, "confirm_required": True}
+        try:
+            contract = generate_safety_contract(collection, profile)
+        except Exception as exc:
+            return {"status": "error", "message": f"Could not generate preview: {exc}"}
+        return {"status": "preview", "contract": contract, "confirm_required": True}

     try:
         return apply_profile_change(collection, profile)
-    except ValueError as exc:
+    except Exception as exc:
         return {"status": "error", "message": str(exc)}
```

**Regression test needed** (`@a-test`): `change_collection_profile(confirm=True)` with a store whose `update_collection_metadata` raises `RuntimeError` must return `{"status": "error", ...}`, not raise. Same for the preview path with `generate_safety_contract` raising.

---

### [MEDIUM] Invalid collection profile tag is silently swallowed by `ingest_documents` and `search_documents`

**Location**: `src/rag_mcp/server.py:64-68` and `:128-132`
**Vulnerability**: Both handlers do `try: effective = _profile_resolver.resolve(collection) except ValueError: effective = None`. The spec scenario "Invalid collection profile tag rejected" requires a clear error naming the invalid tag and listing available profiles. The resolver raises correctly, but the transport discards the error and proceeds with global defaults. A typo'd tag (`profile: "documetns"`) or a `hybrid` tag silently runs the operation under the wrong profile — a silent misconfiguration that returns plausible-looking results.
**Impact**: User believes a collection is codebase-tagged (reranker off, hybrid on) but searches actually run with document defaults, or vice versa. Spec non-compliance by silent degradation.
**Mitigation**: Return `{"status": "error", "message": str(exc)}` from the `except ValueError` branch in both tools instead of `effective = None`.
**Regression test needed** (`@a-test`): `search_documents` and `ingest_documents` against a collection tagged `hybrid` / `nonexistent` must return an error dict naming the tag and available profiles.

---

### [MEDIUM] `metadata_taxonomy_mode` lever is plumbed but never consumed — dead spec lever

**Location**: `src/rag_mcp/core/ingestion/pipeline.py:146-160`
**Vulnerability**: `EffectiveSettings.metadata_taxonomy_mode` (`category` vs `file_type`) is resolved by the resolver, compared in the safety contract, and documented in the `ingest_path_async` docstring ("its `chunk_strategy_fallback` and `metadata_taxonomy_mode` supply the defaults for … metadata classification"), but grep confirms zero consumers outside resolver/contract/settings. The ingest pipeline passes only `chunk_strategy_fallback` to the chunker; the metadata extractor never receives the taxonomy mode. Task 4.4 ("Thread resolved levers … chunking fallback + taxonomy mode") is checked off but the taxonomy half is not implemented.
**Impact**: The codebase profile's headline `file_type` taxonomy is a no-op. Ingests into a codebase-profile collection classify with the category taxonomy regardless of profile. Spec Tier-2 lever list unmet.
**Mitigation**: Thread `effective_settings.metadata_taxonomy_mode` into the metadata extraction stage (or explicitly descope the lever from the spec/tasks and remove it from the contract diff).

---

### [MEDIUM] `apply_profile_change` on a non-existent collection silently creates it

**Location**: `src/rag_mcp/core/vectordb/chroma.py:323-326` (via `core/profiles/contract.py:208-210`)
**Vulnerability**: `update_collection_metadata` falls back to `client.get_or_create_collection(collection_name)` when the collection doesn't exist. Confirming a profile change against a typo'd collection name creates a new empty collection carrying only the profile tag. The spec requires the change to be "only the collection's metadata dict … updated" — collection creation is a mutation beyond that contract, and the preview's `chunk_count: 0` gives no signal that the target does not exist.
**Impact**: Junk empty collections accumulate; user believes they retagged an existing collection.
**Mitigation**: In `apply_profile_change` (or the store method), raise/return an error when `get_collection_metadata` returns `None` (collection absent), and surface "collection does not exist" in the preview contract.

---

### [MEDIUM] Operation-time bundle validation gap: raw coercion, uncaught YAML errors, no key-named validation errors

**Location**: `src/rag_mcp/config/__init__.py:103-138`, `src/rag_mcp/core/profiles/resolver.py:86-131`
**Vulnerability**: Three gaps against the spec scenario "Invalid bundle rejected … clear validation error naming the offending key":
1. `_load_profile_bundle` catches only `FileNotFoundError`/`ModuleNotFoundError`. A malformed YAML raises `yaml.YAMLError`, which propagates through `resolve()` and — being non-`ValueError` — escapes the MCP tools' `except ValueError` guards (compounds finding 1).
2. `_bundle_to_effective` coerces with bare `int(bundle.get("TOP_K", …))`. A bad value raises `ValueError: invalid literal for int()` without naming `TOP_K` or the bundle.
3. Bundles are not validated "against the same Pydantic settings models" at operation time — the ad-hoc dict coercion in the resolver duplicates (and diverges from) the startup `Settings` path. An unknown key in a bundle is silently ignored by `_ProfileYamlSettingsSource.__call__` (only model-field names are copied).
**Impact**: Corrupted/mistyped bundle edits crash resolution or fail with opaque errors; spec validation requirement unmet on the per-operation path.
**Mitigation**: Validate the loaded bundle dict against the `Settings` model (e.g. `Settings.model_validate` on the mapped keys) inside `_load_profile_bundle` and re-raise as `ValueError(f"profile bundle {name!r}: field {key}: {err}")`; catch `yaml.YAMLError` alongside `FileNotFoundError`.

---

### [LOW] Read-modify-write race in `update_collection_metadata`

**Location**: `src/rag_mcp/core/vectordb/chroma.py:314-329`
ChromaDB `modify(metadata=…)` replaces the whole dict; the implementation reads, merges, writes. Two concurrent metadata writers lose each other's keys. Single-process local ChromaDB with the generation counter kept separately makes this unlikely — noted for the Phase 5 multi-transport future.

### [LOW] Synchronous store I/O in async MCP handlers

**Location**: `src/rag_mcp/server.py:65`, `:129`
`_profile_resolver.resolve()` performs a synchronous ChromaDB metadata read inside the async handler body (`search_documents` previously deferred all blocking work via `asyncio.to_thread`). A slow store blocks the event loop for every other concurrent tool call. Wrap the resolve in `asyncio.to_thread` alongside `search`.

### [LOW] Test quality gaps against spec scenarios

**Location**: `tests/test_profiles.py`
- `TestContentTypeDispatch` asserts only that the `fallback_strategy` parameter exists — the test cannot fail if the chunker's dispatch logic breaks (spec scenarios "Known types ignore profile strategy" / "Ambiguous types use profile fallback" unverified functionally; task 5.5 is checked off on a signature test).
- Task 5.4's "byte-identical embeddings/content" is verified against a `MagicMock` store only.
- Task 2.4's "rejection test for an invalid bundle key" (`test_invalid_bundle_key_rejected_at_validation`) patches the `TOP_K` env var, not a bundle — the bundle-key rejection path is untested.

### [LOW] Stale ADR reference in package docstring

**Location**: `src/rag_mcp/core/profiles/__init__.py:1,13`
Docstring cites "ADR-030" / `docs/adr/030-phase-4-refactor-profiles-dual-use-case.md`; the merged ADR is `035-phase-4-refactor-profiles-dual-use-case.md` (ADR numbering shifted per the reserved-range convention).

### [LOW] Duplicate import

**Location**: `src/rag_mcp/core/retrieval/pipeline.py:15-17` — `from typing import Any` appears twice.

### [INFO] Env-var-only path-traversal surface in `_load_profile_bundle`

`RAG_PROFILE` interpolates directly into the bundle path (`profiles/{name}.yaml`). Not reachable from untrusted input (collection tags are allowlist-validated before `_load_effective`; env vars are trusted local config). No action needed; noted for completeness if Phase 5 ever exposes profile selection over a network transport.

## Dependency CVE Audit

```
uv pip check:   Checked 197 packages — all compatible
uvx pip-audit:  No known vulnerabilities found
```

**CVEs requiring action**: none.

## OWASP Top 10 Coverage

| ID | Category | Status |
|---|---|---|
| A01 | Broken Access Control | N/A — local stdio MCP server, no auth boundary introduced |
| A02 | Cryptographic Failures | N/A — no new crypto/credential handling; bundles contain no credentials (test-pinned) |
| A03 | Injection | ✓ — profile names allowlist-validated; `yaml.safe_load`; no SQL/shell; collection names validated by ChromaDB |
| A04 | Insecure Design | ✗ — silent-fallback design on invalid tags (finding 2); create-on-tag side effect (finding 4) |
| A05 | Security Misconfiguration | ✗ — invalid tags/bundles degrade silently instead of failing closed (findings 2, 5) |
| A06 | Vulnerable Components | ✓ — pip-audit clean |
| A07 | Identification & Auth Failures | N/A |
| A08 | Software & Data Integrity | ✗ — read-modify-write metadata race (finding, LOW); non-atomic create-on-tag (finding 4) |
| A09 | Security Logging & Monitoring | ✓ — resolver logs degraded paths at warning/debug; no PII in logs |
| A10 | SSRF | N/A — no server-side URL fetching in the change |

## Cloudflare Workers Specific

N/A — not a Workers project.

## Gates Run

| Gate | Result |
|---|---|
| `uv run pytest tests/test_profiles.py` | 36 passed |
| `uv run pytest -m "not slow"` (full suite) | 899 passed, 8 deselected |
| `openspec validate phase-4-refactor-profiles-dual-use-case --strict` | valid |
| `uv pip check` / `pip-audit` | clean |

## Verdict Justification

NEEDS FIXES. No CRITICAL findings: no secrets, no injection vectors, no dependency CVEs, input validation on profile names is allowlist-based, and the two-tier resolution itself is correct (verified: per-profile reranker/top_k/hybrid resolution, hybrid-mode fallback, tag rejection at the resolver, cache correctness with immediate post-change effect, no harmful race in the resolver cache). The blockers are one HIGH invariant violation (MCP tool can raise on store errors) and four MEDIUM correctness/spec-compliance gaps (silent tag swallowing at the transport, the dead `metadata_taxonomy_mode` lever, create-on-tag side effect, and the operation-time bundle validation gap). All fixes are small and localised; none require redesign. Verdict upgrades to APPROVED once findings 1–5 are fixed with the regression tests noted.
