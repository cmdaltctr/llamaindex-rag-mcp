## ADDED Requirements

### Requirement: Composition root fails fast on construction and provider-selection errors

`compose.py::ensure_runtime_setup` SHALL raise instead of logging a warning
and continuing when `build_embed_model` or `build_vector_store` fails. A
process that reports successful startup MUST have a working embed model and
a registered default vector store — leaving either unset and continuing
turns a construction failure into a confusing downstream error (or silent
misbehaviour) instead of a clear startup failure.

Because `compose.py` invokes `ensure_runtime_setup()` at module scope, this
failure surfaces at import time. That is the same behaviour the existing
`VECTOR_STORE` unknown-value check already ships (`vectordb-abstraction`,
ADR-034), and it is accepted here for consistency: a traceback plus a
non-zero exit is loud, which is the point. Moving the invocation out of
module scope is tracked as separate work and is NOT part of this
requirement.

`config/__init__.py`'s provider-selection validation SHALL raise
`ValueError` — which pydantic surfaces as a `ValidationError` subclassing
`ValueError` when raised inside a model validator — naming the offending
value and the accepted values, instead of
logging a warning and clamping to a default, for: `EMBED_PROVIDER`,
`METADATA_LLM_PROVIDER`, `LOCAL_BACKEND`, `CLOUD_BACKEND`,
`RETRIEVAL__HYBRID_SPARSE_BACKEND`, and an unrecognised `DOCUMENT_BACKEND`
value. This matches the existing `VECTOR_STORE` unknown-value contract
(`vectordb-abstraction`, ADR-034) and closes the gap left by ADR-029: an
unrecognised provider selection is a misconfiguration a user should see
immediately, not a warning buried in a log stream the MCP transport makes
invisible.

This requirement does NOT apply to the two settings that degrade
deliberately by design: `DOCUMENT_BACKEND=azure` with missing Azure
credentials SHALL still fall back to local processing (required by the
cloud-opt-in-with-local-fallback hard boundary), and an unrecognised
`RAG_PROFILE` SHALL still fall back to `documents` (required by the profile
system's own degrade-gracefully design). `PDF_READER`'s unknown-value
handling is unchanged — it is governed by the `pdf-reader` capability.

#### Scenario: Embed model construction failure fails startup

- **GIVEN** `build_embed_model` raises `ImportError` or `ValueError`
- **WHEN** `ensure_runtime_setup` runs
- **THEN** the exception SHALL propagate and startup SHALL fail
- **THEN** no warning-and-continue path SHALL leave `LlamaIndexSettings.embed_model` unset while reporting success

#### Scenario: Vector store construction failure fails startup

- **GIVEN** `build_vector_store` raises `ImportError` or `ValueError`
- **WHEN** `ensure_runtime_setup` runs
- **THEN** the exception SHALL propagate and startup SHALL fail
- **THEN** no warning-and-continue path SHALL leave the default vector store unregistered while reporting success

#### Scenario: Provider validation runs before dependent validation

- **GIVEN** `EMBED_PROVIDER` is set to an unrecognised value
- **AND** `EMBED_MODEL` is unset, so the `EMBED_MODEL`-required validator would also fail
- **WHEN** settings resolution runs
- **THEN** the raised error SHALL name `EMBED_PROVIDER` as the offending setting, not `EMBED_MODEL`

#### Scenario: Unknown METADATA_LLM_PROVIDER fails startup

- **WHEN** `METADATA_LLM_PROVIDER` is set to a value other than `local` or `cloud`
- **THEN** settings resolution SHALL raise `ValueError` naming the offending value
- **THEN** the system SHALL NOT fall back to `local`

#### Scenario: Unknown LOCAL_BACKEND fails startup

- **WHEN** `LOCAL_BACKEND` is set to a value other than `llamacpp` or `ollama`
- **THEN** settings resolution SHALL raise `ValueError` naming the offending value
- **THEN** the system SHALL NOT fall back to `llamacpp`

#### Scenario: Unknown CLOUD_BACKEND fails startup

- **WHEN** `CLOUD_BACKEND` is set to a value other than `openrouter`
- **THEN** settings resolution SHALL raise `ValueError` naming the offending value
- **THEN** the system SHALL NOT fall back to `openrouter`

#### Scenario: Unknown RETRIEVAL__HYBRID_SPARSE_BACKEND fails startup

- **WHEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND` is set to a value other than `auto`, `native`, or `bm25`
- **THEN** settings resolution SHALL raise `ValueError` naming the offending value
- **THEN** the system SHALL NOT fall back to `bm25`
- **AND** this is distinct from the `native`-requested-but-unsupported capability fallback, which is unchanged (`hybrid-retrieval`)

#### Scenario: Unrecognised DOCUMENT_BACKEND value fails startup

- **WHEN** `DOCUMENT_BACKEND` is set to a value other than `local` or `azure`
- **THEN** settings resolution SHALL raise `ValueError` naming the offending value
- **THEN** the system SHALL NOT fall back to `local`

#### Scenario: DOCUMENT_BACKEND=azure with missing credentials still degrades to local

- **GIVEN** `DOCUMENT_BACKEND=azure` is set
- **WHEN** `AZURE_DOC_INTELLIGENCE_ENDPOINT` or `AZURE_DOC_INTELLIGENCE_KEY` is missing
- **THEN** the system SHALL log a WARNING and fall back to local processing
- **THEN** this scenario SHALL NOT raise, unlike an unrecognised `DOCUMENT_BACKEND` value

#### Scenario: Unrecognised RAG_PROFILE still degrades to documents

- **GIVEN** `RAG_PROFILE` is set to a value outside `documents`, `codebase`, `hybrid`
- **WHEN** settings resolution runs
- **THEN** the system SHALL log a WARNING and fall back to `documents`
- **THEN** this scenario SHALL NOT raise
