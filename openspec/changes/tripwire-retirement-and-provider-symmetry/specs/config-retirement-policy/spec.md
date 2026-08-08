## Purpose

Defines how a configuration variable is withdrawn from service: what the system
guarantees an operator will observe when they set a name that no longer exists,
how long that guarantee lasts, and the promise that the project's own
documentation never instructs setting such a name.

## ADDED Requirements

### Requirement: Retired configuration names are reported, not ignored

When the environment carries a configuration variable that the system no longer
reads, startup SHALL fail with an error naming both the retired variable and its
current replacement. The system SHALL NOT start with the retired variable
silently having no effect.

The check SHALL run before settings resolution, so the operator sees the naming
error rather than a downstream consequence of the missing value.

#### Scenario: Retired flat name set in the environment

- **WHEN** the environment defines a retired flat variable such as `TOP_K`
- **THEN** startup fails
- **AND** the error names `TOP_K` and its replacement `RETRIEVAL__TOP_K`
- **AND** the error is raised before any settings object is constructed

#### Scenario: Retired nested name set in the environment

- **WHEN** the environment defines a retired nested variable such as
  `METADATA__OLLAMA_CLASSIFY_TIMEOUT`
- **THEN** startup fails
- **AND** the error names the variable and its replacement
  `METADATA__CLASSIFY_TIMEOUT`

#### Scenario: Several retired names set at once

- **WHEN** the environment defines more than one retired variable
- **THEN** the error names every offending variable and each replacement
- **AND** the operator can correct them in a single pass

#### Scenario: Error text describes the actual retirement

- **WHEN** the error is raised for a variable retired after v2.0.0
- **THEN** the message SHALL NOT assert that every detected variable is a
  pre-v2.0.0 flat name
- **AND** any documentation the message cites SHALL name the same replacement
  the message names

### Requirement: Retirement lifetime depends on whether the name is detectable without help

A retired **nested** name (one carrying a block prefix, such as
`METADATA__…`) is rejected by its settings block independently of the
retirement list. Such an entry SHALL be retained for one major version after the
release that retired it, and MAY then be deleted; deleting it degrades the
message but preserves the failure.

A retired **flat** name (no block prefix, such as `TOP_K`) is not detectable by
settings validation — an unrecognised flat name is silently discarded. The
retirement list is the only mechanism that detects it. Such an entry SHALL be
retained for as long as an upgrade path exists from a version that read it, and
SHALL NOT be deleted merely because a major version has elapsed.

The lifetime SHALL be expressed as this rule. It SHALL NOT be expressed as a
hardcoded version number, so that a release which retires a name cannot also be
the release that expires it.

#### Scenario: Nested entry reaches the end of its major version

- **WHEN** a nested name has been on the retirement list for a full major version
- **THEN** it MAY be deleted
- **AND** setting that name still fails startup, via block validation

#### Scenario: Flat entry reaches the end of its major version

- **WHEN** a flat name has been on the retirement list for a full major version
- **AND** an upgrade path still exists from a version that read it
- **THEN** it SHALL be retained
- **AND** deleting it would cause that name to be silently ignored

#### Scenario: A release retires a name

- **WHEN** a release adds an entry to the retirement list
- **THEN** that entry SHALL NOT be scheduled for removal in the same release

### Requirement: Operator-facing documentation never instructs setting a retired name

No operator-facing document SHALL instruct the reader to assign a value to a
retired configuration variable. Operator-facing documents are those an operator
copies from or follows to configure a deployment: the environment example file,
the project README, and the user guides.

Naming a retired variable in order to explain its replacement is permitted and
expected; documentation SHALL be free to teach the migration.

This SHALL be enforced automatically, and the enforcement SHALL distinguish an
instruction to set a variable from a mention of it.

#### Scenario: A guide instructs setting a retired variable

- **WHEN** an operator-facing document contains an assignment of a retired
  variable, such as `RERANK_ENABLED=true`
- **THEN** the enforcing check fails
- **AND** it identifies the document, the line, and the replacement name

#### Scenario: A guide explains a retired variable

- **WHEN** an operator-facing document names a retired variable in prose to
  describe what replaced it
- **THEN** the enforcing check passes

#### Scenario: A historical record names a retired variable

- **WHEN** a changelog, architecture decision record, technical decision record,
  or archived planning document names a retired variable
- **THEN** the enforcing check passes, because those records describe the past
  and are not operator instructions
