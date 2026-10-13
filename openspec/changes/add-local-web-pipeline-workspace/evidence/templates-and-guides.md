# Evidence: canonical templates and guides (tasks 4.5, 4.6, 3.7)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted work tree. No installs.

Command prefix:

```bash
PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider <files>
```

## Files

| File | Change |
|---|---|
| `src/omrg/pipeline_templates.py` (new, 218 lines) | `PipelineTemplate`, `TEMPLATE_NAMES`, `ingestion_template`, `search_template`, `answer_template`, `canonical_templates`. Top level, because it names operations from three domains. `core/pipelines` imports no domain. |
| `src/omrg/compose_pipelines.py` (additive, 474 lines) | New `pipeline_templates(engine, collection=None)`. It shapes the templates for one Engine: hybrid from `retrieval.hybrid_enabled`, rerank node bypassed when the Engine has no reranker. |
| `tests/unit/test_pipeline_templates.py` (new) | Search template parity on 15 retrieval cases; template contracts; editable copy. |
| `tests/unit/test_pipeline_templates_parity.py` (new) | Answer template parity on 18 answer cases; ingestion template identity and LanceDB row parity. |
| `tests/unit/test_pipeline_templates_guides.py` (new) | Guide paths, stage tables, defaults and return shapes (task 3.7). |
| `tests/unit/test_pipeline_guide.py` (rewritten) | JSON examples validate against the real Engine catalogue; Python examples run with the web and notebook packages blocked (task 4.6). |
| `docs/guides/pipelines.md` | Real catalogue table, templates section, real-id examples, Python validate/run/cancel/edit examples. "Provisional" removed. |
| `docs/guides/library-usage.md` | Graph methods in the operation list; "Pipeline graphs" section with run and cancel examples. |
| `docs/guides/ingestion.md` | "Ingestion stages as graph operations": seams, adapters, fingerprint, unchanged defaults and result keys. |
| `docs/guides/reranker.md` | "Retrieval stages as graph operations": shared functions, adapters, unchanged defaults, ÷30 rule, row keys. |
| `docs/guides/architecture.md` | `core/answer`, `core/pipelines`, `core/workspace` rows; "Pipeline graphs: who owns what" table; composition-root split; `transports/api` runtime; six new import contracts in the enforced-rules table; integration inventory gains `process_launcher` and five `workspace_sqlite` modules (count 24 to 30). |

`canonical_ingestion_definition` is unchanged. `ingestion_template()` returns it, so the template and the fingerprint read one description. The ingestion graph tests did not need a rerun for that reason; they ran in the regression set anyway.

## Template shapes

| Template | Nodes | Input | Output |
|---|---|---|---|
| `ingestion` | `discover` `identify` `read` `normalise` `enrich` `chunk` `embed` `commit` | `path` | `summary` (commit summary, per unit) |
| `search` | `prepare` `dense` [`sparse` `fuse`] `rerank` `select` `context` | `query` | `results` (`ContextBundle`) |
| `answer` | search chain + `evidence` `synthesise` `cite` `verify` | `query` (to `prepare` and `synthesise`) | `answer` (answer result dict) |

Outputs are commit summaries, context or answers only. `test_template_outputs_are_summaries_or_results` checks the port kind of every output.

## Test-first record

1. Template tests before `pipeline_templates.py` existed: **2 collection errors** (`ModuleNotFoundError`).
2. With the module: `test_pipeline_templates.py` 24 passed; `test_pipeline_templates_parity.py` first run 17 failed (answer template had the rerank node enabled on an Engine without a reranker: `capability_unavailable`) and 1 failed (ingestion outputs are per unit, not top-level). Test fixed to pass `rerank=False` and read `result.units[*].outputs`. Then 21 passed.
3. Guide tests rewritten before the guides: **6 failed, 8 passed** (provisional ids, `select.dense_threshold`, no Python examples). After `pipelines.md`: 2 failed (library guide had no examples). After `library-usage.md`: **14 passed**.
4. `test_strategy_registration_inventory.py` before the architecture edit: **2 failed** (missing `workspace_sqlite` rows; count 24 vs 28 discovered). After the first edit: 2 failed again, because `process_launcher` and `workspace_sqlite.deletion` had appeared from other agents. After both rows: 15 passed.
5. Guides test: first run 1 failed (the retrieval table named registry names, not functions). Table changed to name `_dense_query_rows` and `rrf_with_metadata`. Then 10 passed.

## Mutation checks

A scratch script changed one line, ran the tests, restored the file and compared SHA-256.

| Mutation | Result |
|---|---|
| Hybrid template drops the sparse-to-fuse edge | 8 failed |
| Answer query wired to `prepare` instead of `synthesise` | 22 failed |
| `verify` node not wired | 22 failed |
| Rerank node always enabled | 25 failed |
| `pipeline_templates()` ignores reranker capability | 2 failed |
| `pipeline_templates()` ignores `hybrid_enabled` | 2 failed |
| Template exposes ranked evidence as an output | 1 failed |
| Ingestion guide names a missing module | 2 failed |
| Retrieval guide names a missing function | 1 failed |
| Wrong documented `chunk_overlap` default | 1 failed |
| Ingest key dropped from the guide | 1 failed |
| Guide JSON names an unknown operation | 2 failed |
| Cancel example no longer cancels | 1 failed |
| Guide example imports `fastapi` | 1 failed |
| Wrong inventory row | 1 failed |

## Parity scenarios

| Scenario | Test | Compared |
|---|---|---|
| Canonical retrieval parity (15 cases, dense and hybrid, rerank success/failure, policy, fetch_k, empty) | `test_search_template_matches_engine_search` | `Engine.run_pipeline(search template)` vs `Engine.search`: public rows exactly; ids, scores, score kinds, rank provenance (diagnostics); rerank failure reason as node fallback. |
| Canonical answer parity (18 cases) | `test_answer_template_matches_engine_answer` | `Engine.run_pipeline(answer template)` vs `Engine.answer` on an Engine over the case rows: full result (timings stripped), key order, answer and judge call counts. Covers no-evidence, citations, failure attribution, master switch and every verification outcome. |
| Canonical ingestion parity | `test_ingestion_template_writes_the_same_rows_as_engine_ingest` | Stored rows and source identities in LanceDB, three committed units, `files_indexed == 3`. |
| Template is editable | `test_template_copy_without_reranker_validates_and_runs` | A copy without the rerank node validates, runs, and equals `Engine.search`. |
| Each template validates | `test_every_template_passes_engine_validation` | Draft check and admission, hybrid on/off, reranker present/absent. |

The two `policy_default_*` cases record the process default. Both Engine paths here receive the same explicit settings, as in `retrieval-adapters.md`.

## Guide examples (task 4.6)

- JSON examples: preflight against `build_operation_catalogue()`, the Engine catalogue.
- Python examples (`pipelines.md`: validate, run, cancel, edit; `library-usage.md`: run, cancel) run in order on `build_engine(...)` over `FakeStore`. A meta-path hook blocks `fastapi`, `starlette`, `uvicorn` and `marimo`; the test fails if any of them is in `sys.modules` afterwards.
- A fresh interpreter imports `omrg.engine`, `omrg.core.pipelines`, `omrg.compose_pipelines` and `omrg.pipeline_templates` and loads none of the blocked packages.

## Final results

| Command | Result |
|---|---|
| New and rewritten test files (4) | 69 passed |
| Regression set: all `tests/unit/test_pipeline_*`, `test_engine_pipelines*`, `test_ingestion_graph*`, `test_retrieval_graph*`, `test_answer_graph*`, `tests/test_engine.py`, file size, global settings reads, import boundaries, docs references, retired env vars, strategy inventory, contract coverage (`-m "not slow"`) | 561 passed |
| `PYTHONPATH=src .venv/bin/lint-imports` | 16 kept, 0 broken |
| `ruff format`, `ruff check` on owned Python files | Pass |

## Deviations and open points

1. Templates live in `src/omrg/pipeline_templates.py` as Python builders, not JSON files. The builders produce plain JSON data that `parse_definition` validates. No `engine.py` change was needed.
2. `compose_pipelines.pipeline_templates` reads `engine._graph_host(...)` for capabilities. It is a composition-root module, so the private call stays inside the composition boundary. A public `Engine` accessor was not added.
3. The search template output is named `results` and carries a `ContextBundle`. Callers use `.public_rows()` for the `search()` row shape. The HTTP layer must serialise it with `public_rows()`.
4. The answer template wires `verify.claims` always. It follows `answer.verify_claims`, so it is inert unless verification is on, as in `Engine.answer`.
5. `canonical_templates(rerank=True)` is the default. On an Engine without a reranker, use `pipeline_templates(engine)` or pass `rerank=False`; otherwise validation reports `capability_unavailable` on `rerank`.
