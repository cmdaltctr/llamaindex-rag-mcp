# Design

## Context

See proposal.md, Why. The relevant current state:

- `core/retrieval/pipeline.py::search()` (492 lines) resolves `EffectiveSettings` once, runs `_hybrid_query_rows` (dense + sparse → `registry.get("fusion")`) or `registry.get("dense")`, ending at line 335. Then it optionally reranks (`ops.run_reranker`, line 340), re-queries when a hybrid rerank failed (`ops.needs_dense_fallback`, lines 372–392), thresholds and truncates (lines 394–400), and assembles (`assemble`, line 408). Stage helpers live in `core/retrieval/operations.py` (341 lines). The pipeline never branches on strategy names.
- ADR-080 profile-owned pipeline graphs: `compose_pipelines.py::build_operation_catalogue` (lines 59–70) registers each domain's graph operations. Retrieval operations are described in `core/retrieval/graph_adapters_catalogue.py` and registered by `core/retrieval/graph_adapters.py::register_retrieval_operations`. `Engine.search` (`engine.py:219`) and `Engine.ingest` (`engine.py:176`) send user-profile collections to `engine_profiles.search` and `engine_profiles.ingest`, which run the profile's graphs. An edit to the built-in `search()` path alone never reaches these collections.
- Graph settings reach nodes through `lever_params`. `OperationDescriptor` refuses a lever path that is not in `core/pipelines/levers.py::ALLOWED_LEVERS`. Request values reach node parameters through `engine_profiles._REQUEST_TARGETS`.
- Canonical graphs come from `pipeline_templates.py` (`search_template`, `canonical_templates`). `compose_templates.py::profile_templates` maps each template name to a profile slot, so a new template name would need a new slot.
- `EffectiveSettings` is frozen and composed of frozen blocks (`chunking`, `ingestion`, `embedding`, `retrieval`, `metadata`, `answer`). The `answer` block is the pattern for a new block: a pure-data `core/answer/settings.py` model, nested in `config/__init__.py:96`, copied into `AnswerBlock` at `compose_settings.py:65`, defaults in `config/defaults.yaml`, settable in `omrs.jsonc` (ADR-087), and profile-overlaid levers in `core/profiles/resolver.py`.
- ADR-052 gives every chunk a stable `source_id`, `source_version` and `chunk_id`. ADR-048 keeps the previous version of a source when a replacement fails verification. Ingestion skips unchanged files (`core/ingestion/pipeline.py:291–313`). `build_index_identity` (`core/ingestion/source_state.py:128`) does not and will not include authority settings, so enabling authority never re-ingests a file.
- `core/documents/doc_graph.py` builds a deterministic graph. `core/documents/similarity.py::compute_similarity_edges` builds a full N×N cosine matrix over document chunks. Invariant 8: no LLM in graph construction.
- `core/answer/evidence.py::_EVIDENCE_FIELDS` (line 17) lists the lineage keys copied onto each answer evidence row. `core/answer/retriever.py:106` calls `search()` with keyword arguments and needs no change.
- File sizes that constrain the plan: `compose_pipelines.py` 500, `engine.py` 496, `pipeline.py` 492, `profiles/resolver.py` 483, `config/__init__.py` 470, `core/settings.py` 464. The ceiling test fails above 500.
- Import-linter contracts use `unmatched_ignore_imports_alerting = "error"`. `retrieval-stays-independent-of-ingestion` and `integrations-are-leaves` (around `pyproject.toml:603`) constrain this change.
- Experiment numbering: 36 to 39, 41 and 42 are taken. This change takes 43.

## Goals / Non-Goals

**Goals:**

- A resolver that is deterministic at query time and explainable per row.
- Zero behavioural difference when off, on every surface: `search()`, `Engine.search`, MCP `search_documents`, the HTTP search route, `Engine.ingest` and answer evidence. Golden outputs captured on v4 HEAD before any code enforce this.
- One resolver algorithm shared by the built-in path and the user-profile graph path.
- Relation extraction that works without any model, does not depend on ingestion order, and never touches `core/ingestion/`.
- A benchmark and metric set that a reviewer can rerun.

**Non-Goals:**

- Changing reranker behaviour or feeding authority into the reranker score.
- Two-pass answer generation; `as_of` on the answer operation.
- Clause-level chunk alignment across arbitrary document formats (scope is matched to `header_path` anchors when present).
- Web UI for authority status or an `as_of` control.
- Any Taṣawwur or Qiyās machinery (Paper 2).

## Decisions

### D1. Separate `core/authority/` package with strict import rules

Alternatives: (a) extend `core/documents/doc_graph.py` with new edge types; (b) fold into the reranker; (c) new package.

(a) breaks invariant 8 the moment the model tier lands, and the document graph is a batch analysis product, not a query-time service. (b) collapses relevance and authority, which is the exact confusion the paper argues against. (c) matches invariant 6 and invariant 11. Chosen: (c).

Modules: `settings.py`, `relations.py`, `storage.py`, `extract.py`, `link.py`, `ordering.py`, `resolve.py`, `pairs.py`. Import rules, enforced by import-linter:

- `core.authority` SHALL NOT import `core.ingestion`, `core.retrieval`, `core.answer` or `core.pipelines`. It reads metadata by plain key strings (`source_id`, `source_version`, `chunk_id`, `header_path`), as `core/retrieval/dense.py:139` does with `LINEAGE_METADATA_KEYS`.
- `core.authority` MAY import `core.vectordb` (the store read contract), `core.settings`, and `core.documents` (only `pairs.py`, for the model-tier pair proposer).
- `core.ingestion`, `core.retrieval` and `core.answer` SHALL NOT import `core.authority`. Retrieval reaches it only through the registry string `omrs.core.authority.resolve:resolve_rows`.
- `core.authority.settings` joins `settings-models-are-pure-data`.

### D2. Two-tier extraction, deterministic first

Tier 1 (`extract.py`, always on when enabled) is rule-based: a pattern table for supersession, replacement, amendment, repeal, withdrawal, effective-date clauses and clause references, plus title and canonical-path matching against the collection's source inventory. Output edges have `relation_origin=explicit_text`, `confidence=1.0`. A matched statement whose target cannot be resolved yet is kept as a pending reference (D4), not dropped.

Tier 2 (`model_tier`) is opt-in. `pairs.py` proposes candidate pairs from document-graph `similar` edges and from pairs where tier 1 found a clause reference but could not type the relation, capped at `max_candidate_pairs_per_source` per source. The similarity proposer still computes its N×N matrix; the cap limits typed pairs, not the similarity computation. The decision model receives (state = passage A, question = "How does B relate to A?", options = the seven relations + `unrelated`) and returns a distribution. Two backends live in `integrations/authority_models.py`: `onnx_decision` (Julia 1, 144M parameters, ONNX on CPU) and `nli` (an ONNX NLI cross-encoder mapped: entailment → corroborates/explains, contradiction → conflicts_with). The integration returns `dict[str, float]` keyed by relation name, because `integrations-are-leaves` forbids importing `core`. A name-to-builder mapping in the integration selects the backend, with no `if/elif` chain. The composition layer (`engine_authority.py`) builds the callable and injects it.

ADR-074 decides how to run local decision models of the Clef-flash class: a 9B model as a Q8_0 GGUF behind `llama-server` over HTTP. Julia 1 is 144M parameters with an ONNX export. It runs in-process through ONNX Runtime, which is already a dependency, with no external server and no multi-gigabyte download. ADR-074 also states that each new model needs its own reference check, and it adds no Python package; this choice adds none either. The model-tier candidate is not chosen yet. Experiment 38 found Julia 1 weaker than Clef-flash, so task 9.1 decides the candidate before any model-tier code or cell runs. The options are Julia 1 through ONNX, a Clef-flash class model through ADR-074, an NLI cross-encoder, or no model tier at all. That choice can change the `model_tier` values. The deterministic tier and every other cell do not depend on it. Fallback order if Julia 1 is chosen and its smoke test (task 9.2) fails: (1) a Julia 1 GGUF behind `llama-server`, following ADR-074, if one exists and passes its own reference check; (2) the `torch` extra (ADR-073, ⚠️ Ask); (3) the NLI cell becomes the primary model-tier cell. The small local LLM reference row in D8 runs through `llama-server` per ADR-074.

Alternative rejected: LLM-only extraction. It is the least reproducible and the least auditable, and ADR-059 already showed a local 4B judge is not viable on the target hardware.

### D3. Relation sidecar on local disk, one folder per collection

Alternatives: (a) stamp edges into chunk metadata; (b) a table in the vector store; (c) sidecar files beside the store.

(a) puts N-to-N data on rows that are replaced per source. (b) needs one LanceDB and one Chroma implementation, and Chroma has no second table without a second collection. Chosen: (c).

Location: there is no per-collection folder today, so the sidecar gets its own. Root = `lancedb_uri` when `vector_store=lancedb`, else `chroma_persist_dir`. Folder = `<root>/_authority/<collection>/`. The collection name is checked as a single path component with the same rule as `core/vectordb/lancedb/table_name.py::validate_table_name`. Files:

- `relations.jsonl`: one edge per line, keyed by `(source_id, target_id, relation, scope)`.
- `pending.jsonl`: matched statements whose target is not indexed yet.
- `sources.json`: the `(source_id, source_version, title, path)` inventory seen by the last link pass.

Every write goes to `<name>.tmp` and is renamed into place. `resolve.py` caches the parsed index per folder, keyed by each file's `(mtime_ns, size)`, so a write by another process invalidates it.

`EffectiveSettings` carries no `chroma_mode`, so core cannot detect a cloud store by itself. `compose_settings.py` resolves the root once and bakes it into the host-owned field `AuthorityBlock.sidecar_root` (the same pattern as the resolved `hybrid_sparse_backend` at `compose_settings.py:61`). An empty value means "not supported".

Unsupported stores: Chroma Cloud (`chroma_mode=cloud`, ADR-045) and a `lancedb_uri` that contains `://` have no local disk, so `sidecar_root` is empty. Chosen behaviour: the authority stage is not supported there. Search rows get no authority keys, and with diagnostics each row carries `authority_skipped` naming the reason. The post-ingest pass logs one warning per collection. `omrs authority rebuild` exits non-zero with "The relation sidecar needs a local store folder. Chroma Cloud and remote LanceDB URIs are not supported." A workspace-side store was rejected: it splits one collection's state across two places.

### D4. Linking runs after ingestion and does not depend on order

`link.py::link_collection(store, collection, settings, *, type_pair=None)` runs in three steps:

1. Read the current inventory from `store.iter_metadatas(collection)`. Compare it with `sources.json`. A new or changed `source_version` marks a source for extraction. A missing source is removed.
2. For each marked source, read its chunks with `store.iter_documents(collection)`, run tier 1 (and tier 2 when on), and replace that source's outgoing edges and pending references. For each removed source, delete its outgoing edges and set `target_present=false` on incoming edges.
3. Re-resolve every pending reference against the current inventory. A reference that now matches becomes an edge and leaves `pending.jsonl`.

Callers: `Engine.ingest` calls `engine_authority.link_after_ingest(...)` after either branch (built-in or user profile) when the collection's resolved `authority.enabled` is true or the bound user profile's Search graph has an `authority.resolve` step. The check reads settings first, so `core.authority` is not imported when off. `omrs authority rebuild <collection>` calls the same function with an empty inventory, so every source is extracted.

Consequences:

- Ingesting B (which supersedes A) before A still produces the edge: B's statement waits in `pending.jsonl` until A appears.
- ADR-048 failure safety holds by construction: a failed replacement leaves the old `source_version` in the store, so the pass sees no change and keeps the old edges.
- Deletion through `delete_documents` needs no hook: the next pass or rebuild marks the edges. The resolver never sees a deleted source as a candidate.
- `core/ingestion/{pipeline,replacement,writer}.py` stay untouched.
- Existing collections: ingestion skips unchanged files and `build_index_identity` ignores authority settings, so the next ingest only links changed sources. `omrs authority rebuild` is the documented first step for an existing collection.
- Direct `ingest_path_async` callers that bypass `Engine.ingest` (the daemon watcher and the login watcher for built-in profiles) do not run the pass. The next `Engine.ingest` or a rebuild catches up.

### D5. Resolver contract: exact statuses, annotate, never filter

Entry: `resolve.py::resolve_rows(rows, *, sidecar_dir, as_of, today=date.today, reconcile=True, diagnostics=None) -> list[dict]`. `as_of=None` means `today()`. The `today` clock is injected for tests. `reconcile=False` exists only for the Experiment 43 ablation.

Statuses, for one row at the date `as_of`. An edge is *in force* when (`effective_from` is absent or ≤ `as_of`) and (`effective_until` is absent or > `as_of`).

| Status | Exact meaning |
|---|---|
| `controlling` | The row's text governs its scope at `as_of`, and at least one applied relation says so. |
| `qualified` | The row stays valid, but another candidate narrows it (`specialises` or `restricts` targets this row), or the row belongs to a source with an in-force clause-scoped `amends` and has no anchor to place it inside or outside that clause. |
| `superseded` | An in-force `amends` or `supersedes` edge replaces this row's text within the edge's scope. |
| `historical` | Older amending or replacing text that no longer controls: a later in-force edge on the same target and scope displaced it, or its own edge expired before `as_of`. |
| `not_yet_in_force` | The row's source replaces or amends another text, but the edge's `effective_from` is after `as_of`. The target is not affected by that edge. |
| `unresolved_conflict` | Two applicable rows state incompatible rules on the same scope and no ordered relation resolves them. |
| `unknown` | No relation applies to the row. |

Steps:

1. **Candidates.** Collect candidate `source_id`s and anchors (`header_path`). Load edges whose endpoints are both candidates and whose `target_present` is true.
2. **One relation per pair.** For each ordered pair, keep the edges of the best origin (`explicit_text` over `model`; then highest confidence). Pick the first relation in the fixed order: `corroborates` → `explains` → `specialises`/`restricts` → `amends`/`supersedes` → `conflicts_with`. A reconciling edge therefore always wins over supersession for the same pair.
3. **Time and scope.** For each pair whose relation is `amends` or `supersedes`: not yet in force → source rows `not_yet_in_force`; expired → source rows `historical`; in force → target rows inside the scope `superseded`, target rows outside it `controlling`, source rows `controlling`. Amendment chains: when several in-force edges share a target and scope, the edge with the latest `effective_from` controls and the sources of earlier edges are `historical`. Two such edges with the same `effective_from` and no edge between their sources make both sources `unresolved_conflict`.
4. **Applicability** ("does this text apply to the question"). A pair applies only when both rows are in this query's first-stage candidate set, their scopes overlap (`document` scope, or the clause scope matches both rows' `header_path` anchors), and neither row became `superseded`, `historical` or `not_yet_in_force` for that scope in step 3. The resolver makes no semantic relevance judgement; retrieval already did. Pairs that do not apply are skipped in step 5.
5. **Reconcile, then conflict.** On applicable pairs: `corroborates` → both `controlling`; `explains` → both `controlling`, target's `qualified_by` gains the source; `specialises`/`restricts` → target `qualified` with `qualified_by`, source `controlling`; `conflicts_with` → both `unresolved_conflict`, each listing the other in `authority_conflicts`.
6. **Combine.** A row touched by several pairs keeps the first status in this order: `not_yet_in_force`, `superseded`, `historical`, `unresolved_conflict`, `qualified`, `controlling`, `unknown`.
7. **Attach** three keys to every row; do not touch `score`, `score_kind`, order or count:
   - `authority_status`: one value from the table.
   - `authority_reason`: `{"edge_id", "relation", "relation_origin", "evidence_text", "counterpart_source_id", "qualified_by"}`. `evidence_text` is an excerpt of at most 300 characters. `qualified_by` lists the `source_id`s whose rows qualify or explain this row (empty list when none). All fields are `null` or empty for `unknown`.
   - `authority_conflicts`: a list of `{"source_id", "chunk_id", "reason"}` for each conflicting partner row; empty list when none.

With `reconcile=False` (ablation only), steps 4 and 5 skip reconciling relations: `specialises` and `restricts` count as `amends` within their scope, and `corroborates` and `explains` are ignored.

Ordering rationale: it is the uṣūl sequence for taʿāruḍ al-adillah rendered as a decision procedure (al-jamʿ before al-tarjīḥ before al-naskh, with tawaqquf as the terminal state). The paper states this mapping; code comments cite ADR-090, not the fiqh literature.

### D6. Two opt-in routes into one algorithm

**Built-in profiles.** `ops.authority_context(settings, collection, as_of)` returns `None` when `settings.authority.enabled` is false, without importing `core.authority`. `ops.apply_authority(rows, context, timing_report)` returns the rows unchanged for `None`; otherwise it calls `registry.get("authority")` and adds `timing_report["authority_seconds"]` and the edges consulted. `pipeline.py` gains: the `as_of` parameter, one context line, one `apply_authority` call after line 335 (end of the first stage), and one after the fallback re-query (line 392). The net growth is 8 lines or fewer, so the file stays at or under 500 lines; if it would not, `list_collections` moves to `core/retrieval/collections.py` first, with its lazy export kept.

**User profiles.** A new `authority.resolve` operation: `AuthorityParams(enabled: bool | None = None, as_of: date | None = None)`, evidence in and evidence out, `lever_params={"enabled": "authority.enabled"}`, and a bypass that passes evidence through when disabled. An explicit node value wins, then the graph's `authority.enabled` lever, then the profile setting. The adapter calls the same `ops.authority_context` and `ops.apply_authority`. The descriptor goes in `graph_adapters_catalogue.py` and the adapter in `graph_adapters.py`; `build_operation_catalogue` needs no edit because `register_retrieval_operations` registers it. `RankedEvidence` (`graph_adapters_values.py`) gains one `authority` field holding the context, so `threshold_adapter` re-applies authority after its own fallback re-fusion. `ALLOWED_LEVERS` gains `authority.enabled`; `authority.model`, `authority.model_tier` and `authority.sidecar_root` join the host-owned set, because a graph cannot download a model or move storage.

**Templates.** `search_template` and `answer_template` gain `authority: bool = False`, which inserts the step between fusion (or dense) and rerank. `canonical_templates` and `TEMPLATE_NAMES` do not change. `profile_templates` passes `authority=True` only when the base profile's `authority.enabled` is true. Experiment 43 builds its graph cells with `search_template(..., authority=True)`.

**`as_of` plumbing.** `search(..., as_of: date | None = None)`; `Engine.search(..., as_of=None)`; `engine_profiles._REQUEST_TARGETS["as_of"] = ("authority.resolve", "as_of")`, passed as an ISO string; MCP `search_documents(as_of: str | None)` parsed with `date.fromisoformat` inside the existing `try`, so a bad value returns the validation envelope; HTTP `SearchBody.as_of: date | None` plus `SearchRequest.as_of` (`format: date`) in `openapi.yaml`; CLI `--as-of`. When the stage does not run, `as_of` has no effect. For a user-profile collection whose graph has no authority step, diagnostics list `as_of` under `unused_request_values`.

**Head-room.** `engine.py` (496) cannot take `as_of` and the post-ingest call. The `Engine.search` dispatch body moves to a new `engine_search.py` with no behaviour change, before any feature edit. The post-ingest pass, the rebuild entry and the model-tier construction live in a new `engine_authority.py`. `compose_pipelines.py` (500) is not edited.

### D7. Later pipeline stages keep the annotations

- **Rerank-failure fallback.** The re-query at `pipeline.py:378` returns fresh rows without annotations. `ops.apply_authority` runs again on them. The graph `threshold_adapter` does the same after its `_fuse` call.
- **Reranker, threshold and truncation.** The reranker (`reranker.py:464` keeps `top_k`), the threshold and `rank_and_truncate` can cut one side of a conflict or a supersession pair. Chosen behaviour: statuses are computed before the cut and are not recomputed; the surviving row keeps its status and its `authority_conflicts` and `authority_reason.counterpart_source_id` entries naming the cut partner. The reranker never reads the authority keys.
- **Assembly.** `assemble` (`pipeline.py:408`) merges adjacent chunks of one `(source_id, source_version)`. Two such chunks can carry different statuses (a partially amended contract). Chosen rule: assembly splits a contiguous run wherever the three authority keys differ, and merges each part on its own. A neighbour added by `expand_window` has no annotation, so it never merges with an annotated row. Rows without authority keys merge exactly as today. The rule lives in `core/retrieval/assembly.py` (359 lines), so both paths share it.

### D8. Answer evidence passthrough (owned here for Paper 2)

`core/answer/evidence.py::_evidence_rows` copies `authority_status`, `authority_reason` and `authority_conflicts` onto an evidence row only when the search row has the key. `_EVIDENCE_FIELDS` itself does not change, so evidence rows, labelled nodes and answer output stay identical when the keys are absent. The manṭiq change reads `authority_status` from evidence rows when present; this change supplies it.

### D9. Settings block and profile overlay

`core/authority/settings.py::AuthoritySettings` (pydantic, `extra="forbid"`): `enabled: bool = False`, `model_tier: Literal["off","onnx_decision","nli"] = "off"`, `model: str = ""`, `max_candidate_pairs_per_source: int = 50`. Wiring follows the `answer` block: `AuthorityBlock` in `core/settings.py`, with the four fields above plus the derived, host-owned `sidecar_root: str = ""` (D3); `authority: AuthoritySettings` in `config/__init__.py` next to line 96; `authority=AuthorityBlock(...)` in `compose_settings.py` next to line 65; an `authority:` section in `config/defaults.yaml`; `omrs.jsonc` accepts `authority.enabled` by the ADR-087 naming rule. The profile overlay for `enabled` and `model_tier` lives in a new `core/profiles/authority_overlay.py`, called once from `resolver.py`, because `resolver.py` is at 483 lines. Env keys `AUTHORITY__ENABLED` and `AUTHORITY__MODEL_TIER` win over the bundle. `config/legacy.py` gains no entries.

### D10. Experiment 43 design

- Synthetic corpus: 15 documents across the five case types (three per type) plus at least two amendment chains (three dated edges on one clause). About 60 questions, each labelled with controlling, qualifying, superseded, historical and not-yet-in-force sources, an `as_of` where relevant, and `unresolved_conflict`. Built by hand under `experiments/43-authority-resolution-<date>/corpus/`.
- Real corpus: one UK Act with at least three amending statutory instruments from legislation.gov.uk, about 40 questions with point-in-time ground truth from the "changes to legislation" tables. Stored under `corpus/` with source URLs and retrieval dates.
- Cells, paired by question: (1) baseline, authority off; (2) newest-document-wins heuristic: candidate sources grouped by normalised title with years, dates and version numbers removed, the latest effective date in the text (else latest modification time) marked `controlling` and the rest `superseded`, singletons `unknown`; experiment code only, not shipped; (3) deterministic tier only; (4) and (5) deterministic tier plus the model-tier candidates chosen in task 9.1 (until then the plan marks these two cells as pending); (6) deterministic tier with `reconcile=False`. Cells 3 to 6 also run once through the graph path with `search_template(..., authority=True)` to show parity.
- Metric definitions (a row "returned" means present in the final rows; an absent status counts as no warning):
  - Stale authority rate = questions where a ground-truth non-controlling source (superseded, historical or not yet in force at `as_of`) is returned with status `controlling`, `unknown` or no status, divided by questions where such a source is returned. Lower is better.
  - Incorrect supersession rate = questions where a ground-truth controlling or qualifying source is returned as `superseded`, `historical` or `not_yet_in_force`, divided by questions where such a source is returned.
  - Scope resolution accuracy = over general + specific and partial-amendment questions, the share where every returned row of the labelled sources has the expected status.
  - Conflict detection recall = over questions labelled `unresolved_conflict` where both conflicting sources are returned, the share where both rows are `unresolved_conflict` and each lists the other in `authority_conflicts`.
  - Historical authority accuracy = over questions with `as_of`, the share where the source in force at `as_of` is returned as `controlling` and every returned source not in force at `as_of` is `superseded`, `historical` or `not_yet_in_force`.
- Gates (frozen in the plan before any cell runs): stale authority rate ≤ 0.10 synthetic and ≤ 0.20 real; incorrect supersession rate ≤ 0.05; scope resolution accuracy ≥ 0.85; conflict detection recall ≥ 0.80; historical authority accuracy ≥ 0.85; recall@k drops by no more than 1 point against cell 1.
- A ground-truth check in the experiment directory rejects a question without the `unresolved_conflict` field or with an unknown status label before any cell runs. `experiments/_lib/plan.py` checks plans only, so this check is new.
- Paper 2 export: the labelled evidence set (question, returned rows with the three authority keys, ground-truth labels) goes to `output/paper2_evidence.jsonl` with a SHA-256 in the manifest.

### D11. Relation-typing model evaluation is its own small dataset

Around 200 hand-labelled passage pairs, drawn from both corpora. Report accuracy and macro-F1 per model: the candidates chosen in task 9.1, plus a small local LLM through `llama-server` per ADR-074 as a reference row. This is a paper table and the input to choosing the shipped `model_tier` default, which stays `off` regardless.

### D12. Delivery order and timeline

Sixteen weeks, from week 1 (week of 12 October 2026) to week 16 (ending 31 January 2027), matching the research proposal.

| Weeks | Work (task groups) | Milestone |
|---|---|---|
| 1 to 2 | Group 0: golden outputs on v4 HEAD, Experiment 43 plan with frozen gates and metric definitions, synthetic corpus, ground-truth check | M1: plan frozen before any product code |
| 3 to 6 | Groups 1 to 9: head-room moves, settings, sidecar, linking, resolver, both routes, transports, evidence passthrough, model tier | M2: all golden tests pass with authority off; Core + MCP coverage ≥ 95% for `core/authority` |
| 7 to 9 | Group 10 (10.1 to 10.5): real corpus, runner, all cells on the synthetic corpus, then the UK statute corpus | M3: all cells run, gates evaluated |
| 10 to 12 | Group 10 (10.6 to 10.8), group 11 (web workspace) and group 12: relation-typing comparison, Paper 2 evidence export, status badge and `as_of` field in the Knowledge Base search, report, ADR-090, docs | M4: report and ADR-090 written; Paper 2 receives the evidence set (week 10) |
| 13 to 16 | Outside this change: paper draft, reproducibility package, arXiv preprint, venue submission | M5: preprint |

## Risks / Trade-offs

- [Deterministic patterns miss real-world phrasing] → Report extractor recall on the real corpus separately; the model tier exists for this gap; pending references are logged so the pattern table can grow from evidence.
- [Clause anchors are absent in many PDFs] → An unanchored row of a partially amended source is `qualified`, never `superseded`; the report states how often that happened.
- [The sidecar lags the store] → Each `Engine.ingest` re-links changed sources; `omrs authority rebuild <collection>` regenerates everything; direct `ingest_path_async` callers are named in D4.
- [The link pass reads the whole inventory on every ingest] → `iter_metadatas` pages are bounded; chunk text is read only for changed sources; the report states pass time per corpus.
- [Model tier cost] → Typed pairs are capped per source; the similarity proposer's N×N matrix is the existing cost of the document graph and is reported.
- [The sidecar folder confuses a store listing] → A test asserts `list_collections()` is unchanged with `_authority/` present, on LanceDB and local Chroma.
- [Reviewers read "Islamic methodology" as domain-specific] → The vocabulary and ordering are presented as a general normative-relation model with its provenance stated; the real corpus is UK legislation.
- [The chosen decision model does not load] → Task 9.2 smoke-tests it before any model-tier code; D2 gives the fallback order.
- [Watchers skip linking] → The folder watcher and the login watcher call ingestion directly, so a source they index gets no edges until the next `Engine.ingest` or `omrs authority rebuild`. See Open Questions.
- [Reranker consumers start reading `authority_status`] → The spec forbids it; a test asserts reranker output is invariant to the annotation.
- [Head-room moves introduce a regression] → They come first, carry no behaviour change, and must pass the golden tests on their own.

## Migration Plan

Additive. With `enabled=false` nothing changes. To enable on an existing collection: set `AUTHORITY__ENABLED=true` (or the profile or `omrs.jsonc` value), then run `omrs authority rebuild <collection>`. Later ingests keep the sidecar current. Rollback is `AUTHORITY__ENABLED=false`; the `_authority/<collection>/` folder can be deleted safely.

## Open Questions

- Which UK Act to use for the real corpus. Candidate: one with a well-populated "changes to legislation" table and three or more amending instruments after 2015. This affects only the experiment's `corpus/` directory.
- Which model-tier candidate to use (task 9.1). Deferred by the user on 22 October 2026. Experiment 38 found Julia 1 weaker than Clef-flash. Decide before group 9; nothing in groups 0 to 8 depends on it.
- How watchers get edges. Options: (1) run a link pass when a watcher batch ends; (2) document `omrs authority rebuild` for watched collections. Decide before the watcher is used with authority on.
