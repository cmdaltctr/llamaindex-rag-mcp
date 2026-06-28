## Purpose

Define the document graph construction contract — embedding-based similarity edges, metadata category edges, heading hierarchy edges, Louvain community detection for documents, and cross-links between document and code communities.

## Requirements

### Requirement: Embedding similarity edges

After all document chunks are embedded in ChromaDB, the system SHALL compute pairwise cosine similarity between document chunk embeddings. Edges SHALL be drawn between chunks whose similarity exceeds `DOC_SIMILARITY_THRESHOLD` (configurable, default 0.85). Similarity computation SHALL use the existing embeddings from ChromaDB — no new LLM calls.

#### Scenario: High-similarity documents connected

- **WHEN** chunk A ("authentication flow") and chunk B ("login endpoint") have cosine similarity 0.91
- **AND** `DOC_SIMILARITY_THRESHOLD` is 0.85
- **THEN** an edge SHALL be added between chunk A and chunk B with `relation="similar"` and `weight=0.91`

#### Scenario: Below-threshold documents not connected

- **WHEN** chunk A and chunk B have cosine similarity 0.72
- **AND** `DOC_SIMILARITY_THRESHOLD` is 0.85
- **THEN** no edge SHALL exist between chunk A and chunk B

#### Scenario: Within-type pair computation only

- **WHEN** computing document similarity
- **THEN** the system SHALL only compute similarity between document-type chunks (not code chunks)
- **THEN** this SHALL keep computation efficient (500 doc chunks → 124,750 pairs, sub-second)

### Requirement: Metadata category edges

The system SHALL build edges between document chunks that share the same normalised `category` metadata (from the existing `metadata_extractor`). Shared keyword edges SHALL be added with lower weight.

#### Scenario: Same category connected

- **WHEN** chunk A and chunk B both have `category="security"`
- **THEN** an edge SHALL be added with `relation="category"` and `weight=1.0`

#### Scenario: Shared keywords connected with lower weight

- **WHEN** chunk A has `keywords=["redis", "session", "auth"]` and chunk B has `keywords=["redis", "cache", "ttl"]`
- **THEN** an edge SHALL be added with `relation="keyword"`, `weight=0.5`, and `shared_keywords=["redis"]`

#### Scenario: No shared metadata

- **WHEN** two chunks share neither category nor keywords
- **THEN** no metadata-based edge SHALL exist between them (similarity edges may still exist)

### Requirement: Heading hierarchy edges (document structure)

For markdown files parsed by `MarkdownNodeParser`, the system SHALL build parent-child edges from the heading hierarchy. In hybrid mode with Azure Document Intelligence, the system SHALL use Azure's paragraph role annotations (title, section heading) for the same purpose.

#### Scenario: Markdown heading hierarchy

- **WHEN** a markdown file has `# API` (chunk 2) with children `## Authentication` (chunk 3) and `## Rate Limiting` (chunk 4)
- **THEN** edges SHALL exist: chunk 2 → chunk 3 and chunk 2 → chunk 4, with `relation="heading_child"`

#### Scenario: Azure paragraph roles

- **WHEN** Azure Document Intelligence returns paragraphs with roles `title`, `sectionHeading`, and `content`
- **THEN** the system SHALL build parent-child edges based on the role hierarchy

### Requirement: Document community detection

The system SHALL run `networkx.algorithms.community.louvain_communities()` on the combined document graph (similarity + category + heading edges) to identify topic clusters.

#### Scenario: Document communities identified

- **WHEN** the document graph contains 20+ chunks with similarity and category edges
- **THEN** Louvain SHALL partition the graph into topic communities
- **THEN** each community SHALL include the chunk count, document count, and representative category

#### Scenario: Single document (no communities)

- **WHEN** only one document has been ingested
- **THEN** the system SHALL return a single community containing all its chunks

### Requirement: Cross-links between code and document communities

The system SHALL detect connections between code communities and document communities using filename matching, symbol matching, and category keyword overlap.

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
