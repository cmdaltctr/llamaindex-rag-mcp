# dependency-floor-integrity Specification

## Purpose

Guarantees that the lower version bounds declared in `pyproject.toml` describe
a dependency set that actually installs and passes the test suite, so a
consumer resolving without the lockfile gets a working package rather than an
untested combination.
## Requirements
### Requirement: Declared floors form an installable, tested contract

The lowest versions permitted by `[project.dependencies]` and
`[project.optional-dependencies]` SHALL resolve to a working installation.
Continuous integration SHALL install at those floors and run the fast test
suite against them. A floor that resolves but fails the suite SHALL fail the
build.

#### Scenario: Floor resolution is exercised in CI

- **WHEN** the CI pipeline runs on a push or pull request
- **THEN** a job MUST resolve dependencies with the lowest declared direct
  versions rather than the lockfile
- **AND** that job MUST run the fast test suite and report its result without
  suppression

#### Scenario: An unsatisfiable floor set fails the build

- **WHEN** a floor is raised to a version that cannot co-resolve with the
  other declared floors
- **THEN** the floor job MUST fail at the resolution step
- **AND** the failure output MUST name the conflicting requirement

#### Scenario: A floor that installs but breaks fails the build

- **WHEN** the floor set resolves but a permitted old version omits an API the
  project calls
- **THEN** the floor job MUST fail on the test that exercises that API

---

### Requirement: ChromaDB minimum excludes the collection-listing regression

The declared `chromadb` minimum SHALL exclude every release in which
`list_collections()` returns collection names rather than collection objects.
The vector store adapter reads the `name` attribute of each listed collection,
so any permitted version MUST return objects carrying that attribute.

#### Scenario: Collection listing returns named objects at the floor

- **WHEN** the vector store adapter lists collections against the lowest
  permitted `chromadb` version
- **THEN** each listed item MUST expose a `name` attribute
- **AND** the call MUST NOT raise `AttributeError`

#### Scenario: The regression range is not installable

- **WHEN** a resolver applies the declared `chromadb` constraint
- **THEN** it MUST NOT be able to select a release from the affected range

---

### Requirement: Floor drift from the lockfile is detected automatically

Every direct dependency's declared floor SHALL be checked against the version
recorded in `uv.lock`. An automated test SHALL fail when a floor sits below
its locked version by more than one minor release, naming each offending
package with both versions. The check SHALL be a test rather than a review
convention.

#### Scenario: Drift is reported per package

- **WHEN** the drift test runs against `pyproject.toml` and `uv.lock`
- **THEN** it MUST pass with zero packages exceeding the permitted gap

#### Scenario: A newly stale floor is caught

- **WHEN** the lockfile advances a direct dependency two or more minors past
  its declared floor
- **THEN** the drift test MUST fail naming that package, its declared floor,
  and its locked version

#### Scenario: A floor above the lock is rejected

- **WHEN** a declared floor is set higher than the version in `uv.lock`
- **THEN** the drift test MUST fail, because the lockfile would no longer
  satisfy the declared contract

#### Scenario: A missing package is rejected

- **WHEN** a declared dependency is not found in `uv.lock`
- **THEN** the drift test MUST fail naming that package and its source table

#### Scenario: Exemptions apply only to drift, not to presence or contract

- **WHEN** a package is listed in the drift-exemption table
- **THEN** the drift test MUST still verify the package is present in
  `uv.lock`
- **AND** the drift test MUST still verify the package's floor does not sit
  above its locked version
- **AND** the drift test MUST skip only the one-minor drift check for that
  package
- **AND** each exemption entry MUST name the reason inline in the test source
- **AND** each exemption MUST be recorded in an architecture decision record

---

### Requirement: Floor raises are declared as breaking changes

Raising a declared minimum SHALL be treated as a breaking change to the
install contract. The commit SHALL carry a `BREAKING CHANGE` footer naming the
packages and their new minimums, and an architecture decision record SHALL
capture the evidence for each raise.

#### Scenario: The decision record cites upstream evidence

- **WHEN** a floor is raised
- **THEN** the decision record MUST name the package, the old floor, the new
  floor, and an upstream changelog, release note, or migration guide reference
  justifying the new minimum

#### Scenario: Upstream-blocked packages are recorded, not silently skipped

- **WHEN** a dependency cannot be advanced because a transitive parent
  constrains it
- **THEN** the decision record MUST list it as a watch item naming the
  constraining parent

### Requirement: Base and Chroma-extra dependency contracts SHALL be tested separately

The built base package and a fresh base installation SHALL exclude both Chroma
distributions. The optional `chroma` group SHALL retain supported floors and run
in a separate complete CI job.

#### Scenario: Built base wheel excludes Chroma

- **WHEN** base wheel metadata is inspected
- **THEN** neither Chroma package MUST be an unconditional `Requires-Dist`
- **AND** the Chroma extra markers MUST be represented accurately

#### Scenario: Fresh base installation excludes Chroma

- **WHEN** the base wheel is installed without extras in a fresh environment
- **THEN** both Chroma distributions MUST be absent from import metadata and installed-distribution inventory
- **AND** the full LanceDB-default fast suite and base import-lint contracts MUST pass

#### Scenario: Chroma extra resolves at floors

- **WHEN** the `chroma` group is resolved at lowest direct versions
- **THEN** every Chroma-skipped base case MUST run in the extra job
- **AND** contract, local, hybrid and cloud suites MUST pass
- **AND** floor drift checks MUST cover both packages

### Requirement: Residual advisory findings SHALL require explicit release-policy disposition

Optionalisation SHALL NOT by itself clear a release gate. Base-artifact and
universal-lock/all-extras findings SHALL be observed and recorded separately.

#### Scenario: Base artefact is scanned

- **WHEN** the base wheel or base-install SBOM is scanned
- **THEN** the actual result MUST be recorded with artefact identity and scanner version
- **AND** it MUST be distinguished from the universal-lock result

#### Scenario: Universal lock still reports the advisory

- **GIVEN** `uv.lock` contains the optional Chroma group
- **WHEN** security tooling reports CVE-2026-45829
- **THEN** the release MUST remain blocked until a named policy owner records acceptance or rejection
- **AND** any acceptance MUST include scope, rationale, date, expiry/review date and patch/advisory triggers
- **AND** the advisory MUST remain tracked

#### Scenario: Policy refuses the residual finding

- **WHEN** policy cannot waive the optional universal-lock finding
- **THEN** this change MUST NOT claim release clearance
- **AND** Chroma support MUST be separately locked/distributed or removed temporarily before release

