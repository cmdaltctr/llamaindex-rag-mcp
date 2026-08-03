## Why

The project serves two distinct retrieval philosophies — document grounding (facts from papers/reports for writing) and codebase context (fast code understanding for coding agents) — but the distinction exists only as implicit env-var combinations a user must reverse-engineer. This is Phase 4 of the five-phase refactor (`docs/brainstorm/refactor-proposal/PROPOSAL.md` §6, §8): make the two use cases first-class through named, documented YAML profiles that bind to ChromaDB collections, with per-operation resolution so one server can serve both use cases simultaneously. This phase is new capability, not reorganisation. **Dependency: Phase 2 MUST be complete** — profiles ride on Phase 2's typed settings resolver.

## What Changes

- Create `config/profiles/documents.yaml`, `codebase.yaml`, and `hybrid.yaml` — version-controlled policy bundles validated against the root settings schema, containing no credentials.
  - `documents`: markdown chunking fallback, reranker ON, top_k=10, dense-only, category taxonomy (restores ADR-018 intent).
  - `codebase`: code chunking fallback, reranker OFF, top_k=20, hybrid (dense + BM25 + RRF), file_type taxonomy.
- Add `RAG_PROFILE` env var selecting the server-wide default (`documents` / `codebase` / `hybrid`).
- Collections declare a profile via ChromaDB metadata (`metadata={"profile": "codebase"}`); collections with no tag inherit the server-wide default (backward compatible with all existing collections, Decision 3).
- Implement `ProfileResolver` (H1, §6.3.1): maps `collection_name → effective Settings` per operation. Tier 1 (embedder, registries, store handle, reranker model) is constructed once in `compose.py`; Tier 2 levers (reranker on/off, top_k, hybrid/RRF, chunking fallback, taxonomy mode) resolve per operation and pass as parameters to `search()` and `ingest_path_async()` — no global reads in `core/`.
- Profile changes on non-empty collections surface the safety contract (§6.4): existing chunks NOT re-chunked/re-embedded; query-time levers apply immediately; taxonomy caveat stated honestly. **Transport-specific (M6):** CLI prompts interactively (`Continue? [y/N]`); MCP returns a preview object (`{"status": "preview", "confirm_required": true}`) and mutates only on re-invocation with `confirm=True`.
- Content-type dispatch always wins for known file types regardless of profile (Decision 4); the profile's `active_strategy` is the fallback for ambiguous types only.
- **Deliberate behaviour change (M1):** the `documents` profile sets `reranker_enabled: true`, restoring ADR-018's balanced intent. The current code default is `false` (flipped post-Experiment 10). This MUST be revalidated against Experiment 10's findings before the phase ships, and AGENTS.md invariant #5 (stale `RERANK_ENABLED=true` claim) MUST be corrected in the same sweep.
- New ADR 030: Profiles — Dual Use Cases (Documents + Codebase).

## Capabilities

### New Capabilities

- `profiles-dual-use-case`: The profiles system — YAML profile bundles, `RAG_PROFILE` selection, per-collection profile binding via collection metadata, two-tier (construction-time vs per-operation) settings resolution, non-destructive profile changes with the transport-specific safety contract.

### Modified Capabilities

- `reranking`: The effective reranker enablement for an operation MAY come from the collection's resolved profile (documents=on, codebase=off) in addition to the global `RERANK_ENABLED` default and explicit per-request flags. Explicit per-request rerank flags still bypass policy.

## Impact

- **Code**: new `config/profiles/*.yaml`, `core/profiles/resolver.py`, profile-bundle loading in the Phase 2 resolver, `search()` and `ingest_path_async()` accept resolved levers as parameters, profile-change tooling (CLI prompt + MCP preview/confirm flow).
- **Data**: profile tag is additive collection metadata — existing collections are untouched and inherit the default profile. No data migration.
- **Behaviour**: `RAG_PROFILE=documents` deliberately differs from today's default (reranker ON) pending Experiment 10 revalidation (M1).
- **Docs/ADRs**: AGENTS.md invariant #5 corrected; new ADR 030; `docs/guides/configuration.md` gains the profiles section.
- **Dependencies**: none new (PyYAML arrived in Phase 2).
- **Risk**: Medium — new behaviour, new tests, new ADR; the M1 reranker flip is the main behavioural risk and is gated on revalidation.
