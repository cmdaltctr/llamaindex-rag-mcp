## MODIFIED Requirements

### Requirement: The OCR routing gate SHALL be calibrated evidence expressed as injected configuration

The threshold that selects the OCR fallback SHALL be a calibrated value carried in injected configuration, not a constant in the routing module. It SHALL follow the shape the existing PDF knobs already use: top-level fields on the effective settings beside `pdf_reader` and `liteparse_ocr_enabled`, resolved once at the composition root and passed downstream.

The gate SHALL be calibrated on a committed fixture set disjoint from the fixtures used to evaluate whether the OCR fallback improves retrieval. Calibration SHALL report routing behaviour — text-based PDFs the gate would route to OCR, and OCR-required PDFs it would leave on the fast path — and SHALL NOT be the same run that measures downstream retrieval quality.

The packaged default SHALL be the promoted pair validated by the repeat routing study (`29-pdf-routing-repeat-2026-09-13`): routing enabled, `0.5` minimum confidence, `0.10` flagged-page fraction. The enable flag and both thresholds SHALL ship together — enabling routing while leaving thresholds at the `0.0` sentinels is the bare-enable configuration the study showed silently misses threshold-flagged documents, and packaged defaults SHALL NOT present it. `config/` SHALL NOT probe the worker, and no module SHALL read a settings singleton to obtain the gate.

#### Scenario: Routing threshold is read from injected settings

- **WHEN** the routing seam decides whether a PDF needs OCR
- **THEN** it SHALL read the gate from the injected effective settings
- **AND** the routing module SHALL NOT contain a hardcoded threshold constant

#### Scenario: Calibration and evaluation fixtures are disjoint

- **GIVEN** the committed PDF calibration fixtures and the committed PDF evaluation fixtures
- **WHEN** the OCR routing gate is calibrated
- **THEN** calibration SHALL use only the calibration fixtures
- **AND** the evaluation fixtures SHALL remain unused until the Stage 5 ablation

#### Scenario: Packaged default routes OCR-required PDFs

- **GIVEN** a fresh installation whose operator has set no OCR routing configuration
- **AND** the isolated OCR worker is provisioned and compatible
- **WHEN** a scanned PDF is ingested
- **THEN** the OCR fallback SHALL be selected
- **AND** a healthy text-based PDF SHALL stay on the fast path

#### Scenario: Unprovisioned worker degrades deterministically

- **GIVEN** a fresh installation with no OCR worker provisioned
- **WHEN** an OCR-required PDF is ingested
- **THEN** the file SHALL keep the partial pdf-inspector extraction with degraded diagnostics
- **AND** the batch SHALL continue with an actionable warning naming the provisioning step
