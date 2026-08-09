## Why

Three ADRs and one guide describe a provider-registry mechanism that no longer
exists. `LOCAL_EMBED_PROVIDERS`, `CLOUD_EMBED_PROVIDERS`, `LOCAL_LLM_PROVIDERS`
and `CLOUD_LLM_PROVIDERS` have **zero occurrences in `src/`** — they were
replaced by flat, per-domain lazy registries using `register(name,
import_path)` string dispatch. `docs/guides/providers.md` still instructs a
contributor to add a dict entry to `src/rag_mcp/config.py`, a file that has not
existed since the v2 split (it is `src/rag_mcp/config/__init__.py`). A
contributor following that guide today writes code that cannot work.

The rot is self-documenting: ADR-027 recorded the gap as *"the LLM path will
follow when a second LLM sub-provider is added"*. OpenRouter was added, the
dispatch path **was** rewritten to go through the registry, and no document was
updated to say so. The docs drifted because nothing checks them.

## What Changes

- **Forward-note two ADRs** (026 and 027, the former also carrying its own stale 2026-08-04
  update) with dated notes recording that the nested registries were replaced,
  not relocated, and that the LLM-dispatch gap is now **closed**. ADRs are
  immutable records: no decision text is rewritten.
- **Rewrite `docs/guides/providers.md` "Registry pattern"** to describe the
  mechanism that actually exists — `core/providers/{embeddings,llm}/registry.py`
  and `core/metadata/registry.py`, lazy `"module:attr"` resolution, and the real
  "add a provider" procedure.
- **Fix two factual errors**: `getting-started.md:50` claims the reranker is
  "enabled by default" (the code default is `False`, flipped off after
  Experiment 10 showed a 19–27% degradation on technical workloads);
  `tests/TEST_README.md:92` documents a `sys.modules` constant-patching fixture
  deleted by ADR-037.
- **Add two enforcement tests** so this class of rot fails the build rather than
  ageing silently: a documentation path-resolution check and a
  documented-provider-name pin against the live registries.

### Scope boundary with `tripwire-retirement-and-provider-symmetry`

That change owns **everything about retired env-var names** — the 36 entries in
`config/legacy.py`, the lifetime policy, and its guard test. This change touches
no env-var name.

The two changes both touch `docs/guides/getting-started.md:48-56`. The split is:

| Concern | Owner |
| --- | --- |
| `RERANK_ENABLED` → `RETRIEVAL__RERANK_ENABLED` (**name**) | `tripwire-retirement-and-provider-symmetry` |
| "The reranker is enabled by default" (**factual claim**) | **this change** |

`openspec/specs/metadata-extraction/spec.md`'s flat `OLLAMA_CLASSIFY_MODEL`
reference is **explicitly deferred to the tripwire change**, not fixed here:
`OLLAMA_CLASSIFY_MODEL` is a live entry in `_RETIRED_ENV_VARS`
(`config/legacy.py:56`), which places it squarely on that change's side of the
boundary despite being flagged as general rot.

## Capabilities

### New Capabilities

None. No product behaviour changes.

### Modified Capabilities

- `internal-maintainability`: gains two enforced requirements — documentation
  file-path references SHALL resolve, and provider names documented in the
  providers guide SHALL match the live registries. This spec already carries
  this exact class of requirement (e.g. "Unsupported file discovery comments
  match behavior"), enforced by tests rather than review.

## Impact

**Documentation (content changes only, no behaviour):**

- `docs/adr/026-provider-registry-and-openrouter.md` — appended forward note
- `docs/adr/027-local-cloud-provider-naming.md` — appended forward note
- `docs/guides/providers.md` — "Registry pattern" section rewritten
- `docs/guides/getting-started.md` — reranker default claim corrected
- `tests/TEST_README.md` — stale fixture description replaced

**Tests (new enforcement):**

- `tests/test_docs_references.py` — new; documentation path resolution
- `tests/test_registry_contract.py` — extended with the documented-name pin
  (this file already imports all five registries and defines `ALL_REGISTRIES`)

**Not touched:** `src/` (no source change), any env-var name, `config/legacy.py`.

**Risk:** Low. The only failure mode is a new test that is too strict; both
proposed checks are pinned to exact-match oracles rather than heuristics, and
the design records a measured false-positive rate for the broader alternative
that was rejected.
