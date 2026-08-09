## Context

See proposal.md — Why. On the `v3` branch (after PRs #22/#24/#25) the timeout plumbing is
already sound: `providers/llm/{llamacpp,ollama,openrouter}.py` each expose
`build(settings, *, timeout=None)`; the direct-chat backends read
`metadata.classify_timeout` (30s) via `_get_classify_timeout` in `core/metadata/_common.py`;
and `core/metadata/llamaindex.py` passes `metadata.pipeline_timeout` (180s) into the
registry-resolved provider. Two gaps remain: those two timeouts are shared across every
provider, and the LLM-path fallback to keyword metadata is invisible outside the logs. The
chunker (`chunker.py:168`) also still calls `extract_metadata_async(file_text, file_path.name)`
without forwarding resolved settings.

Relevant constraints:
- Invariant #9: settings are injected, resolved once at the boundary, passed down. No singleton.
- Gotcha #1: MCP handlers never raise — errors are returned as dicts.
- `MetadataSettings` (`core/metadata/settings.py`) is a frozen pure-data model consumed by the root resolver; it must not import upward.
- `core/settings.py` mirrors `MetadataSettings` (the `EffectiveSettings` block used at runtime). Both must stay in sync.
- Coverage: `core/metadata` and `core/ingestion` are ≥95% tier.
- Built on `v3`; provider `build()` already takes `timeout=` and uses it correctly (OpenAILike `timeout`, Ollama `request_timeout`).

## Goals / Non-Goals

**Goals:**
- Make the `llamaindex` per-LLM-call timeout tunable per provider, defaulting to preserve current behaviour.
- Report metadata degradation in the ingestion result dict, additively.
- Forward resolved settings from chunker to extraction.
- One timeout-resolution mechanism shared by the direct-chat and `llamaindex` paths.

**Non-Goals:**
- Changing the fallback *ladder* itself (`llamaindex → local → keyword`). It stays.
- Changing the metadata dict shape written to chunks.
- Retrying differently, or making timeouts abort ingestion. Degradation stays non-fatal.
- Per-provider tuning of `classify_max_attempts` (only timeout is split now; attempts stay shared).

## Decisions

### D1: Per-provider override with shared fallback, for BOTH timeouts

`v3` already has two shared timeouts (`classify_timeout` 30s, `pipeline_timeout` 180s).
Add six optional overrides to `MetadataSettings`, all defaulting to `None`:

```python
llamacpp_classify_timeout_override:   float | None = Field(default=None, gt=0)
ollama_classify_timeout_override:     float | None = Field(default=None, gt=0)
openrouter_classify_timeout_override: float | None = Field(default=None, gt=0)
llamacpp_pipeline_timeout_override:   float | None = Field(default=None, gt=0)
ollama_pipeline_timeout_override:     float | None = Field(default=None, gt=0)
openrouter_pipeline_timeout_override: float | None = Field(default=None, gt=0)
```

Two resolvers in `core/metadata/_common.py`:

```python
def _resolve_classify_timeout(resolved, provider: str) -> float:
    override = getattr(resolved.metadata, f"{provider}_classify_timeout", None)
    return override if override is not None else resolved.metadata.classify_timeout

def _resolve_pipeline_timeout(resolved, provider: str) -> float:
    override = getattr(resolved.metadata, f"{provider}_pipeline_timeout", None)
    return override if override is not None else resolved.metadata.pipeline_timeout
```

`provider` is the registered backend name (`llamacpp` / `ollama` / `openrouter`) — the
direct-chat modules each know their own; the pipeline computes it exactly as it already
does to pick the registry entry (`resolved.local_backend` / `resolved.cloud_backend`).

**Why `None` sentinel over a magic default:** `None` means "unset, use shared". A float
default would make "did the operator set this?" unanswerable and couple the field to the
shared default's value. All six default to `None`, so behaviour is byte-for-byte unchanged
until an operator sets one.

**Why both timeouts get overrides (user decision):** the classify path and the pipeline
path have different work profiles and can hit different backends at different speeds; a
machine running a slow local model wants a long pipeline budget without loosening the
fast-fail classify budget, and vice versa. Overriding only one would leave half the tuning
story unaddressed.

### D2: Wire the resolvers into the two existing consumption paths

No hardcoded literals remain to replace (PR #22 removed them). The change is to route the
two existing reads through the resolvers:

- **Direct-chat classify path:** `core/metadata/llamacpp.py` and `core/metadata/ollama.py`
  currently call `_get_classify_timeout(resolved)`; the OpenRouter chat path in
  `core/metadata/extractor.py` reads `classify_timeout` via the same helper. Each switches
  to `_resolve_classify_timeout(resolved, "<its provider>")`. `_get_classify_timeout` is
  retired if no caller remains.
- **Pipeline path:** `core/metadata/llamaindex.py` currently passes
  `resolved.metadata.pipeline_timeout` into `build()`. It switches to
  `_resolve_pipeline_timeout(resolved, backend)`, reusing the `backend` it already computes.

Provider `build(settings, *, timeout=None)` defaults are left untouched — the pipeline
always passes an explicit resolved timeout, so the default is never exercised on that path.

### D3: Degradation signalled through a return-value side channel, not metadata mutation

`extract_metadata_async` today returns a bare metadata dict. The fallback branches in
`llamaindex.py` and `extractor.py` call `_dispatch_local_extraction` / keyword directly
and return their result, losing the fact that a fallback happened.

Chosen approach: thread a boolean back to the pipeline **without** changing the metadata
dict written to chunks. `read_and_chunk_file_async` already attaches `doc_metadata` to
nodes; it will also return (or record) whether extraction degraded, and the pipeline
aggregates that into `metadata_degraded` + the per-file marker.

Mechanism: add an internal `extract_metadata_with_status_async(...) -> tuple[dict, bool]`
that wraps the existing dispatch and reports whether the returned dict came from a tier
below the configured mode. `extract_metadata_async` stays as the dict-only public entry
(keyword/disabled callers and existing tests unaffected). The chunker calls the status
variant, keeps the dict for nodes, and surfaces the bool.

**Why a tuple over a sentinel key in the metadata dict:** the spec forbids changing the
chunk metadata shape, and a `_degraded` key would leak into ChromaDB and search results.

**Why detect at the dispatch boundary, not inside each backend:** the "configured mode"
is known only at the `extract_metadata_async` entry (it reads `extraction_mode`). A
backend cannot know it was reached as a fallback vs. as the primary. So the wrapper
compares "mode requested" against "tier that produced the result".

Detection rule: degraded ⇔ configured mode is an LLM-backed mode (`llamaindex` or
`local`) AND the result came from a lower tier. Concretely, the fallback branches set a
flag; the wrapper reads it. Keyword/disabled as the *configured* mode never degrade.

### D4: Chunker forwards settings

`chunker.py:168` becomes `extract_metadata_with_status_async(file_text, file_path.name, resolved)`.
`resolved` is already in scope (`resolved = resolve_effective_settings(settings)` at the
function top). One-line correctness fix for invariant #9.

## Risks / Trade-offs

- **[Two settings models drift]** `MetadataSettings` exists in both `core/metadata/settings.py` and mirrored in `core/settings.py`. → Add the six fields to both in the same change; a settings round-trip/parity test already guards this — extend it.
- **[Detecting "degraded" is subtle across nested fallbacks]** `llamaindex → local → keyword` is two hops. → The flag is set at the point the LLM path is abandoned (`llamaindex.py` except-branches and the `local` backend's own exhausted-retry fallback to `uncategorised`). Test each hop independently: package-missing, timeout, unparseable.
- **[No behaviour change is easy to under-test]** all six overrides default to `None`, so a passing suite could hide a broken resolver. → Test each resolver with the override set (uses it) and unset (falls back), per provider, not just the default path.
- **[Result-shape consumers]** CLI and MCP format the result dict. → Fields are additive; existing formatters ignore unknown keys. Add a CLI line only if trivial; not required by the spec.

## Migration Plan

No data migration. All six new settings default to `None` and inherit the existing shared
timeouts, so behaviour is unchanged until an operator opts in. Rollback is reverting the
change — no persisted state depends on it. Built on `v3`.
