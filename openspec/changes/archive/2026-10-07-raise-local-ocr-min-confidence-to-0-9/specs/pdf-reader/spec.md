## ADDED Requirements

### Requirement: Local OCR tier SHALL escalate pages below a default confidence of 0.9

When `OCR_ROUTING_UNIT=page` and the operator has not set `OCR_LOCAL_MIN_CONFIDENCE`, a page the local OCR tier reads SHALL escalate to the worker when its reported confidence is below 0.9. The tier SHALL keep a page whose confidence is 0.9 or higher, unless the page is empty, has no reported confidence, or carries the engine's hosted recommendation. A value the operator sets SHALL replace the default without change to the rule.

The page-unit index identity SHALL change when the effective cut changes, so that sources read under a different cut are re-indexed. The default `document` routing unit has no local tier, and its index identity SHALL NOT change.

#### Scenario: Page below the default cut escalates

- **GIVEN** `page` routing unit and no operator value for `OCR_LOCAL_MIN_CONFIDENCE`
- **WHEN** the local tier reads a page with text and confidence 0.85
- **THEN** the page SHALL escalate to the worker

#### Scenario: Page at the default cut stays local

- **GIVEN** `page` routing unit and no operator value for `OCR_LOCAL_MIN_CONFIDENCE`
- **WHEN** the local tier reads a page with text, confidence 0.9 and no hosted recommendation
- **THEN** the page SHALL keep its local text

#### Scenario: Operator value replaces the default

- **GIVEN** `OCR_LOCAL_MIN_CONFIDENCE=0.7`
- **WHEN** the local tier reads a page with text and confidence 0.75
- **THEN** the page SHALL keep its local text

#### Scenario: Page unit re-indexes when the default changes

- **GIVEN** a source indexed under `page` routing with the previous default cut of 0.8
- **WHEN** the source is ingested again under the default cut of 0.9
- **THEN** the source SHALL be re-indexed

#### Scenario: Document unit keeps its index identity

- **GIVEN** the default `document` routing unit
- **WHEN** the default cut changes from 0.8 to 0.9
- **THEN** the index identity of every source SHALL stay the same
