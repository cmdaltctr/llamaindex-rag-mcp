# large-collection-statistics Specification

## Purpose

Define paginated metadata scan behaviour so document and collection statistics remain accurate when a ChromaDB collection exceeds the configured scan page size, and centralise the page-size configuration.

## Requirements
### Requirement: Paginated metadata scans for document statistics
The system SHALL compute indexed document statistics by scanning ChromaDB metadata with pagination rather than a single hardcoded maximum result limit.

#### Scenario: Listing documents above one scan page
- **WHEN** a collection contains more chunks than the configured metadata scan page size
- **THEN** `list_documents(collection_name=...)` SHALL include chunks from all pages
- **THEN** each returned document chunk count SHALL reflect the complete collection, not only the first page

#### Scenario: Listing collections above one scan page
- **WHEN** `list_collections()` inspects a collection with more chunks than the configured metadata scan page size
- **THEN** `document_count` SHALL be computed from all metadata pages
- **THEN** `chunk_count` SHALL still reflect the ChromaDB collection count

### Requirement: Configurable metadata scan page size
The system SHALL define one central configuration value for ChromaDB metadata scan page size.

#### Scenario: Page size overridden in tests or environment
- **WHEN** `CHROMA_SCAN_PAGE_SIZE` is set to a positive integer
- **THEN** all paginated metadata scans SHALL use that value as their page size
- **THEN** no source file SHALL contain a separate hardcoded `limit=10000` for these scans
