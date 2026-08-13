## Purpose

Define optional cross-encoder reranking, score filtering, model loading, and runtime configuration for improving retrieval result precision.
## Requirements
### Requirement: Reranker candidate pool is configurable

The system SHALL keep reranker candidate-pool sizing configurable via `RETRIEVAL__RERANK_MAX_FETCH` and `RETRIEVAL__RERANK_FETCH_MULTIPLIER`. A realistic technical-workload calibration experiment SHALL evaluate whether the current defaults remain appropriate for technical documentation, especially when hybrid BM25/RRF retrieval is enabled.

#### Scenario: Technical workload calibration records reranker policy

- **GIVEN** a realistic technical-document benchmark with dense-only and hybrid retrieval modes
- **WHEN** reranker policies are evaluated
- **THEN** the experiment SHALL record the active `RETRIEVAL__RERANK_ENABLED`, `RETRIEVAL__RERANK_MAX_FETCH`, `RETRIEVAL__RERANK_FETCH_MULTIPLIER`, reranker model, retrieval mode, and latency for each cell
- **THEN** the recommendation SHALL state whether reranking should remain default, become conditional, change pool size, or stay opt-in for technical workloads

### Requirement: Reranker can be evaluated independently from hybrid retrieval

The system SHALL support experiments that compare reranking on and off for both dense-only and hybrid retrieval without changing the underlying corpus or query set.

#### Scenario: Reranker on/off comparison

- **GIVEN** the same indexed corpus and query set
- **WHEN** dense-only and hybrid retrieval are each evaluated with reranking disabled and enabled
- **THEN** the experiment SHALL attribute quality changes separately to first-stage retrieval and reranker policy
- **THEN** the experiment SHALL fail loudly if completed cells cannot be distinguished by retrieval mode and reranker policy

### Requirement: cross-encoder re-ranking for precision

The system SHALL provide an optional cross-encoder reranker that re-scores
initial vector search results to improve retrieval precision. When reranking
is enabled and hybrid retrieval is also enabled, the reranker SHALL receive
the fused dense+sparse candidate list. When reranking is enabled and hybrid
retrieval is disabled, the reranker SHALL receive the dense-only candidate
list. The fetch pool size SHALL be governed by `RETRIEVAL__RERANK_MAX_FETCH` and
`RETRIEVAL__RERANK_FETCH_MULTIPLIER` regardless of whether hybrid retrieval is active.
The tokenizer `max_length` SHALL default to 2048 tokens to balance
context window utilisation with latency.

#### Scenario: Rerank over dense-only candidates

- **GIVEN** documents have been indexed
- **WHEN** `search_documents(query="X", rerank=True, hybrid=False)` is called
- **THEN** the system SHALL fetch dense-only candidates up to the configured fetch pool
- **THEN** the reranker SHALL re-score those candidates
- **THEN** the calibrated reranker score scaling SHALL be applied unchanged

#### Scenario: Rerank over hybrid candidates

- **GIVEN** documents have been indexed
- **WHEN** `search_documents(query="X", rerank=True, hybrid=True)` is called
- **THEN** the system SHALL run dense and sparse retrievers and fuse them via RRF
- **THEN** the top fused candidates up to the configured fetch pool SHALL be passed to the reranker
- **THEN** the calibrated reranker score scaling SHALL be applied unchanged

#### Scenario: Hybrid does not change reranker scoring semantics

- **WHEN** the same query is run with `hybrid=False, rerank=True` and `hybrid=True, rerank=True` against a corpus where dense retrieval already finds the correct chunk
- **THEN** the reranker SHALL produce equivalent reranker scores for that chunk in both runs (within numerical tolerance)
- **THEN** the calibrated reranker threshold scaling factor SHALL NOT require recalibration

#### Scenario: Reranker model unavailable with hybrid

- **GIVEN** the ONNX reranker model is not downloaded or fails to load
- **WHEN** `search_documents` is called with `rerank=True, hybrid=True`
- **THEN** the system SHALL fall back to fused (un-reranked) results trimmed to `top_k`
- **THEN** the system SHALL emit a warning log without crashing

### Requirement: ONNX inference via pure onnxruntime

The reranker SHALL use `onnxruntime.InferenceSession` for ONNX inference
with the `tokenizers` package for tokenisation, removing all PyTorch
runtime dependencies from the default install path. `transformers` SHALL
NOT be used by the ONNX backend, because it consolidates on `torch` as its
sole backend from v5 onward and would reintroduce the dependency this
requirement exists to prevent. Pre-exported ONNX models are downloaded
from HuggingFace Hub.

The tokeniser's maximum sequence length SHALL be capped at the model's own
limit. Where the tokeniser does not report that limit, the configured
default SHALL apply. Exceeding the model's position-embedding size causes
an ONNX broadcast error at inference time.

#### Scenario: ONNX model loads successfully

- **GIVEN** the reranker model ID is `cross-encoder/ms-marco-MiniLM-L-6-v2`
- **WHEN** the reranker initialises for the first time
- **THEN** the system SHALL load the model via `onnxruntime.InferenceSession`
- **AND** the tokenizer SHALL be loaded via the `tokenizers` package
- **AND** no `sentence_transformers`, `torch`, `optimum`, or `transformers` import SHALL occur

#### Scenario: max sequence length capped at the model's own limit

- **GIVEN** a model whose position embeddings support 512 tokens
- **WHEN** the configured tokeniser maximum exceeds 512
- **THEN** the effective maximum SHALL be reduced to 512
- **AND** inference SHALL NOT raise a dimension mismatch error

#### Scenario: tokeniser and model config report no usable maximum

- **GIVEN** a tokeniser that reports no maximum sequence length, or reports an implausible sentinel value
- **AND** the model's `config.json` either lacks `max_position_embeddings` or reports an implausible sentinel value
- **WHEN** the reranker initialises
- **THEN** the configured default maximum SHALL apply

#### Scenario: model config provides maximum when tokeniser does not

- **GIVEN** a tokeniser that reports no maximum sequence length
- **AND** a model whose `config.json` reports `max_position_embeddings` as 512
- **WHEN** the reranker initialises
- **THEN** the effective maximum SHALL be 512
- **AND** the configured default maximum SHALL NOT apply

#### Scenario: platform-aware ONNX variant selection

- **GIVEN** the reranker is running on macOS ARM
- **WHEN** the reranker downloads the ONNX model
- **THEN** for the default model `cross-encoder/ms-marco-MiniLM-L-6-v2` on ARM64, it SHALL prefer `onnx/model_qint8_arm64.onnx` (~23 MB quantised variant)
- **AND** fall back to `onnx/model.onnx` if the ARM variant is unavailable
- **AND** for ModernBERT-based models (e.g. `Alibaba-NLP/gte-reranker-modernbert-base`), it SHALL prefer `onnx/model_quantized.onnx` (int8) with a fallback chain through `model_int8.onnx` → `model_fp16.onnx` → `model.onnx`

#### Scenario: module docstring reflects correct model

- **GIVEN** `reranker.py` is loaded
- **WHEN** the module docstring is read
- **THEN** it SHALL reference `cross-encoder/ms-marco-MiniLM-L-6-v2` as the default
- **AND** it SHALL NOT reference `Xenova/ms-marco-MiniLM-L-6-v2`

### Requirement: similarity threshold filtering

The system SHALL provide a configurable similarity threshold to filter out
low-confidence results.

#### Scenario: threshold filters low scores

- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called with `similarity_threshold=0.5`
- **THEN** any chunk with `score < 0.5` SHALL be excluded from results

#### Scenario: aggressive threshold returns empty

- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called with `similarity_threshold=0.99`
- **THEN** the system MAY return zero results (empty list)

#### Scenario: threshold of 0.0 includes all (default)

- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called without `similarity_threshold`
- **THEN** all chunks from vector search SHALL be returned (no filtering)

### Requirement: reranker configuration via environment

The system SHALL support the following environment variables for reranker configuration, with sensible defaults:

| Variable                                 | Default                                | Description                                                                                                           |
| ---------------------------------------- | -------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `RETRIEVAL__RERANK_BACKEND`              | `onnx`                                 | Reranker inference backend (`onnx` or `torch`)                                                                        |
| `RETRIEVAL__RERANK_MODEL`                | `cross-encoder/ms-marco-MiniLM-L-6-v2` | HuggingFace model ID for reranker                                                                                     |
| `RETRIEVAL__RERANK_ENABLED`              | `false`                                | Global default rerank behaviour for omitted rerank requests                                                           |
| `RETRIEVAL__RERANK_ENABLED_FOR_SEMANTIC` | `true`                                 | Policy knob allowing omitted rerank requests to enable reranking for semantic workloads below the technical threshold |
| `RETRIEVAL__HARD_TECHNICAL_THRESHOLD`    | `0.3`                                  | Identifier-heavy workload fraction at or above which semantic policy reranking SHALL NOT be enabled                   |
| `RETRIEVAL__SIMILARITY_THRESHOLD`        | `0.0`                                  | Default minimum score to include a result                                                                             |
| `RETRIEVAL__RERANK_FETCH_MULTIPLIER`     | `3`                                    | Multiplier applied to `top_k` when reranking is enabled                                                               |
| `RETRIEVAL__RERANK_MAX_FETCH`            | `100`                                  | Lower bound on the rerank candidate pool size                                                                         |

In addition to the global `RETRIEVAL__RERANK_ENABLED` default, the effective rerank enablement for an omitted rerank request SHALL be resolvable per operation from the target collection's profile (e.g. `documents` enables, `codebase` disables). Profile-resolved enablement SHALL take precedence over the global default for that operation. Explicit per-request rerank flags SHALL continue to bypass both profile and semantic policy.

`RETRIEVAL__RERANK_BACKEND` selects the inference engine only. It SHALL NOT
affect whether reranking happens, which model is used, or how candidates
are pooled — those remain governed by the other variables in this table.

#### Scenario: env vars set defaults

- **GIVEN** `RETRIEVAL__SIMILARITY_THRESHOLD=0.25` is set in `.env`
- **WHEN** `search_documents` is called with no explicit threshold
- **THEN** results with `score < 0.25` SHALL be filtered out

#### Scenario: backend selection is orthogonal to enablement

- **GIVEN** `RETRIEVAL__RERANK_BACKEND=torch` and `RETRIEVAL__RERANK_ENABLED=false`
- **WHEN** `search_documents` is called with no explicit rerank flag against a collection whose profile disables reranking
- **THEN** no reranking SHALL occur
- **AND** no torch backend model SHALL be loaded

#### Scenario: rerank pool sizing env vars apply

- **GIVEN** `RETRIEVAL__RERANK_FETCH_MULTIPLIER=4` and `RETRIEVAL__RERANK_MAX_FETCH=20` are set
- **WHEN** `search_documents` is called with `rerank=True` and `top_k=3`
- **THEN** the reranker SHALL receive `max(20, 3 * 4) = 20` candidates

#### Scenario: semantic policy env vars are exposed

- **GIVEN** `RETRIEVAL__RERANK_ENABLED_FOR_SEMANTIC=true` and `RETRIEVAL__HARD_TECHNICAL_THRESHOLD=0.3` are set
- **WHEN** the effective rerank policy resolver is called for an omitted rerank request
- **THEN** the resolver SHALL consider those values when deciding whether policy reranking is allowed

#### Scenario: explicit rerank bypasses semantic policy env vars

- **GIVEN** `RETRIEVAL__RERANK_ENABLED_FOR_SEMANTIC=false`
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** reranking SHALL be applied regardless of the semantic policy setting

#### Scenario: profile-resolved enablement for omitted requests

- **GIVEN** a query against a `documents`-profile collection with no explicit
  rerank flag
- **WHEN** the effective rerank enablement is resolved
- **THEN** reranking SHALL be enabled (documents profile) even though the
  global `RETRIEVAL__RERANK_ENABLED` default is `false`
- **AND** a query against a `codebase`-profile collection in the same process
  SHALL resolve to reranking disabled

### Requirement: reranker as singleton with recovery

The reranker model SHALL be loaded once per process and reused across calls
to avoid repeated model loading overhead. The reranker SHALL be constructed
in `compose.py` (the composition root) as an injected dependency, with
process-wide model caching preserving the load-once behaviour of the former
`__new__` singleton. The reranker SHALL receive its settings (model ID,
enabled flag) via injection and SHALL NOT call `load_dotenv()` independently
of the settings resolver. The reranker SHALL recover from transient failures
rather than permanently disabling itself.

When no reranker is injected, `core/retrieval/pipeline.py::search` constructs a
fresh instance through the retrieval registry; both paths are intentional, and
the process-wide model cache makes the fresh construction cheap (no reload).
This is why the consecutive-failure counter is module-level, not instance state.

The reranker SHALL distinguish a transient failure from a persistent one by
tracking consecutive failures with the same error signature. Below the
escalation threshold, a failure SHALL log at WARNING as today. At or above
the threshold, the failure SHALL log at ERROR instead, so a persistently
broken provider stops being indistinguishable from an occasional transient
hiccup in the logs. The escalation SHALL NOT change the fallback behaviour —
retrieval SHALL still return un-reranked results and SHALL NOT raise.

The test reset hook (`CrossEncoderReranker._instance = None`) SHALL either be
preserved in an equivalent form (e.g. a cache-reset function) or be
deliberately retired with every affected test updated; it SHALL NOT be
silently dropped. The consecutive-failure counter SHALL reset alongside the
model cache so tests remain isolated.

#### Scenario: repeated calls reuse model
- **GIVEN** the reranker has been constructed and its model loaded once
- **WHEN** `search_documents` is called with `rerank=True` multiple times
- **THEN** the model SHALL NOT be re-loaded on subsequent calls

#### Scenario: retry after transient failure
- **GIVEN** the reranker model failed to load due to a transient error
  (e.g., network timeout downloading model weights)
- **WHEN** `search_documents` is called again with `rerank=True`
- **THEN** the system SHALL attempt to load the model again
- **AND** if the retry succeeds, results SHALL be reranked normally

#### Scenario: persistent failure still falls back gracefully
- **GIVEN** the reranker model is permanently unavailable (e.g., invalid
  model ID)
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the system SHALL fall back to un-reranked results
- **AND** SHALL emit a log on each failed attempt — at WARNING below the
  escalation threshold, at ERROR at or above it
- **AND** SHALL NOT crash or raise an exception

#### Scenario: persistent failure escalates to ERROR at the threshold
- **GIVEN** the reranker has failed with the same error signature on
  N-1 consecutive calls, where N is the configured escalation threshold
- **WHEN** the reranker fails again with the same error signature — the
  Nth consecutive failure (e.g. the 3rd when N=3)
- **THEN** the system SHALL log at ERROR level instead of WARNING
- **AND** SHALL still fall back to un-reranked results without raising

#### Scenario: a successful call resets the consecutive-failure counter
- **GIVEN** the reranker has failed one or more consecutive times
- **WHEN** a subsequent call succeeds
- **THEN** the consecutive-failure counter SHALL reset to zero
- **AND** the next failure (if any) SHALL log at WARNING, not ERROR

#### Scenario: test isolation preserved
- **GIVEN** a test suite that resets reranker state between cases
- **WHEN** the reset hook (or its replacement) is invoked
- **THEN** no reranker state, including the consecutive-failure counter,
  MUST leak across test cases

### Requirement: reranked provenance flag

Each search result SHALL include a `reranked` boolean field indicating whether
the cross-encoder reranker was successfully applied.

When `include_diagnostics=True` and reranking was requested but did not
apply because the reranker failed (transient or persistent), the diagnostic
`rerank_reason` field SHALL explain the failure rather than only a policy
skip reason. This makes a broken reranker distinguishable from a
policy-driven skip without grepping logs.

#### Scenario: reranking applied successfully
- **GIVEN** documents have been indexed
- **AND** the reranker model is available
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** every result dict SHALL include `"reranked": true`

#### Scenario: reranking disabled (default)
- **GIVEN** documents have been indexed
- **WHEN** `search_documents` is called without `rerank` (or `rerank=False`)
- **THEN** every result dict SHALL include `"reranked": false`

#### Scenario: reranking requested but model unavailable
- **GIVEN** documents have been indexed
- **AND** the reranker model fails to load
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** every result dict SHALL include `"reranked": false`
- **AND** scores SHALL be the original vector similarity scores

#### Scenario: failure reason surfaced in diagnostics
- **GIVEN** the reranker model fails to load
- **WHEN** `search_documents` is called with `rerank=True` and
  `include_diagnostics=True`
- **THEN** the `rerank_reason` diagnostic field SHALL describe the failure
  (e.g. identify it as a load or inference failure), not only a policy
  decision string

### Requirement: no PyTorch at runtime

The `sentence-transformers`, `optimum`, `transformers`, and `torch`
packages SHALL NOT be base runtime dependencies. No `torch` import SHALL
occur at runtime under the default configuration.

PyTorch SHALL remain reachable through an explicitly named optional extra,
so operators who want a PyTorch reranker can opt into that weight
deliberately. Installing the extra SHALL NOT change default behaviour: the
default backend stays ONNX, and an install that never requests the extra
SHALL never resolve `torch`.

The constraint is on the **base install and the default retrieval path**,
not on the existence of PyTorch code in the repository. The former is what
keeps this a lightweight local tool. The latter was never the goal, and
enforcing it as though it were has excluded otherwise-suitable components
from unrelated decisions.

#### Scenario: dependency audit

- **GIVEN** the project's `pyproject.toml`
- **WHEN** the base `dependencies` list is inspected
- **THEN** `sentence-transformers`, `torch`, `optimum`, and `transformers` SHALL NOT be listed
- **AND** only `onnxruntime`, `tokenizers`, and `huggingface-hub` SHALL be
  used for default-backend reranker inference and model management

#### Scenario: torch confined to an optional extra

- **GIVEN** the project's `pyproject.toml`
- **WHEN** the optional dependency groups are inspected
- **THEN** `sentence-transformers` SHALL appear in exactly one named extra
- **AND** that extra SHALL NOT be included in any default install path

#### Scenario: runtime tripwire on the default path

- **GIVEN** a base install with no optional extras
- **AND** `RETRIEVAL__RERANK_BACKEND` is not set (or is set to `onnx`)
- **WHEN** the package is imported and a search is run with `rerank=True` in a clean subprocess
- **THEN** `torch` SHALL NOT appear in the set of loaded modules
- **AND** the ONNX backend SHALL perform the re-scoring

#### Scenario: installing the extra does not change defaults

- **GIVEN** the `torch` optional extra is installed
- **AND** `RETRIEVAL__RERANK_BACKEND` is not set
- **WHEN** a search is run with `rerank=True`
- **THEN** the ONNX backend SHALL perform the re-scoring
- **AND** `torch` SHALL NOT be imported

### Requirement: ONNX execution provider selection

The reranker SHALL select its ONNX Runtime execution provider via
`RERANK_ONNX_PROVIDER`, defaulting to CPU. CoreML SHALL only be used when
explicitly requested and available on the current platform, since CoreML's
static graph compilation cannot handle the variable sequence lengths
produced by cross-encoder tokenisation (ADR-029).

#### Scenario: default provider is CPU
- **GIVEN** `RERANK_ONNX_PROVIDER` is unset
- **WHEN** the reranker model loads
- **THEN** the ONNX session SHALL use `CPUExecutionProvider` only

#### Scenario: CoreML opt-in when available
- **GIVEN** `RERANK_ONNX_PROVIDER=coreml` is set
- **AND** `CoreMLExecutionProvider` is in the platform's available providers
- **WHEN** the reranker model loads
- **THEN** the ONNX session SHALL use `CoreMLExecutionProvider` with
  `CPUExecutionProvider` as a fallback provider

#### Scenario: CoreML requested but unavailable falls back to CPU
- **GIVEN** `RERANK_ONNX_PROVIDER=coreml` is set
- **AND** `CoreMLExecutionProvider` is NOT in the platform's available
  providers
- **WHEN** the reranker model loads
- **THEN** the ONNX session SHALL use `CPUExecutionProvider` only

