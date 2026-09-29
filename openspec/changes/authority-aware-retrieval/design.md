# Design

## Context

See proposal.md, Why. The relevant current state:

- `core/retrieval/pipeline.py::search()` resolves `EffectiveSettings` once, runs `_hybrid_query_rows` (dense + sparse → `registry.get("fusion")`) or dense alone, then optionally `reranker.rerank(...)`, then threshold/truncate, then `assemble(...)`. Every stage is obtained through `registry.get(name)`; the pipeline never branches on strategy names.
- `EffectiveSettings` is frozen and composed of frozen blocks (`chunking`, `ingestion`, `embedding`, `retrieval`, `metadata`, `answer`). The `answer` block established the pattern for a new block: a pure-data `core/<pkg>/settings.py` model, a mirrored `<Pkg>Block` in `core/settings.py`, env prefix `<PKG>__`, and a profile overlay for the levers that are per-use-case (`verify_*` in `core/profiles/resolver.py`).
- ADR-052 gives every chunk a stable `source_id` and `chunk_id`; ADR-048 gives failure-safe replacement with a verify-then-commit window.
- `core/documents/doc_graph.py` builds a deterministic graph with `similar`, `category`, `keyword`, `heading_child` edges. Invariant 8: no LLM in graph construction.
- ADR-057 and ADR-059 established the answer-side evidence/verdict shape and the injected-completion seam. The authority stage sits upstream of both.
- Import-linter: `core-business-avoids-providers-transports` with `unmatched_ignore_imports_alerting = "error"`. Adding a source module and no ignore entry is the intended path.
- Experiment numbering: 36 is used, 37 is claimed by `modular-ocr-workers-dots-mocr`. This change takes 38.

## Goals / Non-Goals

**Goals:**

- A resolver that is deterministic at query time and explainable per row.
- Zero behavioural difference when disabled, enforced by a byte-equality test on search output.
- Relation extraction that works without any model, with a quarantined opt-in model tier.
- A benchmark and metric set that a reviewer can rerun.

**Non-Goals:**

- Changing reranker behaviour or feeding authority into the reranker score.
- Two-pass answer generation.
- Clause-level chunk alignment across arbitrary document formats (scope is a string reference, matched to chunk headings/anchors when present; exact clause boundaries are best-effort).
- Any Taṣawwur or Qiyās machinery (Paper 2).

## Decisions

### D1. Separate `core/authority/` package, registered as a retrieval strategy

Alternatives: (a) extend `core/documents/doc_graph.py` with new edge types; (b) fold into the reranker; (c) new package.

(a) breaks invariant 8 the moment the model tier lands, and the document graph is a batch analysis product, not a query-time service. (b) collapses relevance and authority, which is the exact confusion the paper argues against. (c) matches invariant 6 (graph-like modules under `core/`, no cross-imports with ingestion/retrieval) and invariant 11 (one file + one `register()`). Chosen: (c). The package imports `core/settings.py` models and `core/ingestion/source_state.py` key constants only.

### D2. Two-tier extraction, deterministic first

Tier 1 (`extract.py`, always on when enabled) is rule-based: a small pattern table for supersession, replacement, amendment, repeal, withdrawal, effective-date clauses and clause references, plus title/path matching against the collection's source inventory (from `store.iter_metadatas`). Output edges have `relation_origin=explicit_text`, `confidence=1.0`.

Tier 2 (`model_tier`) is opt-in. Candidate pairs come from the document-graph `similar` edges (the existing similarity threshold, ADR-generated, is reused as the proposer) and from any pair where tier 1 found a clause reference but could not type the relation. The decision model receives (state = passage A, question = "How does B relate to A?", options = the seven relations + `unrelated`) and returns a distribution. Two backends: `onnx_decision` (a small ONNX decision model such as Julia 1, 2–20 options, ONNX Runtime already a dependency) and `nli` (an ONNX NLI cross-encoder mapped: entailment → corroborates/explains, contradiction → conflicts_with, plus heuristics for scope words). Both are `integrations/` concerns constructed in `compose.py` and injected as a callable, mirroring the reranker and the verify judge. No PyTorch on the default path; the `torch` extra remains ⚠️ Ask.

Alternative rejected: LLM-only extraction. It is the least reproducible and the least auditable, and ADR-059 already showed a local 4B judge is not viable on the target hardware.

### D3. Relation store is a per-collection sidecar, not vector-row metadata

Alternatives: (a) stamp edges into chunk metadata; (b) a table in the vector store; (c) a sidecar file under the collection storage layout.

(a) puts N-to-N data on rows that are replaced per source and breaks when the target source is replaced. (b) forces a LanceDB-specific and a Chroma-specific implementation and, on Chroma, there is no second table concept without a second collection. (c) is store-neutral, survives replacement, and is small (edges are per source pair, not per chunk). Chosen: (c). Format: a single JSONL file `authority/relations.jsonl` beside the collection's other artefacts, with an atomic `.tmp` → rename write, one record per edge, keyed by `(source_id, target_id, relation, scope)`. `storage.py` owns read/write; `resolve.py` loads it into an in-memory index keyed by `source_id` and caches by the same validity token the BM25 cache uses (`get_data_version()` on Lance, generation counter on Chroma) plus the sidecar's mtime.

Replacement semantics: extraction for source S runs on the candidate chunks inside the ADR-048 window; the new edges are written to `relations.jsonl.candidate.<attempt>` and swapped into the main file only after the candidate write verifies. Failure leaves the previous edges intact.

### D4. Resolver contract: annotate, never filter, fixed ordering

Input: fused (or dense) rows with `source_id`, `chunk_id`, and any `section`/`heading` anchors. Steps:

1. Collect the set of candidate `source_id`s. Load only edges whose endpoints are both in that set (plus edges to/from the candidate set with `scope` matching a candidate chunk anchor).
2. For each ordered source pair with edges, pick the highest-priority edge by origin (`explicit_text` > `metadata` > `model`), then apply the ordering: corroborates → explains → specialises/restricts → amends/supersedes → conflicts_with.
3. Apply `as_of` (default today) against `effective_from`/`effective_until`: an amend/supersede edge not yet effective marks the source as `historical` instead of `controlling`.
4. Scope check: an `amends` edge with a clause scope only marks chunks whose anchor matches; unmatched chunks of the target stay `controlling`.
5. Rows with no edges: `unknown`. Rows whose sources are pairwise `conflicts_with`, or share a scope with incompatible effective windows and no resolving edge: `unresolved_conflict`, plus a `conflicts` entry.
6. Attach `authority_status`, `authority_reason` (edge id, relation, origin, evidence excerpt). Do not touch `score`, order or count.

Ordering rationale: it is the uṣūl sequence for taʿāruḍ al-adillah rendered as a decision procedure (al-jamʿ before al-tarjīḥ before al-naskh, with tawaqquf as the terminal state). The paper states this mapping explicitly; the code comments cite the ADR, not the fiqh literature.

### D5. `as_of` is a first-class parameter

Alternatives: (a) encode dates in `metadata_filter`; (b) new parameter. (a) leaks the resolver's data model into the filter grammar and is store-specific. Chosen: (b). `search(..., as_of: str | None = None)`, validated at the boundary (`transports/mcp/search.py`, CLI) into a `date`; core receives a `date | None`.

### D6. Settings block and profile overlay

`core/authority/settings.py::AuthoritySettings` (pydantic, `extra="forbid"`) with `enabled: bool = False`, `model_tier: Literal["off","onnx_decision","nli"] = "off"`, `model: str = ""` (identity for the model tier), `max_candidate_pairs_per_source: int = 50`. Mirrored `AuthorityBlock` on `EffectiveSettings`. Profile overlay in `core/profiles/resolver.py` for `enabled` and `model_tier` only (the levers that differ per use case), env keys `AUTHORITY__ENABLED`, `AUTHORITY__MODEL_TIER`. `config/legacy.py` gains no entries (no renamed keys).

### D7. Experiment 38 design

- Synthetic corpus: 15 documents across the five case types (three per type), ~60 questions, each labelled with controlling / qualifying / superseded sources, an `as_of` where relevant, and an `unresolved_conflict` flag. Built by hand, checked in under `experiments/38-authority-resolution-<date>/corpus/`.
- Real corpus: one UK Act with at least three amending statutory instruments from legislation.gov.uk, ~40 questions with point-in-time ground truth taken from the consolidated "changes to legislation" tables. Stored under `corpus/` with source URLs and retrieval dates.
- Cells: baseline (authority off) × resolver on (deterministic only) × resolver on + `nli` × resolver on + `onnx_decision` × resolver on without the reconciliation step (ablation). Paired by question. Local hardware only for the deterministic and NLI cells; the ONNX decision-model cell runs locally if the export loads under ONNX Runtime Python, otherwise it is recorded as not run.
- Gates (pre-registered, to be frozen in the plan file before any cell runs): stale authority rate ≤ 0.10 on synthetic and ≤ 0.20 on real; incorrect supersession rate ≤ 0.05; scope resolution accuracy ≥ 0.85; conflict detection recall ≥ 0.80; historical authority accuracy ≥ 0.85. Ordinary recall@k must not regress by more than 1 point (the resolver drops nothing, so this is a guard on the pipeline wiring).
- Metrics are computed by a summariser in the experiment directory; definitions live in the report and the ADR.

### D8. Relation-typing model evaluation is its own small dataset

Around 200 hand-labelled passage pairs with the relation vocabulary, drawn from both corpora. Report accuracy and macro-F1 per model (`onnx_decision`, `nli`, and a small local LLM as a reference row). This is a paper table and the input to choosing the shipped `model_tier` default (which stays `off` regardless).

## Risks / Trade-offs

- [Deterministic patterns miss real-world phrasing] → Report extractor recall on the real corpus separately; the model tier exists for exactly this gap; unresolved targets are logged so the pattern table can grow from evidence.
- [Clause anchors are absent in many PDFs] → Scope falls back to `document`; the report states how often that happened; partial-amendment accuracy is reported only where anchors exist.
- [The sidecar drifts from the vector store after a crash] → Validity token check on load; a `omrg authority rebuild <collection>` CLI command regenerates from stored chunks.
- [Quadratic pair typing in the model tier] → Candidates are capped per source and come only from similarity edges and clause references; the cap is reported.
- [Reviewers read "Islamic methodology" as domain-specific] → The vocabulary and ordering are presented as a general normative-relation model with its provenance stated; the real corpus is UK legislation, not fiqh texts.
- [ONNX export of the decision model does not load in Python ONNX Runtime] → Verified in a scratch script before the wiring task; if it fails the `onnx_decision` backend ships behind the `torch` extra and the paper reports the NLI cell as primary.
- [Reranker consumers start reading `authority_status`] → The spec forbids it; a test asserts the reranker output is invariant to the annotation.

## Migration Plan

Additive. No migration for existing collections: with `enabled=false` nothing changes; on first enable, `omrg authority rebuild <collection>` (or the next ingest) populates the sidecar. Rollback is `AUTHORITY__ENABLED=false`; the sidecar can be deleted safely.

## Open Questions

- Which UK Act to use for the real corpus. Candidate: one with a well-populated "changes to legislation" table and three or more amending instruments after 2015. This affects only the experiment's `corpus/` directory, not the specs or code.
- Exact ADR number at write time (currently expected to be 071).
