## Context

The provider registry (ADR-026) currently uses flat provider names: `ollama`, `llamacpp`, `openrouter`. This exposes implementation details and creates naming asymmetry (e.g. `OLLAMA_CLASSIFY_MODEL` vs `LLAMACPP_CHAT_MODEL`). The registry works technically but the user-facing naming is confusing.

Current state:
- `EMBED_PROVIDER=ollama|llamacpp|openrouter` (default: `llamacpp`)
- `METADATA_LLM_PROVIDER=ollama|llamacpp|openrouter` (default: `llamacpp`)
- Two flat dicts: `EMBED_PROVIDERS`, `LLM_PROVIDERS`
- `_build_provider(registry, name)` does a single lookup

## Goals / Non-Goals

**Goals:**
- Simplify user mental model to `local` vs `cloud`
- Preserve mix-and-match (local embeddings + cloud LLM, etc.)
- Keep sub-provider selection (`LOCAL_BACKEND=llamacpp|ollama`) for implementation details
- Make adding new providers trivial (one dict entry)
- Clean break — no backward compat for old provider names

**Non-Goals:**
- Auto-detection of running servers (too fragile)
- Dropping `OllamaEmbedding` (ollama's native API has better batch handling)
- Supporting more than one cloud provider (OpenRouter only for now, but pattern is extensible)

## Decisions

### 1. Two-tier category + sub-provider

```
EMBED_PROVIDER=local|cloud          (default: local)
METADATA_LLM_PROVIDER=local|cloud   (default: local)
LOCAL_BACKEND=llamacpp|ollama       (default: llamacpp)
CLOUD_BACKEND=openrouter            (default: openrouter)
```

**Why not flat names?** Flat names (`ollama`, `llamacpp`, `openrouter`) don't convey local vs cloud. Users must know which name is local and which is cloud. The category makes it obvious.

**Why not auto-detect?** Probing ports at startup is fragile and slow. Explicit config is predictable.

**Why not drop OllamaEmbedding?** Ollama's native `/api/embed` has better batch handling than its OpenAI-compatible `/v1/embeddings` endpoint. Keeping `LOCAL_BACKEND=ollama` with `OllamaEmbedding` preserves this.

### 2. Nested registry structure

Replace flat dicts with nested:

```python
LOCAL_EMBED_PROVIDERS = {
    "llamacpp": { ... },  # OpenAIEmbedding at localhost:8080/v1
    "ollama":   { ... },  # OllamaEmbedding at localhost:11434
}
CLOUD_EMBED_PROVIDERS = {
    "openrouter": { ... },  # OpenAIEmbedding at openrouter.ai/api/v1
}
# Same pattern for LLM_PROVIDERS
```

`_build_provider()` resolves: category → sub-provider env var → registry lookup → dynamic import.

### 3. Metadata extractor dispatch

`metadata_extractor.py` currently checks `METADATA_LLM_PROVIDER == "llamacpp"` / `"ollama"` / `"openrouter"`. New logic checks `METADATA_LLM_PROVIDER == "local"` then dispatches based on `LOCAL_BACKEND`, or `"cloud"` based on `CLOUD_BACKEND`.

The `_extract_llamacpp_chat_async` and `_extract_ollama_async` functions keep their names (they're implementation details). A new `_extract_local_chat_async` wrapper dispatches to the correct one based on `LOCAL_BACKEND`. Similarly `_extract_cloud_chat_async` for cloud.

### 4. Env var naming

Provider-specific env vars keep their prefixes (`LLAMACPP_*`, `OLLAMA_*`, `OPENROUTER_*`). These are implementation details of the sub-provider, not user-facing categories. The category env vars (`EMBED_PROVIDER`, `METADATA_LLM_PROVIDER`, `LOCAL_BACKEND`, `CLOUD_BACKEND`) are the primary user interface.

## Risks / Trade-offs

- **[Risk: Breaking existing .env files]** → Users must update `.env`. Mitigation: clear error message on unknown provider values, migration guide in docs.
- **[Risk: More env vars to understand]** → Four instead of two. Mitigation: `LOCAL_BACKEND` and `CLOUD_BACKEND` have sensible defaults; most users only set `EMBED_PROVIDER` and `METADATA_LLM_PROVIDER`.
- **[Trade-off: Indirection]** → One extra lookup layer in `_build_provider`. Negligible runtime cost (runs once at import).
