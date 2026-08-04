## MODIFIED Requirements

### Requirement: Reader factory SHALL be extensible without modifying ingestion code

The system SHALL expose a `BaseReader` protocol in `src/rag_mcp/integrations/pdf/base.py` defining the contract every PDF adapter must implement. New adapters SHALL be addable by creating a single module in `src/rag_mcp/integrations/pdf/` and registering it in the factory's resolution map. The ingestion loader call site SHALL NOT require modification when a new reader is added; only `config.py` (env var accepted values) and the factory map SHALL change.

The former `src/rag_mcp/readers/` package SHALL resolve via a deprecated re-export shim (removal scheduled for v2.0.0) so existing `from rag_mcp.readers import ...` consumers keep working with a `DeprecationWarning`.

#### Scenario: Adding a new adapter
- **WHEN** a developer creates `src/rag_mcp/integrations/pdf/spdf.py` implementing `BaseReader` and adds `"spdf"` to the accepted values in `config.py`
- **THEN** no other source file SHALL require modification to make `PDF_READER=spdf` functional

#### Scenario: Factory returns adapter, not reader instance
- **WHEN** `get_pdf_reader()` is called
- **THEN** it SHALL return a callable (typically a LlamaIndex-compatible reader class or a closure wrapping one), not a parsed-document instance, so `SimpleDirectoryReader(file_extractor={".pdf": get_pdf_reader()})` works at the ingestion loader call site

#### Scenario: Legacy readers import path resolves
- **WHEN** code executes `from rag_mcp.readers import get_pdf_reader` (or any other former `readers/` export)
- **THEN** the import SHALL succeed via the deprecated shim
- **AND** a `DeprecationWarning` SHALL be emitted naming `rag_mcp.integrations.pdf` as the new path

#### Scenario: Factory dispatch behaviour unchanged
- **WHEN** the `auto` backend resolution runs after the relocation
- **THEN** backend preference order, graceful fallback, and `PDF_READER` env var handling SHALL be identical to the pre-refactor factory (ADR-020 amended for location only)
