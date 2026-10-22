# Spec Delta

## MODIFIED Requirements

### Requirement: Answers are grounded in retrieved evidence

The prompt SHALL instruct the model to answer only from the supplied sources,
to cite the sources it used, and to state when the sources do not support an
answer. The operation SHALL return the exact chunks supplied as context
alongside the answer. When a search row carries `authority_status`,
`authority_reason` or `authority_conflicts`, its evidence row SHALL carry the
same keys and values; when a search row has none of them, its evidence row
SHALL NOT gain them.

#### Scenario: Supplied context is returned with the answer

- **WHEN** an answer is produced
- **THEN** the result SHALL include every chunk that was placed in the prompt
- **AND** each SHALL carry its `chunk_id`, `source_id`, `source_version`,
  `source`, `source_chunk_index` and retrieval score

#### Scenario: The model is instructed to stay within the evidence

- **WHEN** the prompt is constructed
- **THEN** it SHALL instruct the model to use only the provided sources
- **AND** to indicate when the sources do not contain the answer
- **AND** to cite the sources supporting each claim

#### Scenario: Authority keys pass through when present

- **WHEN** the search rows used for an answer carry authority annotations
- **THEN** each evidence row SHALL carry the same `authority_status`,
  `authority_reason` and `authority_conflicts` values as its search row

#### Scenario: Evidence is unchanged when authority keys are absent

- **WHEN** the search rows used for an answer carry no authority keys
- **THEN** the evidence rows and the answer result SHALL equal those produced
  before this change
