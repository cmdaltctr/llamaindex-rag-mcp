# Pipeline graphs

A pipeline graph connects registered OMRS operations. The saved connections decide which operations run and in which order. This guide describes the graph document, the operation catalogue, the canonical templates, profiles, connections, validation errors, and how to run and cancel a graph from Python.

The graph contracts live in `omrs.core.pipelines`. The domain packages register the operations. The Engine validates and runs graphs with `Engine.validate_pipeline` and `Engine.run_pipeline`. These methods need no web server and no notebook package.

## Graph document and layout

A pipeline definition has two parts:

| Part | Contents | Changes execution identity |
|---|---|---|
| `graph` | Schema version, nodes, edges, graph inputs, graph outputs, profile, default collection, overrides. | Yes |
| `layout` | Title, node positions, viewport, selection. | No |

Moving a node or changing the viewport does not change the execution identity. A new connection, parameter or operation version does.

The current schema version is `1`. OMRS rejects other versions with the `unsupported_schema_version` code. Re-save an old graph with the current OMRS, or upgrade OMRS to read a newer graph.

Each node has these fields:

| Field | Meaning |
|---|---|
| `id` | Unique identifier. Starts with a letter. Letters, digits, `_` and `-` only. |
| `operation` | Registered operation identifier, for example `retrieve.dense`. |
| `version` | Optional pinned operation version. When omitted, admission uses the latest version and records it. |
| `params` | JSON parameters. The operation's parameter schema validates them and rejects unknown keys. |
| `enabled` | Set to `false` to bypass the node. Only operations that declare a bypass accept this. |

## Operation catalogue

The Engine catalogue holds these operations. Each operation is version `1`. The domain package that owns the algorithm registers the operation, so a graph and the standard operation call the same code.

| Operation | Input ports | Output port | Host resources | Bypass |
|---|---|---|---|---|
| `source.discover` | `sources` (a path) | `sources` | None | No |
| `source.identify` | `sources` | `sources` | `store`, `embedder` | No |
| `read.document` | `sources` | `documents` | None | No |
| `prepare.normalise` | `documents` | `documents` | None | Yes |
| `prepare.enrich` | `documents` | `documents` | `store` | Yes |
| `prepare.chunk` | `documents` | `chunks` | None | No |
| `embed.chunks` | `chunks` | `chunks` (embedded) | `embedder` | No |
| `commit.source` | `chunks` (embedded) | `summary` | `store` | No |
| `retrieve.prepare_query` | `query` | `query` (prepared) | `store` | No |
| `retrieve.dense` | `query` | `evidence` (`dense_similarity_v1`) | `embedder`, `store` | No |
| `retrieve.sparse` | `query` | `evidence` (`sparse_rank_v1`) | `store` | No |
| `combine.rrf` | `ranked` (many) | `evidence` (`rrf_v1`) | None | No |
| `select.rerank` | `evidence` | `evidence` | `reranker` | Yes |
| `select.threshold` | `evidence` | `evidence` | None | No |
| `context.assemble` | `evidence` | `context` | `store` | No |
| `answer.prepare_evidence` | `context` | `context` | None | No |
| `answer.synthesise` | `query`, `context` | `answer` | Answer model, built on first use | No |
| `answer.cite` | `answer` | `answer` | None | No |
| `verify.claims` | `answer` | `answer` | Judge model, built on first use | Yes |

`retrieve.prepare_query` resolves `top_k`, the similarity threshold, the rerank decision and the candidate pool once. Connect it before the dense and sparse nodes, as the templates do. `select.threshold` applies the score-kind-aware threshold and the `top_k` cut. After a successful rerank it divides the threshold by 30, as `search()` does.

### PDF reader on the Read document step

The Read document step has a `pdf_reader` setting. Use it to read the PDF files of one pipeline with a different reader from the host default.

- `null` (Inherit) uses the host reader. The host reader comes from `PDF_READER`, resolved once at start-up.
- A value must be a registered concrete reader: `pypdf`, `pypdfium2`, `liteparse` or `pdf_inspector`.
- `auto` is not a choice. It is a host policy. Validation rejects it with `invalid_parameter`.
- A graph-wide `overrides.pdf_reader` stays refused (`host_owned_setting`). Set the reader on the Read document step instead.
- The step setting changes only that step. The environment, the standard ingest path and other pipelines keep the host reader.

The host probes each reader once for each Engine. A reader whose package is not installed gives `option_unavailable` at validation, and no node runs. The catalogue reports this for each operation:

- `unavailable_options` maps a setting to its unavailable choices and the reason for each. For `read.document` it lists the uninstalled readers and names the missing package.
- `inherited_values` maps a setting to the value that `null` uses. For `read.document` it holds the host reader.

Both fields are empty for an operation that has no such setting. The operation stays available when a choice is not.

What a step reader changes:

- OCR routing and the rescue for PDFs that give no text apply only to `pdf_inspector`, under the host OCR settings. A step that selects another reader reads without them. A scanned PDF that `pypdf` reads can give no text and fail with "No chunks produced".
- A step that selects `pdf_inspector` on a host with another default turns OCR routing on for that step. It adds no OCR route and starts no worker that the host has not set up.
- When the host uses the Azure document backend, Azure reads the PDF files. The step reader applies only when a read falls back to the local backend.
- The stored source identity names the step reader. When you change the reader, or any other Read document setting, each affected source is processed again on its next explicit ingest. A rerun with the same settings reuses the source.

## Canonical templates

`omrs.pipeline_templates` publishes three canonical graphs. Each graph reproduces one standard Engine operation:

| Template | Same result as | Graph input | Graph output |
|---|---|---|---|
| `ingestion` | `Engine.ingest` | `path` | `summary` (commit summary per source) |
| `search` | `Engine.search` | `query` | `results` (assembled context) |
| `answer` | `Engine.answer` | `query` | `answer` (answer result) |

The node chains are:

- `ingestion`: `source.discover`, `source.identify`, `read.document`, `prepare.normalise`, `prepare.enrich`, `prepare.chunk`, `embed.chunks`, `commit.source`.
- `search`: `retrieve.prepare_query`, `retrieve.dense`, then `retrieve.sparse` and `combine.rrf` when hybrid, then `select.rerank`, `select.threshold`, `context.assemble`.
- `answer`: the `search` chain, then `answer.prepare_evidence`, `answer.synthesise`, `answer.cite`, `verify.claims`.

Graph outputs carry summaries and results only. No template returns chunks or vectors as a graph output.

Use `omrs.compose_pipelines.pipeline_templates(engine, collection)` to get the templates for one Engine. It adds the sparse branch when the collection setting `retrieval.hybrid_enabled` is true. It bypasses the rerank node when the Engine has no reranker model. You can also call `search_template(collection, hybrid=..., rerank=...)` and the other template functions directly.

The ingestion template is the graph that `canonical_ingestion_definition()` returns. The ingestion index-shaping fingerprint reads the same graph, so the standard path and the template share one shaping identity.

A template is a starting point. You can copy it, then remove, add or rewire nodes. Validation checks the edited graph. The runner follows the saved connections. It does not replace them with the template order. Tests in `tests/unit/test_pipeline_templates.py` and `tests/unit/test_pipeline_templates_parity.py` compare each template with its standard operation on recorded fixtures.

## Graph inputs and outputs

A graph input is a value that you supply when a run starts, for example a query or a source path. Each input has a `name`, a `kind` and one or more `targets` (input ports). Set `required` to `false` for an optional input.

A graph output names a node output port. The run result returns it under the output `name`.

Admission rejects a run that does not supply every required input (`missing_graph_input`). It also rejects inputs that the graph does not declare (`unknown_graph_input`).

## Connections

An edge connects an output port to an input port. Each port has a type:

| Type property | Meaning |
|---|---|
| `kind` | What the value is: `sources`, `documents`, `chunks`, `embedded_chunks`, `commit_summary`, `query`, `query_vector`, `ranked_evidence`, `context` or `answer`. |
| `provenance` | Guarantees the value carries: `source`, `collection`, `chunk_lineage`. |
| `score_kinds` | Score kinds of ranked evidence, for example `dense_similarity_v1` or `rrf_v1`. |
| `embedding_identity` | The value is bound to the host embedding model. |
| `reader_declarations` | Reader facts that must survive, for example `text_format`. |

A connection is valid only when the producer gives every guarantee the consumer needs. For example, `select.threshold` needs scored evidence. A sparse ranking carries ranks only (`sparse_rank_v1`), so it cannot connect directly to `select.threshold`. Fuse it with a dense ranking first.

Each input port has a cardinality:

- `one`: connect exactly one value.
- `optional`: connect zero or one value.
- `many`: connect one or more values. The operation receives them in edge order, not in completion order.

Two connections into a `one` port are ambiguous. Add a combine node, or remove a connection.

When you disable a node, its declared bypass forwards the input value unchanged. The forwarded value keeps its upstream type. Validation checks that type against the downstream ports.

## Profiles and overrides

The `profile` field selects the operational defaults:

- Omit `profile` to inherit each collection's resolved profile.
- Set `documents` or `codebase` to use that bundle for the run. The collection's stored profile tag does not change.
- Do not set `hybrid`. It selects a server default and is not an operational profile.

Collection-bound nodes use their `collection` parameter. When a node does not name a collection, it uses the graph `collection`. When the graph does not name one, it uses the host default collection.

Precedence, highest first:

1. A node parameter that maps to a setting lever, when the value is not `null`.
2. A graph-wide entry in `overrides`.
3. The resolved profile and defaults. Environment values keep their priority over profile bundle values.

Admission records each effective value and its source (`node`, `graph`, `environment` or `profile`). An admitted run keeps these values. Later edits to the draft graph or the collection profile apply only to later runs.

Graph overrides accept these levers only:

| Lever | Index-shaping |
|---|---|
| `retrieval.top_k`, `retrieval.rerank_enabled`, `retrieval.hybrid_enabled`, `retrieval.hybrid_rrf_k`, `retrieval.similarity_threshold`, `retrieval.rerank_fetch_multiplier` | No |
| `answer.verify_claims` | No |
| `chunking.chunk_size`, `chunking.chunk_overlap`, `chunking.markdown_chunk_size`, `chunking.code_chunk_lines`, `chunking.strategy_fallback` | Yes |
| `metadata.taxonomy_mode` | Yes |

The host owns provider and model identity, secrets, storage locations and reader backends. A graph cannot change them (`host_owned_setting`). Change them in the environment and restart OMRS. The one exception is the PDF reader: the Read document step can choose an installed reader for itself (see "PDF reader on the Read document step"), but the host default stays host-owned.

## Profiles own pipelines

A user profile owns three pipelines. Each pipeline has one purpose, called a **slot**. A collection that follows a user profile uses these pipelines for every request: Chat, Knowledge Base search, MCP tools, the CLI and the watcher. A collection that follows a built-in profile (`documents` or `codebase`) does not run a saved pipeline. It keeps the direct Engine path, with the same speed and results as before. See [Configuration](configuration.md#user-profiles) for the tag and for the processes that read user profiles.

| Slot | Graph input | Graph output | Write steps |
|---|---|---|---|
| Ingest | `path` (kind `sources`) | `summary` (kind `commit_summary`) | Exactly one enabled write step (`commit.source`) |
| Search | `query` (kind `query`) | `results` (kind `context`) | None |
| Answer | `query` (kind `query`) | `answer` (kind `answer`) | None |

Each slot graph names the base profile of the user profile as its `profile`. The code that checks this is in `src/omrs/compose_profiles.py`.

### Readiness

A profile is **ready** when each pipeline has a saved revision, passes the draft check (`validatePipeline` without run inputs) and meets the contract in the table. A profile that is not ready cannot be bound to a collection. Each failure gives one plain line that names the pipeline, and the step when one step causes it. The check in `src/omrs/core/profiles/readiness.py` writes these lines.

When you bind a profile to a collection, the check also runs against that collection. It then includes the embedding model of the collection.

### What a request does

A request runs the current revision of the slot graph. It uses the same `Engine.run_pipeline` call as Studio, but it makes no run record and does not use the run queue. The code is in `src/omrs/engine_profiles.py`.

- The graph names the collection of the request.
- A value that the caller sets replaces the matching step setting. `top_k`, `similarity_threshold`, `rerank`, `fetch_k` and `metadata_filter` replace settings of `retrieve.prepare_query`. `expand_window` replaces the setting of `context.assemble`. `include_diagnostics` replaces the setting of `answer.synthesise`. `chunk_size` and `chunk_overlap` replace the settings of the steps that map to `chunking.chunk_size` and `chunking.chunk_overlap`.
- `hybrid` and `technical_fraction` have no step setting. The wiring of the graph decides. With `include_diagnostics`, the result lists these values under `unused_request_values`.
- `expand_window=0` means "not set". The step keeps its own value.

The result has the shape of the built-in operation:

| Operation | Graph output | Result |
|---|---|---|
| `search` | `results` | The rows of `Engine.search`. With diagnostics, the full rows. |
| `answer` | `answer` | The result dict of `Engine.answer`. |
| `ingest` | One `summary` for each source | The summary of `Engine.ingest`. `peak_rss_bytes` is `null`, and `progress_callback` is called once for each source after the run. |

An answer from a user profile always uses the server answer model. A client completion (MCP sampling) and pre-fetched rows cannot pass into a pipeline run. `Engine.answer` refuses both for a user profile with a `ValueError`.

A change to an Ingest pipeline does not start an ingestion. Each source is processed again on its next ingestion, because the ingestion fingerprint holds the operations, versions, parameters and connections.

### Concurrency

Graph runs that only read run at the same time on one Engine. A graph with an enabled write step waits for other graphs that write. The reranker records its last failure on the shared instance, so `run_reranker` in `src/omrs/core/retrieval/operations.py` runs the rerank call and reads the failure reason as one locked step for each reranker.

### Latency

A request on a user profile admits and runs the graph, so it costs more than the direct path. The test `tests/unit/test_profile_dispatch_latency.py` measures the difference. It runs the 15 recorded retrieval cases through a built-in collection and through a duplicate user profile, 20 times each, and checks that the rows are equal. Run it with `uv run pytest -m slow tests/unit/test_profile_dispatch_latency.py -s`.

The test uses an in-memory store with three chunks and scripted dense scores. The numbers therefore show the cost of the graph only. Real embedding, store and reranker time is the same on both paths. Measured on one development machine (macOS, Python 3.14):

| Measure | Direct path | Graph path | Difference |
|---|---|---|---|
| Median of the per-query medians (15 queries) | 0.02 ms | 1.38 ms | 1.36 ms |
| Median of the per-query 95th percentiles (15 queries) | 0.02 ms | 1.43 ms | 1.41 ms |

The difference of the per-query median is 1.24 to 1.41 ms for every query. The overhead is well below the design limit of 50 ms, so definitions are not cached. The test asserts no time limit.

## Examples

### Hybrid search and answer

<!-- pipeline-example: valid -->
```json
{
  "graph": {
    "schema_version": 1,
    "nodes": [
      {"id": "prepare", "operation": "retrieve.prepare_query", "params": {"top_k": 8}},
      {"id": "dense", "operation": "retrieve.dense"},
      {"id": "sparse", "operation": "retrieve.sparse"},
      {"id": "fuse", "operation": "combine.rrf"},
      {"id": "rerank", "operation": "select.rerank", "params": {"enabled": false}},
      {"id": "select", "operation": "select.threshold"},
      {"id": "context", "operation": "context.assemble"},
      {"id": "evidence", "operation": "answer.prepare_evidence"},
      {"id": "answer", "operation": "answer.synthesise"},
      {"id": "cite", "operation": "answer.cite"}
    ],
    "edges": [
      {"source": {"node": "prepare", "port": "query"}, "target": {"node": "dense", "port": "query"}},
      {"source": {"node": "prepare", "port": "query"}, "target": {"node": "sparse", "port": "query"}},
      {"source": {"node": "dense", "port": "evidence"}, "target": {"node": "fuse", "port": "ranked"}},
      {"source": {"node": "sparse", "port": "evidence"}, "target": {"node": "fuse", "port": "ranked"}},
      {"source": {"node": "fuse", "port": "evidence"}, "target": {"node": "rerank", "port": "evidence"}},
      {"source": {"node": "rerank", "port": "evidence"}, "target": {"node": "select", "port": "evidence"}},
      {"source": {"node": "select", "port": "evidence"}, "target": {"node": "context", "port": "evidence"}},
      {"source": {"node": "context", "port": "context"}, "target": {"node": "evidence", "port": "context"}},
      {"source": {"node": "evidence", "port": "context"}, "target": {"node": "answer", "port": "context"}},
      {"source": {"node": "answer", "port": "answer"}, "target": {"node": "cite", "port": "answer"}}
    ],
    "inputs": [
      {"name": "query", "kind": "query", "targets": [
        {"node": "prepare", "port": "query"},
        {"node": "answer", "port": "query"}
      ]}
    ],
    "outputs": [{"name": "answer", "source": {"node": "cite", "port": "answer"}}],
    "overrides": {"retrieval.top_k": 12, "retrieval.hybrid_rrf_k": 40}
  },
  "layout": {"title": "Hybrid answer", "positions": {"dense": {"x": 0, "y": 0}}}
}
```

In this graph, the prepare node sets `top_k = 8`. This node value wins over the graph override `retrieval.top_k = 12`. The fusion node uses the graph override `rrf_k = 40`. The rerank node skips inference for this run, whatever the profile says.

### Ingestion into one collection with the codebase profile

<!-- pipeline-example: valid -->
```json
{
  "schema_version": 1,
  "profile": "codebase",
  "collection": "code",
  "nodes": [
    {"id": "discover", "operation": "source.discover"},
    {"id": "identify", "operation": "source.identify"},
    {"id": "read", "operation": "read.document"},
    {"id": "normalise", "operation": "prepare.normalise"},
    {"id": "enrich", "operation": "prepare.enrich", "enabled": false},
    {"id": "chunk", "operation": "prepare.chunk", "params": {"chunk_size": 256}},
    {"id": "embed", "operation": "embed.chunks"},
    {"id": "commit", "operation": "commit.source"}
  ],
  "edges": [
    {"source": {"node": "discover", "port": "sources"}, "target": {"node": "identify", "port": "sources"}},
    {"source": {"node": "identify", "port": "sources"}, "target": {"node": "read", "port": "sources"}},
    {"source": {"node": "read", "port": "documents"}, "target": {"node": "normalise", "port": "documents"}},
    {"source": {"node": "normalise", "port": "documents"}, "target": {"node": "enrich", "port": "documents"}},
    {"source": {"node": "enrich", "port": "documents"}, "target": {"node": "chunk", "port": "documents"}},
    {"source": {"node": "chunk", "port": "chunks"}, "target": {"node": "embed", "port": "chunks"}},
    {"source": {"node": "embed", "port": "chunks"}, "target": {"node": "commit", "port": "chunks"}}
  ],
  "inputs": [{"name": "path", "kind": "sources", "targets": [{"node": "discover", "port": "sources"}]}],
  "outputs": [{"name": "summary", "source": {"node": "commit", "port": "summary"}}]
}
```

A bare graph document (without `graph` and `layout`) is also accepted. It gets an empty layout. In this graph the enrichment node is bypassed, so the documents go to the chunker unchanged. `chunk_size` is index-shaping. A changed value makes the next explicit ingest rebuild the affected sources.

### A sparse ranking cannot feed threshold selection

<!-- pipeline-example: invalid incompatible_ports -->
```json
{
  "schema_version": 1,
  "nodes": [
    {"id": "prepare", "operation": "retrieve.prepare_query"},
    {"id": "sparse", "operation": "retrieve.sparse"},
    {"id": "select", "operation": "select.threshold"}
  ],
  "edges": [
    {"source": {"node": "prepare", "port": "query"}, "target": {"node": "sparse", "port": "query"}},
    {"source": {"node": "sparse", "port": "evidence"}, "target": {"node": "select", "port": "evidence"}}
  ],
  "inputs": [{"name": "query", "kind": "query", "targets": [{"node": "prepare", "port": "query"}]}]
}
```

### A feedback loop

<!-- pipeline-example: invalid cycle -->
```json
{
  "schema_version": 1,
  "nodes": [
    {"id": "prepare", "operation": "retrieve.prepare_query"},
    {"id": "dense", "operation": "retrieve.dense"},
    {"id": "fuse", "operation": "combine.rrf"},
    {"id": "rerank", "operation": "select.rerank"}
  ],
  "edges": [
    {"source": {"node": "prepare", "port": "query"}, "target": {"node": "dense", "port": "query"}},
    {"source": {"node": "dense", "port": "evidence"}, "target": {"node": "fuse", "port": "ranked"}},
    {"source": {"node": "fuse", "port": "evidence"}, "target": {"node": "rerank", "port": "evidence"}},
    {"source": {"node": "rerank", "port": "evidence"}, "target": {"node": "fuse", "port": "ranked"}}
  ],
  "inputs": [{"name": "query", "kind": "query", "targets": [{"node": "prepare", "port": "query"}]}]
}
```

### A graph tries to change the embedding model

A graph cannot set the embedding model or provider. The `Embed chunks` step
and the dense retrieval step use the model that the collection's profile
names (the server default when the profile names none). To change the model,
set it on the profile's Embed step. See "Embedding model per profile" in the
configuration guide.

<!-- pipeline-example: invalid host_owned_setting -->
```json
{
  "schema_version": 1,
  "nodes": [{"id": "dense", "operation": "retrieve.dense"}],
  "inputs": [{"name": "query", "kind": "query", "targets": [{"node": "dense", "port": "query"}]}],
  "overrides": {"embed_model": "another-model"}
}
```

## Validation errors

Validation runs before any node, model call or store change. It reports every problem in one `PipelineValidationError`. Each issue has a `code`, a plain-English `message`, and the `node_id`, `port`, `edge` or `lever` to change.

| Code | Cause | Action |
|---|---|---|
| `unsupported_schema_version` | The graph uses another schema version. | Re-save the graph with this OMRS. |
| `invalid_document` | The JSON does not match the graph document. | Correct the named field. |
| `duplicate_node` | Two nodes use the same `id`. | Rename one node. |
| `unknown_operation`, `unknown_operation_version` | The operation or pinned version is not registered. | Select an operation from the catalogue. |
| `unknown_node`, `unknown_port` | An edge or output names a missing node or port. | Connect existing ports. |
| `invalid_parameter` | A parameter fails the operation schema. | Correct the value, or remove the unknown key. |
| `executable_text` | A value looks like code, a shell command or an import. | Use data values only. |
| `missing_input` | A required input port has no connection. | Connect the port. |
| `ambiguous_input` | A single-value port has more than one connection. | Remove a connection, or add a combine node. |
| `incompatible_ports` | The producer does not give a guarantee that the consumer needs. | Connect a compatible port. |
| `cycle` | The connections form a loop. | Remove one connection in the loop. |
| `invalid_bypass` | A node without a bypass is disabled, or the bypass forwards an incompatible value. | Enable the node, or change the downstream connection. |
| `capability_unavailable` | The host cannot supply a resource, for example the reranker model. | Follow the reason in the message, or disable the node when it has a bypass. |
| `option_unavailable` | A node selects a choice the host cannot run, for example a PDF reader whose package is not installed. | Install the package and restart OMRS, or choose another value, or set the step to Inherit. |
| `embedding_identity_mismatch` | The collection uses another embedding provider or model. Equal dimensions do not make two models compatible. | Select a collection built with the host model. |
| `conflicting_commit`, `multiple_commit_destinations` | More than one commit node writes sources. | Keep one commit node per graph. |
| `unsupported_profile` | The profile is not `documents` or `codebase`. | Use an operational profile, or omit it. |
| `host_owned_setting`, `invalid_override` | An override changes a host setting or is not an allowed lever. | Remove the override, or use an allowed lever. |
| `missing_graph_input`, `unknown_graph_input` | The run inputs do not match the declared graph inputs. | Supply every required input by name. |
| `profile_resolution_failed` | A collection carries an invalid profile tag. | Tag the collection `documents` or `codebase`. |

## Run a graph from Python

The examples below use an `engine` that you built with `Engine.from_environment()` or the `Engine` constructor (see [Library usage](library-usage.md)). They import no web or notebook package. A test runs them in this order on an Engine over in-memory fakes.

### Validate

`validate_pipeline` without `inputs` runs a draft check and returns a `PreflightReport`. With `inputs` it admits the graph and returns a frozen `AdmissionSnapshot`. Both forms raise `PipelineValidationError` and change nothing.

<!-- pipeline-python: validate -->
```python
from omrs.compose_pipelines import pipeline_templates
from omrs.core.pipelines import PipelineValidationError

templates = {template.name: template for template in pipeline_templates(engine)}
definition = templates["search"].definition

report = engine.validate_pipeline(definition)
print(report.ok)  # True

snapshot = engine.validate_pipeline(definition, inputs={"query": "What is RRF?"})
print(snapshot.order)  # ('prepare', 'dense', 'rerank', 'select', 'context')

try:
    engine.validate_pipeline(definition, inputs={"question": "What is RRF?"})
except PipelineValidationError as error:
    for issue in error.issues:
        print(issue.code, issue.message)  # missing_graph_input, then unknown_graph_input
```

### Run and read events

`run_pipeline` is a coroutine. In an async application, `await` it. In a script, use `asyncio.run`. It accepts a definition with `inputs`, or an admitted snapshot without `inputs`. The optional `on_event` coroutine receives each `PipelineEvent`. An event holds small summaries only, never vectors or full documents.

<!-- pipeline-python: run -->
```python
import asyncio

kinds = []


async def on_event(event):
    kinds.append(event.kind)


result = asyncio.run(engine.run_pipeline(snapshot, on_event=on_event))
print(result.status)  # succeeded
print(kinds[0], kinds[-1])  # run_started run_completed
for row in result.outputs["results"].public_rows():
    print(row["score"], row["source"])
for node in result.nodes:
    print(node.node_id, node.status, node.fallback)
```

`result.outputs["results"].public_rows()` returns the rows in the same shape as `Engine.search`. A node that used a domain fallback, for example a failed rerank, reports the reason in `node.fallback`. A failed run returns a result with `status == "failed"`, `failed_node` and `completed_effects`. Only a validation error raises.

### Cancel

Give a `RunCancellation` token to `run_pipeline`, then call `cancel()` on the event-loop thread of the run. From another thread, use `loop.call_soon_threadsafe(token.cancel)`. Cancellation is cooperative:

- The runner starts no new node after the request.
- A node that has started finishes. A blocking model call finishes.
- A source commit that has started finishes its write, verification and clean-up. A commit that has not started does not start.
- The result lists every effect that completed before the stop, in `completed_effects`.

<!-- pipeline-python: cancel -->
```python
from omrs.core.pipelines import RunCancellation

token = RunCancellation()


async def stop_after_first_node(event):
    if event.kind == "node_completed":
        token.cancel("user request")


result = asyncio.run(
    engine.run_pipeline(
        definition,
        inputs={"query": "What is RRF?"},
        on_event=stop_after_first_node,
        cancellation=token,
    )
)
print(result.status)  # cancelled
print([node.node_id for node in result.nodes if node.status == "cancelled"])
```

One token belongs to one run. A cancelled token does not cancel other runs on the same Engine. Runs on one Engine are serialised. `Engine.close()` raises `RuntimeError` while a run is active, and the Engine stays usable.

### Edit a template

<!-- pipeline-python: edit -->
```python
data = definition.model_dump(mode="json")
graph = data["graph"]
graph["nodes"] = [node for node in graph["nodes"] if node["id"] != "rerank"]
graph["edges"] = [
    edge
    for edge in graph["edges"]
    if "rerank" not in (edge["source"]["node"], edge["target"]["node"])
]
graph["edges"].append(
    {
        "source": {"node": "dense", "port": "evidence"},
        "target": {"node": "select", "port": "evidence"},
    }
)

result = asyncio.run(engine.run_pipeline(data, inputs={"query": "What is RRF?"}))
print(result.status)  # succeeded
```

### Lower-level functions

`omrs.core.pipelines` also exports `parse_definition`, `preflight` and `admit_pipeline`. Use them when you build your own host. The Engine methods call them with the Engine catalogue, the host context and the Engine profile resolver. `omrs.compose_pipelines.build_operation_catalogue()` returns the same catalogue the Engine uses.
