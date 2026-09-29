# Spec Delta

## ADDED Requirements

### Requirement: Authority experiments report authority metrics, not only recall
An experiment that evaluates the authority stage SHALL pre-register gates for stale authority rate, incorrect supersession rate, scope resolution accuracy, conflict detection recall and historical authority accuracy, and SHALL report them beside ordinary retrieval metrics. Ground truth SHALL label, per question, the controlling source, any qualifying source, any superseded source and whether the corpus holds an unresolved conflict for that question. Reports SHALL state the deterministic tier and model tier in force for each cell.

#### Scenario: Cell manifest records the tiers
- **WHEN** a cell runs with `authority.model_tier=nli`
- **THEN** the runtime manifest records `authority.enabled`, `authority.model_tier` and the model identity, and the report table shows them per cell

#### Scenario: Missing conflict label fails the plan check
- **WHEN** a ground-truth question lacks the `unresolved_conflict` label field
- **THEN** the plan validator rejects the ground truth before any cell runs
