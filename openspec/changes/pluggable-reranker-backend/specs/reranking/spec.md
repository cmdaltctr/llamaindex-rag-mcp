## MODIFIED Requirements

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

#### Scenario: tokeniser reports no usable maximum
- **GIVEN** a tokeniser that reports no maximum sequence length, or reports an implausible sentinel value
- **WHEN** the reranker initialises
- **THEN** the configured default maximum SHALL apply

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

### Requirement: reranker configuration via environment

The system SHALL support the following environment variables for reranker configuration, with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `RETRIEVAL__RERANK_BACKEND` | `onnx` | Reranker inference backend (`onnx` or `torch`) |
| `RETRIEVAL__RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | HuggingFace model ID for reranker |
| `RETRIEVAL__RERANK_ENABLED` | `false` | Global default rerank behaviour for omitted rerank requests |
| `RETRIEVAL__RERANK_ENABLED_FOR_SEMANTIC` | `true` | Policy knob allowing omitted rerank requests to enable reranking for semantic workloads below the technical threshold |
| `RETRIEVAL__HARD_TECHNICAL_THRESHOLD` | `0.3` | Identifier-heavy workload fraction at or above which semantic policy reranking SHALL NOT be enabled |
| `RETRIEVAL__SIMILARITY_THRESHOLD` | `0.0` | Default minimum score to include a result |
| `RETRIEVAL__RERANK_FETCH_MULTIPLIER` | `3` | Multiplier applied to `top_k` when reranking is enabled |
| `RETRIEVAL__RERANK_MAX_FETCH` | `100` | Lower bound on the rerank candidate pool size |

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
- **WHEN** the package is imported and a search is run with `rerank=True`
- **THEN** `torch` SHALL NOT appear in the set of loaded modules

#### Scenario: installing the extra does not change defaults
- **GIVEN** the `torch` optional extra is installed
- **AND** `RETRIEVAL__RERANK_BACKEND` is not set
- **WHEN** a search is run with `rerank=True`
- **THEN** the ONNX backend SHALL perform the re-scoring
- **AND** `torch` SHALL NOT be imported
