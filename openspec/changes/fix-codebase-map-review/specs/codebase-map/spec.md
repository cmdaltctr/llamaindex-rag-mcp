## ADDED Requirements

### Requirement: Path boundary validation

The `get_codebase_map` tool SHALL validate that the resolved path is within the current working directory (project root) before scanning. Paths that resolve outside the project root SHALL be rejected with an error dict, not scanned. The check SHALL use `Path.resolve().relative_to(Path.cwd())` and catch `ValueError` to detect traversal.

#### Scenario: Absolute path outside project rejected

- **WHEN** `get_codebase_map(path="/etc")` is called
- **THEN** the tool SHALL return `{"status": "error", "message": "..."}` without scanning
- **THEN** `build_codebase_map` SHALL NOT be invoked

#### Scenario: Dotdot escape rejected

- **WHEN** `get_codebase_map(path="../secret")` is called from inside a project directory
- **AND** `../secret` resolves to an existing directory outside the project root
- **THEN** the tool SHALL return `{"status": "error", "message": "..."}` without scanning

#### Scenario: Current directory allowed

- **WHEN** `get_codebase_map(path=".")` is called
- **THEN** the tool SHALL scan the current working directory normally

#### Scenario: Subdirectory of project allowed

- **WHEN** `get_codebase_map(path="src/rag_mcp")` is called from the project root
- **THEN** the tool SHALL scan the subdirectory normally (it resolves within the project root)

### Requirement: File count and depth limits

The system SHALL enforce configurable limits on the number of files scanned (`CODEBASE_MAP_MAX_FILES`, default 5000) and the maximum directory depth (`CODEBASE_MAP_MAX_DEPTH`, default 10). When limits are exceeded, the system SHALL truncate scanning, log a warning, and continue with the truncated result. The Magika subprocess SHALL have a timeout of 30 seconds; if exceeded, the system SHALL fall back to suffix-based detection.

#### Scenario: Large project truncated

- **WHEN** a project contains 10,000 files and `CODEBASE_MAP_MAX_FILES=5000`
- **THEN** the system SHALL scan only the first 5,000 files
- **THEN** a warning SHALL be logged indicating truncation

#### Scenario: Magika subprocess timeout

- **WHEN** the Magika CLI takes longer than 30 seconds to complete
- **THEN** the system SHALL terminate the subprocess and fall back to suffix-based detection
- **THEN** a warning SHALL be logged

### Requirement: Cache files in gitignore

The cache files `.opencode/codebase-graph.json` and `.opencode/magika-inventory.json` SHALL be listed in `.gitignore` to prevent accidental commits.

#### Scenario: Cache files ignored by git

- **WHEN** `git status` is run after a codebase map has been generated
- **THEN** `.opencode/codebase-graph.json` and `.opencode/magika-inventory.json` SHALL NOT appear as untracked files

### Requirement: Aligned directory exclusions

The Magika scanner and suffix scanner SHALL use the same set of excluded directories (e.g., `.git`, `node_modules`, `__pycache__`, `.venv`, `.pytest_cache`, `dist`, `build`). This ensures consistent file inventories regardless of which scanner is active.

#### Scenario: Same exclusions for both scanners

- **WHEN** a project contains `node_modules/` and `.git/` directories
- **AND** Magika is installed
- **THEN** files in `node_modules/` and `.git/` SHALL NOT appear in the inventory
- **WHEN** the same project is scanned with the suffix fallback (Magika not installed)
- **THEN** files in `node_modules/` and `.git/` SHALL also NOT appear in the inventory
