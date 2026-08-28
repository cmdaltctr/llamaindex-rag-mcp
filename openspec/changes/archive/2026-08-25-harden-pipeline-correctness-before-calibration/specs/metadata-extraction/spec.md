## ADDED Requirements

### Requirement: Metadata extractor chunk caps use actual chunk units

When `LLAMANDEX_EXTRACTOR_MAX_CHUNKS=N` limits LlamaIndex metadata extraction, the implementation SHALL cap the actual metadata-extraction chunk sequence to at most N chunks. It SHALL NOT multiply a token-oriented chunk-size setting by N and use that value as a raw character slice.

#### Scenario: Token/character-divergent document
- **GIVEN** a document whose first `N * chunk_size` characters represent materially fewer than N SentenceSplitter chunks
- **WHEN** metadata extraction runs with max chunks N
- **THEN** up to the first N actual metadata chunks SHALL be eligible for extraction
- **AND** the cap SHALL be expressed/observed in chunks rather than inferred character count

### Requirement: Persisted LlamaIndex metadata granularity is documented accurately

If per-chunk extractor outputs are aggregated into one file-level metadata object and that object is copied onto final stored chunks, the system SHALL describe the persisted granularity as file-level aggregate metadata. Documentation SHALL NOT claim that distinct per-chunk LLM enrichment survives into the stored index unless the implementation actually persists distinct values per final chunk.

#### Scenario: Temporary extractor chunks differ
- **GIVEN** temporary metadata-extractor chunks produce different metadata values
- **WHEN** the current aggregator selects/combines them into one metadata dict
- **THEN** final stored chunks SHALL receive the declared aggregate according to the aggregation rule
- **AND** diagnostics/documentation SHALL identify the persisted granularity as file aggregate
