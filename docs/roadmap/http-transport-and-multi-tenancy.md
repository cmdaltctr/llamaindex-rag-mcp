# HTTP transport and multi-tenancy exploration

> **Status: exploration — not an active OpenSpec change.**
>
> This note records decisions that must be made before a proposal can define
> requirements and scenarios. It is not authorised implementation scope.

## Existing contract boundary

`src/rag_mcp/transports/api/openapi.yaml` is a contract-only OpenAPI 3.1
surface. The baseline `transport-separation` requirement explicitly forbids
runtime `.py` files in that package. The contract already declares
`202 Accepted` job responses for ingestion and codebase-map generation plus
`GET /v1/jobs/{jobId}` polling.

A future implementation proposal must therefore MODIFIED the baseline
transport-separation requirement; merely adding an HTTP server would contradict
the current specification.

## Decisions required before proposing

### Deployment and storage

- Choose Cloud Run, GKE or a VM. Record the concurrency model, process lifetime,
  writable-local-disk assumptions and scale-to-zero behaviour.
- Qualify LanceDB on the chosen storage. A `gs://` URI and
  `storage_options` establish connectivity, not acceptable latency,
  consistency or concurrent-writer safety.
- Decide whether ingestion has one writer per dataset, an external queue/lock,
  or another failure-safe coordination model.
- Re-run platform-pinned quality and performance experiments on the selected
  Linux/x86 or accelerator environment instead of editing Darwin/arm64
  baselines.

### Request inputs and trust boundary

The current contract accepts server filesystem `path` values for ingestion
and codebase-map requests. A hosted API must replace or constrain that surface:
upload, signed object URI, pre-registered workspace identifier, or an
equivalent sandboxed input. Arbitrary caller-selected server paths are not an
acceptable hosted contract.

### Authentication and authorisation

- Decide managed identity (for example gateway/IAP) versus in-process
  authentication.
- Specify authentication separately from authorisation: issuer, audience,
  claims, tenant binding, scopes/roles, and distinct 401/403 behaviour.
- Ensure tenant identity comes from trusted credentials, never a caller-editable
  metadata filter.

### Tenancy and deletion safety

- Choose collection-per-tenant, database-per-tenant, or a first-class tenant
  dimension.
- If tenant identity is stored in metadata, include it in source identity and
  scope every read, replacement, stale-row selection, deletion and collection
  operation. Today `source_id` derives only from canonical absolute path, so
  adding a result filter alone would not isolate writes or deletes.
- Define destructive-delete request schemas so an empty or malformed request
  cannot broaden into collection deletion. Preserve preview/confirm semantics
  where already contracted.

### Result and diagnostic projection

The local API returns full stored metadata, including absolute paths and file
timestamps. Define an allowlisted hosted projection for normal results,
diagnostics, errors, logs and job output. Tenant separation must hold across
all of those surfaces.

### Jobs and long-running operations

- Choose a durable job store compatible with the deployment target.
- Define job ownership checks for create, poll and cancel.
- Specify idempotency keys, retry semantics, terminal states, retention,
  cancellation and cleanup.
- Preserve the existing 202-plus-polling contract or propose an explicit
  MODIFIED delta.

### Abuse controls and streaming

- Define request/body/context limits, concurrency limits, quotas and audit
  events before exposing expensive ingest or answer operations.
- Decide whether streaming is in the first release. Change 3 deliberately
  excludes it, so inclusion requires an explicit answering-contract delta.

## Prerequisites and order

1. `fix-retrieval-freshness-and-context-assembly` is a hard prerequisite for
   multi-process BM25 correctness, subject to qualifying its durable token.
2. `add-grounded-answer-synthesis` is required only if the first HTTP release
   exposes an answer endpoint; raw retrieval does not depend on it.
3. `make-omrg-a-standalone-framework` should land before the runtime so the
   server composes the public Engine rather than adding another private startup
   path.
4. Re-enter `openspec/changes/` only after the decisions above are recorded
   as testable ADDED/MODIFIED requirements with scenarios.

## Evidence to collect

- LanceDB cross-process mutation and concurrent-writer behaviour on the chosen
  storage.
- Deployment-specific latency, durability and restart tests.
- Threat model covering tenant crossover, path traversal, confused deputy,
  job enumeration and destructive operations.
- OpenAPI diff showing every runtime operation implements, rather than silently
  diverges from, the existing contract.
