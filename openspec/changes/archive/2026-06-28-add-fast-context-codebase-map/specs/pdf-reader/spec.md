## MODIFIED Requirements

### Requirement: Auto resolution SHALL probe backends in preference order with graceful fallback

When `PDF_READER=auto` (the proposed default after Experiment 11 passes), the system SHALL probe backend imports in the order `liteparse → pypdfium2 → pypdf` and SHALL select the first importable backend. PyMuPDF is structurally excluded from accepted values entirely (AGPL-3 incompatibility — see design.md Decision 4). If no optional backend is installed, the system SHALL fall back to `pypdf` (always available via `llama-index-readers-file`). **When `DOCUMENT_BACKEND=azure` is configured, the PDF reader chain SHALL be bypassed for document files — Azure Document Intelligence becomes the primary parser, with the existing reader chain as fallback only when Azure fails.**

#### Scenario: LiteParse installed and selected by auto

- **WHEN** `PDF_READER=auto` is set and the `liteparse` package is importable
- **THEN** `RESOLVED_PDF_READER` SHALL equal `"liteparse"`

#### Scenario: LiteParse missing, pypdfium2 installed

- **WHEN** `PDF_READER=auto` is set, `liteparse` is not importable, and `pypdfium2` is importable
- **THEN** `RESOLVED_PDF_READER` SHALL equal `"pypdfium2"` and the system SHALL log an informational message that LiteParse was not available

#### Scenario: No optional backend installed

- **WHEN** `PDF_READER=auto` is set and neither `liteparse` nor `pypdfium2` is importable
- **THEN** `RESOLVED_PDF_READER` SHALL equal `"pypdf"` and ingestion SHALL behave identically to the pre-change pipeline

#### Scenario: Explicit backend requested but not installed

- **WHEN** `PDF_READER=liteparse` is set but `liteparse` is not importable
- **THEN** the system SHALL log an error naming the missing package and SHALL fall back to `pypdf` rather than raising

#### Scenario: Azure backend bypasses PDF reader chain

- **WHEN** `DOCUMENT_BACKEND=azure` is configured and a PDF file is ingested
- **THEN** the PDF reader chain (`PDF_READER` / `RESOLVED_PDF_READER`) SHALL NOT be invoked
- **THEN** Azure Document Intelligence SHALL parse the document directly

#### Scenario: Azure failure falls back to PDF reader chain

- **WHEN** `DOCUMENT_BACKEND=azure` is configured but Azure is unreachable
- **THEN** the system SHALL fall back to the `RESOLVED_PDF_READER` chain (LiteParse → pypdfium2 → pypdf)
- **THEN** a warning SHALL be logged
