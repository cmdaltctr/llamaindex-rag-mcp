# Spec Delta

## ADDED Requirements

### Requirement: Authority resolver is a registered retrieval strategy
The `"authority"` strategy SHALL be registered in `core/retrieval/registry.py` with an import path into `core/authority/resolve.py`. The retrieval pipeline SHALL obtain it through `registry.get("authority")` behind the `authority.enabled` check and SHALL NOT import `core.authority` at module level or branch on the strategy name.

#### Scenario: Registry inventory lists authority
- **WHEN** the registry inventory test enumerates registered strategies
- **THEN** `"authority"` is present alongside `dense`, `bm25`, `fusion`, `reranker_onnx` and `reranker_torch`

#### Scenario: Pipeline module does not import authority eagerly
- **WHEN** `omrg.core.retrieval.pipeline` is imported with `authority.enabled` false
- **THEN** `omrg.core.authority.resolve` is absent from `sys.modules`
