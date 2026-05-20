## Context

The metadata extraction system currently supports four modes (`disabled`, `keyword`, `ollama`, `llamaindex`) but only two produce meaningful results beyond regex. The `ollama` mode sends text to a local LLM via raw HTTP but only requests a single category string — underutilising the model's capability. The `llamaindex` mode is a stub that logs "not yet implemented" and falls back to keyword regex. This design implements both modes properly in two stages.

### Current State

```
config.py
  ├── Settings.embed_model = OllamaEmbedding(...)  ✅ configured
  ├── Settings.llm = None                           ❌ not configured
  ├── METADATA_EXTRACTION_MODE                      ✅
  └── OLLAMA_CLASSIFY_MODEL = qwen3:0.6b            ✅

metadata_extractor.py
  ├── _extract_keyword() → {"category": "AI"}       ✅ implemented
  ├── _extract_ollama() → {"category": "AI"}       ✅ implemented (urllib, single label)
  └── _extract_llamaindex() → falls back to keyword ❌ stub
```

### Constraints

- **No API keys, no cloud services** — everything runs locally via Ollama
- **No PyTorch at runtime** — only ONNX Runtime for the reranker; LLM calls go through Ollama's HTTP API
- **`config.py` is the single source of truth** — all model configuration centralised there
- **MCP tool handlers never raise** — metadata extraction failures must return a dict, not an exception
- **British English** spelling in all documentation and comments

## Goals / Non-Goals

**Goals:**

1. **Stage 1**: Enrich `ollama` mode to return `{"category": "<category>", "keywords": [...], "summary": "..."}` via a better Ollama prompt — same transport, richer output, no new dependencies
2. **Stage 2**: Implement real `llamaindex` mode using LlamaIndex's `IngestionPipeline` with `TitleExtractor`, `KeywordExtractor`, and `SummaryExtractor` — per-chunk enrichment, LLM-backed
3. Maintain backward compatibility — existing `ollama` mode callers still receive `category` in every result dict
4. Graceful degradation — all modes fall back to keyword on failure, never crash ingestion
5. Testable design — mock `Settings.llm` and Ollama HTTP responses for fast unit tests

**Non-Goals:**

- Adding `EntityExtractor` or `QuestionsAnsweredExtractor` — these require additional dependencies and are out of scope for v1
- Changing the `keyword` mode behaviour — regex-based extraction is intentionally simple and fast
- Adding new LLM backends beyond Ollama — the requirement is local-only
- Per-node extraction in `ollama` mode — stays per-file for speed

## Decisions

### Decision 1: Stage 1 stays on raw `urllib`, not LlamaIndex LLM abstraction

**Chosen**: Keep `_extract_ollama()` using `urllib.request` → Ollama `/api/generate`.

**Rationale**: The `ollama` mode is designed for lightweight, low-latency classification. Switching to LlamaIndex's `Ollama` LLM class would add `llama-index-llms-ollama` as a hard dependency and require `Settings.llm` configuration — exactly what we want to keep **optional** for this mode. The raw HTTP approach keeps the mode self-contained, dependency-free, and suitable for resource-constrained machines.

**Alternative considered**: Unify both modes under LlamaIndex's `Ollama` class. Rejected because it forces all ollama mode users to install the LLM integration package and configure `Settings.llm`, even though they only need simple classification.

### Decision 2: Structured JSON prompt for ollama mode

**Chosen**: Prompt the model to reply with a JSON object containing `category`, `keywords`, and `summary`.

```
system: "You are a document classifier. Analyse this document and return ONLY a JSON object..."
user:   "File: {file_name}\n\n{text[:3000]}"
```

The response is parsed with `json.loads()`. If parsing fails, the raw response is used as the category and keywords/summary default to empty.

**Rationale**: JSON prompts work reliably with modern small models like qwen3:0.6b (validated in metadata extraction experiments). The structured output lets us add fields without changing the transport or breaking callers.

**Alternative considered**: Multiple separate API calls (one for category, one for keywords, one for summary). Rejected — triples latency from ~2s to ~6s per file.

### Decision 3: Lazy `Settings.llm` initialisation for llamaindex mode

**Chosen**: Do NOT set `Settings.llm` unconditionally in `config.py`. Instead, initialise it lazily inside `_extract_llamaindex()` on first call:

```python
_llm: Optional["Ollama"] = None

def _get_llm():
    global _llm
    if _llm is None:
        from llama_index.llms.ollama import Ollama
        _llm = Ollama(model=OLLAMA_CLASSIFY_MODEL, base_url=OLLAMA_BASE_URL, request_timeout=60.0)
    return _llm
```

**Rationale**: Only users who set `METADATA_EXTRACTION_MODE=llamaindex` should pay the import cost and memory overhead of `llama-index-llms-ollama`. Users on `keyword` or `ollama` mode should not need the package installed. A lazy approach also avoids the circular import risk mentioned in AGENTS.md (config.py runs `OllamaEmbedding()` at import time — adding `Ollama()` would be fine for config.py itself, but the pattern precedent is clean).

**Alternative considered**: Set `Settings.llm` in `config.py` unconditionally. Rejected — forces a new dependency on all users and adds import-time overhead.

### Decision 4: Per-chunk `IngestionPipeline` for llamaindex mode

**Chosen**: Use `IngestionPipeline(transformations=[TitleExtractor(...), KeywordExtractor(...), SummaryExtractor(...)])` run against the document's nodes.

**Flow**:
```
Document → SentenceSplitter → [TitleExtractor, KeywordExtractor, SummaryExtractor] → metadata dict
```

Each extractor enriches each node's metadata (e.g., `document_title`, `excerpt_keywords`, `section_summary`). The aggregator (in `_extract_llamaindex`) takes the first non-empty value from each field across all nodes and returns a merged dict.

**Rationale**: Per-chunk extraction is LlamaIndex's intended pattern for metadata enrichment — it gives the LLM better context about each chunk rather than making a single coarse-grained classification. The pipeline can process chunks in parallel if needed.

**Alternative considered**: Single LLM call with a rich prompt (like enhanced ollama mode). Rejected — this would make `llamaindex` mode identical to `ollama` mode and defeat the purpose of having two separate modes. The value of `llamaindex` mode is the per-chunk granularity.

### Decision 5: Default model for llamaindex mode

**Chosen**: Reuse `OLLAMA_CLASSIFY_MODEL` (default `qwen3:0.6b`) for Stage 2 as well. Users can upgrade to a larger model (e.g., `qwen3:8b`) by changing the env var.

**Rationale**: Avoids adding yet another env var. The classify model is already a chat model suitable for extraction. Users who want heavier extraction can point `OLLAMA_CLASSIFY_MODEL` at a larger model — the pipeline code doesn't change.

**Alternative considered**: Separate `LLAMANDEX_EXTRACTOR_MODEL` env var. Rejected for now — premature complexity. Can be added later if user demand warrants different models for classification vs. extraction.

### Decision 6: Fallback strategy

All extraction modes follow the same fallback pattern:

| Mode         | Failure scenario                                   | Fallback                          |
| ------------ | -------------------------------------------------- | --------------------------------- |
| `ollama`       | Ollama unreachable, model not pulled, JSON invalid | `{"category": "uncategorised", "keywords": [], "summary": ""}` |
| `llamaindex`   | `llama-index-llms-ollama` not installed              | Log WARNING, fall back to keyword |
| `llamaindex`   | LLM call fails mid-extraction                      | Log WARNING, fall back to keyword |
| All modes    | Any unexpected exception                           | Log WARNING, return empty dict    |

**Rationale**: Ingestion must never fail because of metadata extraction. The worst case is uncategorised documents with no metadata — search still works, just without category filtering.

### Decision 7: Hybrid category taxonomy — query existing + seed + propose new

**Chosen**: Before each Ollama classification call, query ChromaDB for all unique category values currently in use. Merge with seed categories from keyword mode. Include the deduplicated list in the prompt with instructions to prefer existing labels but propose a new concise label if nothing fits. Normalise all output: lowercase, underscores for spaces, max 3 words.

**Rationale**: This follows the TnT-LLM pattern (Microsoft, KDD 2024): sample the corpus → build a taxonomy → lock it and classify into it. Our continuous-ingestion adaptation lets the taxonomy grow organically as new domains appear, while the "prefer existing" instruction prevents category proliferation. Normalisation ensures `metadata_filter={"category": "ai"}` reliably matches regardless of how the LLM originally capitalised or spaced the label — critical because ChromaDB uses exact string matching for `where` clauses.

**Flow**:
```
ChromaDB query (unique categories)  +  seed categories (keyword mode)
                   │
                   ▼
          deduplicate + normalise
                   │
                   ▼
          "Existing categories: ai, biology, philosophy, programming"
                   │
                   ▼
          Ollama prompt → prefers existing, can propose new
                   │
                   ▼
          Normalise output → lowercase, max 3 words, underscores
```

**Alternative considered**: Pure fixed category list (current). Rejected — misses novel domains entirely. Pure open-ended classification. Rejected — `metadata_filter` breaks within 20 documents due to label fragmentation. Query ChromaDB but skip seed categories. Rejected — empty ChromaDB on first run means zero categories, forcing the LLM to invent labels for everything.

## Risks / Trade-offs

| Risk                                                               | Mitigation                                                                                                                              |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| **Small models may produce unparseable JSON**                      | `json.loads()` wrapped in try/except; fall back to using raw response as category; log WARNING for debugging                        |
| **`llama-index-llms-ollama` not installed**                          | `import ` inside try/except; fall back to keyword mode with clear WARNING log                                                        |
| **Ollama model not pulled**                                        | HTTP 404 → WARNING log → fall back to keyword or uncategorised. No crash.                                                              |
| **Per-chunk pipeline slower than expected**                        | Cap chunks processed to first 10 by default (configurable via `LLAMANDEX_EXTRACTOR_MAX_CHUNKS`). Log timing at DEBUG level.        |
| **Richer metadata increases ChromaDB storage size**                | Keywords stored as comma-separated string in a single metadata field; summary limited to ~200 chars. Negligible storage impact.        |
| **`Settings.llm` singleton pattern conflicts with reranker singleton** | Both singletons are independent (different classes, different modules). No conflict. Both reset in test teardown.                   |
| **Stage 2 introduces new import dependency**                       | `llama-index-llms-ollama` added to `pyproject.toml` as optional extra `[metadata]`; code handles `ImportError` gracefully.             |

## Open Questions

1. **Should the ollama mode use `/api/chat` instead of `/api/generate`?** The `/api/chat` endpoint supports system/user message separation, which improves JSON prompt adherence. This would change from raw `urllib` to LlamaIndex's `Ollama` class — crossing into Decision 1's rejected alternative. **Recommendation**: Keep `/api/generate` for Stage 1. Revisit if qwen3:0.6b consistently produces malformed JSON with the generate endpoint.

2. **Should the llamaindex pipeline use a different (larger) model than the ollama classify model?** Currently both use `OLLAMA_CLASSIFY_MODEL`. A 0.6B model may struggle with per-chunk summary extraction. **Recommendation**: Start with the same model for simplicity. Document that users should upgrade to `qwen3:8b` or similar for production-quality llamaindex mode. Add a separate env var if user feedback demands it.
