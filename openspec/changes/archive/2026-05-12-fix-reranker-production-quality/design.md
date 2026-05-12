## Context

The `add-advanced-rag-features` change shipped a working cross-encoder
reranker, but five production-quality issues were identified during testing:

1. **Score scale mismatch** — raw logits (~−12 to +10) break `similarity_threshold`
   when `rerank=True` because the threshold was designed for 0–1 vector scores
2. **PyTorch pulled in** — `sentence-transformers` transitively installs
   PyTorch (~1 GB), violating the "no PyTorch at runtime" rule in `AGENTS.md`
3. **Singleton cannot recover** — once `_failed=True`, the reranker is dead
   for the rest of the process lifetime even if the failure was transient
4. **No reranking provenance** — callers cannot tell whether results were
   actually reranked or fell back to vector scores
5. **Stale docstring** — module docstring still references `Xenova/` model name

## Goals / Non-Goals

**Goals:**
- Normalise reranker scores to a 0–1 range so `similarity_threshold` works
  consistently regardless of whether reranking is active
- Remove the PyTorch dependency entirely by switching to `optimum` ONNX
  inference directly
- Allow the singleton to retry model loading after transient failures
- Add a `reranked` boolean field to each search result
- Fix the stale docstring

**Non-Goals:**
- Changing the reranker model (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
- Modifying the vector search score scale (already 0–1 cosine similarity)
- Changing the MCP tool signatures (parameters stay the same)
- Adding async inference (the reranker is CPU-bound and fast enough synchronously)
- Batch reranking across multiple queries

## Decisions

### 1. Sigmoid normalisation for reranker scores

The cross-encoder model (`cross-encoder/ms-marco-MiniLM-L-6-v2`) outputs a
single raw logit per query-document pair. Applying `sigmoid(logit)` maps the
output to (0, 1):

```
score = 1 / (1 + exp(-logit))
```

This is safe because the model has `num_labels=1`, so logits are always a
single float per pair.

**Why sigmoid:**
- Scores become directly comparable with vector cosine similarity (both 0–1)
- `similarity_threshold` works uniformly whether reranking is on or off
- The function is monotonic, so ranking order is preserved

**Alternative considered: min-max normalisation** — requires a calibration
dataset to determine the range. Sigmoid is parameter-free and well-understood.

### 2. Replace `sentence-transformers` with pure ONNX Runtime

Instead of:
```python
from sentence_transformers import CrossEncoder
model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
scores = model.predict(pairs)
```

Use:
```python
import onnxruntime as ort
from transformers import AutoTokenizer
from huggingface_hub import hf_hub_download

onnx_path = hf_hub_download(
    repo_id=MODEL_ID, filename="onnx/model_qint8_arm64.onnx",
)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])

encoded = tokenizer(pairs, padding=True, truncation=True, return_tensors="np")
outputs = session.run(None, {k: v for k, v in encoded.items()})
logits = outputs[0].squeeze(-1)
scores = [sigmoid(float(v)) for v in logits]
```

**Why this approach (revised from original `optimum` plan):**
- `optimum` declares `torch` as a hard dependency (~1 GB), even though
  ONNX inference doesn't need it at runtime
- Pre-exported ONNX models already exist on HuggingFace Hub for
  `cross-encoder/ms-marco-MiniLM-L-6-v2` (quantised ARM64 variant is ~23 MB)
- Pure `onnxruntime.InferenceSession` + `transformers.AutoTokenizer` is
  all that's needed — no PyTorch, no `optimum`
- `transformers` is only needed for the tokenizer (tokenizer-only mode
  works without PyTorch)
- `huggingface_hub` handles ONNX model download and local caching

**Dependency changes (revised):**
- Remove: `sentence-transformers`, `optimum`
- Keep: `onnxruntime>=1.17.0,<1.26.0`
- Add: `transformers>=4.40.0` (tokenizer only), `huggingface-hub>=0.20.0`

### 3. Singleton recovery with retry

Replace the permanent `_failed` flag with a retry mechanism:

```python
_load_attempted: bool = False
_load_error: str | None = None

def _load_model(self) -> None:
    if self._loaded:
        return
    # Allow retry if previous attempt failed
    # (transient errors like network timeouts should be retriable)
    ...
```

**Strategy:** Reset `_load_attempted` on each call if loading previously
failed. This means the first call after a transient failure will retry. To
avoid spamming retries on permanent failures (e.g., model not found), we
log the error and let it retry naturally on the next call — worst case it
fails again quickly since the model cache is local.

### 4. `reranked` flag in results

Each result dict gets a `reranked: bool` field:
- `True` if the cross-encoder successfully re-scored the results
- `False` if reranking was disabled or the reranker fell back

This is set in `retrieval.py` after calling `reranker.rerank()` — the
reranker returns results with a `_reranked` metadata key, and `retrieval.py`
propagates it to each result dict.

### 5. Updated module docstring

Fix the model name from `Xenova/ms-marco-MiniLM-L-6-v2` to
`cross-encoder/ms-marco-MiniLM-L-6-v2` and update the size reference
(the ONNX export is ~23MB from the HF cache, not a separate download).

## Architecture

### Before (current)

```
retrieval.py
    │
    └─ CrossEncoderReranker.rerank(query, results, top_k)
         │
         ├─ sentence_transformers.CrossEncoder(MODEL)
         ├─ model.predict(pairs) → raw logits
         └─ results sorted by raw logit score
```

### After (proposed)

```
retrieval.py
    │
    └─ CrossEncoderReranker.rerank(query, results, top_k)
         │
         ├─ onnxruntime.InferenceSession(model_qint8_arm64.onnx)
         ├─ transformers.AutoTokenizer(MODEL_ID)
         ├─ tokenize pairs → session.run() → logits
         ├─ sigmoid(logits) → normalised 0–1 scores
         └─ results sorted by normalised score, with reranked=True
```

### Data flow

```
search_documents(query, top_k, similarity_threshold, rerank)
    │
    ├─ 1. embed query (OllamaEmbedding — unchanged)
    │
    ├─ 2. vector search (ChromaDB — unchanged)
    │    retrieve top_k × 2 if rerank=True
    │
    ├─ 3. rerank? (CrossEncoderReranker — rewritten)
    │    │
    │    └─ reranker.rerank(query, candidates, top_k)
    │         ├─ download ONNX model from HF Hub (singleton, retryable)
    │         ├─ tokenize [query, chunk.text] pairs (numpy arrays)
    │         ├─ onnxruntime session.run() → raw logits
    │         ├─ sigmoid(logits) → 0–1 normalised scores
    │         └─ sort by score, keep top_k, mark reranked=True
    │
    ├─ 4. filter by similarity_threshold (unchanged logic,
    │    but now scores are always 0–1 regardless of reranking)
    │
    └─ 5. format & return (adds reranked field to each result)
```

## File Changes Summary

| File | Change | Lines (est.) |
|------|--------|-------------|
| `src/rag_mcp/reranker.py` | Major rewrite: swap to pure onnxruntime, add sigmoid, retry logic, `_reranked` metadata | ~160 lines |
| `src/rag_mcp/retrieval.py` | Minor: propagate `reranked` flag to result dicts | ~5 lines added |
| `pyproject.toml` | Remove `sentence-transformers` and `optimum`, add `transformers`, `huggingface-hub` | ~3 lines changed |
| `AGENTS.md` | Update reranker model name, remove `sentence-transformers`/`optimum` from deps | ~8 lines changed |

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| `optimum` ONNX export fails on first load | Low | High — reranker unusable | Graceful fallback returns un-reranked results; log the ONNX export error |
| `transformers` tokenizer pulls in unexpected deps | Low | Low — tokenizer is lightweight | `transformers` is already a transitive dep of `optimum`; no new deps |
| Sigmoid normalisation changes score semantics for existing users | Medium | Low — scores were previously undocumented range | Scores are internal to the MCP tool; no public API contract on score range |
| Singleton retry causes repeated error logs | Low | Low — noisy logs | Log at WARNING level; consider backoff in future if spammy |
| ONNX model download on first use (~23MB) | Expected | Low — one-time cost | Clear error message if network unavailable; model cached locally after first download |
