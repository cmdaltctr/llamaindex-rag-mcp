## Purpose

Lets operators choose which inference engine re-scores search results, so a heavyweight PyTorch reranker can be opted into for quality work without that weight ever reaching the default install. Guarantees every backend produces scores on the same scale, so the calibrated similarity threshold stays valid whichever engine runs.

## Requirements

### Requirement: reranker backend is selectable

The system SHALL support more than one reranker inference backend and SHALL
select between them from configuration. The selected backend SHALL apply to
both the composition-root-constructed reranker and any reranker constructed
lazily during retrieval, so the two paths cannot diverge.

| Variable                    | Default | Description                                    |
| --------------------------- | ------- | ---------------------------------------------- |
| `RETRIEVAL__RERANK_BACKEND` | `onnx`  | Reranker inference backend (`onnx` or `torch`) |

#### Scenario: default backend is onnx

- **GIVEN** `RETRIEVAL__RERANK_BACKEND` is not set
- **WHEN** a search is run with `rerank=True`
- **THEN** the ONNX backend SHALL perform the re-scoring
- **AND** result scores and ordering SHALL be unchanged from before this capability existed

#### Scenario: torch backend selected by configuration

- **GIVEN** `RETRIEVAL__RERANK_BACKEND=torch` and the `torch` optional extra is installed
- **WHEN** a search is run with `rerank=True`
- **THEN** the PyTorch backend SHALL perform the re-scoring
- **AND** every result SHALL carry `"reranked": true`

#### Scenario: lazily constructed reranker honours the configured backend

- **GIVEN** `RETRIEVAL__RERANK_BACKEND=torch` and the `torch` optional extra is installed
- **WHEN** a search is run with `rerank=True` and no reranker instance is injected
- **THEN** the reranker constructed on demand SHALL be the torch backend
- **AND** it SHALL NOT fall back to the ONNX backend silently

#### Scenario: unknown backend name is rejected at startup

- **GIVEN** `RETRIEVAL__RERANK_BACKEND=tensorflow`
- **WHEN** settings are resolved
- **THEN** the system SHALL fail with an error naming the accepted values
- **AND** SHALL NOT start with a silently substituted default

#### Scenario: retired registry name is rejected

- **GIVEN** the bare registry name `"reranker"` has been retired in favour of `"reranker_onnx"` and `"reranker_torch"`
- **WHEN** registry resolution is attempted with that name
- **THEN** it SHALL raise `KeyError` listing `"reranker_onnx"` and `"reranker_torch"` as available names

#### Scenario: torch backend selected but extra not installed

- **GIVEN** `RETRIEVAL__RERANK_BACKEND=torch` and the `torch` optional extra is NOT installed
- **WHEN** the reranker is constructed
- **THEN** the system SHALL emit an error naming the extra required to install it
- **AND** SHALL fall back to the ONNX backend rather than crashing

#### Scenario: torch extra missing and ONNX backend also fails

- **GIVEN** `RETRIEVAL__RERANK_BACKEND=torch`, the `torch` optional extra is NOT installed, AND the ONNX backend cannot load its model
- **WHEN** a search is run with `rerank=True`
- **THEN** the system SHALL return un-reranked results truncated to `top_k`
- **AND** every result SHALL carry `"reranked": false`
- **AND** the system SHALL NOT raise

### Requirement: all backends share one score range and public contract

Every reranker backend SHALL expose the same public behaviour: re-score
query-document pairs, return results sorted by descending relevance,
truncate to `top_k`, and set the reranked provenance flag. Every backend
SHALL normalise raw model outputs to the `(0, 1)` range via a sigmoid
transform so scores remain comparable with vector cosine similarity and
with each other.

This is a correctness requirement, not a stylistic one. The similarity
threshold is scaled by a factor calibrated against sigmoid-normalised
scores. A backend emitting raw logits would make threshold filtering
admit everything or reject everything with no error raised.

#### Scenario: every backend returns normalised scores

- **GIVEN** any registered reranker backend
- **WHEN** it re-scores a set of results
- **THEN** every returned score SHALL be greater than 0.0 and less than or equal to 1.0

#### Scenario: backends agree on ranking

- **GIVEN** a fixed query and a fixed set of candidate documents
- **WHEN** the ONNX backend and the torch backend each re-score them using the same model ID
- **THEN** the top-ranked document SHALL be the same for both backends

#### Scenario: threshold filtering behaves the same across backends

- **GIVEN** a similarity threshold that admits N results under the ONNX backend
- **WHEN** the same query is run under the torch backend with the same model ID
- **THEN** the number of admitted results SHALL NOT differ by more than one

#### Scenario: every backend degrades gracefully

- **GIVEN** any registered reranker backend whose model cannot be loaded
- **WHEN** a search is run with `rerank=True`
- **THEN** the system SHALL return un-reranked results truncated to `top_k`
- **AND** every result SHALL carry `"reranked": false`
- **AND** the system SHALL NOT raise

### Requirement: default install is free of PyTorch

The base install SHALL NOT contain `torch`, whether directly or
transitively. PyTorch SHALL be reachable only through an explicitly named
optional extra. This SHALL be enforced by an automated check rather than by
convention, because the previous violation entered through a transitive
dependency that no one audited.

#### Scenario: torch absent after a default search

- **GIVEN** a base install with no optional extras
- **WHEN** the package is imported and a search is run with the default backend
- **THEN** `torch` SHALL NOT be present in the set of loaded modules

#### Scenario: base dependency audit

- **GIVEN** the project's base dependency list
- **WHEN** it is inspected
- **THEN** `sentence-transformers`, `torch`, `optimum`, and `transformers` SHALL NOT appear
- **AND** the tokeniser dependency SHALL be a package that cannot pull `torch`

#### Scenario: fast test suite stays torch-free

- **GIVEN** the test suite is run excluding slow-marked tests
- **WHEN** the run completes
- **THEN** no test SHALL have required the `torch` optional extra

### Requirement: active backend and reranker health are observable

When diagnostics are requested, the system SHALL report which backend
performed the re-scoring and whether it succeeded. A backend that fails on
every call is a configuration error, and the system SHALL make that
distinguishable from reranking being switched off.

#### Scenario: diagnostics name the active backend

- **GIVEN** a search is run with `rerank=True` and diagnostics requested
- **WHEN** results are returned
- **THEN** the diagnostics SHALL name the backend that performed the re-scoring

#### Scenario: diagnostics expose a failed rerank

- **GIVEN** the selected backend's model cannot be loaded
- **WHEN** a search is run with `rerank=True` and diagnostics requested
- **THEN** the diagnostics SHALL indicate that reranking was requested but not applied
- **AND** SHALL carry the reason for the failure

#### Scenario: persistent backend failure escalates

- **GIVEN** the selected backend has failed to load on every attempt
- **WHEN** the failure count passes the escalation threshold
- **THEN** the system SHALL log at error severity rather than warning severity
