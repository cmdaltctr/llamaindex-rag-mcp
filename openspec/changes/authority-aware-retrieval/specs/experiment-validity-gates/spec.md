# Spec Delta

## ADDED Requirements

### Requirement: Authority experiments report authority metrics, not only recall
An authority experiment SHALL pre-register gates and exact definitions for stale authority rate, incorrect supersession rate, scope resolution accuracy, conflict detection recall and historical authority accuracy, and SHALL report them beside recall@k. Ground truth SHALL label each question's controlling, qualifying, superseded, historical and not-yet-in-force sources, and whether it holds an unresolved conflict. Cells SHALL include a baseline and a newest-document-wins heuristic.

#### Scenario: Cell manifest records the tiers
- **WHEN** a cell runs with `authority.model_tier=nli`
- **THEN** the runtime manifest records `authority.enabled`, `authority.model_tier` and the model identity, and the report table shows them per cell

#### Scenario: Missing conflict label fails the ground-truth check
- **WHEN** a ground-truth question lacks the `unresolved_conflict` label field
- **THEN** the experiment's ground-truth validator rejects the ground truth before any cell runs

#### Scenario: Not-yet-in-force text counts as stale when controlling
- **WHEN** a question has `as_of="2024-03-15"`, source B's replacement takes effect on 2025-01-01, and a cell returns B as `controlling`
- **THEN** the question counts towards stale authority rate and fails historical authority accuracy

#### Scenario: Newest-document-wins is a comparator
- **WHEN** the report lists the cells
- **THEN** it includes the newest-document-wins cell beside the baseline and the resolver cells, paired by question
