## Why

The reranker we shipped in `add-advanced-rag-features` works but has five
quality issues that make it unreliable in practice: the score scale breaks the
similarity threshold when reranking is on, PyTorch was accidentally introduced
(violating the "no PyTorch" rule), the singleton can't recover from transient
failures, callers can't tell if reranking actually happened, and a docstring
still references the wrong model name.

## What Changes

- Normalise reranker scores to 0–1 range (sigmoid) so `similarity_threshold`
  behaves consistently whether reranking is on or off
- Replace `sentence-transformers` with `optimum` + `onnxruntime` for the
  reranker, removing the PyTorch dependency (~1 GB saving)
- Allow the singleton to recover from transient model-load failures
- Add a `reranked` boolean field to each search result so callers know whether
  reranking was actually applied
- Fix stale `Xenova/` model name in `reranker.py` docstring

## Capabilities

### New Capabilities

- `score-normalisation`: Normalise reranker raw logits to a 0–1 range so the
  similarity threshold works predictably regardless of whether reranking is
  active

### Modified Capabilities

- `reranking`: Singleton recovery, `reranked` flag in results, PyTorch removal
  (swap to `optimum` ONNX backend)

## Impact

- **`src/rag_mcp/reranker.py`** — Major rewrite: swap `sentence-transformers`
  for `optimum` ONNX inference, add sigmoid normalisation, add retry logic,
  return `reranked` metadata
- **`src/rag_mcp/retrieval.py`** — Minor: propagate `reranked` flag through
  to results
- **`pyproject.toml`** — Remove `sentence-transformers` dep (PyTorch goes with
  it); `optimum` and `onnxruntime` already present
- **`README.md`** / **`.env.example`** — No changes needed (model name already
  correct, env vars unchanged)
- **Disk size** — ~1 GB reduction by removing PyTorch transitively
