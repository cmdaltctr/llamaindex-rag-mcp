# ADR-027: Local/Cloud Provider Naming Taxonomy

**Date:** 2026-07-16
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Md Hawari
**Change:** `local-cloud-provider-naming`
**Amends:** ADR-026 (naming aspects only — registry mechanics unchanged)

## Context

ADR-026 introduced a provider registry with three flat provider names: `ollama`, `llamacpp`, and `openrouter`. The registry pattern itself was sound — adding a provider required only a dict entry — but the **user-facing naming** had three problems:

1. **No local/cloud distinction.** The names `ollama`, `llamacpp`, and `openrouter` are all implementation details. A user wanting "local inference" had to know that `ollama` and `llamacpp` are local whilst `openrouter` is cloud. The category was implicit, never stated.

2. **Naming asymmetry.** `OLLAMA_CLASSIFY_MODEL` existed but there was no `LLAMACPP_CLASSIFY_MODEL` equivalent — each sub-provider had its own env var prefix scheme. Mixing providers (local embeddings + cloud LLM) required knowing three different sets of prefixes with no unifying structure.

3. **Poor extensibility story.** Adding a second cloud provider (e.g., OpenAI, Voyage AI) would mean another flat name in `EMBED_PROVIDER` — `openai` — which still doesn't tell the user it's cloud-hosted or that it requires an API key. The flat namespace doesn't scale.

The registry internals (nested dicts, `_build_provider`) were not the problem. The problem was the vocabulary exposed to users via env vars.

## Decision

Replace the flat provider-name vocabulary with a **two-tier category + sub-provider taxonomy**:

| Env var                 | Purpose                 | Accepted values            | Default      |
| ----------------------- | ----------------------- | -------------------------- | ------------ |
| `EMBED_PROVIDER`        | Embedding category      | `local` \| `cloud`         | `local`      |
| `METADATA_LLM_PROVIDER` | Metadata LLM category   | `local` \| `cloud`         | `local`      |
| `LOCAL_BACKEND`         | Local sub-provider      | `llamacpp` \| `ollama`     | `llamacpp`   |
| `CLOUD_BACKEND`         | Cloud sub-provider      | `openrouter`               | `openrouter` |

### Resolution chain

```
EMBED_PROVIDER (category) → LOCAL_BACKEND or CLOUD_BACKEND (sub-provider) → registry lookup → dynamic import
```

The category tells the user *what kind* of inference (local vs cloud, free vs paid). The sub-provider tells the system *which implementation* to load. This separation makes the mental model explicit: "I want local" comes first, "which local server" comes second.

### Why not auto-detect?

Probing ports (11434 for Ollama, 8080 for llama.cpp) at startup is fragile and slow. A server might be down, or both might be running. Explicit config via `LOCAL_BACKEND` is predictable and debuggable — the user states their intent, the system honours it.

### Why keep `OllamaEmbedding` separate?

Ollama's native `/api/embed` endpoint has better batch handling than its OpenAI-compatible `/v1/embeddings` endpoint. The `LOCAL_BACKEND=ollama` path uses `OllamaEmbedding` (native API), whilst `LOCAL_BACKEND=llamacpp` uses `OpenAIEmbedding` (OpenAI-compatible API). Dropping the ollama sub-provider would lose this optimisation.

### Migration: intended clean break, retained as flat aliases

The decision was a clean break: old values (`EMBED_PROVIDER=ollama`, `EMBED_PROVIDER=llamacpp`, `EMBED_PROVIDER=openrouter`) would no longer be accepted, with no deprecation alias.

**This is not what the shipped code does.** `Settings._validate_provider_selections()` (`src/rag_mcp/config/__init__.py`) still accepts `ollama`, `llamacpp`, and `openrouter` as valid `EMBED_PROVIDER` values alongside `local`/`cloud`, and `_resolve_effective_embed_provider()` treats them as direct aliases for the sub-provider, bypassing `LOCAL_BACKEND`/`CLOUD_BACKEND` category resolution entirely. A stale `.env` with `EMBED_PROVIDER=ollama` therefore keeps working exactly as it did before this ADR.

> **Update (silent-failure-audit-and-guards, 2026-08-11):** A genuinely
> unknown value no longer triggers a warning and falls back. It raises
> `ValueError` at settings-resolution time, matching the `VECTOR_STORE`
> precedent (ADR-034). See `docs/guides/configuration.md` for the
> accepted sets.

## Consequences

### Positive

- **Mental model matches intent.** Users configure `EMBED_PROVIDER=local` or `EMBED_PROVIDER=cloud` — the category they actually care about. The sub-provider (`LOCAL_BACKEND=llamacpp`) is a secondary implementation detail with a sensible default.
- **Extensible without vocabulary bloat.** Adding a new cloud provider (e.g., `openai`) means adding one entry to `CLOUD_EMBED_PROVIDERS` — the user-facing `EMBED_PROVIDER=cloud` value doesn't change. Compare this to the flat scheme, where each new provider would add another value to `EMBED_PROVIDER`.
- **Mix-and-match is obvious.** A user can set `EMBED_PROVIDER=cloud` (paid cloud embeddings) with `METADATA_LLM_PROVIDER=local` (free local LLM for metadata classification) without any coupling surprises. The two axes are independent.
- **Graceful degradation.** Unknown `EMBED_PROVIDER`, `LOCAL_BACKEND`, or `CLOUD_BACKEND` values log a warning and fall back to the default rather than crashing. A typo doesn't brick the server.
- **Sub-provider-specific env var prefixes preserved.** `LLAMACPP_*`, `OLLAMA_*`, `OPENROUTER_*` prefixes are unchanged — they're implementation details of the sub-provider, not user-facing categories. This means existing per-provider configuration (model names, URLs, API keys) didn't need renaming.

> **Update (silent-failure-audit-and-guards, 2026-08-11):** the "Graceful
> degradation" bullet above described the original shipped behaviour. As of
> that change, unknown `EMBED_PROVIDER`, `METADATA_LLM_PROVIDER`,
> `LOCAL_BACKEND`, `CLOUD_BACKEND`, `RETRIEVAL__HYBRID_SPARSE_BACKEND`, and
> `DOCUMENT_BACKEND` values no longer fall back — they raise at startup with
> a clear error naming the value and the accepted set. The accepted aliases
> (`ollama`, `llamacpp`, `openrouter` for `EMBED_PROVIDER`) are unaffected.
> Empty or whitespace-only values reset to the default rather than raising.

### Negative

- **Breaking change for existing `.env` files (as designed).** Users with `EMBED_PROVIDER=ollama` were expected to migrate to `EMBED_PROVIDER=local` + `LOCAL_BACKEND=ollama`. Mitigation: `.env.example` has clear comments. In practice the flat values were kept as accepted aliases (see the "Migration" section above) — a stale `.env` never actually broke. (Note: as of `silent-failure-audit-and-guards`, unknown values no longer fall back — they raise at startup. The accepted aliases `ollama`, `llamacpp`, `openrouter` are unaffected.)
- **Four env vars instead of two.** The cognitive surface area increased. Mitigation: `LOCAL_BACKEND` and `CLOUD_BACKEND` have sensible defaults (`llamacpp` and `openrouter` respectively), so most users only set `EMBED_PROVIDER` and `METADATA_LLM_PROVIDER`. The sub-providers are only needed when the default isn't desired.
- **One extra indirection layer.** `_build_provider` now resolves category → sub-provider → registry → import, instead of name → registry → import. This runs once at import time — negligible runtime cost.
- ~~**LLM registries not yet fully wired.**~~ **Resolved — see the Update below.** At the time of this decision, `LOCAL_LLM_PROVIDERS` and `CLOUD_LLM_PROVIDERS` were defined but `metadata_extractor.py` still used if/elif dispatch (`_dispatch_local_extraction`) rather than the registry for LLM selection. This was a known gap documented in ADR-026; the embedding path was fully registry-driven, and the LLM path followed once a second LLM sub-provider was added.

> **Update (doc-rot-sweep, 2026-08-07):** The follow-up condition — "when a
> second LLM sub-provider is added" — was met (OpenRouter). The nested dicts
> named here (`LOCAL_LLM_PROVIDERS`, `CLOUD_LLM_PROVIDERS`) were replaced by
> flat per-domain registries using `register(name, "module:attr")` string
> dispatch. Metadata extraction LLM selection resolves through
> `core/metadata/registry.py`; LLM client construction resolves through
> `core/providers/llm/registry.py` via `compose.build_llm_model`. No
> `if/elif` dispatch over strategy names remains.

### Neutral

- **`METADATA_LLM_PROVIDER` defaults to `local` regardless of `EMBED_PROVIDER`.** This prevents surprising cloud API costs — a user setting `EMBED_PROVIDER=cloud` for embeddings does not unknowingly route metadata LLM calls to a paid API. Explicit opt-in via `METADATA_LLM_PROVIDER=cloud` is required.
- **ChromaDB dimension lock still applies.** Switching from `local` + `ollama` (1024-dim `qwen3-embedding:0.6b`) to `cloud` + `openrouter` (1536-dim `text-embedding-3-small`) requires deleting `chroma_db/` and re-ingesting. This is a ChromaDB constraint, not a naming issue.

## Alternatives Considered

| Option | Rejected Because |
| ------ | --------------- |
| **Keep flat names (`ollama` / `llamacpp` / `openrouter`) as `EMBED_PROVIDER` values** | Doesn't convey local vs cloud category. Users must memorise which name is local and which is cloud. Adding a second cloud provider (`openai`) would add another opaque flat name. |
| **Auto-detect running servers by probing ports** | Fragile — a server might be down, or both might be running. Slow at startup. Not debuggable. Explicit config is predictable. |
| **Single `INFERENCE_BACKEND` with three values** | Couples embeddings and metadata LLM. Setting `INFERENCE_BACKEND=openrouter` forces both to cloud — no way to mix local LLM with cloud embeddings. Already rejected in ADR-026. |
| **Inherit `METADATA_LLM_PROVIDER` from `EMBED_PROVIDER` by default** | Surprising cloud API costs. A user setting `EMBED_PROVIDER=cloud` for embeddings would unknowingly route metadata LLM to a paid API. Explicit opt-in is safer. |
| **Keep old names as deprecated aliases** | Backward compat is debt for a single-user project. The decision was no aliases, no silent mappings — a clean break is simpler and the graceful fallback handles stale configs. (See Migration above: the flat values were in fact retained as accepted aliases in the shipped code.) |
| **Do nothing / status quo** | Cannot scale to additional cloud providers without vocabulary bloat. The flat naming doesn't convey the local/cloud distinction that users actually reason about. |

## References

- [ADR-026](./026-provider-registry-and-openrouter.md) — Provider registry pattern and OpenAI-compatible API providers (registry mechanics; this ADR amends only the naming taxonomy)
- [ADR-025](./025-pluggable-inference-backend.md) — Original pluggable inference backend (superseded by ADR-026)
- [`src/rag_mcp/config/__init__.py`](../../src/rag_mcp/config/__init__.py) — `EMBED_PROVIDER`, `METADATA_LLM_PROVIDER`, `LOCAL_BACKEND`, `CLOUD_BACKEND` env var validation and effective-provider resolution
- [`src/rag_mcp/core/metadata/extractor.py`](../../src/rag_mcp/core/metadata/extractor.py) — `_dispatch_local_extraction()` routes on `METADATA_LLM_PROVIDER` + `LOCAL_BACKEND` / `CLOUD_BACKEND`
- [`.env.example`](../../.env.example) — Provider configuration with inline comments
- [`openspec/changes/local-cloud-provider-naming/`](../../openspec/changes/local-cloud-provider-naming/) — OpenSpec change with full design rationale

> **Update (doc-rot-sweep, 2026-08-07):** the links in this section were
> updated to their v2 locations. The original decision text cited the v1
> paths `src/rag_mcp/config.py` and `src/rag_mcp/metadata_extractor.py`,
> deleted in v2.0.0. The registry dicts and `_build_provider()` this ADR
> describes no longer exist as such; provider construction now lives in
> `compose.py` (`build_embed_model`, `build_llm_model`), and registries
> live in `core/providers/{embeddings,llm}/registry.py` and
> `core/metadata/registry.py`.
