# Metadata context repair delta

## MODIFIED Requirements

### Requirement: Ollama LLM-based categorisation with hybrid category lookup

When `METADATA__EXTRACTION_MODE` is `"local"`, the system SHALL make bounded HTTP requests to classify the document using the provider selected by `METADATA_LLM_PROVIDER`. When `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=ollama`, the system SHALL use Ollama's `/api/generate` endpoint with the model specified by `METADATA__OLLAMA_CLASSIFY_MODEL`. When `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=llamacpp`, the system SHALL use the OpenAI-compatible `/v1/chat/completions` endpoint at `LLAMACPP_CHAT_URL` with the model specified by `LLAMACPP_CHAT_MODEL`. When `METADATA_LLM_PROVIDER=cloud` with `CLOUD_BACKEND=openrouter`, the system SHALL use the OpenAI-compatible `/v1/chat/completions` endpoint at `https://openrouter.ai/api/v1` with the model specified by `OPENROUTER_LLM_MODEL` and `OPENROUTER_API_KEY` for authentication. Before sending the prompt, the system SHALL query all collections and metadata scan pages of the explicitly supplied vector store for unique category values and SHALL include them as "existing categories" alongside configured seed categories. Without a supplied store, it SHALL use seeds only, without a missing-store warning or degradation signal. It SHALL NOT query a process-default store or construct a backend client. The prompt SHALL instruct the model to prefer an existing category when applicable, but to propose a new concise category label (1-3 words, lowercase) when no existing category fits. The prompt SHALL instruct the model to return a JSON object with keys `category`, `keywords`, and `summary`. On transient HTTP failure or invalid JSON response, the system SHALL retry within configured limits. After retries are exhausted, the system SHALL fall back to `{"category": "uncategorised", "keywords": [], "summary": ""}` and log a WARNING.

The deprecated `METADATA__EXTRACTION_MODE=ollama` value SHALL be silently mapped to `local` with no warning, as it is a pure rename.

#### Scenario: Successful classification reuses existing category
- **WHEN** local classification receives a store containing ai, biology, and philosophy
- **AND** the document concerns machine learning
- **THEN** its prompt SHALL include ai as an existing option
- **AND** the normal response SHALL reuse the applicable existing label

#### Scenario: Category exists beyond first metadata page
- **WHEN** an owning-store category appears only on a later metadata page
- **THEN** category gathering SHALL discover it and include it in the prompt

#### Scenario: First run with no existing categories
- **WHEN** the supplied store has no category values
- **THEN** the prompt SHALL use configured seed categories and classification SHALL proceed normally

#### Scenario: Transient backend failure succeeds on retry
- **WHEN** a transient request failure is followed by success inside the retry budget
- **THEN** extraction SHALL return that successful response without exhausted-attempt fallback

#### Scenario: JSON wrapped in markdown code fence
- **WHEN** a response contains valid JSON inside a Markdown fence
- **THEN** the existing parser SHALL strip the fence and normalise the object

#### Scenario: Retries exhausted
- **WHEN** all classification attempts fail
- **THEN** the existing uncategorised/empty-keywords/empty-summary fallback and warning SHALL remain

#### Scenario: Legacy ollama mode name silently mapped
- **WHEN** the supported legacy Ollama mode alias is used
- **THEN** its existing compatibility mapping and warning behaviour SHALL remain unchanged

#### Scenario: Owning store differs from process default
- **WHEN** an Engine supplies one store and a different process default exists
- **THEN** prompts SHALL include labels from the supplied store only
- **AND** absence or poisoning of the default accessor SHALL not affect the result

### Requirement: Hybrid category taxonomy for ollama mode

Category gathering SHALL scan every collection of the supplied vector store,
normalise/deduplicate its labels, and merge configured seeds. Shared prompts
used by Ollama, llama.cpp, and OpenRouter SHALL retain the same ownership.
Store omission SHALL mean seed-only classification without a warning or
metadata-degradation signal for the omission itself. Real supplied-store
failures SHALL retain the existing warning/seed fallback.

#### Scenario: ChromaDB lookup succeeds
- **WHEN** the supplied compatible Chroma store contains multiple collections
- **THEN** its full category metadata SHALL be scanned and normalised
- **AND** configured seed categories SHALL be merged

#### Scenario: ChromaDB lookup fails
- **WHEN** lookup against the supplied store fails
- **THEN** the existing warning and seed-only classification fallback SHALL apply

#### Scenario: Category normalisation produces duplicates
- **WHEN** stored and seed categories contain case variants or repeated labels
- **THEN** the merged prompt taxonomy SHALL be normalised and deduplicated

#### Scenario: Other registered store supplies categories
- **WHEN** the supplied store is LanceDB or another compatible implementation
- **THEN** category gathering SHALL use the vector-store contract without a backend-specific client

#### Scenario: Standalone caller supplies no store
- **WHEN** classification has resolved settings but no store
- **THEN** its prompt SHALL use configured seeds plus uncategorised
- **AND** no global store lookup or missing-store warning/degradation SHALL occur

#### Scenario: Collection lookup fails among healthy siblings
- **WHEN** one owning-store collection cannot be read and other collections succeed
- **THEN** healthy sibling categories SHALL remain available under the existing failure-handling policy

## ADDED Requirements

### Requirement: Metadata store ownership is behaviourally tested
Metadata isolation tests SHALL capture actual classification prompts from Engine-driven ingestion using fake model calls. They SHALL distinguish disjoint stores, all owning-store collections, supplied-store failure, store omission, and fallback forwarding. Poisoned global-access errors SHALL not satisfy the test by being swallowed.

#### Scenario: Two Engines classify interleaved sources
- **WHEN** two Engines with disjoint stores classify sources in either order
- **THEN** each captured prompt SHALL contain its owning labels and seeds
- **AND** neither SHALL include labels from the other store

#### Scenario: Default lookup silently falls back
- **WHEN** a broken implementation swallows a poisoned default lookup and omits owning-store labels
- **THEN** the isolation regression SHALL fail on prompt contents
