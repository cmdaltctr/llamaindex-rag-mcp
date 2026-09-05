## ADDED Requirements

### Requirement: New input-quality inputs SHALL participate in the complete index identity

The index-shaping identity SHALL cover every input this change adds that can alter emitted chunk text or stored vectors. The identity SHALL include the configured embedding-tokenizer identity and revision, the **resolved** active Markdown splitter (model-token-aware or legacy fallback), the OCR routing configuration, and the **resolved** OCR fallback capability.

Resolved values SHALL be recorded, not only configured values. A configured tokenizer that cannot be loaded runs the legacy splitter, and a configured OCR gate without an installed OCR stack runs the fast path alone; recording only the configuration would leave both degraded results indistinguishable from the intended ones.

These inputs SHALL enter the existing `source_index_identity` payload and its failure-safe replacement path. A second identity mechanism SHALL NOT be introduced. The payload's schema version SHALL be raised once for the new shape.

Inclusion SHALL follow the existing conservative rule for parser and chunking selectors: an input is hashed whether or not a given file type uses it, because unnecessary reprocessing is safer than reusing stale chunks.

The optional query-only embedding instruction SHALL NOT participate in this identity.

#### Scenario: Tokenizer identity change forces reprocessing

- **GIVEN** a previously indexed, byte-identical Markdown source
- **WHEN** the configured embedding-tokenizer identity or revision changes and ingestion runs again
- **THEN** the source SHALL NOT be reported as `skipped_unchanged`
- **AND** it SHALL be re-chunked, re-embedded, and replaced through the existing failure-safe replacement path

#### Scenario: Degraded chunking recovers when the tokenizer becomes resolvable

- **GIVEN** a byte-identical Markdown source previously indexed while the configured tokenizer could not be resolved, so the legacy splitter produced its chunks
- **WHEN** the tokenizer becomes resolvable and ingestion runs again with no other change
- **THEN** the resolved active splitter SHALL differ from the stored index identity
- **AND** the source SHALL NOT be reported as `skipped_unchanged`

#### Scenario: Degraded extraction recovers when the OCR capability becomes available

- **GIVEN** a byte-identical PDF previously indexed while the optional OCR capability was absent, so it retained the partial `pdf-inspector` extraction
- **WHEN** the OCR capability becomes available and ingestion runs again with no other change
- **THEN** the resolved OCR capability SHALL differ from the stored index identity
- **AND** the source SHALL NOT be reported as `skipped_unchanged`
- **AND** it SHALL be re-extracted through the routing seam rather than remaining permanently on its degraded chunks

#### Scenario: OCR routing configuration change forces reprocessing

- **GIVEN** a previously indexed, byte-identical PDF
- **WHEN** the calibrated OCR routing configuration changes and ingestion runs again
- **THEN** the source SHALL NOT be reported as `skipped_unchanged`

#### Scenario: Query instruction change alone does not force reprocessing

- **GIVEN** a previously indexed, byte-identical source
- **WHEN** only the embedding query instruction changes and ingestion runs again
- **THEN** the stored index identity SHALL be unchanged
- **AND** the source SHALL be reported as `skipped_unchanged`

#### Scenario: Unchanged input-quality inputs still skip

- **GIVEN** a previously indexed, byte-identical source
- **WHEN** ingestion runs again with the tokenizer identity, resolved splitter, OCR routing configuration, and resolved OCR capability all unchanged
- **THEN** the source SHALL be reported as `skipped_unchanged`
