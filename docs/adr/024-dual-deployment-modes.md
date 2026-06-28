# ADR-024: Dual deployment modes — Full Local vs Hybrid

**Date:** 2026-01-15  
**Status:** Proposed  
**Change:** `add-fast-context-codebase-map`

## Context

The codebase map feature introduces an optional Azure Document Intelligence backend for document parsing. This creates two deployment modes:
1. **Full Local** — all parsing done locally (LiteParse → pypdfium2 → pypdf chain)
2. **Hybrid** — documents parsed by Azure Document Intelligence, with local fallback

The system must gracefully handle both modes without requiring Azure credentials for local-only deployments.

## Decision

Use a `DOCUMENT_BACKEND` environment variable in `config.py` to select the parsing backend:

- `"local"` (default): Uses the existing LiteParse → pypdfium2 → pypdf reader chain.
- `"azure"`: Uses Azure Document Intelligence for PDF/DOCX files, with automatic fallback to the local chain on any error.

### Azure SDK as Optional Dependency

`azure-ai-documentintelligence` is an optional dependency under the `azure` extra:
```bash
uv sync --extra azure
```

The SDK is imported **lazily** at runtime in `azure_reader.py` — never at module top-level. This ensures the module loads even when the Azure SDK is not installed.

### Config-Time Validation

`config.py` validates Azure credentials at import time. If `DOCUMENT_BACKEND=azure` but `AZURE_DOC_INTELLIGENCE_ENDPOINT` or `AZURE_DOC_INTELLIGENCE_KEY` is missing, the system logs a warning and falls back to `"local"` mode.

### Runtime Fallback

`azure_reader.py` implements a three-tier fallback:
1. **ImportError** (SDK not installed) → immediate fallback to local chain
2. **Network error** → retry once after 5s, then fallback to local chain
3. **Any other error** → fallback to local chain

### Table-Aware Chunking

Azure Document Intelligence returns structured tables. These are kept as intact chunks with `content_type: "table"` metadata. Large tables (>50 rows) are split into row groups to stay within chunk size limits.

## Consequences

- **Positive:** Local-only deployments work without any Azure dependency or credentials.
- **Positive:** Hybrid deployments get superior table extraction and heading hierarchy.
- **Positive:** Graceful fallback ensures the system never fails completely — worst case uses local chain.
- **Negative:** Two code paths to maintain (Azure and local).
- **Mitigation:** Azure logic is isolated in `azure_reader.py`; ingestion.py has a single branch point.

## Alternatives Considered

- **Always use Azure:** Rejected — violates the "no cloud services" hard boundary for local deployments.
- **Plugin-based backend selection:** Rejected — adds complexity for a simple two-option choice.
- **Google Document AI / AWS Textract:** Rejected — Azure was chosen for existing organisational access.
