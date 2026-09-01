# Add HTTP transport and multi-tenancy

> **STATUS: SCAFFOLD ONLY — NOT READY TO PROPOSE.**
>
> This folder is a placeholder so the work has a home and a name. It is
> deliberately not specified yet: the decisions below depend on a GCP
> deployment target that has not been chosen. Writing specs now would be
> guessing, and guesses become requirements.
>
> Do not run `/opsx-apply` on this change. Do not treat the content below as
> agreed scope.

## Why (provisional)

`transports/api/openapi.yaml` is a contract-first OpenAPI 3.1 document with no
runtime behind it. Change 3 adds the answering endpoint to that contract, so
the contract keeps growing correctly while nothing serves it.

Once `omrg` is a framework (change 4), the missing piece for a standalone
deployment is a server: an HTTP runtime implementing the existing contract,
plus the concerns a served API has that a local single-user MCP server does
not.

## Open questions to settle before specifying

These are the reasons this is a scaffold rather than a proposal.

**Deployment target**

- Cloud Run, GKE, or a VM? This decides the concurrency model, whether the
  process is long-lived, and whether local disk exists at all.
- LanceDB over `gs://` object storage, or a persistent disk? `lancedb.connect`
  accepts object-store URIs and `storage_options`, so this is a configuration
  decision rather than an architectural one — but read/write latency and
  concurrent-writer semantics differ enough to change the ingestion design.

**Authentication and authorisation**

- Managed (IAP, API Gateway) or in-process? Managed is less code and no
  credential handling; in-process is portable off GCP.
- The audit recorded no tenant, user or permission dimension anywhere. That is
  correct for a local single-user server and a prerequisite for a hosted one.

**Tenancy model**

- Collection-per-tenant, database-per-tenant, or a tenant dimension in
  metadata filters? The metadata-filter path already fails closed on malformed
  filters, which is the right foundation, but a tenant filter that a caller
  can supply is not access control.

**Result-metadata scoping**

- Every result row currently returns the full stored metadata, including
  absolute machine paths and file timestamps (audit P3). Harmless locally,
  disclosure by default when hosted. A served API needs a projection.

**Long-running operations**

- The contract already specifies `202 Accepted` plus job polling for ingestion
  and codebase-map generation. That needs a job store, and the job store's
  durability requirements depend on the deployment target.

**Streaming**

- Change 3 lists streaming as a non-goal. For a product UI it usually matters.
  Whether it is needed depends on whether a UI is in scope for the first
  hosted release.

**Concurrency**

- Change 2 moves sparse-cache invalidation to a durable data version, which is
  what makes multi-process correct. Multi-writer ingestion against one LanceDB
  URI still needs qualifying — the existing watch-command warning about
  concurrent writers to one persist dir is the open thread.

**Experiment portability**

- The quality-gate Tier-2 baseline pins `runner_os: Darwin`,
  `runner_architecture: arm64`, the Ollama version and the model digest. On
  Linux/x86 it will refuse rather than silently pass. A per-runner baseline
  record is needed, not an edited one.
- Experiment 19's BM25-versus-native verdict and the reranker's ARM-specific
  ONNX variant selection are both Apple-silicon evidence. Several settled
  decisions may come out differently on GCP hardware and should be re-run
  there before being trusted.

## Capabilities

To be determined once the questions above are answered.

## Impact

To be determined.
