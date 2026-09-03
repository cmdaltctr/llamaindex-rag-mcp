## ADDED Requirements

### Requirement: Query embedding preparation SHALL support an optional query-only instruction

The system SHALL support an optional injected embedding query instruction. When the instruction is non-empty, the query embedding input SHALL be prepared as:

```text
Instruct: <instruction>
Query: <raw query>
```

When the instruction is empty or unset, the query embedding input SHALL remain the raw query exactly as before this change.

Retrieval documents and indexed chunk text SHALL NOT receive this query instruction.

#### Scenario: Empty instruction preserves current behaviour

- **GIVEN** `EMBEDDING__QUERY_INSTRUCTION` is empty or unset
- **WHEN** a query is embedded
- **THEN** `get_query_embedding()` SHALL receive the original raw query
- **AND** no instruction prefix SHALL be added

#### Scenario: Configured instruction is applied to the query

- **GIVEN** `EMBEDDING__QUERY_INSTRUCTION="Given a user query, retrieve relevant passages"`
- **AND** the raw query is `How does metadata extraction work?`
- **WHEN** the query embedding input is prepared
- **THEN** it SHALL equal `Instruct: Given a user query, retrieve relevant passages\nQuery: How does metadata extraction work?`

#### Scenario: Document embeddings remain un-instructed

- **GIVEN** a non-empty query instruction
- **WHEN** document chunks are embedded during ingestion
- **THEN** their embedding text SHALL NOT receive the query instruction
- **AND** enabling the query instruction alone SHALL NOT require document re-ingestion

### Requirement: Query preparation SHALL remain model-agnostic inside retrieval

Retrieval SHALL consume the injected query-preparation configuration without branching on Qwen, provider names, or embedding-model substrings. Model-specific policy belongs in configuration or the embedding preparation seam, not in dense-retrieval dispatch.

#### Scenario: Dense retrieval has no Qwen name dispatch

- **WHEN** the query-preparation implementation is inspected
- **THEN** dense retrieval SHALL NOT contain `if/elif` dispatch on `qwen`, `qwen3`, Ollama model aliases, or equivalent model-name substrings
- **AND** an empty instruction SHALL remain valid for any embedding provider

### Requirement: Query instruction defaults SHALL be evidence-gated

The first Qwen3-Embedding-4B instruction candidate SHALL be evaluated against the current raw-query baseline before any non-empty packaged default is promoted. The candidate is:

```text
Given a user query, retrieve passages that provide relevant and accurate evidence for answering the query.
```

A production default SHALL NOT be set solely because upstream model documentation recommends instructions; repository retrieval evidence SHALL decide promotion.

#### Scenario: Candidate instruction is evaluated as an ablation

- **GIVEN** a fixed index, embedding model, and retrieval configuration
- **WHEN** the query-instruction experiment runs
- **THEN** raw-query and instructed-query retrieval SHALL be measured on the same query set
- **AND** semantic and identifier-heavy technical queries SHALL both be represented
- **AND** the result SHALL record whether the instruction qualifies for promotion
