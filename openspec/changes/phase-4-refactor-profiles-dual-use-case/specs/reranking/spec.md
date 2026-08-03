## MODIFIED Requirements

### Requirement: reranker configuration via environment

The system SHALL support the following environment variables for reranker configuration, with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `RERANK_MODEL` | `Alibaba-NLP/gte-reranker-modernbert-base` | HuggingFace model ID for reranker |
| `RERANK_ENABLED` | `false` | Global default rerank behaviour for omitted rerank requests |
| `RERANK_ENABLED_FOR_SEMANTIC` | `true` | Policy knob allowing omitted rerank requests to enable reranking for semantic workloads below the technical threshold |
| `HARD_TECHNICAL_THRESHOLD` | `0.3` | Identifier-heavy workload fraction at or above which semantic policy reranking SHALL NOT be enabled |
| `SIMILARITY_THRESHOLD` | `0.0` | Default minimum score to include a result |
| `RERANK_FETCH_MULTIPLIER` | `10` | Multiplier applied to `top_k` when reranking is enabled |
| `RERANK_MAX_FETCH` | `50` | Lower bound on the rerank candidate pool size |

In addition to the global `RERANK_ENABLED` default, the effective rerank enablement for an omitted rerank request SHALL be resolvable per operation from the target collection's profile (e.g. `documents` enables, `codebase` disables). Profile-resolved enablement SHALL take precedence over the global default for that operation. Explicit per-request rerank flags SHALL continue to bypass both profile and semantic policy.

#### Scenario: env vars set defaults
- **GIVEN** `SIMILARITY_THRESHOLD=0.25` is set in `.env`
- **WHEN** `search_documents` is called with no explicit threshold
- **THEN** results with `score < 0.25` SHALL be filtered out

#### Scenario: rerank pool sizing env vars apply
- **GIVEN** `RERANK_FETCH_MULTIPLIER=4` and `RERANK_MAX_FETCH=20` are set
- **WHEN** `search_documents` is called with `rerank=True` and `top_k=3`
- **THEN** the reranker SHALL receive `max(20, 3 * 4) = 20` candidates

#### Scenario: semantic policy env vars are exposed
- **GIVEN** `RERANK_ENABLED_FOR_SEMANTIC=true` and `HARD_TECHNICAL_THRESHOLD=0.3` are set
- **WHEN** the effective rerank policy resolver is called for an omitted rerank request
- **THEN** the resolver SHALL consider those values when deciding whether policy reranking is allowed

#### Scenario: explicit rerank bypasses semantic policy env vars
- **GIVEN** `RERANK_ENABLED_FOR_SEMANTIC=false`
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** reranking SHALL be applied regardless of the semantic policy setting

#### Scenario: profile-resolved enablement for omitted requests
- **GIVEN** a query against a `documents`-profile collection with no explicit
  rerank flag
- **WHEN** the effective rerank enablement is resolved
- **THEN** reranking SHALL be enabled (documents profile) even though the
  global `RERANK_ENABLED` default is `false`
- **AND** a query against a `codebase`-profile collection in the same process
  SHALL resolve to reranking disabled
