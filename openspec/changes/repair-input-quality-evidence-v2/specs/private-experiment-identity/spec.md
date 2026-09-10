## ADDED Requirements

### Requirement: Experiment 28 identity is privately persisted and immutable

Experiment 28 tooling SHALL assign opaque document IDs once from a
deduplicated content-digest population and persist a private digest-to-ID
mapping before checkpointing classifications. The mapping SHALL contain a
schema version and study identifier, SHALL NOT contain filenames or paths,
and SHALL never be replaced or extended during resume. Digests, mapping files,
path locators, private diagnostics and their temporary files SHALL remain
local, excluded from version control and accessible only to the operator.

#### Scenario: File order or filename changes
- **GIVEN** a stored mapping for an unchanged unique digest population
- **WHEN** enumeration order or a file's name changes
- **THEN** its original document ID remains unchanged

#### Scenario: Duplicate content appears at another location
- **GIVEN** two synthetic files have identical bytes
- **WHEN** identity is assigned or checked
- **THEN** they represent one digest and one document ID

#### Scenario: Mapping publication fails
- **GIVEN** private storage or atomic initial publication cannot be established
- **WHEN** tooling starts a new synthetic study
- **THEN** it returns PRIVATE_STORAGE_UNAVAILABLE or OUTPUT_FAILED
- **AND** no classification checkpoint is created
- **AND** public output contains no private path

#### Scenario: Existing map would be overwritten
- **GIVEN** a mapping already exists
- **WHEN** initialisation attempts to publish another mapping at that location
- **THEN** it refuses without changing the existing bytes

### Requirement: Incompatible Experiment 28 resumes fail before classification

Resume SHALL validate the stored schema, study association, complete digest
population, unique assignments and checkpoint IDs before skipping any work
or invoking classification. It SHALL refuse missing, corrupt, incompatible
or unbound legacy identity records. It SHALL preserve existing mappings and
checkpoints on refusal.

#### Scenario: A new digest would shift sequential IDs
- **GIVEN** a checkpoint exists for an earlier digest population
- **WHEN** a new digest sorts before existing documents
- **THEN** resume returns IDENTITY_INCOMPATIBLE
- **AND** no old ID is reassigned and no document is classified

#### Scenario: A document is removed or its bytes change
- **GIVEN** an existing mapping and checkpoint
- **WHEN** the unique digest set differs
- **THEN** resume refuses without changing either file

#### Scenario: Legacy checkpoint has no digest mapping
- **GIVEN** the historical checkpoint has no verified associated identity map
- **WHEN** resume is requested
- **THEN** it returns IDENTITY_MISSING or IDENTITY_INCOMPATIBLE
- **AND** it does not reconstruct a mapping from the current personal library

#### Scenario: Mapping is corrupt or IDs collide
- **GIVEN** an invalid schema, malformed digest, duplicate ID assignment or unknown checkpoint ID
- **WHEN** identity validation runs
- **THEN** it returns IDENTITY_INVALID or IDENTITY_INCOMPATIBLE
- **AND** classification does not start

#### Scenario: Unchanged synthetic study resumes
- **GIVEN** a compatible stored mapping and valid associated checkpoint
- **WHEN** resume processes the same synthetic population
- **THEN** completed IDs are skipped and remaining IDs retain their assignments

### Requirement: Experiment 28 public errors disclose only bounded information

Experiment 28 tooling SHALL expose only fixed error codes and messages,
with validated opaque document IDs where applicable. Public JSON, reports,
stdout, stderr and normal logs SHALL NOT contain private filenames, paths,
digests, extracted text, raw exception text, exception attributes or chained
tracebacks. Untrusted exception class names SHALL NOT become public codes.

The allowed codes SHALL be IDENTITY_MISSING, IDENTITY_INCOMPATIBLE,
IDENTITY_INVALID, PRIVATE_STORAGE_UNAVAILABLE, INPUT_UNAVAILABLE,
CLASSIFICATION_FAILED, OUTPUT_FAILED and INTERNAL_ERROR.

#### Scenario: Parser exception contains a private filename
- **GIVEN** a synthetic reader raises an exception containing a private path and document text
- **WHEN** the classifier handles it
- **THEN** the public row contains CLASSIFICATION_FAILED and a validated opaque ID
- **AND** captured public output contains none of the exception payload

#### Scenario: Discovery or setup fails
- **GIVEN** synthetic discovery, hashing, reader construction or checkpoint loading raises
- **WHEN** the top-level boundary handles the failure
- **THEN** it emits an allowed code and fixed message
- **AND** no private path or traceback reaches stdout, stderr or normal logs

#### Scenario: Sensitive exception class and nested cause
- **GIVEN** a custom exception class name and chained cause contain private markers
- **WHEN** the error is handled
- **THEN** neither marker appears in any public output
- **AND** the public error code remains from the fixed allowlist

#### Scenario: Private diagnostic writing fails
- **GIVEN** detailed diagnostics cannot be written to the private local sink
- **WHEN** the error boundary completes
- **THEN** it returns a bounded public error
- **AND** it does not fall back to printing the diagnostic or its path

### Requirement: Personal-document work and routing decisions require operator approval

Completion of Experiment 28 tooling SHALL NOT authorise reading personal
PDFs, scanning personal documents, running a repeat study, selecting a
candidate routing policy, changing production routing, adopting a mixed
patch, promoting an OCR default, replacing the current routing policy or
making claims from new private-document measurements. The local agent SHALL
stop before each applicable action and obtain explicit operator approval
under a separately agreed scope.

#### Scenario: Synthetic verification is complete
- **GIVEN** identity and privacy regressions pass on synthetic data
- **WHEN** the local agent reaches the operator gate
- **THEN** it reports tooling verification and the outstanding decisions
- **AND** it does not scan or read the personal library

#### Scenario: An attractive mixed-policy result appears in older records
- **GIVEN** ADR-064 records an exploratory mixed-policy observation
- **WHEN** the tooling repair is complete
- **THEN** the agent does not select or apply that policy
- **AND** production routing and OCR defaults remain unchanged

#### Scenario: Final tooling validation follows the stop
- **GIVEN** the operator gate remains closed
- **WHEN** the local agent runs final validation of the repaired tree
- **THEN** it uses synthetic tests and authorised offline evidence only
- **AND** it makes no new personal-document measurement claim
