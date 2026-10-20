## ADDED Requirements

### Requirement: The page may write the document-reading keys

The keys the Settings page may write SHALL include `pdf_reader`, `ocr_fallback_enabled`, `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction`, `ocr_routing_unit`, `ocr_engine_primary`, `ocr_engine_fallback`, `ocr_maths_routing_enabled` and `ocr_maths_page_fraction`. A page write of one of these keys SHALL check the value before it writes: `pdf_reader` SHALL be one of `auto`, `liteparse`, `pdf_inspector`, `pypdfium2` and `pypdf`; an engine name SHALL start with a letter or digit, SHALL hold only letters, digits, dots, hyphens and underscores, and SHALL be at most 64 characters; a boolean key SHALL take only `true` or `false`; a fraction key SHALL take only a number from 0.0 to 1.0; `ocr_routing_unit` SHALL be `document` or `page`; and a blank text value SHALL be refused. `null` SHALL remove the key. These write checks SHALL NOT change how a value is read at startup: a `pdf_reader` value outside the five names, from any source, SHALL still log a warning and fall back to `auto`.

#### Scenario: Valid reader written

- **WHEN** the page writes `pdf_reader` `liteparse`
- **THEN** `omrg.jsonc` MUST hold `"pdf_reader": "liteparse"` and every other byte of the file MUST stay as it was

#### Scenario: Unknown reader refused on write

- **WHEN** the page writes `pdf_reader` `pdfminer`
- **THEN** the write MUST be refused with "pdf_reader: The value must be one of: auto, liteparse, pdf_inspector, pypdfium2, pypdf." and the file MUST NOT change

#### Scenario: Unknown reader in the file at startup

- **WHEN** a person writes `"pdf_reader": "pdfminer"` into `omrg.jsonc` by hand and the server starts
- **THEN** the server MUST log a warning and MUST use `auto`, as before this change

#### Scenario: Engine name with a path

- **WHEN** the page writes `ocr_engine_fallback` `../other`
- **THEN** the write MUST be refused with the engine name rule and the file MUST NOT change

#### Scenario: Blank engine name refused

- **WHEN** the page writes `ocr_engine_fallback` as an empty string
- **THEN** the write MUST be refused with "ocr_engine_fallback: The value must not be blank. Send null to use the default." and the file MUST NOT change

#### Scenario: Text where a boolean is expected

- **WHEN** the page writes `ocr_fallback_enabled` as the text `"true"`
- **THEN** the write MUST be refused with "ocr_fallback_enabled: The value must be true or false." and the file MUST NOT change
