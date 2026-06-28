# ADR-022: Code graph via tree-sitter AST extraction

**Date:** 2026-01-15  
**Status:** Proposed  
**Change:** `add-fast-context-codebase-map`

## Context

The `get_codebase_map` MCP tool needs to construct a structural graph of code files to detect communities, hubs, and bridges. This requires extracting imports, exports, class definitions, and inheritance relationships from source files across multiple programming languages.

## Decision

Use **tree-sitter** for AST extraction, combined with **NetworkX** for graph construction and **Louvain community detection** for clustering.

### Rationale

1. **Tree-sitter** provides language-agnostic parsing with grammars for 30+ languages via `tree-sitter-language-pack`. It is the same engine used by LlamaIndex's `CodeSplitter`, ensuring consistency between chunking and graph extraction.

2. **NetworkX** is a mature, pure-Python graph library with built-in Louvain community detection, betweenness centrality, and directed graph support. No external dependencies beyond NumPy (already installed).

3. **Regex-based extraction** is used alongside tree-sitter for robustness. Tree-sitter validates parseability, while regex handles the actual extraction of imports, classes, and functions. This avoids language-specific node traversal code for each supported language.

4. **Louvain community detection** partitions the graph into clusters of related files. Communities with fewer than 5 files are merged into a single community to avoid over-fragmentation.

5. **Hub detection** uses the more inclusive of: top 10% in-degree, or in-degree ≥ 5. This ensures small codebases still identify hubs.

## Consequences

- **Positive:** Deterministic, no LLM involvement. Works offline. Supports 20+ languages via Magika label mapping.
- **Positive:** Regex extraction is more resilient to syntax variations than pure AST traversal.
- **Negative:** Regex extraction may miss edge cases (e.g., dynamic imports, metaprogramming).
- **Negative:** Import resolution is heuristic — only relative imports and same-directory module imports are resolved.
- **Mitigation:** Unresolved imports are silently skipped; the graph still captures resolved relationships.

## Alternatives Considered

- **Pure tree-sitter node traversal:** More accurate but requires per-language visitor code. Rejected for maintenance burden.
- **LSP-based extraction:** Most accurate but requires running language servers. Rejected for deployment complexity.
- **LLM-based extraction:** Non-deterministic and requires network access. Rejected — violates the "no LLM for graph construction" invariant.
