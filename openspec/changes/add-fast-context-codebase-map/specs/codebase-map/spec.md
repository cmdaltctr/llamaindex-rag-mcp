## Purpose

Define the codebase map generation and MCP tool contract — Magika file-type inventory, graph assembly from code and document sub-graphs, compact map formatting, caching, and the `get_codebase_map` MCP tool interface.

## Requirements

### Requirement: Magika file-type inventory

The system SHALL scan a project directory using the Magika CLI binary and produce a file-type inventory grouping every file by `group/label` (e.g., `code/typescript`, `document/markdown`, `config/yaml`). The inventory SHALL include file counts per type, representative glob patterns, and binary file warnings. When Magika is not installed, the system SHALL fall back to `Path.suffix`-based detection and log a warning.

#### Scenario: Magika CLI available

- **WHEN** `get_codebase_map(path="/project")` is called and the `magika` CLI is on `$PATH`
- **THEN** the system SHALL run `magika -r <path> --jsonl` and parse each line's `output.group`, `output.label`, `output.is_text`, and `path` fields
- **THEN** the inventory SHALL group files as `{group}/{label}: {count} files ({glob_pattern})`

#### Scenario: Magika CLI not installed

- **WHEN** `get_codebase_map(path="/project")` is called and the `magika` CLI is NOT on `$PATH`
- **THEN** the system SHALL fall back to `Path.suffix`-based detection
- **THEN** the system SHALL log a warning indicating Magika is unavailable
- **THEN** the inventory SHALL still group files by inferred type, using suffix-to-group mapping

#### Scenario: Binary files flagged with warning

- **WHEN** Magika detects a file with `output.is_text == false` (e.g., executables, images, archives)
- **THEN** the inventory SHALL include a `⚠ BINARY: <filename> (<label>)` warning line
- **THEN** binary files SHALL NOT be counted in code/document/config groups

#### Scenario: File type mismatch detected

- **WHEN** Magika's detected content type differs from the file extension (e.g., `.txt` detected as JavaScript)
- **THEN** the inventory SHALL include a `⚠ MISMATCH: <filename> → detected as <label>` warning line

### Requirement: Graph assembly from sub-graphs

The system SHALL assemble a unified codebase graph by combining the code graph (from `code_graph` module) and the document graph (from `doc_graph` module) with cross-links between them. The assembly SHALL produce code communities, document communities, cross-links, and hub identification.

#### Scenario: Full assembly with both sub-graphs

- **WHEN** both code files and document files exist in the project
- **THEN** the codebase map SHALL include code communities (from tree-sitter + Louvain), document communities (from embedding similarity + Louvain), and cross-links connecting related code and document clusters

#### Scenario: Code-only project (no documents)

- **WHEN** the project contains only code files (no markdown, PDF, or other documents)
- **THEN** the codebase map SHALL include code communities and hubs but omit the document communities and cross-links sections

#### Scenario: Document-only project (no code)

- **WHEN** the project contains only documents (no code files)
- **THEN** the codebase map SHALL include document communities but omit the code communities, hubs, and cross-links sections

### Requirement: Compact map output format

The `get_codebase_map` tool SHALL return a compact text output targeting 500–800 tokens. The output SHALL include sections for File Types, Code Communities, Document Communities, Cross-links, and Architectural Hubs. Each section SHALL use counts and representative names, not exhaustive file lists.

#### Scenario: Output within token budget

- **WHEN** `get_codebase_map` is called on a 500-file project
- **THEN** the output SHALL be no more than 800 tokens (approximately 3200 characters)
- **THEN** communities with more than 4 representative files SHALL show only the top 4 by centrality

#### Scenario: Community truncation

- **WHEN** a code community contains 20+ files
- **THEN** the output SHALL show the community name, total file count, edge count, and the top 4 most central files
- **THEN** remaining files SHALL be indicated by `... and N more`

### Requirement: Per-project caching keyed by git commit

The codebase map SHALL be cached at `<project>/.opencode/codebase-graph.json` and `<project>/.opencode/magika-inventory.json`. The cache SHALL be keyed by `git rev-parse HEAD`. When the cache key matches, the tool SHALL return the cached result without recomputation.

#### Scenario: Cache hit

- **WHEN** `get_codebase_map(path="/project", refresh=False)` is called
- **AND** `.opencode/codebase-graph.json` exists with a `commit_hash` field matching current `git rev-parse HEAD`
- **THEN** the system SHALL return the cached map without running Magika, tree-sitter, or similarity computation

#### Scenario: Cache miss (new commit)

- **WHEN** `get_codebase_map(path="/project", refresh=False)` is called
- **AND** `.opencode/codebase-graph.json` exists but its `commit_hash` differs from current `git rev-parse HEAD`
- **THEN** the system SHALL rebuild the full codebase map and update the cache

#### Scenario: Force refresh

- **WHEN** `get_codebase_map(path="/project", refresh=True)` is called
- **THEN** the system SHALL rebuild the codebase map regardless of cache state

#### Scenario: No git repository

- **WHEN** `get_codebase_map` is called on a directory that is not a git repository
- **THEN** the system SHALL build the map without caching
- **THEN** the system SHALL log an informational message that caching is disabled (no git)

### Requirement: MCP tool interface

The `get_codebase_map` MCP tool SHALL accept `path` (string, default `"."`) and `refresh` (boolean, default `False`) parameters. The tool SHALL return a text string with the formatted codebase map. The tool SHALL have `ToolAnnotations` with `readOnlyHint=True` and `destructiveHint=False`.

#### Scenario: Default invocation

- **WHEN** an MCP client calls `get_codebase_map()` with no arguments
- **THEN** the tool SHALL scan the current working directory
- **THEN** the tool SHALL return a formatted text map

#### Scenario: Error handling

- **WHEN** `get_codebase_map` encounters an error (permission denied, path not found)
- **THEN** the tool SHALL return `{"status": "error", "message": "<description>"}` as a JSON string
- **THEN** the tool SHALL NOT raise an exception

#### Scenario: Tool annotations present

- **WHEN** the `get_codebase_map` tool is registered with the MCP server
- **THEN** it SHALL have `ToolAnnotations(readOnlyHint=True, destructiveHint=False)`
