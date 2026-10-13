# Offline end-to-end: browser and notebook clients run one rewired graph (task 9.1)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted work tree. No installs, no network, no model download, no real LLM call. `.env` not read (`Settings(_env_file=None)`).

**Verdict: PASS.** The browser run and the notebook run of the same saved revision match on graph identity and revision, effective settings snapshot, inputs, status, ranked rows and score kinds, outputs (timings removed) and the event sequence (kinds and node order).

## Set-up

The launcher is a scratch script, not in the repository: `scratchpad/e2e/launch.py`. It does this:

1. Writes four synthetic Markdown sources. One is Arabic prose with the English identifiers `ingest_path_async`, `Engine` and `LanceVectorStore` (design D9).
2. Builds a real `Engine` with `EffectiveSettings(metadata.extraction_mode="disabled", embedding tokenizer fields empty, pdf_reader="pypdf", vector_store="lancedb", lancedb_uri=<scratch>)`, a `LanceVectorStore` in the scratch directory, a deterministic hashed bag-of-words embedder (a `MockEmbedding` subclass, 64 dimensions, unit norm), `answer_llm_factory` returning a fake LLM with fixed text, and no reranker.
3. Ingests the sources with `Engine.ingest` (6 chunks), then closes that Engine.
4. Builds the real application: `create_app(WebConfig(workspace, host="127.0.0.1", port, roots=(sources,), experiment_roots=(experiments,), experiments_factory=...), policy=AccessPolicy.for_launch(...), engine_factory=..., run_service_factory=runs_wiring.run_service_factory)` with the built assets from `npm run build`. The experiment factory is a real `ExperimentEngines(experiment_registry(roots), Settings(_env_file=None, ...), build_engine=...)` whose builder uses the same fakes.
5. Serves it with the CLI's own `_bind_socket("127.0.0.1", 0)` and `_serve` (Uvicorn, one process). The launch URL is written to a private file.

```bash
cd web && npm run build
cd .. && env -i HOME=$HOME PATH=/usr/bin:/bin PYTHONPATH=src PDF_READER=pypdf \
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python scratchpad/e2e/launch.py scratchpad/e2e/run
# INGEST {'status': 'ok', 'chunks_created': 6}
# LAUNCH http://127.0.0.1:63640/#bootstrap=<secret>
```

## Browser client (Chrome DevTools, 1280 px)

1. Open the launch URL. The page removes the fragment and starts a session.
2. Canvas: title "Search hybrid rewired", template **Search**, **Start from template**. The template has `prepare → dense → rerank (bypassed: no reranker) → select → context`.
3. Rewire:
   - remove node `rerank` (its two connections go with it);
   - add `retrieve.sparse` (id `sparse`) and `combine.rrf` (id `rrf`) from the catalogue;
   - connect with the Connect ports form: `prepare.query → sparse.query`, `dense.evidence → rrf.ranked`, `sparse.evidence → rrf.ranked`, `rrf.evidence → select.evidence`.
4. **Save revision**: revision 1, `revision_id 00e5d572853d4669959657da9e87a254`, pipeline `2211b7f6b0004d3886e14fb96db13a89`.
5. Input query "How does hybrid retrieval fuse dense and sparse ranks?". **Validate**: "The graph is valid and admissible. Order: prepare, dense, sparse, rrf, select, context." The rrf inspector shows effective `retrieval.hybrid_rrf_k = 60` from profile `documents` (collection).
6. **Run**: run `388baa3d9b4c498db7d5f7e469771fff`, `succeeded`, wall time 0.04 s. Each node shows "Completed".

## Notebook client

Script: `scratchpad/e2e/notebook_client.py`. It loads `plugins/marimo/starter_notebook.py` with `importlib` (marimo is not installed: `find_spec("marimo") is None`) and uses only its helpers: `ApiClient`, `read_token`, `ExperimentSession.follow/result/run`, `experiment_record`, `checkpoint`, `experiment_context_from_environment`.

Credentials were issued through the API from the browser session (`POST /v1/credentials`):

- unbound bearer, scopes `graph`, `read`, `run`, label `notebook-live`;
- experiment context `exp_bc4f63b176040804` registered with `POST /v1/experiments` below the approved experiment root;
- bound bearer, scopes `graph`, `read`, `run`, `experiment_context = exp_bc4f63b176040804`.

Both tokens went into mode-600 files. The script reads them through `OMRG_TOKEN_FILE` and `OMRG_EXP_TOKEN_FILE`. No token was printed or logged.

```bash
env -i HOME=$HOME PATH=/usr/bin:/bin OMRG_WT=<WT> \
  OMRG_TOKEN_FILE=<scratch>/live.token OMRG_EXP_TOKEN_FILE=<scratch>/exp.token \
  OMRG_EXPERIMENT_CONTEXT=exp_bc4f63b176040804 \
  .venv/bin/python -I scratchpad/e2e/notebook_client.py \
  http://127.0.0.1:63640 388baa3d9b4c498db7d5f7e469771fff scratchpad/e2e/compare.json
```

Steps:

1. Read the browser run and its saved revision with the unbound bearer.
2. Submit the SAME `revision_id` with the SAME `inputs` to `POST /v1/runs` (live library, no experiment context): run `d40ffb98b1c745a2a71f2cf0c744cc47`.
3. Follow both runs with `ExperimentSession.follow` (event polling with `after_sequence`), fetch both results, build both records with `experiment_record`, and write a checkpoint with `checkpoint` (temporary file, then rename).
4. Compare.

## Comparison

| Check | Browser run `388baa3d…` | Notebook run `d40ffb98…` | Equal |
|---|---|---|---|
| Pipeline / revision | `2211b7f6…` / `00e5d572…` | same | yes |
| Graph hash and graph identity | `25c0279c904e5e25da918474e73726e5d8c116f7d2068b1dddb6f9eea53d4ac0` | same | yes |
| Effective settings snapshot | profile `documents` (origin `collection`); retrieval `hybrid_rrf_k 60`, `hybrid_sparse_backend bm25`, `rerank_enabled false`, `similarity_threshold 0.0`, `top_k 10` | identical dict | yes |
| Inputs | `{"query": "How does hybrid retrieval fuse dense and sparse ranks?"}` | same | yes |
| Status | `succeeded` | `succeeded` | yes |
| Ranked rows (`results`) | 4 rows: `chk_7e9c1bf5…` 0.032787, `chk_42e010a4…` 0.016129, `chk_10bccd87…` 0.015625, `chk_7e8cd03b…` 0.015152 | same order, same scores | yes |
| Score kinds | all `rrf_v1` | all `rrf_v1` | yes |
| Outputs without timing keys | full `results` bundle | same | yes |
| Events (kind, node) | 23 events | 23 events | yes |

Event sequence of both runs (timestamps and run ids ignored):

```text
run.status, run.status, run_started,
node_queued prepare, node_started prepare, node_completed prepare,
node_queued dense, node_queued sparse,
node_started dense, node_completed dense, node_started sparse, node_completed sparse,
node_queued rrf, node_started rrf, node_completed rrf,
node_queued select, node_started select, node_completed select,
node_queued context, node_started context, node_completed context,
run_completed, run.status
```

The settings snapshot shows `hybrid_enabled false` for the profile. The graph still fuses dense and sparse ranks, because the graph names the sparse and fusion nodes explicitly. The snapshot records the profile value; the graph shape decides the stages.

## Experiment-bound credential and the live library

| Request with the bound bearer | Result |
|---|---|
| `POST /v1/runs` with the live revision and no `experiment_context` | **403** `code: live_library_target`, "An experiment credential cannot run graphs against the live library." |
| `GET /v1/runs/388baa3d…` (a live run) | **404** "Unknown run." (live runs are not visible to it) |
| `GET /v1/collections` | **403** "An experiment credential cannot read or change the live library; it can use only pipeline, run and template routes." |
| `ExperimentSession.run(document, inputs, run_requested=True)` | run `9232a26a84f14b2fbf556913e3131b60` `succeeded` in context `exp_bc4f63b176040804`; same graph hash `25c0279c…`; backend store `…/experiments/exp-e2e/output/lancedb`, index identity `67ea325ad7b203fb` (not the live store) |
| `ExperimentSession.run(..., run_requested=False)` | returns `None`; `runs_submitted` stays 1 |

The bound session saved its own pipeline and revision (`dada594b…` / `87f31bd2…`), because a bound credential cannot read live pipelines. The graph identity is the same.

## Notes and limits

1. The experiment identity shows `embedding_provider: llamacpp` with an empty model. It comes from the base `Settings` defaults that composition passes to the builder. The launcher's builder injects the hashed fake embedder, so no provider was called. This is a launcher artefact, not a product defect.
2. The comparison used the run event store (polling), not the live SSE stream. The SSE stream was checked separately (see `browser.md`, action walk).
3. The graph was run against one LanceDB live library. A Chroma store was not tried.
4. The notebook client ran as plain Python. A real marimo editor was not started (no installs). Task 8.4 covers that.
5. Server shutdown: SIGINT; the log ends "Application shutdown complete." An open SSE stream ended with `run.end`. No process stayed on the port. Server log: 0 tracebacks, 0 `ERROR` lines, 0 occurrences of either bearer secret. The one bootstrap secret appears only in the launcher's own `LAUNCH` line, which this script printed on purpose; the server's access log has no secret.
