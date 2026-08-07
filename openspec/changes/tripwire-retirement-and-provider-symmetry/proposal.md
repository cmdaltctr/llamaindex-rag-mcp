## Why

The v2 migration left two threads unfinished, and both are now actively
misleading. The retired-env-var tripwire (`_RETIRED_ENV_VARS`, 27 entries) has a
removal trigger of v3.0.0 hardcoded in three places — but the change that
released v3.0.0 also *added* entries, so those entries are born expired. And
OpenRouter, added as the second LLM sub-provider, was never wired into either
registry the way ADR-027 said it would be; it is registered against the dispatch
module in one registry and hardcoded around the other entirely.

Neither is urgent on its own. Together they are the reason the codebase's own
documentation and invariants no longer describe it accurately, and both are
cheap to close now while the v3 line is open for breaking work.

## What Changes

### Thread A — retired env-var lifetime

- Replace the hardcoded "removed in v3.0.0" trigger with a stated **lifetime
  policy** in `legacy.py` and CLAUDE.md gotcha #11, so a rename never again
  collides with the release that introduces it.
- The policy is **shape-aware**, not uniform. This is forced by a measured
  asymmetry in how pydantic-settings handles the two kinds of retired name:
  - **Nested** names (`METADATA__OLLAMA_CLASSIFY_TIMEOUT`) already raise without
    the tripwire, because every settings block is `extra="forbid"`. The tripwire
    only improves the message. These are safe to delete after one major.
  - **Flat** names (`TOP_K`) are **silently ignored** and no pydantic
    configuration can change that — `extra="forbid"` on the root model does not
    catch them, verified empirically (see design.md D1). For these the tripwire
    is the *only* detector, and deleting an entry genuinely restores silent
    misconfiguration.
- **BREAKING** Delete the 2 nested classify entries once v3.0.0 ships (they will
  have had their major). Retain the 25 flat pre-v2 entries beyond v3.0.0,
  reversing the previously scheduled removal — with the reasoning recorded, so
  the retention is a decision rather than a deferral.
- Fix the single genuine doc bug: `docs/guides/getting-started.md:54` instructs
  users to set `RERANK_ENABLED=true`, which is on the tripwire and hard-fails
  startup.
- Update the 10 living `openspec/specs/*.md` files that still name flat
  variables in requirement text.

### Thread B — OpenRouter registry symmetry

- Extract `_extract_openrouter_chat_async` out of the dispatch module
  `core/metadata/extractor.py` into its own `core/metadata/openrouter.py`,
  matching every other backend.
- Add `core/providers/llm/openrouter.py` with a `build` function and register
  it, replacing the hardcoded `OpenAILike(api_base="https://openrouter.ai/...")`
  construction inlined at `core/metadata/llamaindex.py:179-184`.
- Remove the one-entry identity dict `_CLOUD_BACKENDS = {"openrouter":
  "openrouter"}` in `extractor.py`.
- Append a dated forward-note to ADR-027, whose "Consequences" section still
  records this gap as open and deferred.

### Prevention (the durable part of this change)

- A **guard test** asserting no operator-facing document instructs the reader to
  set a retired variable. Detection is assignment-form (`^\s*#?\s*NAME=`), not
  substring: measured against the current tree, substring matching yields 35
  files of which ~34 are legitimate migration prose, while assignment-form
  yields exactly 1 — the real bug. Precision is what makes this test survivable.
- A **symmetry test** asserting every metadata backend that names an LLM
  sub-provider is registered in both registries and implemented outside the
  dispatch module, so Thread B cannot silently regress.

## Capabilities

### New Capabilities

- `config-retirement-policy`: how a configuration name is retired — the
  tripwire's detection guarantee, the shape-aware lifetime rule, and the
  guarantee that operator-facing docs never instruct setting a retired name.

### Modified Capabilities

- `inference-backend`: requires OpenRouter to be reachable through the LLM
  provider registry rather than inline construction, and requires backend
  symmetry across both registries.
- `metadata-extraction`: requires every registered extraction backend to be
  implemented in its own module, not in the dispatch module.

## Impact

**Code**
- `src/rag_mcp/config/legacy.py` — policy docstring, entry retention/removal.
- `src/rag_mcp/core/metadata/extractor.py` — loses the OpenRouter implementation
  and `_CLOUD_BACKENDS`; shrinks toward pure dispatch.
- `src/rag_mcp/core/metadata/openrouter.py` — **new**.
- `src/rag_mcp/core/providers/llm/openrouter.py` — **new**.
- `src/rag_mcp/core/providers/llm/registry.py`, `core/metadata/registry.py` — one
  `register()` line each.
- `src/rag_mcp/core/metadata/llamaindex.py` — inline construction removed.

**Tests**
- New guard test and symmetry test.
- `tests/test_config_no_legacy_surface.py` — mapping pin updated for the deleted
  entries.
- Patch targets move for OpenRouter tests: `_extract_openrouter_chat_async`
  leaves `extractor.py`, so `tests/test_metadata_extractor.py` patch paths and
  the PEP 562 `_NAMES` map in `core/metadata/__init__.py` must move with it
  (CLAUDE.md gotcha 8b).

**Docs**
- `docs/guides/getting-started.md`, `CLAUDE.md` gotcha #11, ADR-027 forward-note,
  10 `openspec/specs/*.md` files.

**Not in scope** — owned by the parallel `doc-rot-sweep` change: the claim at
`getting-started.md:49` that the reranker is enabled by default (it is not), and
the stale provider-registry descriptions in ADR-026/027 and
`docs/guides/providers.md`. This change touches `getting-started.md` only at
line 54.

**Release** — targets the `v3` branch. `python-semantic-release` cuts a version
on every push to `main`, so breaking work accumulates on `v3` and merges once.
