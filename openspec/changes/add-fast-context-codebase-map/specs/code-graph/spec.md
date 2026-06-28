## Purpose

Define the code graph construction contract — tree-sitter AST extraction for code files, NetworkX directed graph construction, Louvain community detection, and hub identification.

## Requirements

### Requirement: tree-sitter AST extraction

The system SHALL parse each code file using tree-sitter to extract structural relationships: imports, exports, function definitions, class definitions, class inheritance, and optionally function calls. The extraction SHALL be deterministic — no LLM involvement. The system SHALL support all languages provided by `tree-sitter-language-pack`.

#### Scenario: TypeScript import extraction

- **WHEN** a TypeScript file containing `import { Auth } from './auth'` is processed
- **THEN** the extractor SHALL produce an edge from the importing file to `auth.ts` (or `auth/index.ts`) with `relation="import"`

#### Scenario: Python import extraction

- **WHEN** a Python file containing `from rag_mcp.config import TOP_K` is processed
- **THEN** the extractor SHALL produce an edge from the importing file to `config.py` with `relation="import"`

#### Scenario: Class inheritance extraction

- **WHEN** a file containing `class Admin extends User` (or `class Admin(User)` in Python) is processed
- **THEN** the extractor SHALL produce an edge from `Admin` to `User` with `relation="inheritance"`

#### Scenario: Unsupported language

- **WHEN** a code file in a language not covered by `tree-sitter-language-pack` is encountered
- **THEN** the extractor SHALL skip AST extraction for that file
- **THEN** the file SHALL still appear in the Magika inventory but not in the code graph
- **THEN** a debug-level log SHALL indicate the unsupported language

#### Scenario: Malformed source file

- **WHEN** a code file has syntax errors that prevent tree-sitter from producing a complete AST
- **THEN** the extractor SHALL extract whatever partial relationships the tree can provide
- **THEN** the extractor SHALL NOT raise — it SHALL log a warning and continue

### Requirement: NetworkX directed graph construction

The system SHALL build a `networkx.DiGraph` where nodes represent files and edges represent structural relationships (imports, inheritance, calls). Each node SHALL carry metadata: `type` (literal `"file"`), `content_type` (Magika label, e.g., `code/typescript`), `functions` (list of defined function names), and `imports` (list of imported file paths).

#### Scenario: Node metadata

- **WHEN** `src/auth/login.ts` is added to the graph
- **THEN** the node SHALL have `type="file"`, `content_type="code/typescript"`, and lists of functions and imports extracted by tree-sitter

#### Scenario: Edge metadata

- **WHEN** an import relationship is detected from `login.ts` to `session.ts`
- **THEN** the edge SHALL have `relation="import"` and `confidence="exact"`

#### Scenario: Self-import ignored

- **WHEN** a file imports itself (circular or re-export)
- **THEN** no self-loop edge SHALL be added to the graph

### Requirement: Louvain community detection

The system SHALL run `networkx.algorithms.community.louvain_communities()` on the code graph to identify clusters of related files. Each community SHALL be labelled with representative file names and shared keywords.

#### Scenario: Communities identified

- **WHEN** the code graph contains 50+ files with import relationships
- **THEN** `louvain_communities()` SHALL partition the graph into 2+ communities
- **THEN** each community SHALL include a list of member files and a count of internal edges

#### Scenario: Small graph (fewer than 5 files)

- **WHEN** the code graph contains fewer than 5 files
- **THEN** the system SHALL return a single community containing all files
- **THEN** community detection SHALL NOT raise

### Requirement: Hub detection

The system SHALL identify hub nodes — files with high in-degree (imported by many other files). A hub is defined as any node in the top 10% of in-degree, or any node with in-degree ≥ 5, whichever is more inclusive.

#### Scenario: Hub identified

- **WHEN** `src/config/database.ts` is imported by 14 other files
- **THEN** it SHALL appear in the hubs list with its in-degree count

#### Scenario: No hubs in flat project

- **WHEN** no file has in-degree ≥ 5 and all files have similar in-degree
- **THEN** the hubs list SHALL be empty
- **THEN** the codebase map SHALL omit the hubs section

### Requirement: Bridge node detection

The system SHALL identify bridge nodes — files that connect otherwise separate communities. Bridge nodes SHALL be detected by high betweenness centrality.

#### Scenario: Bridge between communities

- **WHEN** a file is imported by members of two different communities but is not central to either
- **THEN** it SHALL be flagged as a bridge node between those communities
