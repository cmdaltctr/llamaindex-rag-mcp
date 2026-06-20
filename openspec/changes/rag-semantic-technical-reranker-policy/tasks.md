## 1. Policy Resolver

- [x] 1.1 Add a central effective rerank policy resolver in `src/rag_mcp/retrieval.py` or a small helper module.
- [x] 1.2 Change internal search handling to distinguish explicit `rerank=True`, explicit `rerank=False`, and omitted/`None` rerank.
- [x] 1.3 Ensure explicit `rerank=True` forces reranking even when `RERANK_ENABLED=false` and `RERANK_ENABLED_FOR_SEMANTIC=false`.
- [x] 1.4 Ensure explicit `rerank=False` disables reranking even when `RERANK_ENABLED=true`.
- [x] 1.5 Ensure omitted rerank follows `RERANK_ENABLED` before semantic/technical policy is considered.

## 2. Technical/Semantic Classification

- [x] 2.1 Add a deterministic identifier-heavy query classifier using the Experiment 9a/10 identifier rules.
- [x] 2.2 Add support for optional workload technical-fraction metadata when available.
- [x] 2.3 Apply `HARD_TECHNICAL_THRESHOLD` so policy reranking is disabled when technical fraction is at or above the threshold.
- [x] 2.4 Apply `RERANK_ENABLED_FOR_SEMANTIC` so omitted rerank can enable reranking for semantic queries/workloads below the technical threshold.
- [x] 2.5 Include policy reason diagnostics when `include_diagnostics=True`.

## 3. Public Surface Defaults

- [x] 3.1 Update direct retrieval default handling so omitted rerank uses the policy resolver.
- [x] 3.2 Update MCP `search_documents()` so omitted rerank follows `config.py` and does not hardcode reranking on.
- [x] 3.3 Update CLI search defaults so omitted rerank follows `config.py` and preserves explicit override flags.
- [x] 3.4 Update `.env.example` to document `RERANK_ENABLED=false`, `RERANK_ENABLED_FOR_SEMANTIC`, and `HARD_TECHNICAL_THRESHOLD` accurately.

## 4. Tests

- [x] 4.1 Add unit tests for explicit rerank true/false overriding policy.
- [x] 4.2 Add unit tests for omitted rerank following `RERANK_ENABLED`.
- [x] 4.3 Add unit tests for semantic policy enabling reranking below `HARD_TECHNICAL_THRESHOLD`.
- [x] 4.4 Add unit tests for identifier-heavy policy disabling reranking at or above `HARD_TECHNICAL_THRESHOLD`.
- [x] 4.5 Update MCP default tests to assert config-driven rerank behaviour.
- [x] 4.6 Update CLI default tests to assert config-driven rerank behaviour.

## 5. Validation

- [x] 5.1 Run targeted reranking/retrieval tests.
- [x] 5.2 Run MCP and CLI default tests.
- [x] 5.3 Run `openspec validate --change rag-semantic-technical-reranker-policy` or equivalent validation command.
- [x] 5.4 Review ADR-019 and config comments after implementation to ensure they no longer describe unimplemented behaviour.
