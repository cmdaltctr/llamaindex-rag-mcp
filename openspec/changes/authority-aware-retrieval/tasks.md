# Tasks

Timeline: design D12. Group 0 is weeks 1 to 2 (milestone M1). Groups 1 to 9 are weeks 3 to 6 (M2). Group 10 is weeks 7 to 12 (M3, M4). Group 11 (web workspace) runs after Experiment 43 and does not block it. Group 12 closes the change by week 12.

## 0. Baseline and pre-registration (weeks 1 to 2, before any product code)

- [ ] 0.1 Capture golden outputs on v4 HEAD before any code change: run a fixed fixture collection through `search()`, `Engine.search`, MCP `search_documents`, the HTTP route `POST /collections/{collection}/search` and `Engine.ingest`, for one built-in-profile collection and one user-profile collection, and store the outputs without timing and memory fields under `tests/golden/authority_off/`; verify `tests/test_authority_golden_off.py` passes on v4 HEAD and fails when one stored value is changed by hand
- [ ] 0.2 Create `experiments/43-authority-resolution-<date>/` from `EXP_PROTOCOL_TEMPLATE.md` and write the plan with the cell matrix, the frozen gates and the exact metric definitions from design D10, with model-tier cells 4 and 5 marked pending until task 9.1; verify the plan validator in `experiments/_lib/plan.py` accepts the plan
- [ ] 0.3 Write `validate_ground_truth.py` in the experiment directory; verify a unit test that it rejects a question without the `unresolved_conflict` field and a question with an unknown status label
- [ ] 0.4 Build the synthetic corpus (15 documents, five case types, at least two amendment chains) and about 60 labelled questions; verify `validate_ground_truth.py` accepts the ground truth

## 1. Head-room, settings and package scaffold

- [ ] 1.1 Move the body of `Engine.search` to a new `src/omrg/engine_search.py` with no behaviour change, and add the module to `tests/unit/test_verification_gaps_boundaries.py` and the `core-never-imports-top-level-modules` contract; verify the golden test from 0.1, `lint-imports` and `uv run pytest tests/test_file_size_ceiling.py` pass
- [ ] 1.2 Add `src/omrg/core/authority/settings.py` with `AuthoritySettings` (`enabled=False`, `model_tier="off"`, `model=""`, `max_candidate_pairs_per_source=50`, `extra="forbid"`); verify a unit test rejects unknown fields and an invalid `model_tier`
- [ ] 1.3 Add `AuthorityBlock` (the four fields plus `sidecar_root=""`) to `src/omrg/core/settings.py` and wire `authority: AuthorityBlock` into `EffectiveSettings`; verify the frozen-block tests and the file-size ceiling test pass
- [ ] 1.4 Wire the `AUTHORITY__` source: add `authority: AuthoritySettings` in `src/omrg/config/__init__.py` next to line 96, `authority=AuthorityBlock(...)` with the resolved `sidecar_root` in `src/omrg/compose_settings.py` next to line 65, and an `authority:` section in `src/omrg/config/defaults.yaml`; verify settings tests that `AUTHORITY__ENABLED=true` and `authority.enabled: true` in `omrg.jsonc` (ADR-087) each resolve to `True`, that `CHROMA_MODE=cloud` gives an empty `sidecar_root`, and that the `omrg config init` template lists the `authority` keys
- [ ] 1.5 Add `src/omrg/core/profiles/authority_overlay.py` for `authority.enabled` and `authority.model_tier` with env-over-bundle precedence, and call it once from `core/profiles/resolver.py`; verify the `profiles-dual-use-case` scenarios with tests and the file-size ceiling test
- [ ] 1.6 Set `authority.enabled: false` in `src/omrg/config/profiles/codebase.yaml`; verify the "Codebase profile never enables authority" scenario with a test
- [ ] 1.7 Create `src/omrg/core/authority/__init__.py` with PEP 562 lazy exports; verify that importing `omrg.core.authority` loads no submodule
- [ ] 1.8 Add `omrg.core.authority` to `core-business-avoids-providers-transports` and `omrg.core.authority.settings` to `settings-models-are-pure-data` in `pyproject.toml`, with no ignore entry; verify `lint-imports` passes
- [ ] 1.9 Add two import-linter contracts with `allow_indirect_imports = true` and no ignore entry: `core.authority` must not import `core.ingestion`, `core.retrieval`, `core.answer` or `core.pipelines`, and those four must not import `core.authority`; verify `lint-imports` passes and fails on a temporary bad import

## 2. Relation model and sidecar

- [ ] 2.1 Implement `core/authority/relations.py`: `Relation` (seven values), `RelationOrigin` (`explicit_text`, `model`) and the frozen `AuthorityEdge` with `target_present`; verify unit tests for both vocabulary scenarios in the `authority-resolution` delta
- [ ] 2.2 Implement `core/authority/storage.py` for `<sidecar_root>/_authority/<collection>/` with atomic `.tmp` then rename writes of `relations.jsonl`, `pending.jsonl` and `sources.json`; verify tests that an interrupted write keeps the old file and that a collection name with a path separator is rejected
- [ ] 2.3 Add the parsed-index cache keyed by each file's `(mtime_ns, size)`; verify a test that a write from a second process invalidates the cache
- [ ] 2.4 Test `list_collections()` with an `_authority/` folder present; verify the names are unchanged on LanceDB and on local Chroma (Chroma case skips without the extra)

## 3. Deterministic extraction and post-ingest linking

- [ ] 3.1 Implement the `core/authority/extract.py` pattern table for supersession, replacement, amendment, repeal, withdrawal, effective-date and clause-reference language; verify a table-driven test with at least 25 positive and 10 negative sentences
- [ ] 3.2 Implement target resolution by title and canonical path, storing a pending reference and an `unresolved_target` diagnostic when no source matches; verify both extraction scenarios with tests
- [ ] 3.3 Implement `core/authority/link.py::link_collection` to compare the inventory from `store.iter_metadatas` with `sources.json`, extract changed sources from `store.iter_documents`, and remove deleted sources' outgoing edges; verify tests for new, changed, unchanged and deleted sources
- [ ] 3.4 Re-resolve pending references at the end of each link pass; verify a test that ingests B (which supersedes A) before A in two `Engine.ingest` calls and finds `B → A supersedes` after the second call
- [ ] 3.5 Add `src/omrg/engine_authority.py::link_after_ingest` and one call to it in `Engine.ingest` after both branches, gated on resolved settings or a graph `authority.resolve` step; add the module to the boundaries test and contract list as in 1.1; verify the `Engine.ingest` golden output, a subprocess test that `omrg.core.authority` is not imported when off, and the file-size ceiling test
- [ ] 3.6 Test a failed replacement of source B; verify the sidecar keeps B's previous edges and holds no edge from the failed attempt
- [ ] 3.7 Test deletion of source A through `delete_documents` followed by a link pass; verify `B → A` keeps `target_present=false` and the resolver ignores it
- [ ] 3.8 Add `omrg authority rebuild <collection>` in `src/omrg/transports/cli/authority.py` and import it in `src/omrg/transports/cli/__init__.py`; verify a CLI test on a fixture collection indexed before authority was enabled, and the Chroma Cloud refusal message on stderr with a non-zero exit

## 4. Query-time resolver

- [ ] 4.1 Implement `core/authority/ordering.py` with the fixed relation order, origin priority and status combination order from design D5; verify unit tests for the ordering scenarios, including "Reconciliation outranks supersession" and "Explicit text outranks a model guess"
- [ ] 4.2 Implement `core/authority/resolve.py::resolve_rows` with the status table, the applicability step, `header_path` scope matching, in-force windows and an injected `today` clock; verify unit tests for every status, applicability, conflict and point-in-time scenario in the `authority-resolution` delta
- [ ] 4.3 Implement amendment-chain resolution; verify the "Three amendments to one clause" scenario and a same-date tie that gives `unresolved_conflict`
- [ ] 4.4 Add the `reconcile=False` ablation switch; verify a test that `specialises` then acts as `amends` within its scope
- [ ] 4.5 Register `"authority"` in `core/retrieval/registry.py` pointing at `omrg.core.authority.resolve:resolve_rows`, and add `authority` to the `registry-names:retrieval` block in `docs/guides/architecture.md` (around line 635); verify `tests/test_strategy_registration_inventory.py` passes
- [ ] 4.6 Write a subprocess test that imports `omrg.core.retrieval.pipeline` and runs a search with `authority.enabled` false; verify `omrg.core.authority.resolve` is absent from `sys.modules`

## 5. Built-in search path

- [ ] 5.1 Add `ops.authority_context` and `ops.apply_authority` to `core/retrieval/operations.py`; verify unit tests that a `None` context returns the rows unchanged and that an enabled context adds the three keys and `timing_report["authority_seconds"]`
- [ ] 5.2 Add `as_of`, one context line and one `ops.apply_authority` call after the first stage (after line 335) to `core/retrieval/pipeline.py::search()`; verify the golden test, a test that scores, order and row count are unchanged when enabled, and the file-size ceiling test
- [ ] 5.3 Add one `ops.apply_authority` call after the fallback re-query (after line 392); verify a test that forces a hybrid rerank failure and gets annotated rows
- [ ] 5.4 Test a conflict pair where truncation keeps one row; verify the surviving row keeps `unresolved_conflict` and names the cut row in `authority_conflicts`
- [ ] 5.5 Split contiguous runs in `core/retrieval/assembly.py` where the three authority keys differ; verify the "Assembly does not merge across statuses" scenario and that the existing assembly tests pass unchanged
- [ ] 5.6 Test the reranker with and without annotation keys on the same rows; verify scores and order are identical
- [ ] 5.7 Add the `authority_skipped` diagnostic for an empty `sidecar_root`; verify the "Search on an unsupported store stays unchanged" scenario

## 6. User-profile graph path

- [ ] 6.1 Add `authority.enabled` to `ALLOWED_LEVERS` and `authority.model`, `authority.model_tier` and `authority.sidecar_root` to the host-owned set in `core/pipelines/levers.py`; verify tests that a graph may override `authority.enabled` and may not override `authority.model_tier`
- [ ] 6.2 Add `AuthorityParams` and the `authority.resolve` descriptor (bypass, `lever_params={"enabled": "authority.enabled"}`) to `core/retrieval/graph_adapters_catalogue.py` and register it in `register_descriptors`; verify a catalogue test lists `authority.resolve` with `compose_pipelines.py` unchanged
- [ ] 6.3 Add `authority_adapter` to `core/retrieval/graph_adapters.py` and an `authority` field to `RankedEvidence` in `graph_adapters_values.py`; verify the "Graph step annotates like the built-in path" and "Disabled step is a pass-through" scenarios
- [ ] 6.4 Re-apply authority in `threshold_adapter` after its `_fuse` fallback; verify a graph test that forces a rerank failure and gets annotated rows
- [ ] 6.5 Add `authority: bool = False` to `search_template` and `answer_template` in `src/omrg/pipeline_templates.py`; verify `tests/unit/test_pipeline_templates.py` passes unchanged and a test that the option inserts the step between fusion or dense and rerank
- [ ] 6.6 Pass `authority=True` from `compose_templates.py::profile_templates` only when the base profile enables authority; verify a test for both base-profile values
- [ ] 6.7 Map `as_of` to `("authority.resolve", "as_of")` in `engine_profiles._REQUEST_TARGETS`; verify tests that `as_of` reaches the step and that diagnostics list `as_of` in `unused_request_values` for a graph without the step

## 7. Engine and transports

- [ ] 7.1 Add `as_of: date | None = None` to `Engine.search` in `engine_search.py` and pass it to both branches; verify the historical scenario through `Engine.search` for a built-in and a user-profile collection
- [ ] 7.2 Add `as_of: str | None = None` to `transports/mcp/search.py::search_documents`, parsed inside the existing `try`; verify every scenario in the `mcp-search-filtering` delta
- [ ] 7.3 Add `as_of` to `SearchBody` in `transports/api/routes/documents.py` and to `SearchRequest` (`format: date`) in `transports/api/openapi.yaml`; verify the OpenAPI conformance tests and a route test for the historical scenario and a 400 on a bad date
- [ ] 7.4 Add `--as-of` to `transports/cli/search.py` with output still on stderr; verify a CLI test
- [ ] 7.5 Keep `ToolAnnotations` on every touched MCP tool; verify the annotation test passes
- [ ] 7.6 Run the golden test from 0.1 on all five surfaces with authority off, with and without `as_of`; verify every output equals its golden file

## 8. Answer evidence passthrough (for Paper 2)

- [ ] 8.1 Copy `authority_status`, `authority_reason` and `authority_conflicts` in `core/answer/evidence.py::_evidence_rows` only when the search row has them, leaving `_EVIDENCE_FIELDS` unchanged; verify both `grounded-answer-synthesis` scenarios with tests
- [ ] 8.2 Test an answer on an authority-enabled collection through the core answer path and the MRTR resolver; verify evidence rows carry `authority_status` with `core/answer/retriever.py` unchanged

## 9. Model tier (opt-in)

- [ ] 9.1 Decide the model-tier candidates with the user (Julia 1 through ONNX, a Clef-flash class model through ADR-074, an NLI cross-encoder, or no model tier) and record the decision in the Experiment 43 plan, updating the `model_tier` values in design D2, D9 and the `profiles-dual-use-case` delta if they change; verify the plan validator accepts the plan with cells 4 and 5 no longer pending
- [ ] 9.2 Write a scratch script outside `src/` that loads each chosen candidate and scores one 8-option relation question; verify the result and any fallback route from design D2 are recorded in the experiment notes
- [ ] 9.3 Add `src/omrg/integrations/authority_models.py` with one builder per candidate chosen in 9.1 behind a name-to-builder mapping, each returning `type_pair(a_text, b_text) -> dict[str, float]`, and add its row to the `integration-inventory` table in `docs/guides/architecture.md` (around line 536) with the marker count raised by one; verify `lint-imports`, `tests/test_strategy_registration_inventory.py` and a unit test with a stub session pass
- [ ] 9.4 Build the `type_pair` callable in `engine_authority.py` when `model_tier` is not `off` and inject it into `link_collection`; verify the "Model tier off emits no model edges" scenario
- [ ] 9.5 Implement `core/authority/pairs.py` to propose pairs from document-graph `similar` edges and untyped clause references with the per-source cap; verify the "Typed pairs respect the cap" scenario
- [ ] 9.6 Emit `relation_origin=model` edges with the model probability as confidence; verify a link test with a stub callable and that the document graph edge count is unchanged

## 10. Experiment 43 (weeks 7 to 12)

- [ ] 10.1 Assemble the real corpus: one UK Act plus at least three amending instruments from legislation.gov.uk and about 40 point-in-time questions; verify `validate_ground_truth.py` accepts it and `corpus/README.md` records source URLs and retrieval dates
- [ ] 10.2 Build the relation-typing dataset (about 200 labelled passage pairs); verify an inter-annotator spot check on 40 pairs is recorded
- [ ] 10.3 Implement the newest-document-wins heuristic from design D10 in the experiment directory; verify a unit test on a three-document fixture
- [ ] 10.4 Write `run_eval.py` with checkpoint and resume, per-stage JSONL traces and atomic `output/` writes, and `summarise_eval.py` with the five metric definitions from the plan plus recall@k; verify a dry run on two questions produces a checkpoint and a summary
- [ ] 10.5 Run all six cells from design D10 paired by question, plus the graph-path parity run; verify `output/` holds every cell's manifest with `authority.enabled`, `authority.model_tier` and the model identity
- [ ] 10.6 Run the relation-typing model comparison; verify the report records accuracy and macro-F1 per model
- [ ] 10.7 Export the labelled evidence set for Paper 2 to `output/paper2_evidence.jsonl`; verify the manifest records its SHA-256 and the file holds the three authority keys and the ground-truth labels per row
- [ ] 10.8 Write `report.md` separating measurements, explanations and decisions, and `analysis.py` (Jupytext percent format); verify `EXP_README.md` lists Experiment 43 with its verdict

## 11. Web workspace (after Experiment 43)

- [ ] 11.1 Load the `omrg-design` skill and read `web/DESIGN.md`; verify the plan for 11.2 to 11.4 uses only `components/ui/` primitives and tokens
- [ ] 11.2 Add the optional `authority_status`, `authority_reason` and `authority_conflicts` fields to `SearchHit` and an `as_of` field to the `searchCollection` body in `web/src/api/documents.ts`, sent as `null` when omitted; verify `npm run typecheck` and a unit test of the request body with and without a date
- [ ] 11.3 Add an optional "As of" date field to `web/src/knowledge-base/SearchForm.tsx`; verify tests that an empty field sends `null` and an invalid date shows an error message without a request
- [ ] 11.4 Show a status badge, the reason text and the conflicting rows in `web/src/knowledge-base/ResultList.tsx` only when a row has `authority_status`; verify tests for the three scenarios in "The web workspace shows authority annotations" and that the existing `ResultList` and `SearchSection` tests pass unchanged
- [ ] 11.5 Run `npm run lint`, `npm run typecheck` and `npm test` in `web/`; verify all three pass
- [ ] 11.6 Check the search form and an annotated result list in a browser at 1280 px and 390 px, in light and dark themes; verify four screenshots show no overflow or contrast failure

## 12. Decision, docs and closure

- [ ] 12.1 Write `docs/adr/090-authority-aware-retrieval.md` (ADR-090) recording the vocabulary, the ordering, the status definitions, the sidecar decision, the ADR-074 relation and the gate outcomes; verify it is linked from `docs/adr/ADR_README.md`
- [ ] 12.2 If every gate passes, set `authority.enabled: true` in `src/omrg/config/profiles/documents.yaml` and update the `profiles-dual-use-case` delta; otherwise leave it `false` and record the reason in ADR-090; verify the profile test matches the chosen default
- [ ] 12.3 Update `docs/guides/configuration.md`, `docs/guides/mcp-tools.md`, `docs/guides/architecture.md` (package, import rules, sidecar location) and `.env.example`; verify a grep for `AUTHORITY__` finds each file
- [ ] 12.4 Run `uv run pytest -m "not slow" --cov=omrg`, `./scripts/local_ci.sh` and `openspec validate --all --strict`; verify Core + MCP coverage for `core/authority` is at least 95 percent and `tests/test_file_size_ceiling.py` passes
