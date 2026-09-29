# Spec Delta

## Purpose

Send born-digital maths pages, whose equations the text readers cannot extract faithfully, to the OCR routes, which read equations from the page image. A page counts as maths from its font evidence, whether or not the maths font carries a Unicode map.

## ADDED Requirements

### Requirement: Maths pages SHALL be detected from font evidence

When maths routing is enabled, the pdf-inspector path SHALL flag a page as a maths page when the page uses a font from the maths-font list. It SHALL flag the page whether or not that font carries a Unicode map, because a Unicode map restores characters but not equation structure. Font names SHALL be matched after any subset prefix. Fonts used through nested form objects on the page SHALL count.

The maths-font list SHALL be closed and versioned. It SHALL contain these families:

- Computer Modern maths: CMMI, CMMIB, CMSY, CMBSY and CMEX, at any design size;
- Latin Modern maths: the LMMathItalic, LMMathSymbols and LMMathExtension Type 1 families, and Latin Modern Math;
- AMS and Euler symbol fonts: MSAM, MSBM, EUFM, EUSM and EUEX, at any design size;
- OpenType maths fonts: Cambria Math, STIX Math, STIX Two Math, XITS Math, the TeX Gyre maths fonts, Libertinus Math, Asana Math and Fira Math.

A change to the list SHALL change the detector version.

Detection SHALL be deterministic. It SHALL read font resources only. It SHALL NOT render pages, run OCR, or call a language model or network service. A PDF whose font resources cannot be read SHALL flag no pages and SHALL NOT fail the file.

#### Scenario: A LaTeX maths page without a Unicode map is flagged

- **GIVEN** a born-digital page that uses CMMI10 and CMEX10 with no Unicode map
- **WHEN** the page is inspected
- **THEN** the page SHALL be flagged as a maths page

#### Scenario: A maths font with a Unicode map is flagged

- **GIVEN** a page whose CMMI10 font carries a Unicode map
- **WHEN** the page is inspected
- **THEN** the page SHALL be flagged as a maths page

#### Scenario: A Word equation page is flagged

- **GIVEN** a born-digital page that uses Cambria Math
- **WHEN** the page is inspected
- **THEN** the page SHALL be flagged as a maths page

#### Scenario: Prose-only pages are not flagged

- **GIVEN** a born-digital page that uses only CMR or Times text fonts
- **WHEN** the page is inspected
- **THEN** the page SHALL NOT be flagged

#### Scenario: Unreadable font resources flag nothing

- **GIVEN** a PDF whose font resources raise an error when read
- **WHEN** the PDF is inspected
- **THEN** no page SHALL be flagged
- **AND** the file SHALL continue on its normal route

### Requirement: Maths pages SHALL route to the OCR routes

Under the `page` routing unit, flagged maths pages SHALL skip the local OCR tier. They SHALL go to the primary route in one page-listed request. A page flagged both as a maths page and as needing OCR SHALL be sent once, in that request. If the primary route is unavailable before dispatch, the flagged pages SHALL go to the fallback route in one request. If both routes are unavailable, the pages SHALL keep native text and SHALL count as unresolved. A page for which the engine returns empty Markdown SHALL keep native text and SHALL count as unresolved.

Under the `document` routing unit, a PDF SHALL go whole to the OCR routes when the flagged-page fraction is at or above the configured maths page fraction. This condition SHALL be in addition to the existing OCR gate. A fraction of `0.0` SHALL disable it. The default fraction SHALL be `0.10`. The document unit SHALL NOT merge pages from two engines.

When maths routing is disabled, routing SHALL behave as it did before this capability.

#### Scenario: Only maths pages go to the primary engine

- **GIVEN** the `page` routing unit and a 12-page PDF with 4 flagged maths pages and no page needing OCR
- **AND** the primary route is available
- **WHEN** the PDF is ingested
- **THEN** exactly those 4 pages SHALL be sent to the primary route in one request
- **AND** the other 8 pages SHALL keep native Markdown
- **AND** the local OCR tier SHALL NOT process the 4 maths pages

#### Scenario: A missing primary engine falls back

- **GIVEN** the `page` routing unit, 4 flagged maths pages, an unavailable primary route and an available fallback route
- **WHEN** the PDF is ingested
- **THEN** the 4 pages SHALL be sent to the fallback route in one request

#### Scenario: No engine keeps native text

- **GIVEN** 4 flagged maths pages and no available route
- **WHEN** the PDF is ingested
- **THEN** the 4 pages SHALL keep native text
- **AND** they SHALL count as unresolved without failing the file

#### Scenario: Document unit sends a maths paper whole to the primary engine

- **GIVEN** the `document` routing unit, the default maths page fraction, and a 14-page PDF with 9 flagged pages
- **AND** the primary route is available
- **WHEN** the PDF is ingested
- **THEN** the whole PDF SHALL be parsed by the primary route

#### Scenario: Document unit keeps a PDF with few maths pages on the fast path

- **GIVEN** the `document` routing unit, the default maths page fraction, and a 40-page PDF with 1 flagged page that the OCR gate does not select
- **WHEN** the PDF is ingested
- **THEN** no parse request SHALL be dispatched

#### Scenario: Disabled maths routing changes nothing

- **GIVEN** maths routing is disabled
- **WHEN** a PDF with flagged maths pages is ingested
- **THEN** no page SHALL be routed because of maths fonts

### Requirement: Maths routing SHALL be injected configuration

The enable flag and the document-unit maths page fraction SHALL be top-level fields on the effective settings, beside the other OCR routing fields. They SHALL be resolved once at the composition root and passed downstream. Maths routing SHALL be enabled by default. The routing modules SHALL NOT contain a hardcoded fraction.

#### Scenario: The fraction is read from injected settings

- **WHEN** the document unit decides whether a PDF goes to the OCR routes because of maths pages
- **THEN** it SHALL read the fraction from the injected effective settings

### Requirement: Maths routing diagnostics SHALL be honest

A scalar `pages_maths_font` SHALL carry the count of flagged maths pages when maths routing is enabled. Under the `page` unit, maths pages read by either engine SHALL count as worker pages, and the four page-source counts SHALL still sum to the page count.

`pages_maths_font` SHALL be diagnostic metadata. It SHALL NOT enter embedded text or the metadata text shown to a language model.

#### Scenario: A page-unit document with maths pages reports mixed

- **GIVEN** the `page` unit and a PDF with native pages and primary-route maths pages
- **WHEN** the adapter emits its document
- **THEN** `ocr_backend` SHALL be `mixed`
- **AND** the four page-source counts SHALL sum to `page_count`

#### Scenario: The maths-page count does not reach embeddings

- **WHEN** a document with `pages_maths_font` is chunked and embedded
- **THEN** the embedded text SHALL NOT contain `pages_maths_font`

### Requirement: Maths routing SHALL participate in the source index identity

The existing source index identity SHALL include a maths-routing block: the resolved enable flag, the maths page fraction and the detector version. The block SHALL be present for every source. The identity schema SHALL advance by one.

#### Scenario: A detector change triggers re-ingestion

- **GIVEN** a previously indexed, byte-identical PDF
- **WHEN** the detector version changes
- **THEN** the source SHALL NOT be reported as `skipped_unchanged`

#### Scenario: Toggling maths routing triggers re-ingestion

- **GIVEN** a previously indexed, byte-identical PDF
- **WHEN** maths routing is turned off
- **THEN** the source SHALL NOT be reported as `skipped_unchanged`

#### Scenario: Unchanged maths routing inputs still skip

- **GIVEN** a previously indexed, byte-identical source
- **WHEN** it is ingested again with every maths-routing input unchanged
- **THEN** it SHALL be reported as `skipped_unchanged`
