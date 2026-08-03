# Phase 1 Baseline (task 1.2)

Recorded on `feat/phase-1-refactor-modular-extraction` at `main` (b86fb0d).

## Test run

```
uv run pytest -m "not slow" --cov=rag_mcp
```

- Result: **581 passed, 8 deselected** in 80.05s
- Overall coverage: **88%** (3159 stmts, 385 missed)

## Per-module coverage (target files)

| Module                 | Stmts | Miss | Cover |
| ---------------------- | ----- | ---- | ----- |
| `ingestion.py`         | 340   | 33   | 90%   |
| `metadata_extractor.py`| 371   | 52   | 86%   |
| `retrieval.py`         | 235   | 7    | 97%   |
| `sparse_retriever.py`  | 134   | 10   | 93%   |
| `reranker.py`          | 115   | 5    | 96%   |

## Phase gate reference

- Tests must stay green (581 passing) at every sub-phase boundary.
- Coverage must not regress below this baseline. Note: baseline overall
  coverage (88%) is below the AGENTS.md 90% target — this is a pre-existing
  condition, not introduced by Phase 1. The 90% target is addressed by
  follow-up test work, not by this mechanical extraction.
