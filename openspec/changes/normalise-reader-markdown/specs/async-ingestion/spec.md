# Spec Delta

## ADDED Requirements

### Requirement: Reader-output normalisation SHALL participate in the complete index identity

The index-shaping identity SHALL include the reader-output normaliser version and the resolved `ingestion.normalise_reader_output` value. Both SHALL enter the existing `source_index_identity` payload. A second identity mechanism SHALL NOT be introduced. The identity schema SHALL advance from 5 to 6.

The normaliser version SHALL change whenever a normalisation rule changes. Following the existing conservative rule, both inputs SHALL be hashed for every source, whether or not the source is a PDF.

#### Scenario: Normaliser version change forces reprocessing

- **GIVEN** a previously indexed, byte-identical PDF
- **WHEN** the normaliser version changes and ingestion runs again
- **THEN** the source SHALL NOT be reported as `skipped_unchanged`
- **AND** it SHALL be re-chunked, re-embedded, and replaced through the existing failure-safe replacement path

#### Scenario: Toggling normalisation forces reprocessing

- **GIVEN** a previously indexed, byte-identical PDF
- **WHEN** `ingestion.normalise_reader_output` changes and ingestion runs again
- **THEN** the source SHALL NOT be reported as `skipped_unchanged`

#### Scenario: Sources indexed under schema 5 reprocess once

- **GIVEN** a source indexed under identity schema 5
- **WHEN** ingestion runs with schema 6
- **THEN** the source SHALL NOT be reported as `skipped_unchanged`
- **AND** a second ingestion run with no other change SHALL report it as `skipped_unchanged`

#### Scenario: Unchanged normaliser inputs still skip

- **GIVEN** a previously indexed, byte-identical source
- **WHEN** ingestion runs again with the normaliser version and the resolved setting unchanged
- **THEN** the source SHALL be reported as `skipped_unchanged`
