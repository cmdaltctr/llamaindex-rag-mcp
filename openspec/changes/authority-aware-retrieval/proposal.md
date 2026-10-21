# Proposal

## Why

OMRG can say where a chunk came from (ADR-052 lineage) and whether a chunk is relevant (dense + sparse + RRF + optional reranker), but it cannot say whether a chunk is still *controlling*. When a corpus holds an original policy, an addendum that narrows it, and a later document that replaces part of it, all three are legitimate, all three stay indexed, and all three can score highly. The current pipeline hands the reranker a set in which an obsolete rule and its replacement are indistinguishable, and the calling agent is left to guess. This is the failure the fellowship paper targets: retrieval that separates *relevance* from *authority*, using a resolution ordering drawn from the uṣūl al-fiqh treatment of apparently conflicting evidences (reconcile before you supersede; the specific qualifies the general; the restricted qualifies the unrestricted; supersession needs evidence; withhold judgement when nothing resolves the conflict).

Why now: the lineage work is done, the answer pipeline already has an evidence-and-verdict shape (ADR-057, ADR-059), the retrieval registry makes a new stage a one-file addition, and the competing literature (EvoTrustRAG 2608.07933, ConflictRAG 2605.17301, ArbGraph 2604.18362, SAT-Graph RAG 2505.00039 / 2510.06002) collapses every conflict into "which claim wins" or needs a hand-built ontology. A typed, evidence-bearing, deterministic-first relation layer is the open gap, and the four-month fellowship window (to end of January 2027) fits a build, an experiment, and a paper.

## What Changes

- **New `core/authority/` package** (settings, relation vocabulary and edge model, ingestion-time relation extraction, query-time resolver). No cross-imports with `core/ingestion/` or `core/retrieval/` beyond settings; consumed through the retrieval registry.
- **New settings block `AuthorityBlock`** on `EffectiveSettings` with `enabled: bool = False`. Env prefix `AUTHORITY__`. Profile-overlaid: the `documents` profile may enable it, `codebase` keeps it off.
- **New registered retrieval strategy `"authority"`** in `core/retrieval/registry.py`. The `search()` pipeline invokes it after fusion (or dense) and before the reranker, only when enabled. When disabled the search path is byte-identical to today.
- **Relation table per collection.** Directed, typed, evidence-bearing edges between sources: `corroborates`, `explains`, `specialises`, `restricts`, `amends`, `supersedes`, `conflicts_with`. Each edge stores scope, effective dates, the evidence chunk id and text, `relation_origin ∈ {explicit_text, metadata, model}`, and confidence. Stored as a per-collection sidecar under the collection storage layout, not inside the vector rows.
- **Deterministic extraction tier (default when enabled).** Rule-based detection of supersession, amendment, repeal, effective-date and clause-reference language at ingestion. Emits edges with `relation_origin=explicit_text`.
- **Optional model tier (opt-in, off by default).** A local decision model (ONNX) or NLI cross-encoder types candidate pairs proposed by the existing document-graph similarity edges plus shared clause references. Emits `relation_origin=model` with a probability. Model-typed edges never enter `core/documents/doc_graph.py` (invariant 8 stays intact).
- **Resolver output contract.** Every candidate row gains `authority_status ∈ {controlling, qualified, superseded, historical, unresolved_conflict, unknown}` and `authority_reason` (the edge id and relation that produced the status). Rows are never dropped by the resolver. When two applicable rows conflict and no edge resolves them, the result carries a top-level `conflicts` list. Reranking then orders the annotated rows as before.
- **Point-in-time queries.** `search()` and `search_documents` accept an optional `as_of` ISO date. With `as_of`, "superseded" becomes "controlling for that date" when the edge's effective window covers it.
- **Experiment 43 (authority resolution).** Synthetic corpus covering five case types (full supersession, general + specific, partial amendment, corroboration, unresolved conflict), then one real corpus (a UK statute with amending instruments from legislation.gov.uk). Five pre-registered metrics: stale authority rate, incorrect supersession rate, scope resolution accuracy, conflict detection recall, historical authority accuracy. Ablations: deterministic tier only, model tier added, resolver without the reconciliation step, and three relation-typing models (Julia 1 ONNX decision model, an NLI cross-encoder, a small local LLM).
- **ADR** recording the decision after the experiment reports.
- **Docs**: `docs/guides/configuration.md`, `docs/guides/mcp-tools.md`, `.env.example`, and a `docs/proposals/authority-aware-retrieval.md` research proposal (already drafted alongside this change).

No breaking changes. Everything is additive and off by default.

## Capabilities

### New Capabilities

- `authority-resolution`: typed, evidence-bearing relations between indexed sources; ingestion-time extraction; a query-time resolver that annotates candidates with authority status without dropping them, honours `as_of`, and surfaces unresolved conflicts; opt-in per profile; disabled path unchanged.

### Modified Capabilities

- `mcp-search-filtering`: `search_documents` gains an optional `as_of` parameter and, when the authority stage is enabled, `authority_status` / `authority_reason` per row and a top-level `conflicts` field in the result envelope.
- `profiles-dual-use-case`: the profile bundle gains an `authority` section (`enabled`, `model_tier`) overlaid onto `EffectiveSettings.authority`; `documents` may enable it, `codebase` keeps it off.
- `strategy-registration-governance`: the `"authority"` strategy is registered through `core/retrieval/registry.py` and dispatched without name branching in the pipeline.
- `experiment-validity-gates`: Experiment 43 pre-registers the five authority metrics and gates before any default flip.

## Impact

- **Code**: new `src/omrg/core/authority/{__init__,settings,relations,extract,resolve,storage}.py`; one `register()` line in `core/retrieval/registry.py`; a guarded stage call in `core/retrieval/pipeline.py`; `AuthorityBlock` in `core/settings.py` mirrored by `core/authority/settings.py` (the MetadataBlock/MetadataSettings convention); an `authority` overlay in `core/profiles/resolver.py`; an ingestion hook that runs extraction after chunk write and before source-replacement commit; `as_of` plumbed through `transports/mcp/search.py` and the CLI search command.
- **Storage**: a relation sidecar per collection under the existing collection storage layout; store-neutral (works for LanceDB and Chroma); rebuilt for a source on replacement, keyed by `source_id`.
- **Dependencies**: none new for the deterministic tier. The model tier reuses ONNX Runtime already present for the reranker; any new model weights are downloaded on opt-in only. No PyTorch on the default path.
- **Tests**: new `tests/test_authority_*.py` at the Core + MCP ≥95% tier; import-linter contract `core-business-avoids-providers-transports` gains `omrg.core.authority` as a source module with no ignore entry; `tests/test_file_size_ceiling.py` unchanged (each new file under 500 lines).
- **Experiments**: `experiments/43-authority-resolution-2026-10-XX/` with corpus, ground truth, runner, summariser and report.
- **Docs and ADR**: configuration and MCP guides, `.env.example`, ADR-071 (number to be confirmed at write time).
- **Out of scope**: Taṣawwur concept framing and the Qiyās inference gate (Paper 2, change `mantiq-reasoning-gates`); two-pass answer generation; any change to reranker behaviour.
