# ADR-035: Phase 4 Refactor — Profiles: Dual Use Cases

**Date:** 2026-08-04
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `phase-4-refactor-profiles-dual-use-case`
**Amends:** ADR-018 (balanced retrieval defaults — profile-level restoration of reranker-on for documents)
**Supersedes:** ADR-019 (partially — the codebase profile formalises reranker-off for technical workloads)
**Phase:** 4 of 5 (`docs/brainstorm/refactor-proposal/PROPOSAL.md` §6, §8)

> **Numbering note.** The proposal called this "ADR 030" based on the
> pre-refactor numbering. ADRs 028–034 landed before Phase 4, so the next
> available number is 035.

## Context

The project serves two fundamentally different retrieval philosophies —
document grounding (facts from papers/reports for writing) and codebase
context (fast code understanding for coding agents) — but the distinction
existed only as implicit env-var combinations a user had to reverse-engineer.
A new user had to know which env vars to set (`RERANK_ENABLED`,
`HYBRID_ENABLED`, `TOP_K`) and which MCP tools to call for each use case.

Phase 4 is the only phase of the five-phase refactor that adds user-facing
capability. The central design problem (H1 in the proposal): Phase 2's
resolver produces ONE server-wide `Settings` at startup, but `hybrid` mode
needs per-collection levers in the same process.

Dependencies: Phase 2 (typed settings resolver, `ProfileYamlSettingsSource`
extension point) and Phase 3 (`VectorStore` interface for reading collection
metadata) MUST be complete.

## Decision

Introduce a profiles system with three version-controlled YAML bundles,
per-collection profile binding via ChromaDB metadata, and two-tier settings
resolution so one server process can serve both use cases simultaneously.

### D1: Two-tier resolution

Tier 1 components (embedder, chunking/reader registries, vector store
handle, reranker model) are constructed once at startup in `compose.py`
and shared across all collections. Tier 2 levers (reranker on/off, top_k,
hybrid/RRF, chunking fallback, taxonomy mode) are resolved per operation
by a `ProfileResolver` and passed as parameters to `search()` and
`ingest_path_async()`.

**Rejected alternative:** construct a full pipeline per profile. This
would multiply the ONNX reranker model in memory and break the embedder's
dim-lock sharing (ADR-003). The reranker model loads once (Tier 1);
applying it is a per-query decision (Tier 2).

### D2: Profiles bind to collections, not the server

Every concrete operation (one ingest, one query) touches exactly one
collection, so one profile resolves per operation. The tag lives in
ChromaDB collection metadata (`metadata={"profile": "codebase"}`), read
through the Phase 3 `VectorStore` interface. Collections with no tag
inherit the server-wide default (`RAG_PROFILE`).

### D2b: Hybrid is a mode selector, not an operational profile

`hybrid.yaml` declares only a `default_profile` key (`documents` or
`codebase`). When `RAG_PROFILE=hybrid`, an untagged collection resolves
to `default_profile`, never to `hybrid` itself. A collection tagged
`hybrid` is rejected — the tag must name an operational profile. This
prevents `ProfileResolver` from producing an `EffectiveSettings` with
undefined retrieval levers.

### D3: Content-type dispatch always wins

A `.py` file hits the code strategy regardless of profile. The profile's
`active_strategy` is only the fallback for ambiguous file types. This is
what makes profile changes non-destructive: they cannot retroactively
invalidate how existing chunks were cut.

### D4: Safety contract is transport-specific

CLI prompts interactively (`Continue? [y/N]`); MCP returns a preview
object (`{"status": "preview", "confirm_required": true}`) and mutates
only on re-invocation with `confirm=True`. An MCP handler cannot block on
stdin, and the "never raise / never block" invariants outrank UI symmetry.

### D5: Documents profile restores reranker-on deliberately (M1)

The `documents` profile sets `reranker_enabled: true`, restoring ADR-018's
balanced intent. The current code default is `false` (post-Experiment 10).

**M1 revalidation outcome:** Experiment 10 evaluated the reranker
(`cross-encoder/ms-marco-MiniLM-L-6-v2`) on a **technical/codebase
workload** (FreshStack LangChain documentation — identifier-heavy). The
reranker degraded Coverage@20 by 19–27% and added ~14s latency per query.
This evidence supports disabling the reranker for the **codebase** profile
(which the profile does). It does NOT provide evidence against enabling
the reranker for **document grounding** (semantic workloads — research
papers, reports, scientific PDFs). The FreshStack semantic subset was too
small (n=3) to draw conclusions, and the continuity subset (more
document-like) showed no degradation.

The dual-use-case insight: the reranker is harmful for technical workloads
but beneficial for semantic document workloads. The profiles system makes
this split explicit — `documents` enables it, `codebase` disables it.
AGENTS.md invariant #5 is corrected to state the true code default and
the profile-level restoration.

## Consequences

### Positive

* The two use cases are now named, documented, and first-class.
* One server process can serve both use cases simultaneously via
  per-collection profile tags.
* Profile changes are non-destructive (O(1) metadata update).
* Adding a new profile means creating one YAML file — no code changes.
* The reranker policy is now per-use-case instead of a global compromise.

### Negative

* The `ProfileResolver` adds one metadata read per operation (cached
  per profile name after first load).
* Users may expect profile changes to re-chunk existing data — the safety
  contract states the truth explicitly and names the re-ingest path.
* The M1 reranker flip for documents is a deliberate behaviour change
  gated on Experiment 10 revalidation (completed: the evidence supports
  the split).

## Implementation

* `config/profiles/documents.yaml`, `codebase.yaml`, `hybrid.yaml` —
  version-controlled policy bundles.
* `_ProfileYamlSettingsSource` in `config/__init__.py` — loads the
  selected profile bundle at startup, sitting between `defaults.yaml`
  and environment sources in the precedence chain.
* `core/profiles/resolver.py` — `ProfileResolver.resolve(collection) →
  EffectiveSettings` with per-profile-name caching.
* `core/profiles/contract.py` — safety-contract generator and
  `apply_profile_change()` (O(1) metadata update).
* `search()` and `ingest_path_async()` accept `effective_settings`
  parameter for Tier 2 levers.
* `_resolve_rerank_policy()` accepts `profile_reranker_enabled` parameter;
  profile-resolved enablement takes precedence over the global default.
* MCP tool `change_collection_profile` (preview/confirm flow).
* CLI command `rag-mcp set-profile` (interactive prompt).

## References

* `docs/brainstorm/refactor-proposal/PROPOSAL.md` §6 (Profiles), §8 (Migration)
* `docs/brainstorm/refactor-proposal/architecture-diagrams.md` §4 (Profile
  Resolution Flow), §5 (Profiles × Collections Binding)
* ADR-018 (balanced retrieval defaults — amended by profile-level restoration)
* ADR-019 (reranker disabled for technical workloads — formalised by
  codebase profile)
* ADR-031 (three-layer config/compose/DI — profiles ride on Phase 2's resolver)
* ADR-034 (VectorStore ABC — collection metadata read through this interface)
* Experiment 10 (`experiments/10-reranker-technical-workload-calibration-2026-05-31/`)
  — M1 revalidation source data

---

## Amendment (2026-08-05, ADR-037)

**Schema change.** Profile bundles described here use flat
SCREAMING_SNAKE keys (`TOP_K: 10`). ADR-037 moves them to nested blocks:

```yaml
retrieval:
  top_k: 10
  rerank_enabled: true
chunking:
  strategy_fallback: markdown
metadata:
  taxonomy_mode: category
```

A bundle using the flat schema is now rejected with the offending key named.
The three shipped bundles were converted as part of that change; custom
bundles must be converted by hand.

The Tier 1 / Tier 2 split and the safety contract are unchanged. Tier 2
levers are now delivered as a frozen `EffectiveSettings` parameter overlaid
onto the server default, rather than resolved against a global.
