# pipeline-run-records delta

## ADDED Requirements

### Requirement: Truncated run output is readable through a protected route

When a stored run value is larger than its preview, the system SHALL keep the full redacted value as a run artefact and SHALL serve it through `GET /v1/runs/{run_id}/artefacts/{name}`. The route SHALL apply the same access policy as reading the run record: a caller that cannot read the run SHALL NOT read its artefacts, and a bearer credential bound to an experiment SHALL read only artefacts of that experiment's runs. The response SHALL contain the redacted value only. Credentials and raw vectors SHALL NOT appear in it. Errors SHALL NOT expose file system paths or exception text.

#### Scenario: Read a truncated summary in full

- **WHEN** a node summary was cut and carries `truncated: true` with an `artefact_ref` naming an artefact of that run
- **THEN** the route MUST return the full redacted value of that artefact

#### Scenario: Unknown artefact

- **WHEN** the run exists but no artefact has the requested name
- **THEN** the route MUST return 404 with a generic message

#### Scenario: Name outside the run

- **WHEN** the requested name holds a path separator, a dot segment or any value that is not one safe path segment
- **THEN** the route MUST refuse the request with 400 and MUST NOT read any file

#### Scenario: Bound credential and another experiment

- **WHEN** a bearer credential bound to one experiment requests an artefact of a run in another experiment or in the live workspace
- **THEN** the route MUST answer as for an unknown run and MUST NOT return the value
