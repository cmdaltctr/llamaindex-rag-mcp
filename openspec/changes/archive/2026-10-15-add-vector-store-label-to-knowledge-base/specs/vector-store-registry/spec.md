## ADDED Requirements

### Requirement: Registered stores SHALL carry a display label
Each vector-store registry entry SHALL carry a human-readable `label`, given as an optional keyword to `register()`. `describe()` SHALL return it, and SHALL return the registered name when no label was given. Adding a backend SHALL need one module and one `register()` call. No dispatch code SHALL branch on a store name to find a label.

#### Scenario: Built-in backends have labels
- **WHEN** `describe("lancedb")` and `describe("chroma")` are called
- **THEN** the labels SHALL be `LanceDB` and `ChromaDB`

#### Scenario: Registration without a label
- **WHEN** a backend is registered without a label
- **THEN** `describe()` SHALL return its registered name as the label
