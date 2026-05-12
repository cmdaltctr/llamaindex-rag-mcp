## Phase 1 — Dependency Cleanup

- [x] 1.1 Remove `sentence-transformers` from `pyproject.toml` dependencies
- [x] 1.2 Add `transformers>=4.40.0` to `pyproject.toml` if not already
      present (check transitive deps first — `optimum` may pull it in)
- [x] 1.3 Run `uv sync` and verify `torch` is no longer in the resolved
      dependency tree (`uv pip list | grep -i torch` should return nothing)

## Phase 2 — Reranker Rewrite

- [x] 2.1 Rewrite `src/rag_mcp/reranker.py`:
  - Replace `sentence_transformers.CrossEncoder` with
    `onnxruntime.InferenceSession` + `transformers.AutoTokenizer`
    (pure ONNX Runtime — no PyTorch, no optimum)
  - Download pre-exported ONNX model from HuggingFace Hub
    (`model_qint8_arm64.onnx` on macOS ARM, ~23 MB)
  - Add `sigmoid()` normalisation: scores = `1 / (1 + exp(-logit))`
  - Replace permanent `_failed` flag with retryable `_load_attempted` logic
  - Fix module docstring: `Xenova/` → `cross-encoder/`
  - Add `_reranked` metadata key to returned results
  - Keep singleton pattern with thread-safe lazy init
  - Keep graceful fallback (return un-reranked results on failure)

## Phase 3 — Retrieval Integration

- [x] 3.1 Update `src/rag_mcp/retrieval.py`:
  - Propagate `reranked` flag from reranker results to final result dicts
  - Set `reranked=False` when reranking is disabled or fallback occurs
  - Ensure `similarity_threshold` works correctly with normalised 0–1 scores

## Phase 4 — Documentation

- [x] 4.1 Update `AGENTS.md`:
  - Fix reranker model name in Tech Stack table
  - Remove `sentence-transformers` from dependency notes
  - Update "Adding the reranker" section

## Verification

- [x] 5.1 Regression: `search_documents(query)` without rerank returns
      results with `reranked: false`
- [x] 5.2 Reranker: `search_documents(query, rerank=True)` returns results
      with `reranked: true` and scores in 0–1 range
- [x] 5.3 Threshold: `search_documents(query, rerank=True, similarity_threshold=0.5)`
      correctly filters normalised reranker scores
- [x] 5.4 Fallback: simulate model load failure → returns results with
      `reranked: false` and original vector scores, no crash
- [x] 5.5 Dependency audit: `uv pip list` shows no `torch` or
      `sentence-transformers` in the environment
- [x] 5.6 Singleton retry: first call fails (transient), second call
      succeeds and returns `reranked: true`
