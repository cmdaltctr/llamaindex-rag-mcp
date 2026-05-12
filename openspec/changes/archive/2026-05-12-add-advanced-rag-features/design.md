## Context

Our RAG pipeline currently works like this:

```
query → OllamaEmbedding(query) → ChromaDB cosine search → return top_k chunks
```

AnythingLLM showed us two cheap improvements that significantly lift retrieval quality without needing external services or API keys.

## Goals / Non-Goals

**Goals:**
- Cross-encoder reranker that re-scores initial vector search results for better precision
- Configurable similarity threshold to filter out low-confidence results
- All new features opt-in; defaults preserve current behaviour
- Local-first: everything runs on-device via ONNX (no API calls)

**Non-Goals:**
- Hybrid search (BM25 fusion) — future concern
- Query expansion / transformation — not a bottleneck for our use case
- Alternative chunking strategies — SentenceSplitter is adequate
- Multi-tenant / namespace isolation — separate change if needed
- Chat history / source backfill — host-side concern, not server-side

## Decisions

### 1. Reranker model: `Xenova/ms-marco-MiniLM-L-6-v2`

**Rationale**: This is the same model AnythingLLM uses. It's a cross-encoder trained on MS MARCO passage ranking, which means it directly evaluates query-document relevance. At 23MB it's tiny, and ONNX inference via `optimum` gives fast CPU inference (~50-200ms for 5-10 candidates on a MacBook).

Alternatives considered:
- `BAAI/bge-reranker-base` (500MB) — more accurate but 20x larger, overkill for our scale
- `mxbai-rerank-xsmall-v1` (150MB) — newer but less proven

**Cross-encoder vs bi-encoder**: Our embedding model (nomic-embed-text) is a bi-encoder — it encodes query and document independently, then compares with cosine distance. A cross-encoder takes both as a pair, which is slower but significantly more accurate. The reranker only runs on the top N candidates (not the whole corpus), so the latency is bounded.

### 2. Reranker as a separate module

`reranker.py` will be a standalone class `CrossEncoderReranker` with:
- Lazy singleton initialisation (model loaded once, reused across calls)
- `rerank(query: str, chunks: list[dict], top_k: int) -> list[dict]`
- Graceful fallback: if model fails to load, return chunks unchanged and log a warning

### 3. Similarity threshold as a post-filter

After vector search (and optionally after reranking), results with `score < similarity_threshold` are dropped. Threshold applies to:
- Vector search scores if reranking is off
- Reranker scores if reranking is on

This keeps the filtering logic simple and predictable.

### 4. Integration into retrieval pipeline

```python
def search(query, top_k=TOP_K, similarity_threshold=0.0, rerank=False):
    # 1. Vector search (existing)
    nodes = vector_retriever.retrieve(query, top_k * 2 if rerank else top_k)

    # 2. Optional reranker
    if rerank:
        nodes = reranker.rerank(query, nodes, top_k=top_k)

    # 3. Filter by threshold
    nodes = [n for n in nodes if n.score >= similarity_threshold]

    return format_results(nodes)
```

When reranking is enabled, we fetch `top_k * 2` candidates to give the reranker more material to work with.

### 5. Configuration via .env

```env
# Reranker (optional, off by default)
RERANK_MODEL=Xenova/ms-marco-MiniLM-L-6-v2
RERANK_ENABLED=false
SIMILARITY_THRESHOLD=0.0
```

Users can also override via the `search_documents` tool parameters at call time. The env var sets the default; the tool parameter overrides it.

## Architecture

```
search_documents(query, top_k, similarity_threshold, rerank)
    │
    ├─ 1. embed query (OllamaEmbedding — existing)
    │
    ├─ 2. vector search (ChromaDB — existing)
    │    retrieve top_k * 2 if rerank=True, else top_k
    │
    ├─ 3. rerank? (CrossEncoderReranker — new)
    │    │
    │    └─ reranker.rerank(query, candidates, top_k)
    │         ├─ load ONNX model (singleton, cached)
    │         ├─ tokenize [query, chunk.text] pairs
    │         ├─ run model → sigmoid logits → scores
    │         └─ sort by score, keep top_k
    │
    ├─ 4. filter by similarity_threshold (new)
    │    drop chunks with score < threshold
    │
    └─ 5. format & return results (existing)
```

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| ONNX model ~23MB download | Downloaded once, cached in `~/.cache/huggingface/`; clear error message if download fails |
| Reranking latency (50-200ms) | Off by default; user opts in via `rerank=true` |
| ONNX dependency on macOS ARM | `optimum` + `onnxruntime-silicon` supports macOS ARM natively; tested in CI |
| Model not found or fails to load | Graceful fallback: return un-reranked results + warning log |
| Threshold too aggressive (no results) | Valid behaviour — caller gets empty list, can retry with lower threshold |
| Pipeline complexity creep | Explicit non-goals above; if new features are needed, they're separate changes |
