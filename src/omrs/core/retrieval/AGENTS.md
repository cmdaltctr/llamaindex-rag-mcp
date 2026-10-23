# src/omrs/core/retrieval (search)

Search: dense, sparse and hybrid retrieval, and the reranker.

## What belongs here

- Retrieval strategies and the sparse backends (`sparse_registry.py`).
- The reranker and its model cache (`_reranker_cache.py`).

## What it must not import

- `omrs.core.ingestion` (contract `retrieval-stays-independent-of-ingestion`).

## Rules

1. Read `top_k`, thresholds and reranker flags from the injected settings (ADR-018). Do not hardcode them.
2. Do not change the ÷30 rerank threshold scaling without re-running `experiments/1-reranker-threshold-calibration-2026-05-12/`.
3. Reranker tests call `reset_model_cache()` in setup and teardown.
4. A sparse backend is one file plus one `register()` line in `sparse_registry.py`.
5. PyTorch stays off the default path. `reranker_torch.py` needs the `torch` extra (ADR-073).

## Links

- [Root AGENTS.md](../../../../AGENTS.md)
- [Reranker guide](../../../../docs/guides/reranker.md)
