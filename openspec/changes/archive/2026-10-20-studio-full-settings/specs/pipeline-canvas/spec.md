## MODIFIED Requirements

### Requirement: Step cards open their settings
Each step card SHALL show that it opens its settings. The card SHALL show a settings button and a hover state, and SHALL show the shared focus outline when it has keyboard focus. The card SHALL have the accessible name "<step name> step". Selecting the card with a click, Enter or Space SHALL open Step settings for that step. The settings button SHALL have the accessible name "Settings for <step name>", and a click, Enter or Space on it SHALL open the card settings panel for that step. Using the settings button SHALL NOT start a drag.

#### Scenario: A user clicks a step card
- **WHEN** a user clicks the Discover sources card
- **THEN** Step settings SHALL open and show the Discover sources step

#### Scenario: A keyboard user selects a step card
- **WHEN** a keyboard user moves focus to a step card and presses Enter
- **THEN** the card SHALL show the focus outline
- **AND** Step settings SHALL open and show that step

#### Scenario: Assistive technology names the card
- **WHEN** a screen reader reaches the Discover sources card
- **THEN** it SHALL announce the name "Discover sources step"

#### Scenario: The settings button opens the card panel
- **WHEN** a user clicks the settings button on the Prepare query card
- **THEN** the card settings panel for Prepare query SHALL open next to the card
- **AND** the button SHALL report `aria-expanded` true

## ADDED Requirements

### Requirement: The card settings panel edits a step in place
The card settings panel SHALL show the same controls as Step settings for that step: the bypass switch when the operation has one, and one control for each editable setting, with the same labels, value notes and checks. A change in the panel SHALL change the draft exactly as the same change in Step settings does. The panel SHALL end with a button "Open in Step settings" that selects the step and opens Step settings. The panel SHALL close on Escape, on a click outside it and on a second click on the settings button, and Escape SHALL return focus to the settings button. Typing or clicking in the panel SHALL NOT select, drag or remove the step. On a read-only graph every control in the panel SHALL be disabled. The Embed chunks panel SHALL show the model line and "Open in Step settings", and SHALL NOT offer a model control.

#### Scenario: A number is set from the card
- **WHEN** a user opens the card settings panel of Prepare query, chooses "Set value" for "Number of results" and types 20
- **THEN** the draft SHALL hold `top_k: 20` on that step
- **AND** the card SHALL show "Number of results: 20 (set here)"

#### Scenario: A step is bypassed from the card
- **WHEN** a user turns on "Bypass this step" in the card settings panel of Cross-encoder rerank
- **THEN** the step SHALL be disabled in the draft
- **AND** the card SHALL show the Bypassed badge

#### Scenario: Backspace in a field keeps the step
- **WHEN** a user presses Backspace in a text field of the card settings panel
- **THEN** the step SHALL stay in the graph

#### Scenario: The panel leads to Step settings
- **WHEN** a user selects "Open in Step settings" in the card settings panel of Split into chunks
- **THEN** Split into chunks SHALL be selected
- **AND** Step settings SHALL open and show Split into chunks

#### Scenario: A built-in profile shows values only
- **WHEN** a user opens the card settings panel of a step on a built-in profile
- **THEN** the panel SHALL show each setting with its value
- **AND** every control SHALL be disabled

### Requirement: Object settings are edited as JSON text
A step setting whose schema type is a JSON object SHALL show a text field that takes a JSON object, in Step settings and in the card settings panel. Empty text SHALL mean Inherit and SHALL remove the setting from the step. Text that is not a JSON object SHALL show "Enter a JSON object." and SHALL NOT change the draft. The step card SHALL show the value as compact JSON. Such a setting SHALL count as editable when the card chooses its main settings.

#### Scenario: A metadata filter is set
- **WHEN** a user types `{"file_type": "pdf"}` in the Metadata filter field of Prepare query
- **THEN** the draft SHALL hold `metadata_filter: {"file_type": "pdf"}` on that step

#### Scenario: Invalid JSON is refused
- **WHEN** a user types `{file_type: pdf}` in the Metadata filter field
- **THEN** the field SHALL show "Enter a JSON object."
- **AND** the draft SHALL keep its earlier value

#### Scenario: The filter is cleared
- **WHEN** a user clears the Metadata filter field
- **THEN** the step SHALL hold no `metadata_filter` parameter
