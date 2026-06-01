## 1. Policy Resolver

- [ ] 1.1 Add a central effective rerank policy resolver in `src/rag_mcp/retrieval.py` or a small helper module.
- [ ] 1.2 Change internal search handling to distinguish explicit `rerank=True`, explicit `rerank=False`, and omitted/`None` rerank.
- [ ] 1.3 Ensure explicit `rerank=True` forces reranking even when `RERANK_ENABLED=false` and `RERANK_ENABLED_FOR_SEMANTIC=false`.
- [ ] 1.4 Ensure explicit `rerank=False` disables reranking even when `RERANK_ENABLED=true`.
- [ ] 1.5 Ensure omitted rerank follows `RERANK_ENABLED` before semantic/technical policy is considered.

## 2. Technical/Semantic Classification

- [ ] 2.1 Add a deterministic identifier-heavy query classifier using the Experiment 9a/10 identifier rules.
- [ ] 2.2 Add support for optional workload technical-fraction metadata when available.
- [ ] 2.3 Apply `HARD_TECHNICAL_THRESHOLD` so policy reranking is disabled when technical fraction is at or above the threshold.
- [ ] 2.4 Apply `RERANK_ENABLED_FOR_SEMANTIC` so omitted rerank can enable reranking for semantic queries/workloads below the technical threshold.
- [ ] 2.5 Include policy reason diagnostics when `include_diagnostics=True`.

## 3. Public Surface Defaults

- [ ] 3.1 Update direct retrieval default handling so omitted rerank uses the policy resolver.
- [ ] 3.2 Update MCP `search_documents()` so omitted rerank follows `config.py` and does not hardcode reranking on.
- [ ] 3.3 Update CLI search defaults so omitted rerank follows `config.py` and preserves explicit override flags.
- [ ] 3.4 Update `.env.example` to document `RERANK_ENABLED=false`, `RERANK_ENABLED_FOR_SEMANTIC`, and `HARD_TECHNICAL_THRESHOLD` accurately.

## 4. Tests

- [ ] 4.1 Add unit tests for explicit rerank true/false overriding policy.
- [ ] 4.2 Add unit tests for omitted rerank following `RERANK_ENABLED`.
- [ ] 4.3 Add unit tests for semantic policy enabling reranking below `HARD_TECHNICAL_THRESHOLD`.
- [ ] 4.4 Add unit tests for identifier-heavy policy disabling reranking at or above `HARD_TECHNICAL_THRESHOLD`.
- [ ] 4.5 Update MCP default tests to assert config-driven rerank behaviour.
- [ ] 4.6 Update CLI default tests to assert config-driven rerank behaviour.

## 5. Validation

- [ ] 5.1 Run targeted reranking/retrieval tests.
- [ ] 5.2 Run MCP and CLI default tests.
- [ ] 5.3 Run `openspec validate --change rag-semantic-technical-reranker-policy` or equivalent validation command.
- [ ] 5.4 Review ADR-019 and config comments after implementation to ensure they no longer describe unimplemented behaviour.
