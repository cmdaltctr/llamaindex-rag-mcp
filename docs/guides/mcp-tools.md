# MCP Tools Reference

Nine tools are exposed over the MCP protocol. All parameters are optional except where marked _(required)_.

## Connect a client

### Stdio

Each client starts its own `omrg` process:

```json
{ "mcpServers": { "omrg": { "command": "uv", "args": ["run", "omrg"] } } }
```

### HTTP

`omrg web` can serve the same nine tools at `/mcp`, so a client shares the running server and its Engine. The endpoint is off until you turn it on.

1. Start the server: `omrg web --root ~/papers`.
2. In the browser, open Settings > MCP. Turn on MCP over HTTP. Create a token. The token is shown once.
3. Add the server to the client. The URL is the one that Settings shows, for example `http://127.0.0.1:8765/mcp`:

```json
{
  "mcpServers": {
    "omrg": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": { "Authorization": "Bearer omrg_mcp_<token>" }
    }
  }
}
```

With Claude Code: `claude mcp add --transport http omrg http://127.0.0.1:8765/mcp --header "Authorization: Bearer omrg_mcp_<token>"`.

Rules for HTTP:

- A switched-off endpoint answers 404. A foreign `Origin` gets 403. An origin approved with `omrg web --allow-origin` is not foreign. A missing, wrong or revoked token gets 401. The checks run in that order.
- Rotating the token ends access for the old token at the next request. Update each client.
- `ingest_documents` and `get_codebase_map` accept only paths inside a directory that you approved with `--root`. A path outside, or a symlink that leads outside, returns `{"status": "error", ...}`. Stdio keeps its earlier behaviour.
- The token works on `/mcp` only. It never opens a `/v1` route.
- The server must run. Stop it and the client loses the connection. Use stdio if the client should start OMRG itself.
- Without the saved port or `--port`, the server listens on 8765. Save a port in Settings > MCP, or start with `--port <n>`.

---

## `search_documents`

Semantic similarity search over indexed documents.

| Parameter              | Type   | Default       | Description                                                                                                                                                                                              |
| ---------------------- | ------ | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `query`                | string | _(required)_  | Natural language search query                                                                                                                                                                            |
| `top_k`                | int    | `10`          | Maximum number of chunks to return                                                                                                                                                                       |
| `similarity_threshold` | float  | `0.0`         | Minimum canonical dense similarity (0.0 = no filtering). Hybrid/no-rerank applies it to dense evidence before RRF; successful reranking uses the calibrated 30× transform.                               |
| `rerank`               | bool   | `null`        | Tri-state: `true` forces reranking, `false` disables, `null` (default) applies policy resolver based on query type and `RETRIEVAL__RERANK_ENABLED` config                                                |
| `hybrid`               | bool   | `false`       | Fuse dense vector search with sparse BM25 results via RRF before optional reranking. Defaults to `RETRIEVAL__HYBRID_ENABLED` env var. Use for rare terms, exact identifiers, citations, and error codes. |
| `expand_window`        | int    | `0`           | Neighbours added per side of each retrieved chunk during context assembly. Expanded neighbours merge into the retrieved chunk. Retrieved rows are never displaced. |
| `collection`           | string | `"documents"` | Vector-store collection to search                                                                                                                                                                        |
| `metadata_filter`      | dict   | `null`        | ChromaDB-compatible `where` clause, e.g. `{"category": "AI"}`. It constrains both dense and sparse candidates before fusion.                                                                             |
| `diagnostics`          | bool   | `false`       | Include core-produced ranking, policy, threshold, reranker, and sparse-backend diagnostics. Keep disabled for lean responses.                                                                            |

A collection that follows a user profile runs the Search pipeline of that
profile. See [User profiles](#user-profiles).

When `diagnostics` is `true`, results also preserve every diagnostic field
produced by core retrieval. The transport does not define or rename these
fields.

When `diagnostics` is `true`, each result row also carries a `timings` mapping
of per-stage retrieval wall-clock durations in seconds:

| Key                 | Stage                | Present when                           |
| ------------------- | -------------------- | -------------------------------------- |
| `embedding_seconds` | Query embedding      | Always (every search embeds the query) |
| `dense_seconds`     | Dense vector search  | Always                                 |
| `sparse_seconds`    | Sparse (BM25) search | Hybrid queries only                    |
| `fusion_seconds`    | RRF fusion           | Hybrid queries only                    |
| `rerank_seconds`    | Cross-encoder rerank | Reranking ran (success or failure)     |
| `assembly_seconds`  | Context assembly     | Always (every search assembles results) |

A stage that did not run is absent from the mapping. Absence means "did not
execute", never "took zero time". No total duration is emitted.

Dense and sparse stages run concurrently in hybrid mode, so their durations
overlap. Do not sum `dense_seconds` and `sparse_seconds` to get wall time.
Compare each stage independently.

Every ranked result includes `score_kind`: `dense_similarity_v1` for dense search,
`rrf_v1` for non-reranked hybrid fusion, or `reranker_sigmoid_v1` after a
successful rerank. `similarity_threshold` is never applied directly to an
`rrf_v1` value.

### Context assembly

Every search runs an assembly stage between final ranking and return
([ADR-056](../adr/056-lineage-navigation-replaces-a-document-store.md)). The
stage reshapes returned evidence. It never re-ranks, re-scores, or drops
evidence.

**Overlap is removed by default.** Adjacent chunks of one source version
merge into one row. Only the longest exact suffix/prefix match within the
configured `chunk_overlap` budget is removed. When no exact match fits, the
texts concatenate without deletion. A merged row's text is a superset of each
constituent's unique content, so no evidence is lost.

A merged row carries a `chunk_ids` array. It lists the `chunk_id` of every
constituent chunk in ascending order. Its `source_chunk_index` is the lowest
constituent index. Its `score` is the best constituent score. Use any listed
`chunk_id` as a citation; each resolves to exactly one stored chunk. Unmerged
rows keep the plain `chunk_id` key and gain nothing.

**Neighbour expansion is opt-in.** Set `expand_window` above zero to add each
retrieved chunk's neighbours to its context. Expansion is bounded by the
window. Expanded neighbours merge into the retrieved chunk under the merging
rules above. Retrieved rows are never dropped to honour `top_k` after
expansion. Rows added purely by expansion were never ranked, so they carry no
`score` and no `score_kind`.

**The client still owns final context budgeting.** Assembly removes duplicate
text and can add requested neighbours. It does not truncate to a token limit.
Count tokens on the returned text before you send it to a model.

When `diagnostics` is `true`, each row also reports `assembly_merged`,
`assembly_chunk_count`, and `assembly_expanded`.

Every result also carries additive lineage fields: `source_id`,
`source_version`, `chunk_id`, `source_chunk_index`, and `source_chunk_count`
([ADR-052](../adr/052-stable-source-chunk-lineage.md)). Values are `null` for
rows stored without lineage, such as experiment precomputed rows. The
internal attempt-specific vector row ID is not exposed; use `chunk_id` as the
stable per-chunk reference, and `source_id` plus `source_version` to select
one complete source version.

## `answer_documents`

Answer a question from the indexed documents with deterministic, verifiable
citations ([ADR-057](../adr/057-answering-is-additive-and-injected.md)). This
is the first query-time generation path: it performs one or more
language-model completion calls. Retrieval is cheaper. Use
[`search_documents`](#search_documents) when you only need ranked chunks.

| Parameter              | Type   | Default         | Description                                                                                            |
| ---------------------- | ------ | --------------- | ------------------------------------------------------------------------------------------------------ |
| `query`                | string | _(required)_    | Natural language question                                                                              |
| `top_k`                | int    | profile default | Maximum chunks used as evidence                                                                        |
| `similarity_threshold` | float  | `0.0`           | Minimum evidence score. Same semantics as `search_documents`                                           |
| `rerank`               | bool   | `null`          | Tri-state rerank control. Same semantics as `search_documents`                                         |
| `hybrid`               | bool   | `null`          | Tri-state hybrid retrieval control. Same semantics as `search_documents`                               |
| `expand_window`        | int    | `0`             | Neighbours merged into each evidence chunk during context assembly                                     |
| `diagnostics`          | bool   | `false`         | Include retrieval and generation timings, and the completion-call count                                |
| `collection`           | string | `"documents"`   | Collection to answer over                                                                              |
| `metadata_filter`      | dict   | `null`          | ChromaDB-compatible `where` clause restricting the evidence, e.g. `{"category": "AI"}`                 |

Retrieval runs through the same profile-resolved path as
`search_documents`. The answer is synthesised only from the retrieved
evidence. Synthesis uses LlamaIndex COMPACT mode, which packs the evidence
into as few completion calls as the context allows and may refine across more
calls. Rounds are bounded by `ANSWER__MAX_ROUNDS` (1–8; the client-sampling
path caps at 4). Each round gets a per-round context budget in characters
(`ANSWER__CONTEXT_WINDOW`). Later rounds may widen that budget, but never
past a hard character ceiling (262,144). At the ceiling, the lowest-ranked
evidence is dropped or trimmed first, and the prompt carries a truncation
notice.

### Statuses

| Status                  | Meaning                                                                                                            |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `ok`                    | The answer carries at least one verifiable citation                                                                 |
| `no_evidence`           | Retrieval found nothing. Returned before any model call — no completion runs, whatever the provider configuration |
| `generation_unverified` | The model produced a non-empty answer with no valid citation. Never reported as `ok`. The evidence is still returned |
| `unverified_claims`     | Verification was enabled and one or more cited claims failed the judge. The answer, citations, and evidence are all retained; `unverified_claims` in the result lists the failing claims. Opt-in only — see [Claim verification](#claim-verification-optional) |
| `error`                 | A stage failed. `failure_stage` separates `retrieval` from `generation`; `error` carries the message. The tool never raises |

### Result shape

Every result carries `query`, `answer`, `citations[]`, `evidence[]`,
`failure_stage` (`retrieval`, `generation`, or `null`), `error`, and
`completion_source`. With `diagnostics: true`, a `diagnostics` object adds
`retrieval_ms`, `generation_ms`, and `completion_calls`; when claim
verification ran, it also adds `verification_ms` and `verification_calls`,
kept separate from retrieval and generation timings. The HTTP answer
route (`POST /v1/collections/{collection}/answer`) takes the same
`diagnostics` flag and returns the same object. When verification
ran and passed, the result carries `verified: true`; when the judge could
not run or had no cited prose sentence to check, the result carries
`verification_skipped` with the reason (see
[Claim verification](#claim-verification-optional)).

Citations and evidence rows carry `ordinal`, `chunk_id`, `chunk_ids`,
`source_id`, `source_version`, `source`, `source_chunk_index`, `score`, and
`score_kind`. Evidence rows also carry `text`.

### Completion source

`completion_source` names the model that produced the answer:

| Value           | Model that ran                                                                                                                                                                          |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `client_mrtr`   | The MCP client's own model, through the bounded multi-round resolver chain. Modern session (protocol ≥ 2026-07-28) with the sampling capability and `ANSWER__PREFER_CLIENT_SAMPLING=true` |
| `client_legacy` | The client's model through the deprecated `create_message` back-channel. Runs only on a negotiated pre-2026-07-28 session with `ANSWER__ALLOW_LEGACY_SAMPLING=true`. Never runs on a modern session |
| `server`        | The configured server model (`ANSWER__PROVIDER` / `ANSWER__MODEL`), resolved through the same LLM registry as metadata extraction                                                        |
| `none`          | No model ran (`no_evidence`, or an error)                                                                                                                                                |

With evidence but no model available from either side, the tool returns an
actionable error. The error names `ANSWER__PROVIDER` and `ANSWER__MODEL`,
and the client-sampling alternative.

**User-profile collections always use the server model.** When the collection
follows a user profile (see [User profiles](#user-profiles)), the tool runs the
Answer pipeline of that profile. A client sampling request cannot enter a
pipeline run. The tool checks the profile of the collection first and sends no
sampling request to the client, even when the client offers sampling.
`completion_source` is `server`. The server needs a configured answer model
(`ANSWER__PROVIDER` / `ANSWER__MODEL`).

### Citation verifiability

Citations are built from chunk lineage, never from model-invented
identifiers. A `chunk_id` the model invents, or an ordinal outside the
supplied range, is discarded. Malformed and duplicate ordinals are dropped or
deduped. Every cited `chunk_id` re-fetches exactly one stored chunk by
metadata filter. A merged row lists every constituent `chunk_id`, so any
listed id resolves to one stored chunk. A non-empty answer with no valid
citation is `generation_unverified`, never `ok`.

### Prompt-injection caveat

The prompt is a fixed instruction block. Retrieved text is presented as
quoted sources inside it. This does not eliminate prompt injection from
ingested content — the risk is inherent to retrieval-augmented generation.
It is mitigated, not solved. Treat ingested content as untrusted input.

### Claim verification (optional)

A citation proves the ordinal resolves to stored lineage. It does not prove
the cited evidence supports the claim. Setting `ANSWER__VERIFY_CLAIMS=true`
adds an LLM judge that closes this gap (security review F4; mitigated by
[ADR-059](../adr/059-claim-verification-stage.md), with the evidence from
[experiment 20](../../experiments/20-citation-faithfulness-2026-09-02/)).

The judge splits the answer into cited claims and evaluates each against
the text of the evidence its citation references — one judge call **per
cited prose sentence**, to the **configured judge provider**
(`ANSWER__VERIFY_PROVIDER`; default `cloud`, aliasing the configured cloud backend — experiment 20
measured P95 ≈ 3.3 s per claim on the GLM-5.3 cloud judge, and a local
`qwen3:4b` judge was infeasible, so the cloud path is the only tested
one). This is an explicit opt-in against the local-first policy of
ADR-024. Choose it knowingly.

Only cited prose sentences are judged. The splitter skips these markdown
structure lines and sends none of them to the judge:

- ATX headings (`#` to `######`) and setext heading underlines.
- Code-fence lines (```` ``` ```` or `~~~`) and every line inside a fenced
  code block.
- Horizontal rules (`---`, `***`, `* * *`).
- Table separator rows (`|---|---|`).
- Bare list markers (`-`, `1.`).

A citation marker on a skipped line is not judged. A line that holds only
a marker and follows a skipped line is not judged either, and the marker
does not attach to an earlier sentence. The marker still counts for
grounding and stays in `citations`. Prose next to a heading or a code block
is judged as before. Structure-like text inside a sentence, such as
``Use `## Title` syntax [1].``, is also judged.

Outcomes:

- Every cited claim supported → status stays `ok` and the result carries
  `verified: true`.
- Any claim unsupported → `status="unverified_claims"`; the result lists
  the failing claims and keeps the answer, citations, and evidence, so
  the caller decides what to do.
- Mixed supported/unparseable → also `unverified_claims`: an unreadable
  verdict is never silently passed, and the claim is listed with
  `verdict: "unparseable"`.
- Judge unreachable (missing API key, network error) or every verdict
  unparseable → status stays `ok` (the referential-only guarantee) with a
  `verification_skipped` field naming the reason. The answer is never
  blocked behind an unconfigured cloud dependency.
- No cited prose sentence to check (for example, the only citation sits
  on a heading) → no judge call. Status stays `ok`, the result has no
  `verified` field, and `verification_skipped` is
  `no verifiable claims (no cited prose sentence)`.
- Disabled (the default) → no judge calls, no new fields, no behavioural
  change.

The judge prompt wraps evidence in explicit `<evidence>` delimiters,
labels it untrusted source data, and repeats the instruction hierarchy
after each block; angle brackets inside untrusted text are escaped so
the content cannot forge its own delimiter. This is a mitigation, not
a guarantee — treat verification results as advisory when the indexed
evidence may be attacker-controlled.

Configuration: `ANSWER__VERIFY_CLAIMS` (default `false`),
`ANSWER__VERIFY_MODEL` (default empty — the provider's default model),
`ANSWER__VERIFY_PROVIDER` (default `cloud`; aliases `cloud`/`local`
resolve to the configured backends, anything else is a literal registry
name validated at startup). Profile bundles may override the three keys
per collection; environment variables still win over the profile. In
`omrg web`, Settings > Chat can also set the judge provider and model; see
[Web workspace](web-workspace.md#claim-check-judge). See
[Configuration](configuration.md#answering--answer__).

Configuration: the `ANSWER__*` variables. See
[Configuration](configuration.md#answering--answer__).

## `ingest_documents`

Index a file or directory into the vector store.

| Parameter    | Type   | Default       | Description                                   |
| ------------ | ------ | ------------- | --------------------------------------------- |
| `path`       | string | _(required)_  | Path to a file or directory to ingest         |
| `collection` | string | `"documents"` | Vector-store collection to store documents in |

## `list_indexed_documents`

Show what's currently indexed.

| Parameter    | Type   | Default       | Description                                    |
| ------------ | ------ | ------------- | ---------------------------------------------- |
| `collection` | string | `"documents"` | Vector-store collection to list documents from |

Each row is `{"source": <path>, "source_id": <id or null>, "chunks": <count>, "orphaned": <true, false, or null>}`.
Chunks are grouped by `source_id`, so one indexed file appears once with its
chunk total. Rows without lineage metadata (for example experiment
precomputed rows) fall back to path grouping and report `source_id: null`.

The `orphaned` field is machine-local:

- `true`: The absolute source path is missing on this machine.
- `false`: The absolute source path exists on this machine.
- `null`: The row has no absolute path that this machine can check.

This field does not prove that a source is missing elsewhere. An index can
contain paths created on another machine. Listing is read-only and never
deletes indexed chunks. Use [`delete_documents`](#delete_documents) with
`dry_run: true` to preview manual cleanup before explicit deletion.

## `list_collections`

No parameters. Returns a list of objects with `name`, `document_count`, and `chunk_count`.

## `delete_documents`

Remove documents by file path, metadata filter, or drop an entire collection.

| Parameter         | Type   | Default       | Description                                                                                                                                    |
| ----------------- | ------ | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `path`            | string | `null`        | Source file path whose chunks to delete. The path is canonicalised and matched by its derived `source_id`, the same derivation ingestion uses. |
| `metadata_filter` | dict   | `null`        | ChromaDB-compatible `where` clause to match chunks, e.g. `{"category": "uncategorised"}`                                                       |
| `collection`      | string | `"documents"` | Collection to operate on. When provided alone (without `path` or `metadata_filter`), the entire collection is dropped.                         |
| `dry_run`         | bool   | `false`       | Preview what would be deleted without modifying the vector store                                                                               |

The three deletion modes (`path`, `metadata_filter`, `collection`-only) are mutually exclusive.

A `./`-prefixed path is canonicalised before matching, so `./notes/a.md` and
its absolute form delete the same source.

## `get_codebase_map`

Generate a compact codebase map showing file types, code communities, document communities, cross-links, and architectural hubs. Designed for agents starting a session on an unfamiliar codebase.

| Parameter | Type   | Default | Description                                        |
| --------- | ------ | ------- | -------------------------------------------------- |
| `path`    | string | `"."`   | Project directory path to map                      |
| `refresh` | bool   | `false` | If true, rebuild the map regardless of cache state |

Results are cached per project in `<CODEBASE_MAP_CACHE_DIR>/codebase-graph.json` (default `.opencode/`). The tool reuses a cached map only when both of these match:

1. The git commit hash.
2. The owner context: the map settings and the store's durable data version for the `documents` collection.

Any other record is a miss. The tool rebuilds the map and then replaces the record. It does not delete old records in advance. Use `refresh=true` to force a rebuild.

The tool reads the composed settings and store at its own boundary and passes them to the core. The parameters and the JSON error shape stay the same. If no store is composed, the tool builds the map without document communities.

Reuse is reduced in these cases:

- The store gives no durable data version. This applies to Chroma, to an absent `documents` collection, and to a LanceDB table that has no dataset epoch yet. The tool then rebuilds on every call.
- The path is not a git repository. The tool then rebuilds on every call.
- Records written before owner context existed. The first call rebuilds and replaces them.

**Read-only:** This tool does not modify any files or databases.

---

## `change_collection_profile`

Change the profile of a collection. The built-in profiles are `documents` and
`codebase`. A ready user profile also works on the MCP endpoint of `omrg web`
(see [User profiles](#user-profiles)). The change affects retrieval behaviour
only. No chunk is re-chunked or re-embedded.

| Parameter    | Type   | Default      | Description                                                                                  |
| ------------ | ------ | ------------ | -------------------------------------------------------------------------------------------- |
| `collection` | string | _(required)_ | Collection to change                                                                         |
| `profile`    | string | _(required)_ | `documents`, `codebase`, or on the web endpoint the `profile_id` of a ready user profile    |
| `confirm`    | bool   | `false`      | Apply the change. When `false`, returns a preview instead                                    |

Called without `confirm`, it returns a preview describing what would change:
which levers move, whether each applies immediately or only to future ingests,
and the current chunk count. Nothing is modified.

```json
{ "collection": "my_code", "profile": "codebase" }
```

Call again with `"confirm": true` to apply it.

Two-step by design: some levers (top_k, reranker) take effect on the next
query, while others (chunking strategy) only affect documents ingested from
then on. The preview makes that distinction visible before you commit to it.

A collection cannot be set to `hybrid` — that is a server mode, not a
collection profile. See [Configuration](configuration.md#profiles).

For a user profile, the preview adds a `pipelines` list (the three pipelines
with their current revision numbers) and `notes`. The tool refuses a profile
that is not ready. The error carries `not_ready_reasons`, a list of plain
English lines that say what to fix.

On the web endpoint, the tool also refuses any profile, built-in or user,
whose embedding model differs from the model that made the collection's
vectors (ADR-081). The message names both models. The preview and the confirm
step both run this check.

**The stdio server cannot bind a user profile.** It refuses a user profile id
with this message and changes nothing:

```text
Bind user profiles in Knowledge Base > Profile, or through the MCP endpoint of `omrg web`.
```

---

## `list_profiles`

List the profiles that a collection can use. The tool has no parameters and
changes nothing (read-only). Built-in profiles come first, then the user
profiles of the web workspace.

Each item has these fields:

| Field              | Meaning                                                                                       |
| ------------------ | --------------------------------------------------------------------------------------------- |
| `profile_id`       | The id to pass to `change_collection_profile`                                                  |
| `kind`             | `builtin` or `user`                                                                           |
| `title`            | Display name                                                                                  |
| `description`      | Short description                                                                             |
| `base_profile`     | `documents` or `codebase`: the built-in profile whose settings apply                          |
| `slots`            | Pipeline ids for `ingest`, `search` and `answer`. All `null` for a built-in profile            |
| `ready`            | `true` when the profile can be bound to a collection                                          |
| `not_ready_reasons`| Plain English lines that say what to fix when `ready` is `false`                              |
| `used_by`          | Names of the collections whose stored profile tag is this id                                  |

On the web endpoint (`/mcp`) the items are the same as `GET /v1/profiles`.
On the stdio server the items come from the read-only catalogue of the
default workspace (`~/.omrg/workspace/workspace.db`). Readiness and `used_by`
use the same checks as the web server. When that file does not exist, the
list holds the two built-in profiles.

On error the tool returns a list with one `{"status": "error", "message": "..."}` item.

---

## User profiles

A user profile owns three pipelines (Ingest, Search and Answer). You create and
edit user profiles in the web workspace (Knowledge Base > Profile). A
collection that follows a user profile searches, answers and ingests through
those pipelines.

| Server                | `search_documents`, `answer_documents`                                    | Bind a user profile (`change_collection_profile`)       |
| --------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------- |
| `omrg web` at `/mcp`  | Runs the user profile pipelines                                           | Yes, when the profile is ready                          |
| stdio (`omrg`)        | Runs the user profile pipelines, when the default workspace file exists   | No. The tool refuses with the message above             |

The stdio server opens the default workspace database read-only. It never
creates, migrates or writes the file. A workspace that `omrg web --workspace`
placed in another folder is not found.

When the default workspace file does not exist and a collection follows a user
profile, `search_documents` and `answer_documents` return an error. The error
names the profile and the path `~/.omrg/workspace/workspace.db`. It tells you
to start `omrg web` once with the default workspace, or to change the
collection's profile to `documents` or `codebase`.

Values that you pass to `search_documents` (`top_k`, `similarity_threshold`,
`rerank`, `metadata_filter`, `expand_window`) replace the matching pipeline
step settings. Omitted values stay `null`, so the profile decides. For a user
profile, `hybrid` has no effect: the steps of the Search pipeline decide
whether sparse retrieval runs.

---

## Tool behaviour notes

- **Tool handlers never raise exceptions.** Errors are returned as `{"status": "error", "message": "..."}`.
- **All parameters are optional with sensible defaults** — backward compatible with existing clients.
- **Re-ingestion is an upsert** — old chunks for a file are removed before new ones are written. No duplication.
