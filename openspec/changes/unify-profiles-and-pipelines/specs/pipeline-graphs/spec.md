# Spec Delta

## ADDED Requirements

### Requirement: Read-only graph runs on one Engine overlap

Graph runs on one Engine SHALL wait for each other only when both contain an enabled step that writes to a collection. A run with no enabled write step SHALL start at once, also while another run on the same Engine is in progress. The ingestion write lock and the per-run node limits SHALL stay in force.

#### Scenario: Two searches at the same time

- **WHEN** two read-only graphs start on one Engine at the same time
- **THEN** both runs MUST be in progress together before either one ends

#### Scenario: Two ingestions at the same time

- **WHEN** two graphs that each contain an enabled write step start on one Engine
- **THEN** the second run MUST start its steps only after the first run ends

#### Scenario: Search during ingestion

- **WHEN** a read-only graph starts while a writing graph runs on the same Engine
- **THEN** the read-only graph MUST run without waiting for the writing graph to end

### Requirement: The draft check reports effective control values

The draft check (`validatePipeline` with no run inputs) SHALL return `nodes` with the effective controls of each node: for each lever field, its `lever`, `value`, `source` and `detail`, in the same shape as the admission check. It SHALL resolve each node's collection from the node's collection parameter, then `graph.collection`, then the request `collection`, then the host default collection. It SHALL resolve settings from `graph.profile` when it names a built-in profile, else from that collection's profile, and SHALL then apply graph overrides and node parameters in the admission order. When the draft has issues, the error response SHALL still carry `nodes` for each node whose parameters are valid and whose profile resolves. The draft check SHALL run no node, call no model and write nothing.

#### Scenario: Values without run inputs

- **WHEN** a client validates a Search draft with no inputs, `graph.profile` `documents` and no node `top_k`
- **THEN** the response MUST hold the control `retrieval.top_k` for the Prepare query node with the value from `documents` and the source `profile`

#### Scenario: Node parameter wins

- **WHEN** the same draft sets `top_k` to 20 on the Prepare query node
- **THEN** the control MUST show the value 20 and the source `node`

#### Scenario: Collection profile when the graph names none

- **WHEN** a draft names no `graph.profile`, `graph.collection` is `code`, and collection `code` is tagged `codebase`
- **THEN** each control MUST come from the `codebase` settings

#### Scenario: Host default collection

- **WHEN** a draft names no collection, no node names one and the request names none
- **THEN** the controls MUST come from the profile of the host default collection

#### Scenario: Incomplete draft

- **WHEN** a draft has an unconnected input port on one node and valid parameters on the others
- **THEN** the response MUST be the validation failure with its issues
- **AND** it MUST carry `nodes` with the controls of the other nodes

#### Scenario: Same values as admission

- **WHEN** a client validates one graph once without inputs and once with inputs
- **THEN** each node's controls MUST be equal in both responses
