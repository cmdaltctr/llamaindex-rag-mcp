## ADDED Requirements

### Requirement: Only cited prose segments are judged as claims

When claim verification runs, the pipeline SHALL send to the judge only prose segments that carry at least one valid citation ordinal. The pipeline SHALL NOT send markdown structure lines to the judge. Structure lines are ATX headings, setext heading underlines, code-fence delimiter lines, every line inside a fenced code block, horizontal rules, table separator rows and bare list markers. A cited prose sentence next to a structure line SHALL be judged as before.

#### Scenario: A cited heading is not judged

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **AND** the answer contains the line `## Installation [1]` and the sentence `Run uv sync to install [1].`
- **WHEN** verification runs
- **THEN** the judge SHALL receive only the claim `Run uv sync to install.`
- **AND** `verification_calls` SHALL be 1

#### Scenario: Code-fence lines and code are not judged

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **AND** the answer contains a cited sentence, then a fenced block that opens with `` ```bash ``, holds the line `uv sync`, and closes with `` ``` ``
- **WHEN** verification runs
- **THEN** the judge SHALL receive only the cited sentence
- **AND** no fence line and no line inside the block SHALL be judged

#### Scenario: A citation inside a fenced block is not judged

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **AND** a line inside a fenced code block ends with `[1]`
- **WHEN** verification runs
- **THEN** that line SHALL NOT be judged

#### Scenario: Horizontal rules, table separators and bare list markers are not judged

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **AND** the answer contains a line `---`, a line `***`, a table separator row `|---|---|` and a list marker line `-`, each followed by a line that holds only `[1]`
- **WHEN** verification runs
- **THEN** none of those lines SHALL be judged

#### Scenario: A setext underline is not judged and its text line stays a candidate claim

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **AND** the answer contains the line `Fact one [1].` followed by the line `---`
- **WHEN** verification runs
- **THEN** the judge SHALL receive the claim `Fact one.`
- **AND** the line `---` SHALL NOT be judged

#### Scenario: Structure-like text inside prose is still judged

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **AND** the answer contains the sentence ``Use `## Title` syntax for headings [1].``
- **WHEN** verification runs
- **THEN** the judge SHALL receive that sentence as a claim

#### Scenario: Fence delimiters follow CommonMark

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **AND** the answer contains the line ```` ```uv sync``` installs it [1]. ```` followed by the cited sentence `Ollama needs 8 GB of memory [1].`
- **AND** a later fenced block opens with `` ``` ``, holds the line `~~~`, and closes with `` ``` ``
- **WHEN** verification runs
- **THEN** the judge SHALL receive both cited sentences as claims, because a backtick line whose info string holds a backtick is not a fence
- **AND** the line `~~~` SHALL NOT close the backtick block

#### Scenario: A structure-only answer section does not change the status

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true` and the judge returns `unsupported` for any heading or fence line
- **AND** the answer has at least one cited prose sentence, and every cited prose sentence is supported
- **WHEN** verification completes
- **THEN** the result SHALL have `status="ok"` and `verified=true`

### Requirement: A citation on a skipped line is not attached to another claim

A citation marker on a skipped structure line, or on a marker-only line that directly follows a skipped structure line, SHALL NOT be judged and SHALL NOT be attached to an earlier prose claim. The marker SHALL still count for grounding and SHALL still appear in `citations`.

#### Scenario: A marker after a closing fence cites nothing for the judge

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **AND** the answer is `Install it [1].`, then a fenced block, then a line that holds only `[2]`
- **WHEN** verification runs
- **THEN** the judge SHALL receive only `Install it.` with ordinal 1
- **AND** the result `citations` SHALL include ordinals 1 and 2

#### Scenario: A marker after prose still attaches to that prose

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **AND** the answer is `The tower is 100 metres tall. [1]`
- **WHEN** verification runs
- **THEN** the judge SHALL receive the claim `The tower is 100 metres tall.` with ordinal 1

### Requirement: An answer with no judgeable claim reports verification skipped

When claim verification is enabled and the answer is grounded, but no cited prose segment remains to judge, the pipeline SHALL make no judge call. The result SHALL keep `status="ok"`, SHALL NOT carry `verified`, and SHALL carry `verification_skipped` with a reason that states no claim could be verified.

#### Scenario: The only citation sits on a heading

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **AND** the answer is `## Installation [1]` followed by uncited prose
- **WHEN** the answer pipeline runs
- **THEN** no judge call SHALL be made
- **AND** the result SHALL have `status="ok"` with `verification_skipped` naming that no claim could be verified
- **AND** the result SHALL NOT have a `verified` field

#### Scenario: The only marker leads the answer

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **AND** the answer is a line that holds only `[1]`, followed by uncited prose
- **WHEN** the answer pipeline runs
- **THEN** no judge call SHALL be made
- **AND** the result SHALL have `status="ok"` with `verification_skipped` and no `verified` field

## MODIFIED Requirements

### Requirement: Claim verification is an optional stage gated by configuration

The pipeline SHALL provide an optional claim-verification stage that
verifies each cited claim against its cited evidence before reporting `ok`.
The stage SHALL be disabled by default and SHALL be enabled by the
`ANSWER__VERIFY_CLAIMS` setting. When disabled, the existing referential-only
`ok` guarantee SHALL remain unchanged.

#### Scenario: Verification disabled by default

- **GIVEN** the default configuration
- **WHEN** an answer is produced with at least one valid citation
- **THEN** the result SHALL have `status="ok"` with no `verified` field
- **AND** no verification model call SHALL be made

#### Scenario: Verification enabled

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true` and a verification provider is
  configured
- **WHEN** an answer is produced with at least one valid citation
- **THEN** the pipeline SHALL verify each cited prose claim against its
  cited evidence
- **AND** the result SHALL report exactly one verification outcome:
  `verified=true`, an `unverified_claims` list, or `verification_skipped`
  with a reason

#### Scenario: Verification enabled but no citations

- **GIVEN** `ANSWER__VERIFY_CLAIMS=true`
- **WHEN** an answer is produced with no valid citations
- **THEN** the result SHALL have `status="generation_unverified"` as before
- **AND** no verification model call SHALL be made
