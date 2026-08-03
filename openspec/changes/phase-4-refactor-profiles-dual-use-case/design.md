## Context

Phase 4 of the five-phase refactor (`docs/brainstorm/refactor-proposal/PROPOSAL.md` §6). This is the only phase that adds user-facing capability: named profiles for the two use cases. The central design problem is H1 (§6.3.1): Phase 2's resolver produces ONE server-wide `Settings` at startup, but `hybrid` mode needs per-collection levers in the same process. The answer is two-tier resolution.

## Goals / Non-Goals

**Goals:**

- Three YAML profile bundles validated against the settings schema.
- `RAG_PROFILE` server default + per-collection tags via collection metadata.
- `ProfileResolver` mapping collection → effective settings per operation.
- Non-destructive profile changes with the transport-specific safety contract.
- AGENTS.md invariant #5 correction and Experiment 10 revalidation of the documents-profile reranker flip.

**Non-Goals:**

- Per-content-type strategy overrides within a profile (§6.5 — enabled by this design, deliberately not built).
- Re-chunking or re-embedding existing data on profile change.
- GUI/API surfacing of profiles (REST transport is post-Phase 5).
- Embedding-model changes per profile — ChromaDB dim lock (ADR-003) makes the embedder server-wide (Tier 1) regardless of profile.

## Decisions

### D1: Two-tier resolution

Tier 1 (startup, `compose.py`): embedder, registries, store handle, reranker model — stateless or profile-independent. Tier 2 (per operation, `ProfileResolver`): reranker on/off, top_k, hybrid/RRF, chunking fallback, taxonomy mode — passed as parameters. The reranker model loads once (Tier 1); applying it is a per-query decision (Tier 2), preserving "load once, decide per query". Alternative considered: construct a full pipeline per profile — rejected; it would multiply the ONNX model in memory and break the embedder's dim-lock sharing.

### D2: Profiles bind to collections, not the server

Every concrete operation (one ingest, one query) touches exactly one collection, so one profile resolves per operation — the "two profiles at once" paradox dissolves (§6.3). The tag lives in ChromaDB collection metadata, read through the Phase 3 `VectorStore` interface.

### D2b: Hybrid is a mode selector, not an operational profile

`hybrid.yaml` does not carry concrete retrieval settings (top_k, reranker, hybrid flag). It declares only a `default_profile` key (`documents` or `codebase`). When `RAG_PROFILE=hybrid`, an untagged collection resolves to `default_profile`, never to `hybrid` itself. A collection tagged `hybrid` is rejected — the tag must name an operational profile. This prevents `ProfileResolver` from producing an `EffectiveSettings` with undefined retrieval levers.

### D3: Content-type dispatch always wins

A `.py` file hits the code strategy regardless of profile (Decision 4 of the proposal). The profile's `active_strategy` is only the ambiguous-type fallback. This is what makes profile changes non-destructive: they cannot retroactively invalidate how existing chunks were cut.

### D4: Safety contract is transport-specific

CLI prompts interactively; MCP returns a preview object and mutates only on `confirm=True` (M6). An MCP handler cannot block on stdin, and the "never raise / never block" invariants outrank UI symmetry.

### D5: Documents profile restores reranker-on deliberately

The `documents` profile sets `reranker_enabled: true` (ADR-018 intent), differing from the current code default `false` (post-Experiment 10). This is gated: the phase does not ship until Experiment 10's findings are revalidated and the outcome recorded. If revalidation fails, the documents bundle is amended to `false` before merge and the M1 note is updated.

## Risks / Trade-offs

- M1 reranker flip regresses document workloads → gated on Experiment 10 revalidation; the profile makes it per-collection, so a bad flip affects only documents-profile collections and reverts by editing YAML.
- Profile tag metadata format breaks old collections → the tag is additive; absence means default; no migration (Low/High risk retired by design).
- Resolver adds per-operation latency → bundle loading is cached per profile name; the metadata read is one SQLite lookup through the store interface.
- Users expect profile change to re-chunk → the safety contract states the truth explicitly and names the `--force` re-ingest path.
- Scope creep into §6.5 per-content-type overrides → explicitly out of scope; noted as an extension point the design leaves open.

## Migration Plan

1. Create the three YAML bundles + schema validation tests.
2. Add `RAG_PROFILE` to the Phase 2 resolver (ProfileYamlSettingsSource already slots in).
3. Implement `ProfileResolver` + thread resolved levers through `search()` and `ingest_path_async()` as parameters.
4. Implement profile-change tooling (CLI prompt, MCP preview/confirm).
5. Revalidate Experiment 10; correct AGENTS.md invariant #5; write ADR 030.
6. Rollback: branch revert; collections carry an inert metadata key if the phase is reverted after tags were written.

## Open Questions

- Exact revalidation method for M1 (re-run a subset of Experiment 10 vs re-analyse existing data) — decided at task time with the `s-experiment` skill.
