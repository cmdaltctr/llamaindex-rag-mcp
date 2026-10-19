# ADR-080: Profiles Own Pipelines

- **Date:** 2026-10-16
- **Status:** Proposed (evidence is added when the change is verified: `openspec validate unify-profiles-and-pipelines --strict`, the fast suite and `./scripts/local_ci.sh`)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-035](035-phase-4-refactor-profiles-dual-use-case.md) (profiles), [ADR-037](037-architecture-v2-conformance.md) (injected settings), [ADR-075](075-omrg-owned-pipeline-runner-local-web-packaging-and-external-tool-plugins.md) (pipeline runner and web workspace), [ADR-076](076-serve-mcp-from-the-web-server-with-a-lifespan-provided-engine.md) (MCP over HTTP)
- **Change:** `openspec/changes/unify-profiles-and-pipelines/` (design D1 to D25)

## Context

A collection followed one of two fixed YAML profiles (`documents`, `codebase`).
Studio pipelines were a separate thing that only Studio ran. Chat, Knowledge
Base search, MCP tools and ingestion never used a saved pipeline. The web app
could not control how a collection reads, splits, embeds, searches and answers.

## Decision

1. **A user profile owns three pipelines (D1).** The workspace database (schema
   version 3) holds a `profiles` table: an immutable id made from the title, a
   title, a description, a base built-in profile and the pipeline ids of three
   slots: Ingest, Search and Answer. The id, the base profile and the slot ids
   never change. Deleted ids are never reused.
2. **Built-ins keep the direct path (D2).** A collection that follows
   `documents` or `codebase` runs the standard Engine operations. A collection
   that follows a user profile runs the current revision of the slot graph with
   `Engine.run_pipeline` inside the request. No run record is made and the run
   queue is not used.
3. **Only writing graphs take the Engine lock (D3).** Read-only graphs on one
   Engine overlap. Because the reranker keeps its last failure on the shared
   instance, `run_reranker` now runs "rerank, then read the reason" as one
   locked step for each reranker.
4. **Collections follow the current revision (D4).** A save returns
   `affected_collections`. A save that would make a profile in use not ready is
   refused with 409 (D19). A change to an Ingest graph applies at the next
   ingestion (D5). A rename changes the title only (D6). A delete is a soft
   delete, refused while a collection uses the profile (D7).
5. **Slot graphs name the base profile (D8).** Admission loads the base bundle
   and never loops back to the user profile.
6. **Readiness (D9).** Each pipeline needs a saved revision, a clean draft
   check, and its contract: Ingest `path` to `summary` with exactly one write
   step; Search `query` to `results` and Answer `query` to `answer`, both with
   no write step. Every reason is a plain line that names the pipeline.
7. **Upgrade (D10).** On the first web start, each saved Studio pipeline that
   belongs to no profile becomes a user profile. Job pipelines (layout key
   `omrg_task`) are skipped.
8. **Every process reads user profiles from the workspace (D11).** The stdio MCP
   server, the CLI and the watcher open the default workspace read-only and
   never create, migrate or write it. Binding stays in the web server. Without
   a workspace file, a collection that uses a user profile fails with a message
   that names the profile, the path and the fix.
9. **Request values replace step settings (D14); results keep today's shapes
   (D16).** `Engine.search` stays synchronous and runs graphs on a private event
   loop (D15). An answer from a user profile always uses the server model
   (D17). `used_by` comes from collection tags (D18).
10. **`createPipeline` is withdrawn (D20).** `POST /v1/pipelines` answers 410.
    `POST /v1/profiles` replaces it. Duplicates inherit the base profile's levers
    (D21) and a built-in profile returns its `standard_graphs` (D23). The draft
    check returns the effective value of each step setting (D24).
11. **Release (D25).** This change and `studio-profiles-gallery` ship in one
    release.

## Consequences

### Positive

- One concept, the profile, controls every request path.
- Built-in collections keep their speed and results.
- The draft check lets Studio show step values with no run inputs.

### Negative

- A request on a user profile pays graph admission cost. See "Measured
  overhead".
- A profile made on a host with a reranker has an enabled rerank step. A
  process without a reranker cannot run that graph until the step is
  disabled.
- `POST /v1/pipelines` clients break. The old Studio gallery needs
  `studio-profiles-gallery`.

### Neutral

- The CLI shows no live progress for a user-profile ingest: the callback runs
  once for each source after the run.

## Measured overhead

`tests/unit/test_profile_dispatch_latency.py` ran the 15 recorded retrieval
cases 20 times each through a built-in collection and through a duplicate user
profile, over an in-memory store. The median overhead of the graph path is
1.36 ms and the 95th-percentile overhead is 1.41 ms. This is below the 50 ms
limit in the design, so no cache of parsed definitions is needed. The numbers
show the cost of the graph path only; a real store and embedder add the same
time to both paths. See "Latency" in `docs/guides/pipelines.md`.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Run every request through graphs, built-ins included | Built-ins would pay admission cost with no gain in results. |
| Submit requests to `RunService` | One consumer and a bounded queue would make Chat wait behind ingestion. |
| Pin a revision for each collection | The user asked for one simple rule; a save is already explicit. |
| User profiles in the web server only | MCP search and answer must follow the profile, and the stdio server is the usual MCP set-up. |
| Hard delete | It would destroy run history. |

## References

- `src/omrg/compose_profiles.py`, `src/omrg/compose_templates.py`, `src/omrg/engine_profiles.py`
- `src/omrg/core/profiles/{catalogue,readiness,resolver,contract}.py`
- `src/omrg/integrations/workspace_sqlite/{profiles,schema}.py`
- `src/omrg/transports/api/routes/profiles.py`
- `docs/guides/pipelines.md`, `docs/guides/configuration.md`
