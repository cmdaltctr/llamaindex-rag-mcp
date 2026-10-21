# Tasks

## 1. Settings and package scaffold

- [ ] 1.1 Add `src/omrg/core/authority/settings.py` with `AuthoritySettings` (`enabled=False`, `model_tier="off"`, `model=""`, `max_candidate_pairs_per_source=50`, `extra="forbid"`) and verify a unit test rejects unknown fields and an invalid `model_tier`
- [ ] 1.2 Add `AuthorityBlock` to `src/omrg/core/settings.py`, wire `authority: AuthorityBlock` into `EffectiveSettings`, and verify the frozen-block test suite passes with the new block
- [ ] 1.3 Add the `AUTHORITY__` env source in `config/` and verify `AUTHORITY__ENABLED=true` resolves to `EffectiveSettings.authority.enabled is True` in a settings test
- [ ] 1.4 Extend `core/profiles/resolver.py` to overlay `authority.enabled` and `authority.model_tier` with env-over-bundle precedence, set `authority.enabled: false` explicitly in `config/profiles/codebase.yaml`, and verify the three profile scenarios in the `profiles-dual-use-case` delta with tests
- [ ] 1.5 Create `src/omrg/core/authority/__init__.py` with PEP 562 lazy exports and add `omrg.core.authority` to the `core-business-avoids-providers-transports` source modules in `pyproject.toml` with no ignore entry; verify `lint-imports` passes

## 2. Relation model and storage

- [ ] 2.1 Implement `core/authority/relations.py`: `Relation` enum (seven values), `RelationOrigin` enum, `AuthorityEdge` frozen dataclass with validation (`ValueError` on unknown relation; `explicit_text` forces `confidence=1.0`), and verify unit tests cover both scenarios in the `authority-resolution` delta
- [ ] 2.2 Implement `core/authority/storage.py`: JSONL sidecar at `<collection layout>/authority/relations.jsonl`, atomic `.tmp` → rename write, candidate file per attempt, `load(collection)`, `replace_source_edges(collection, source_id, edges, attempt)`, `commit_candidate(...)`, `mark_dangling(target_source_id)`; verify tests for failed-candidate preservation and dangling-on-delete
- [ ] 2.3 Add a validity-token cache in `storage.py` reusing the BM25 cache token pattern (Lance `get_data_version()`, Chroma generation counter) plus sidecar mtime; verify a test that a cross-process sidecar write invalidates the in-memory index

## 3. Deterministic extraction

- [ ] 3.1 Implement `core/authority/extract.py` pattern table for supersession, replacement, amendment, repeal, withdrawal, effective-date and clause-reference language; verify a table-driven test with at least 25 positive and 10 negative sentences
- [ ] 3.2 Implement target resolution by title and canonical path against the collection source inventory (via `store.iter_metadatas`), emitting no edge and an `unresolved_target` diagnostic when unmatched; verify both scenarios with tests
- [ ] 3.3 Hook extraction into the ingestion path after chunking and before write, inside the ADR-048 replacement window, writing to the candidate sidecar and committing with the source commit; verify an integration test that a failed candidate leaves prior edges intact and a successful one replaces them
- [ ] 3.4 Handle source deletion in `core/ingestion` deletion path by removing outgoing edges and marking incoming edges dangling; verify with a test through `delete_documents`

## 4. Query-time resolver

- [ ] 4.1 Implement `core/authority/resolve.py::resolve(rows, edges, as_of, ...)` with the fixed ordering, origin priority, scope matching on chunk anchors, effective-window handling and `unknown` default; verify unit tests for every scenario in the resolver, ordering, conflict and point-in-time requirements of the `authority-resolution` delta
- [ ] 4.2 Register `"authority"` in `core/retrieval/registry.py` pointing at `omrg.core.authority.resolve:resolve_rows`; verify the registry inventory test lists it and a test asserts `omrg.core.authority.resolve` is not in `sys.modules` after importing the pipeline with authority disabled
- [ ] 4.3 Add the guarded stage call in `core/retrieval/pipeline.py::search()` between fusion/dense and rerank, accumulate `timing_report["authority_seconds"]`, attach `conflicts` to the result envelope when enabled; verify a byte-equality test that `search()` output is identical with `authority.enabled=false` before and after this change, and a test that scores, order and row count are unchanged when enabled
- [ ] 4.4 Add `as_of: date | None` to `search()` and thread it to the resolver; verify a unit test for the historical scenario

## 5. Transports

- [ ] 5.1 Add `as_of: str | None = None` to `transports/mcp/search.py::search_documents`, validate to a date at the boundary, return the validation error envelope on bad input; verify both scenarios in the `mcp-search-filtering` delta with tests
- [ ] 5.2 Add `--as-of` to the CLI search command (stderr output unchanged) and verify a CLI test
- [ ] 5.3 Add `omrg authority rebuild <collection>` CLI command that regenerates the sidecar from stored chunks; verify a CLI test on a small fixture collection
- [ ] 5.4 Keep `ToolAnnotations` on every touched MCP tool and verify the annotation test still passes

## 6. Model tier (opt-in)

- [ ] 6.1 Write a scratch script (not committed to `src/`) that loads the Julia 1 ONNX export under ONNX Runtime Python and scores one 8-option relation question; record the result in the experiment notes and choose whether `onnx_decision` ships on the default path or behind the `torch` extra
- [ ] 6.2 Add `integrations/authority_models.py` with two builders (`onnx_decision`, `nli`) returning a `type_pair(a_text, b_text) -> dict[Relation, float]` callable, constructed only in `compose.py` and injected; verify import-linter passes and a unit test uses a stub callable
- [ ] 6.3 Implement candidate-pair proposal from document-graph `similar` edges and untyped clause references with the per-source cap; verify a test that an all-pairs scan never happens (pair count ≤ cap × sources)
- [ ] 6.4 Emit `relation_origin=model` edges with the model probability, and verify the resolver test that an `explicit_text` edge outranks a `model` edge for the same pair

## 7. Experiment 43

- [ ] 7.1 Create `experiments/43-authority-resolution-<date>/` from `EXP_PROTOCOL_TEMPLATE.md`, write the plan with the five pre-registered gates and the cell matrix, and verify the plan validator passes
- [ ] 7.2 Build the synthetic corpus (15 documents, five case types) and ground truth (~60 questions with controlling / qualifying / superseded / `unresolved_conflict` / `as_of` labels); verify the ground-truth validator rejects a question missing the conflict label
- [ ] 7.3 Assemble the real corpus: one UK Act plus at least three amending instruments from legislation.gov.uk with ~40 point-in-time questions; record source URLs and retrieval dates in `corpus/README.md`
- [ ] 7.4 Build the relation-typing dataset (~200 labelled passage pairs) and verify inter-annotator spot check on 40 pairs is recorded
- [ ] 7.5 Write `run_eval.py` with checkpoint/resume, per-stage JSONL traces, atomic `output/` writes, and `summarise_eval.py` computing the five authority metrics plus recall@k; verify a dry run on two questions produces a checkpoint and a summary
- [ ] 7.6 Run all cells (baseline, deterministic, deterministic+nli, deterministic+onnx_decision if 6.1 passed, no-reconciliation ablation) paired by question; verify `output/` holds every cell's manifest with `authority.enabled` and `model_tier` recorded
- [ ] 7.7 Run the relation-typing model comparison and record accuracy and macro-F1 per model in the report
- [ ] 7.8 Write `report.md` separating measurements, explanations and decisions, and `analysis.py` (Jupytext percent format); verify `EXP_README.md` lists Experiment 43 with its verdict

## 8. Decision, docs and closure

- [ ] 8.1 Write the ADR (expected ADR-071) recording the relation vocabulary, the ordering, the storage decision and the gate outcomes; verify it is linked from `docs/adr/ADR_README.md`
- [ ] 8.2 If every gate passes, set `authority.enabled: true` in `config/profiles/documents.yaml` and update the `profiles-dual-use-case` delta; otherwise leave it `false` and record the reason in the ADR; verify the profile test matches the chosen default
- [ ] 8.3 Update `docs/guides/configuration.md`, `docs/guides/mcp-tools.md`, `docs/guides/architecture.md` (new package and invariant note) and `.env.example`; verify a grep for `AUTHORITY__` finds each
- [ ] 8.4 Run `uv run pytest -m "not slow" --cov=omrg`, `./scripts/local_ci.sh` and `openspec validate --all --strict`; verify Core + MCP coverage for `core/authority` is ≥ 95 percent
- [ ] 8.5 Run `graphify update .` and verify the graph lists `core/authority`
