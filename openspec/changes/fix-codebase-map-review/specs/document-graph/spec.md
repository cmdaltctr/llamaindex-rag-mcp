## MODIFIED Requirements

### Requirement: Document community detection

The system SHALL run `networkx.algorithms.community.louvain_communities()` on the combined document graph (similarity + category + heading edges) to identify topic clusters. The document graph SHALL be constructed from the actual ChromaDB collection containing embedded document chunks — not from `None`. If the ChromaDB collection does not exist or is empty, the system SHALL skip document graph construction gracefully and log a warning.

#### Scenario: Document communities identified

- **WHEN** the document graph contains 20+ chunks with similarity and category edges
- **THEN** Louvain SHALL partition the graph into topic communities
- **THEN** each community SHALL include the chunk count, document count, and representative category

#### Scenario: Single document (no communities)

- **WHEN** only one document has been ingested
- **THEN** the system SHALL return a single community containing all its chunks

#### Scenario: No ChromaDB collection

- **WHEN** `build_codebase_map()` is called and no ChromaDB collection exists (no documents ingested)
- **THEN** the system SHALL log a warning indicating the collection is unavailable
- **THEN** document communities and cross-links SHALL be omitted from the codebase map
- **THEN** code communities and file inventory SHALL still appear in the map

### Requirement: Cross-links between code and document communities

The system SHALL detect connections between code communities and document communities using filename matching, symbol matching, and category keyword overlap. Cross-link detection SHALL reuse the already-constructed code graph instead of building it a second time.

#### Scenario: Filename match

- **WHEN** a document chunk in `api-guide.md` contains the text `auth/login.ts`
- **AND** `auth/login.ts` is a file in the code graph
- **THEN** a cross-link SHALL be created between the document chunk and the code file

#### Scenario: Symbol match

- **WHEN** a document heading mentions `UserService`
- **AND** `UserService` is an exported class in the code graph
- **THEN** a cross-link SHALL be created between the document chunk and the code file containing `UserService`

#### Scenario: Minimum path depth for filename matching

- **WHEN** a document mentions the word "config" generically (not as a file path)
- **THEN** no cross-link SHALL be created
- **THEN** filename matching SHALL require at least 2 path segments (e.g., `src/config`) to reduce false positives

#### Scenario: Category keyword overlap

- **WHEN** a code community's files are predominantly in a directory named `auth/`
- **AND** a document community has `category="security"` with keywords including `auth`
- **THEN** a community-level cross-link SHALL be created with `relation="keyword_overlap"`

#### Scenario: Code graph not rebuilt for cross-links

- **WHEN** cross-link detection runs in `build_codebase_map()`
- **THEN** it SHALL reuse the code graph already constructed for code community detection
- **THEN** `build_code_graph()` SHALL NOT be called a second time
