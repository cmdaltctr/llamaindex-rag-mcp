# Spec Delta

## ADDED Requirements

### Requirement: Authority resolver is a registered retrieval strategy
The `"authority"` strategy SHALL be registered in `core/retrieval/registry.py` with an import path into `core/authority/resolve.py`. The retrieval pipeline and the `authority.resolve` graph operation SHALL obtain it through `registry.get("authority")` only when the stage runs. Neither SHALL import `core.authority` at module level or branch on a strategy or operation name. The documented retrieval registry inventory SHALL list `authority` in the same change that registers it.

#### Scenario: Registry inventory lists authority
- **WHEN** the registry inventory test enumerates registered retrieval strategies
- **THEN** `"authority"` is present alongside `dense`, `bm25`, `fusion`, `reranker_onnx` and `reranker_torch`, and the documented inventory block lists the same names

#### Scenario: Pipeline module does not import authority eagerly
- **WHEN** a fresh Python process imports `omrg.core.retrieval.pipeline` and runs a search with `authority.enabled` false
- **THEN** `omrg.core.authority.resolve` is absent from `sys.modules`

#### Scenario: Graph operation is registered with the retrieval operations
- **WHEN** the composition root builds the operation catalogue
- **THEN** the catalogue lists `authority.resolve` and no edit to the catalogue builder was needed
