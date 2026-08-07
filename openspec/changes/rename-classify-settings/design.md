## Context

See `proposal.md` — Why. The design-relevant state: two settings
(`ollama_classify_max_attempts`, `ollama_classify_timeout`) are defined in three
places — `MetadataSettings` (config-layer model), `MetadataBlock`
(runtime `EffectiveSettings` block), and `defaults.yaml` — and consumed by four
call sites across three backend modules plus the LlamaIndex Ollama LLM provider.
Two helper functions (`_get_ollama_max_attempts`, `_get_ollama_timeout`) in
`ollama.py` wrap the settings with a call-time `os.getenv` override and a `max(1,
...)` floor; both helpers are imported by `llamacpp.py` and `extractor.py`.

The `os.getenv` override reads pre-v2 flat names that are on the startup
tripwire (`config/legacy.py`), so the branch is unreachable outside tests.
ADR-037 retired the call-time re-read pattern: settings are injected, never
re-read from the environment below the boundary.

## Goals / Non-Goals

**Goals:**
- Make the setting names honest about their scope (all backends, not Ollama only).
- Remove dead code that creates a false impression of a working override path.
- Make the settings discoverable to operators (`.env.example`).
- Guarantee a usable retry budget and timeout at the point of entry, so a
  misconfigured zero or negative value cannot skip the classification call or
  reach the HTTP client.

**Non-Goals:**
- Splitting the timeout per backend (e.g. a separate cloud timeout). The 30 s
  default is a reasonable starting point for all three; per-backend tuning is a
  separate change if measurement shows it is needed.
- Renaming `ollama_classify_model` — it is genuinely Ollama-specific.
- Unifying the three duplicated retry loops (deferred in the
  `structured-outputs-metadata-classification` design, still out of scope).
- Adding new settings or changing the returned metadata shape.

## Decisions

### 1. `classify_max_attempts` / `classify_timeout`, not `classification_*`

The shorter `classify_` prefix matches the existing `ollama_classify_model`
pattern (which stays) and reads naturally under the `metadata` block:
`metadata.classify_max_attempts`. The alternatives — `classification_max_attempts`
or `metadata_classify_max_attempts` — are either verbose or redundant with the
block name.

### 2. Old v2 nested names go on the tripwire, not a silent alias

`METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS` and `METADATA__OLLAMA_CLASSIFY_TIMEOUT`
were introduced in v2.0.0. Renaming them within the v2 line is a breaking change
for anyone who set them. The tripwire (`check_legacy_env_vars`) already catches
pre-v2 flat names with a clear migration message; extending it to cover the old
v2 nested names gives the same operator experience: a startup error naming the
old and new variable, not a silent ignore.

*Alternative considered:* a pydantic alias that accepts both names. Rejected —
silent acceptance means the old name lives forever and the operator never learns
the canonical name. The tripwire has a removal trigger (v3.0.0) that bounds its
lifetime.

### 3. Drop `os.getenv`, move the floor to a validator

The call-time `os.getenv` was a pre-v2 test hook: settings were resolved once at
import, so a test that wanted a different retry budget had to re-read the
environment at call time. ADR-037 made `EffectiveSettings` a frozen value object
threaded through every call, so the override is now done at the boundary
(`conftest.py` sets `METADATA__CLASSIFY_MAX_ATTEMPTS=1` before resolution). The
call-time re-read is dead code.

The `max(1, value)` floor protected against a zero or negative budget that would
skip the classification call. It is replaced by `Field(gt=0)` on both
`MetadataSettings` and `MetadataBlock`, which moves the guarantee to the point of
entry — env, YAML, or programmatic — instead of a single call site, and extends
it to `classify_timeout`, which had no guard at all.

Rejecting rather than clamping is the deliberate part. A clamp silently rewrites
`0` to `1`, so an operator who misconfigures the budget never learns of it; the
same reasoning that puts retired names on a startup tripwire rather than ignoring
them applies here. `Field(gt=0)` fails at resolution and names the field. This is
a behaviour change for any deployment that was relying on the clamp, and is
recorded as BREAKING in `proposal.md`.

### 4. Rename the helper functions and move them to `_common.py`

`_get_ollama_max_attempts` → `_get_classify_max_attempts` and
`_get_ollama_timeout` → `_get_classify_timeout`. The old names propagate the same
misleading scope signal as the settings fields. The helpers are imported by name
in `llamacpp.py` and `extractor.py`, so the rename is visible at every call site
and leaves no stale `ollama` reference behind.

After the rename, these helpers (plus `_retry_sleep`) no longer belong in
`ollama.py` — a new backend should not import shared infrastructure from a
sibling backend module. They move to `_common.py`, where the other shared
helpers (`_normalise_category`, `_truncate_keywords`, `_truncate_summary`,
`_strip_llm_prefix`) already live. This completes the neutral naming: no `ollama`
reference remains in the shared classification path.

The move has two non-obvious follow-ons. First, the subpackage `__init__.py`
carries a PEP 562 lazy re-export map (`_NAMES`) that currently points
`_get_ollama_max_attempts`, `_get_ollama_timeout`, and `_retry_sleep` at
`.ollama`; all three entries must be renamed/repointed to `._common` or a lazy
`from rag_mcp.core.metadata import _retry_sleep` raises `AttributeError`
(gotcha #8b — the map follows the function, not the old home). Second,
`_retry_sleep` must be imported into `llamacpp.py` at **module level** (not
inside a function), because `tests/unit/test_provider_config.py` rebinds
`llamacpp._retry_sleep = AsyncMock()` and that only reaches the retry loop if the
name is a module global. Both the Ollama-side (`ollama._retry_sleep`) and
llama.cpp-side (`llamacpp._retry_sleep`) patch targets remain valid this way; the
OpenRouter path (`extractor.py`) imports `_retry_sleep` at function level and its
patch target moves to `_common._retry_sleep` (see tasks 9.3, 9.6).

*Alternative considered:* inline the helpers (they become one-liners after
dropping `os.getenv`). Deferred — the indirection gives tests a stable import
target and keeps the retry-loop code symmetric across the three backends.

## Risks / Trade-offs

- **Breaking change for operators using `METADATA__OLLAMA_CLASSIFY_*`** → the
  tripwire gives a clear rename message at startup; the settings are optional
  (they have defaults), so most deployments are unaffected.
- **Test churn** → 6 test files reference the old names. All updates are
  mechanical find-and-replace plus rewriting `TestOllamaKnobResolution` to test
  the settings-injection path.
- **Validator on two models** → `MetadataSettings` (config layer) and
  `MetadataBlock` (runtime layer) both need the bound. This is the existing
  pattern: both models already declare the same fields with the same defaults.
  Both blocks are frozen (`model_config = ConfigDict(frozen=True)`); `Field`
  constraints are validated at construction, before frozen assignment applies,
  so the bound is compatible with the frozen block.
- **Tripwire / conftest coupling** → adding the old v2 nested names to the
  tripwire (task 6.2) and renaming them in `conftest.py` (task 9.1) must land in
  the **same commit**. `conftest.py` sets `METADATA__OLLAMA_CLASSIFY_*`; the
  instant those go on the tripwire, every test reaching `ensure_runtime_setup()`
  raises. Splitting the two tasks across commits red-bars the suite in between.

## Migration Plan

No data migration. For operators: rename `METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS`
→ `METADATA__CLASSIFY_MAX_ATTEMPTS` and
`METADATA__OLLAMA_CLASSIFY_TIMEOUT` → `METADATA__CLASSIFY_TIMEOUT` in `.env` or
shell environment. The tripwire message names both old and new. Rollback is
reverting the commit; no stored state depends on the field names.
