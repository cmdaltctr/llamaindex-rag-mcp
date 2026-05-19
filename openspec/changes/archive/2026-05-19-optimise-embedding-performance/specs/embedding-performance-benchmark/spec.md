## ADDED Requirements

### Requirement: Benchmark subcommand
The system SHALL provide a `rag-mcp benchmark` CLI subcommand that measures end-to-end embedding throughput.

#### Scenario: Run benchmark with custom text
- **WHEN** user runs `rag-mcp benchmark --text "Sample document text" --iterations 10`
- **THEN** the tool SHALL print chunks/second, total time, and model name to stderr
- **THEN** the tool SHALL NOT modify any ChromaDB collection

#### Scenario: Run benchmark with file input
- **WHEN** user runs `rag-mcp benchmark --file /path/to/document.pdf`
- **THEN** the tool SHALL read, chunk, and embed the file using the current `EMBED_MODEL` settings
- **THEN** the tool SHALL print chunks/second, total time, model name, and vector dimension

### Requirement: Benchmark output format
The benchmark SHALL output a structured result table with columns for model name, chunk count, batch size, concurrency, total time, chunks/sec, and vector dimension.

#### Scenario: Output includes key metrics
- **WHEN** the benchmark completes
- **THEN** the output SHALL include: model name, chunk count, total time (seconds), throughput (chunks/sec), and vector dimension

### Requirement: Benchmark is non-destructive
The benchmark SHALL NOT write any data to ChromaDB.

#### Scenario: No side effects
- **WHEN** the benchmark finishes
- **THEN** no collections SHALL be created or modified in the ChromaDB store
