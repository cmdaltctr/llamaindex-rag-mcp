## Why

Experiment 10 and ADR-019 changed the reranker policy: `RERANK_ENABLED` now defaults to `false`, while `RERANK_ENABLED_FOR_SEMANTIC` and `HARD_TECHNICAL_THRESHOLD` were added as policy knobs for future semantic/technical reranker behaviour. The mechanical config values are present, but the current retrieval path does not use the semantic/technical policy knobs, so comments and public defaults risk implying automatic semantic reranking exists when it does not.

## What Changes

- Make the semantic/technical reranker policy explicit and implemented instead of comment-only.
- Add retrieval-side logic to resolve effective rerank behaviour from:
  - explicit per-call `rerank` argument,
  - `RERANK_ENABLED`,
  - `RERANK_ENABLED_FOR_SEMANTIC`, and
  - `HARD_TECHNICAL_THRESHOLD`.
- Add a minimal technical-query classifier/reasoning path so automatic semantic reranking is only enabled when a workload is below the configured technical threshold.
- Update MCP/server/CLI defaults so omitted `rerank` follows `config.py` rather than stale hardcoded `True` defaults.
- Update `.env.example` and tests to document that the semantic override is conditional policy, not unconditional default-on reranking.

No intentional breaking API change: explicit `rerank=True` remains supported and continues to force reranking when requested.

## Capabilities

### New Capabilities

- `semantic-technical-reranker-policy`: Defines how the system decides whether to apply reranking by default based on explicit caller intent and semantic/technical workload policy.

### Modified Capabilities

- `reranking`: Extend reranker configuration and default-behaviour requirements to include semantic/technical policy knobs and default-off behaviour across retrieval, MCP, and CLI surfaces.

## Impact

- Affected code:
  - `src/rag_mcp/config.py`
  - `src/rag_mcp/retrieval.py`
  - `src/rag_mcp/server.py`
  - `src/rag_mcp/cli.py`
  - `.env.example`
- Affected tests:
  - reranker default tests
  - MCP search defaults
  - CLI search defaults
  - new tests for semantic/technical policy resolution
- Affected docs/specs:
  - reranking spec delta
  - new semantic/technical reranker policy spec
  - ADR-019 implementation follow-up
