## Context

The architecture is already positioned for this flip: registry dispatch (`core/vectordb/registry.py`, `compose.build_vector_store`), dual-store contract tests, and Stage 5 evidenced semantic parity (Experiments 2–4: ranking parity, filter semantics, score-kind discipline, BM25 cache isolation). Three sites currently default to `chroma`: `config/__init__.py:140`, `config/defaults.yaml:84`, `.env.example:77`. Two code paths import Chroma unconditionally outside the registry: `core/vectordb/__init__.py::get_default_store` (hard-coded Chroma fallback) and `core/retrieval/sparse.py` (native-capability probe importing `vectordb.chroma`). Base `pyproject.toml` carries `chromadb>=1.0.0` (line 41) and `llama-index-vector-stores-chroma>=0.5.0` (line 18). `tests/conftest.py` imports chromadb at module level and applies an autouse `_patch_chromadb` fixture to every test. Existing extras (`torch`, `community-leiden`, `azure`) plus their dedicated CI jobs provide the packaging precedent.

## Goals / Non-Goals

**Goals:**

- Remove ChromaDB from the base install and the default runtime path.
- Make every default/lazy path resolve LanceDB without importing ChromaDB.
- Give operators who select Chroma actionable startup errors, and existing Chroma users a visible migration path.
- Write ADR-049 recording the decision, the security rationale, and the reconsideration trigger.

**Non-Goals:**

- No data migration tool from `./chroma_db/` to LanceDB (documented re-ingest or keep-and-pin only).
- No removal of Chroma support: the adapter, its contract tests, and Chroma Cloud remain available through the extra.
- No changes to `dense_similarity_v1` semantics or any retrieval behaviour.

## Decisions

### D1: `chroma` optional extra, not deletion

Move `chromadb>=1.0.0` and `llama-index-vector-stores-chroma>=0.5.0` into `[project.optional-dependencies].chroma`. Deletion would break `tests/test_dependency_floors.py` (which walks optional groups and fails on missing declared packages); the extra keeps the floor contract intact, including the existing `_DRIFT_EXEMPT["chromadb"]` entry. Alternative (delete entirely) rejected: loses the tested Chroma path and the documented reconsideration route.

### D2: Default flip in exactly three declaration sites plus two code paths

`config/__init__.py`, `config/defaults.yaml`, `.env.example` flip to `lancedb`. `get_default_store` rewrites its fallback from `from .chroma import build_chroma_vector_store` to a registry-based lazy construction of the configured (now LanceDB) store — the only way to honour invariant #10 (no concrete-store import in dispatch) in that seam. The sparse native-capability probe gains a guarded import: absent Chroma → warning + BM25 fallback (matching the existing `detect_native_sparse_capability` conservative semantics). Alternative (leave the Chroma fallback, flip only the default value) rejected: a base install without the extra would crash on the lazy path.

### D3: Startup errors distinguish "extra absent" from "install broken"

Before factory dispatch, `importlib.util.find_spec("chromadb")` decides which error to raise: absent extra → `ValueError` naming `VECTOR_STORE`, the `uv sync --extra chroma` instruction, and the LanceDB alternative (house convention: startup selection errors are `ValueError`; message shape follows the community-leiden `verify_available` precedent); present-but-broken → `ImportError` chaining the original exception. `registry.get`'s ImportError path gains the same install hint for future backends. Settings validation adds the cross-check: `CHROMA_MODE=cloud` (or any `CHROMA_CLOUD_*` credential) with `VECTOR_STORE=lancedb` fails at resolution — today `chroma_mode` is silently ignored by the LanceDB factory, which would strand cloud users.

### D4: Legacy-data warning, not hard fail

When `VECTOR_STORE` is unset (user did not choose) AND the configured Chroma persist directory exists non-empty, emit one startup warning naming the directory and both options (install extra + select chroma, or re-ingest into LanceDB). Hard-fail rejected: a leftover directory would block fresh installs that never used Chroma. Docs-only rejected: silent empty-store-on-upgrade is the worst outcome.

### D5: Test infrastructure goes store-neutral; Chroma tests move behind the extra

`conftest.py`: `_patch_chromadb` becomes conditional (no-op when chromadb is absent), the autouse default effective-settings fixture points at a `tmp_path` LanceDB URI, and Chroma-specific tests gain skip markers that activate without the extra. CI: the main test job runs the base (now chromadb-free) suite and adds the "default install is chromadb-free" tripwire (import `rag_mcp`, run a default-setup search, assert `chromadb` not in `sys.modules` — mirroring the existing torch tripwire); a new `chroma-extra` job (patterned on `torch-extra`) syncs `--extra chroma` and runs the Chroma halves of the contract/legacy/hybrid/cloud suites; the `floors` matrix adds the `chroma` group; `lint-imports` jobs sync with the extra if the import-linter graph needs chromadb present (verify at implementation; the `chromadb-confined-to-vectordb` contract itself is unchanged).

### D6: ADR-049 and the advisory disposition

ADR-049 records: decision (LanceDB default; Chroma behind extra; experiments-on-LanceDB policy; reconsider only after an official patched release, as a fresh decision); evidence (ADR-046/047 + Stage 5 Experiments 2–4); consequences (re-ingest-or-pin for existing users; conftest/CI restructure). Residual fact to document: `uv.lock` still contains chromadb (uv locks all extras), so lockfile scanners will keep flagging CVE-2026-45829 — the change records the accept/ignore rationale (optional group, vulnerable server component never started, no patched release exists) and keeps the advisory tracked. Alternative (suppress the finding silently) rejected.

### D7: Documentation sweep in the same change

Per the AGENTS.md drift procedure: `.env.example`, `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `docs/guides/{architecture,configuration,mcp-tools,cli-reference,ingestion,mcp-client-setup,providers}.md` — every "ChromaDB is the default" statement and `CHROMA_PERSIST_DIR` guidance, plus a migration note for existing Chroma users. `CHROMA_SCAN_PAGE_SIZE` stays shared (LanceDB reads it as its page size) with a documenting comment; the neutral rename is explicitly deferred as future work.

## Risks / Trade-offs

- [Existing users' data becomes invisible on upgrade] → D4 warning + migration note; keep-and-pin path (`--extra chroma` + `VECTOR_STORE=chroma`) preserves their data unchanged.
- [Base CI discovers hidden Chroma assumptions] → the flip lands with the conftest rework in the same commit; the chromadb-free tripwire runs in the base job, so any surviving assumption fails the build, not production.
- [LanceDB single-writer habits differ (upsert metadata-struct locking)] → already documented in ADR-046; the migration note repeats it for converting users.
- [Lockfile scanners keep failing the release gate on the optional group] → D6 records the disposition; if policy still blocks, a follow-up change can pin an ignore with expiry tied to a patched release.
- [Import-linter graph without chromadb] → verified during implementation; mitigation (sync lint job with the extra) is one line per job.

## Migration Plan

1. Implementation order: packaging (D1) → defaults + code paths (D2/D3) → tests (D5) → CI → docs + ADR-049 (D6/D7). Each step keeps the fast suite green.
2. Rollback: single revert of the change commit restores `chroma` to base and the old default; no data or lockfile surgery (the lockfile never lost the packages).
3. Users: the D4 warning plus the README migration section is the entire user-facing procedure.

## Open Questions

- Whether the Aikido/OSV finding needs a dated ignore entry or a documented-acceptance note only — resolved when the security feed is observed post-change; does not affect code shape.
- Neutral `SCAN_PAGE_SIZE` rename timing — deferred by D7; revisit in a housekeeping change.
