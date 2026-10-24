# Configuration

Where settings live, which one wins, and what every setting does.

---

## The short version

Settings come from six places. Each beats the one above it:

| # | Source | What belongs here |
|---|---|---|
| 1 | Model defaults, in the code | Last resort. You never edit these directly. |
| 2 | `src/omrs/config/defaults.yaml` | Project-wide defaults. Committed. Shared by everyone. |
| 3 | Profile YAML (`config/profiles/*.yaml`) | Per-collection behaviour |
| 4 | `omrs.jsonc` in the [user config folder](#user-config-folder) | Your settings. Edit it by hand or on the Settings page. |
| 5 | `.env` | Your machine: tokens, URLs, paths |
| 6 | Environment variables | Highest. Wins over everything. |

The Settings page shows the source of each value: `env`, `dotenv`, `config-file`, `yaml` or `default`. Only `env` and `dotenv` lock a field on the page. A value in `omrs.jsonc` does not lock it.

**Rule of thumb:**

- Sensible default for everyone → `defaults.yaml`
- Your own settings, kept in one file you can edit or the page can edit → `omrs.jsonc`
- Secret, or specific to your machine → `.env`
- Different for one collection → its profile
- Just for this one command → an environment variable

**Why the schema is Python while the values are YAML.** In short: YAML for
data, Python for the contract. Humans edit values, so the values live in YAML
(`defaults.yaml` and the profile bundles), while the contract (which keys
exist, their types, which source wins) is defined once in the typed Python
models in `config/__init__.py`. A misspelt key in YAML or an environment
variable therefore fails at startup and lists the valid fields, instead of
being silently ignored.

### The trap worth knowing

`.env` and environment variables sit **above** profiles. Put a profile lever
(`retrieval.top_k`, `retrieval.rerank_enabled`, `retrieval.hybrid_enabled`,
`chunking.strategy_fallback`, `metadata.taxonomy_mode`) in either and it
overrides every profile silently.

Real example: `RETRIEVAL__TOP_K=5` in `.env` meant the `documents` profile
(top_k 10) and the `codebase` profile (top_k 20) both returned 5 results.
Profiles looked broken. Nothing warned about it.

The same lever in `omrs.jsonc` does the opposite: each collection's profile
replaces it, so it changes nothing. `omrs config show` still lists it with
source `config-file`, so it looks in force (ADR-087 addendum).

**Keep the profile levers out of `.env` and `omrs.jsonc`. Keep `.env` for connection details and secrets only.**

---

## Variable naming

Settings that belong to one area are nested. The environment variable joins the
block and the field with a double underscore:

```
retrieval.top_k             →  RETRIEVAL__TOP_K
chunking.chunk_size         →  CHUNKING__CHUNK_SIZE
ingestion.embed_batch_size  →  INGESTION__EMBED_BATCH_SIZE
embedding.norm_tolerance    →  EMBEDDING__NORM_TOLERANCE
metadata.extraction_mode    →  METADATA__EXTRACTION_MODE
```

Cross-cutting settings stay flat: `EMBED_MODEL`, `CHROMA_PERSIST_DIR`,
`VECTOR_STORE`, `LANCEDB_URI`, `RAG_PROFILE`, `PDF_READER`, and every
credential.

In YAML the same thing looks like this:

```yaml
retrieval:
  top_k: 10
  rerank_enabled: false

chunking:
  chunk_size: 512

# cross-cutting settings stay at the top level
EMBED_MODEL: qwen3-embedding:0.6b
```

### Upgrading from v1

Pre-v2 flat names (`TOP_K`, `CHUNK_SIZE`, `METADATA_EXTRACTION_MODE`, …) are no
longer read. The app **refuses to start** and names the replacement, rather
than silently falling back to a default.

Two guards catch mistakes:

- A wrong nested key (`RETRIEVAL__TOPK`) fails immediately, listing the valid
  fields.
- An old flat name (`TOP_K`) fails with the new name.

Full rename table: [ADR-037](../adr/037-architecture-v2-conformance.md).

---

## Profiles

A profile is a named bundle of retrieval behaviour, bound to a collection.

| Profile | For | top_k | Reranker | Hybrid search |
|---|---|---|---|---|
| `documents` | Papers, reports, prose | 10 | on | off |
| `codebase` | Source code | 20 | off | on |
| `hybrid` | Not a profile — a mode selector | — | — | — |

**Profiles only control five things:**

- `retrieval.top_k`
- `retrieval.rerank_enabled`
- `retrieval.hybrid_enabled`
- `chunking.strategy_fallback`
- `metadata.taxonomy_mode`

Everything else — chunk size, storage path, embedding model — is shared.

### Choosing a profile

Server-wide default:

```bash
RAG_PROFILE=documents
```

Per collection, which is the point of the feature:

```bash
omrs set-profile -c my_code -p codebase
```

Set `RAG_PROFILE=hybrid` to let each collection pick its own; untagged
collections fall back to `default_profile` in `hybrid.yaml`.

A collection cannot be tagged `hybrid` — it selects a mode, it is not one.

### User profiles

A user profile is a profile that you make in the web workspace. It has an id,
a title, a **base profile** (`documents` or `codebase`) and three pipelines:
**Ingest**, **Search** and **Answer**. The base profile gives the five profile
settings. The pipelines decide how the collection reads, searches and answers.

A collection follows a user profile when its `profile` tag holds the user
profile id, for example `my-notes`. `RAG_PROFILE` and `default_profile` in
`hybrid.yaml` accept `documents` and `codebase` only.

The web server owns the workspace. It reads and writes the database file
`workspace.db` in the folder of `omrs web --workspace` (default
`~/.omrs/workspace`). Other processes read user profiles from that default
folder, read-only, when the file exists:

| Process | Reads user profiles | Binds a user profile to a collection |
|---|---|---|
| `omrs web` and its MCP endpoint | Yes, from its own workspace | Yes |
| Stdio MCP server (`omrs`) | Yes, from the default workspace | No |
| CLI (`search`, `answer`, `ingest`, `watch`) | Yes, from the default workspace | No (`omrs set-profile` takes built-in names only) |

To bind a user profile, use Knowledge Base > Profile in the web app, or the
`change_collection_profile` tool on the MCP endpoint of `omrs web`.

If the default workspace file does not exist, a collection tagged with a user
profile fails with this error:

```text
Collection 'notes' uses the profile 'my-notes', which is not a built-in
profile. User profiles live in the web workspace, and no workspace database
was found at ~/.omrs/workspace/workspace.db. Start `omrs web` once with the
default workspace, or change the collection's profile to 'documents' or
'codebase'.
```

To fix it, do one of these:

1. Start `omrs web` once with the default workspace.
2. Run `omrs set-profile -c notes -p documents` (or `codebase`).

If you start `omrs web` with another `--workspace` folder, the other
processes do not find its profiles. The error names the path they read.

### Why the reranker differs

The `documents` profile turns the reranker on; `codebase` leaves it off. That
is not an oversight. Experiment 10 measured the reranker making code retrieval
**19–27% worse** and adding ~14s per query. On prose it helps. See
[ADR-019](../adr/019-reranker-disabled-for-technical-workloads.md) and
[ADR-030](../adr/030-prefer-int8-onnx-variant-for-modernbert-rerankers.md).

---

## What goes in `.env`

Only these:

```bash
# Where the vector database lives
VECTOR_STORE=lancedb
LANCEDB_URI=./lancedb
COLLECTION_NAME=documents
# Chroma only: install the `chroma` extra, set VECTOR_STORE=chroma,
# then keep CHROMA_PERSIST_DIR pointed at its existing directory.
CHROMA_PERSIST_DIR=./chroma_db

# Which embedding model, and where to reach it
EMBED_MODEL=qwen3-embedding:0.6b
OLLAMA_BASE_URL=http://localhost:11434

# Secrets
HF_TOKEN=...
OPENROUTER_API_KEY=...
AZURE_DOC_INTELLIGENCE_KEY=...
CHROMA_CLOUD_API_KEY=...
```

If you find yourself putting `RETRIEVAL__*` or `CHUNKING__*` in here, it
probably belongs in `defaults.yaml` or a profile instead.

---

## All settings

Defaults below are what ships in `defaults.yaml`.

### Storage

| Variable | Default | What it does |
|---|---|---|
| `CHROMA_PERSIST_DIR` | `./chroma_db` | Where the database is written |
| `COLLECTION_NAME` | `documents` | Default collection |
| `CHROMA_SCAN_PAGE_SIZE` | `10000` | Rows per page when scanning metadata |
| `VECTOR_STORE` | `lancedb` | Store implementation: `lancedb` (base-install default) or `chroma` (optional extra). Unrecognised values fail startup listing the registered names |
| `LANCEDB_URI` | `./lancedb` | Parent directory for LanceDB tables (`VECTOR_STORE=lancedb` only). Embedded/local only in v1 |
| `CHROMA_MODE` | `local` | `local` or `cloud`. Explicit selection; unrecognised values fail startup |
| `CHROMA_CLOUD_API_KEY` | — | Required when `CHROMA_MODE=cloud`. `.env` only — never in YAML, logs, or results |
| `CHROMA_CLOUD_TENANT` | — | Optional tenant. Supplied with `CHROMA_CLOUD_DATABASE`, or both omitted |
| `CHROMA_CLOUD_DATABASE` | — | Optional database. Supplied with `CHROMA_CLOUD_TENANT`, or both omitted |

### Storage layout and concurrency

Three layers are often confused. Keep them separate.

**Layout.** LanceDB (the base-install default) stores each collection as its
own table directory, `{LANCEDB_URI}/{collection_name}.lance`. A collection
name must be a non-empty single path component. Separators, control
characters, `.`, `..`, and absolute paths are rejected. Validation runs
before any table access touches
disk (`core/vectordb/lancedb/table_name.py`). Chroma (the optional extra) keeps
collection names as logical identifiers inside one shared persist directory
(`CHROMA_PERSIST_DIR`). Per-collection Chroma persist directories, and Chroma
name validation, are deferred to a future change.

**Process mutation lock.** Ingestion mutations run inside one process-global
lock (`write_lock` in `core/ingestion/_state.py`, acquired by `_commit_sync`
in `core/ingestion/replacement.py`). The lock serialises mutations across all
collections within one process. It is not per-collection. Other processes
cannot see it.

**Cross-process writes.** Concurrent writes from separate processes (for
example, two stdio MCP clients) are unverified for both backends. No
two-process concurrent-write experiment has run. Do not assume isolation from
the `.lance` layout.

The deferred Chroma scope waits for demonstrated operator demand, and any
future contention claim needs a two-process, two-collection concurrent-write
experiment first.

### Chroma deployment mode

Chroma is an explicit optional backend. Install it with `uv sync --extra chroma`
in a source checkout, or `pip install "omrs[chroma]"` from a package. Set
`VECTOR_STORE=chroma` before using its local or cloud modes. CVE-2026-45829
(PYSEC-2026-311) is active for this optional dependency. Do not expose Chroma's
Python FastAPI server through this project.

`CHROMA_MODE` selects the Chroma deployment explicitly. The default mode is
`local`, the embedded `PersistentClient`. Selecting `cloud` connects to hosted
Chroma Cloud. API-key presence never switches storage: a missing shell
variable cannot silently redirect a process to an empty local database.
Unrecognised values fail settings validation.

Embedding compute and vector storage are independent axes. `EMBED_PROVIDER`
selects where embeddings run; `CHROMA_MODE` selects where vectors are stored.
No third selector named `hybrid` exists. All four combinations are valid:

| Mode | Embeddings | Vector store | Use |
| --- | --- | --- | --- |
| Full local | llama.cpp | local Chroma | Private/offline; strong local hardware |
| Cloud compute, local store | OpenRouter/Fireworks | local Chroma | Fast embeddings, local single-machine index |
| Full cloud | OpenRouter/Fireworks | Chroma Cloud | Shared indexes, parallel read cells, no SQLite lock |
| Local compute, cloud store | llama.cpp | Chroma Cloud | Local model with a shared remote index |

OpenRouter is the existing cloud-compute provider. Fireworks is a compatible
future option that needs a separate provider registration — it is not a
vector store.

Cloud mode validates credentials at `Settings` construction:
`CHROMA_MODE=cloud` without `CHROMA_CLOUD_API_KEY` fails startup. The
connection is checked with a heartbeat during runtime setup, so
authentication, network, and tenant/database mistakes surface before any
work begins. A cloud-mode failure is actionable and never silently falls
back to a local index. Select `CHROMA_MODE=local` deliberately if degraded
operation is acceptable.

`CHROMA_CLOUD_TENANT` and `CHROMA_CLOUD_DATABASE` are optional. Supply both
or neither; omitting both lets the cloud client resolve them from the API
key. The key stays in `.env` only — never in `defaults.yaml`, logs, or
results.

Collection metadata records the embedding provider, model, and index
identity. Changing the embedding provider or model, the corpus or parser,
the chunking configuration, or the vector dimension requires re-ingestion
into a fresh collection. Same-dimension model swaps are rejected rather than
silently mixing incompatible vector spaces.

#### Embedding model per profile

The `EMBED_*` settings choose the server default embedding model. A user
profile can choose another provider and model. Open the profile in Studio,
select its Embed step and use "Check model", then "Save model". The choice
belongs to the profile, so ingest, search, answer and graph runs on every
collection that follows the profile use the same model. A graph cannot set the
model. A built-in profile (`documents`, `codebase`) always uses the server
default. To use another model with a built-in profile, duplicate the profile
first.

A collection keeps vectors from one model only. The model of a profile is
locked while a collection that follows the profile holds rows or a model
stamp. A stamped collection stays locked after all its rows are deleted,
because the store keeps its vector size. A collection with rows but no stamp
is locked too, and the message says that the model is not recorded. To use
another model, create a new collection, bind it to the profile and ingest
again. You can always set the model back to the stamped model.

A collection cannot follow a profile whose model differs from the model that
made the collection's vectors. The refusal names both models.

A profile with no choice follows the server default. If you change `EMBED_*`
in `.env`, collections that follow the server default and hold vectors from
the old model fail with a mismatch message. To avoid this, choose an explicit
model in a user profile. Connection settings (URLs and keys) stay in `.env`
for every model.

Run the opt-in smoke check before using cloud storage:

```bash
uv run python scripts/chroma_cloud_smoke.py
```

The script ingests and queries a disposable collection, then deletes it. It
never runs in CI.

### LanceDB backend

LanceDB is the embedded, local-first base-install default. Each RAG collection
maps to one LanceDB table under `LANCEDB_URI`. Tables are created lazily on
first write, which locks the vector dimension. The store keeps collection
metadata, including profile tags and embedding identity, in durable schema
metadata.

LanceDB Cloud is out of scope. Unknown `VECTOR_STORE` values fail startup with
the registered names listed. The BM25 hybrid path is backend-agnostic: it reads
rows through `iter_documents` and invalidates off the store's durable data
version where one exists, else the process-local generation counter
([ADR-056](../adr/056-lineage-navigation-replaces-a-document-store.md)).
Native LanceDB full-text search is implemented as the `native` sparse backend
(see [Reranker](reranker.md#sparse-retrieval-backends-hybrid-search)).

### Legacy Chroma data and rollback

When the default would select LanceDB and recognised data exists in
`CHROMA_PERSIST_DIR`, startup stops. Choose one path: install the Chroma extra
and explicitly set `VECTOR_STORE=chroma` to keep the data, or explicitly set
`VECTOR_STORE=lancedb` and re-ingest source files. The server never migrates,
deletes, moves, or rewrites the Chroma directory.

Switching stores requires re-ingestion. Before reverting after LanceDB
ingestion, set and verify `VECTOR_STORE=lancedb`. Keep the pin while reverting
so an older release cannot select Chroma and make LanceDB data appear missing.

### Providers

Two Chat providers serve answering only. They are not valid for `EMBED_PROVIDER`, `LOCAL_BACKEND` or `CLOUD_BACKEND`. Set them with `ANSWER__PROVIDER=openai_compatible` or `ANSWER__PROVIDER=anthropic`, or choose them in Settings > Chat.

| Variable | Default | What it does |
|---|---|---|
| `OPENAI_COMPATIBLE_BASE_URL` | `https://api.openai.com/v1` | Address of any server that speaks the OpenAI chat API (OpenAI, Together, vLLM, LM Studio). It can be on this machine or remote |
| `OPENAI_COMPATIBLE_API_KEY` | unset | Optional. LM Studio and vLLM need none. The key goes only to the address above |
| `ANTHROPIC_API_KEY` | unset | Required for the `anthropic` provider. Address fixed at `https://api.anthropic.com`. Needs `uv sync --extra anthropic` |

| Variable | Default | What it does |
|---|---|---|
| `EMBED_PROVIDER` | `local` | `local`, `cloud`, `ollama`, `llamacpp`, or `openrouter` |
| `METADATA_LLM_PROVIDER` | `local` | `local` or `cloud`, independent of the above |
| `LOCAL_BACKEND` | `llamacpp` | `llamacpp` or `ollama` |
| `CLOUD_BACKEND` | `openrouter` | `openrouter` |
| `EMBED_MODEL` | — | Model name for embeddings |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_CONTEXT_WINDOW` | `16384` | Ollama context window in tokens, 2,048 to 262,144. See [Context windows](#context-windows) |
| `LLAMACPP_CONTEXT_WINDOW` | `16384` | Context window (`-c`) for the llama.cpp chat server that `omrs web` starts, 2,048 to 262,144 |
| `LLAMACPP_IDLE_SLEEP_SECONDS` | `300` | Idle seconds before that server frees its model (`--sleep-idle-seconds`), 0 to 86,400. 0 turns sleep off |
| `LLAMACPP_SERVER_BINARY` | unset | Absolute path to `llama-server`, for the server that `omrs web` starts. See [Local llama.cpp server](#local-llamacpp-server) |
| `LLAMACPP_SERVER_MODEL` | unset | Absolute `.gguf` path or Hugging Face id `org/name[:tag]` for that server |

An unrecognised value for any of the four provider selections above
(`EMBED_PROVIDER`, `METADATA_LLM_PROVIDER`, `LOCAL_BACKEND`,
`CLOUD_BACKEND`), plus `DOCUMENT_BACKEND`, fails startup with a clear
error naming the value and the accepted set.
`RETRIEVAL__HYBRID_SPARSE_BACKEND` fails startup the same way, but its
accepted names are registry-owned and validated at the composition
boundary (`capabilities.validate_sparse_backend`): an unknown concrete
name is rejected, listing `auto` plus the registered sparse backends.
Leading and trailing whitespace is stripped before validation, so
`EMBED_PROVIDER=" local "` resolves to `local`.
An empty or whitespace-only value (`SETTING=` in `.env`) is treated
as unset and resets to the default.

Optional dependencies:

```bash
uv sync --extra anthropic    # Anthropic Chat provider (about 40 MB of SDKs)
```

The LlamaIndex OpenAI-like packages are in the base install. The llama.cpp, OpenRouter and OpenAI-compatible providers need no extra. `uv sync --extra llamacpp` and `uv sync --extra openrouter` still work and install nothing more.

Connection details for each: [Providers](providers.md).

#### Change provider values in the web workspace

In `omrs web`, Settings > Providers saves these values in `omrs.jsonc`: `OLLAMA_BASE_URL`, `OLLAMA_CONTEXT_WINDOW`, `LLAMACPP_CHAT_URL`, `LLAMACPP_SERVER_BINARY`, `LLAMACPP_SERVER_MODEL`, `LLAMACPP_CONTEXT_WINDOW`, `LLAMACPP_IDLE_SLEEP_SECONDS`, `OPENROUTER_API_KEY`, `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY` and `ANTHROPIC_API_KEY`. The server uses the first source it finds, highest first:

| Rank | Source | Shown as | Locks the field |
|---|---|---|---|
| 1 | Process environment | `env` | yes |
| 2 | `.env` | `dotenv` | yes |
| 3 | `omrs.jsonc` in the [user config folder](#user-config-folder). A key field holds a reference: `env://` shows `config-file`, `file://` shows `key-file`, `keychain://` shows `keychain`. | `config-file`, `key-file`, `keychain` | no |
| 4 | A key file `secrets/<provider>.key` (keys only) | `key-file` | no |
| 5 | YAML defaults and the profile bundle | `yaml` | no |
| 6 | The code default | `default` | no |

A locked field shows the variable name and where it is set. Remove the variable from the environment or `.env` to edit the field here. A value in `omrs.jsonc`, a key file or a key reference does not lock. A save on the page replaces it.

The page writes `omrs.jsonc`. It changes only the key you save. Comments, key order and the other keys stay. A key saved on the page goes in the system keychain (service `omrs`, user name equal to the provider name), and the file gets `keychain://<provider>`. The app never writes a key to `.env`, to the workspace database or to a file. If no keychain exists, set the key variable (for example `OPENROUTER_API_KEY`) in the environment, or use a key file.

A saved or hand-edited value applies at once to new requests, with no restart. The Ollama address stays locked while embeddings use Ollama. Embedding providers and models are not editable on the page. The stdio MCP server and the CLI read `omrs.jsonc` when they start, so they see a page save at their next launch. See [Web workspace](web-workspace.md#provider-settings).

#### User config folder

The user config folder holds `omrs.jsonc`. You can edit the file by hand. The Settings page also writes it. The CLI, the stdio MCP server and `omrs web` all read it. This mirrors the OMMS layout (`~/.config/omms/omms.jsonc`).

The folder is the first of these:

1. `$OMRS_CONFIG_DIR`.
2. `$XDG_CONFIG_HOME/omrs`.
3. `~/.config/omrs`.

A missing folder or file gives no values and no warning. The folder can hold two things:

- `omrs.jsonc`: JSON with comments and trailing commas. It accepts every setting that the environment accepts.
- `secrets/<provider>.key`: one key for each provider. The file name is the provider name (`openrouter`, `openai_compatible`, `anthropic`). The page never writes it.

##### Key names

A file key is the environment name in lower case. A double underscore (`__`) nests one level. One rule covers every setting, so there is no mapping table:

```text
RETRIEVAL__TOP_K     →  { "retrieval": { "top_k": 7 } }
CHUNKING__CHUNK_SIZE →  { "chunking": { "chunk_size": 512 } }
EMBED_PROVIDER       →  { "embed_provider": "local" }
ANSWER__MODEL        →  { "answer": { "model": "qwen3:8b" } }
```

Three keys exist only in the file: `web_port`, `web_max_upload_mib` and `mcp_http_enabled`. `web_max_upload_mib` also has a launch twin, `WEB_MAX_UPLOAD_MIB`, which locks it.

Example `omrs.jsonc` (fake values):


```jsonc
{
  // Non-secret values
  "ollama_base_url": "http://gpu-box.local:11434",
  "openai_compatible_base_url": "https://api.together.xyz/v1",
  "answer": { "provider": "openrouter", "model": "openai/gpt-4o-mini" },
  "retrieval": { "top_k": 7 },
  "web_port": 9100,

  // Key fields hold references only
  "openrouter_api_key": "keychain://openrouter",
  "anthropic_api_key": "env://MY_ANTHROPIC_KEY",
}
```


A key field takes one of three references:

- `env://NAME`: the value of the environment variable `NAME`.
- `file://<path>`: a file inside `secrets/`. A leading `~` is the home folder.
- `keychain://<provider>`: the system keychain entry `omrs` / `<provider>`. Every process resolves it: the web server, the CLI and the stdio MCP server. The first read can make macOS ask you to allow access. Use `env://` or `file://` to avoid the prompt.

Example layout and permissions:


```text
~/.config/omrs/
  omrs.jsonc
  secrets/
    openrouter.key      one line: the key
    anthropic.key
```

```bash
chmod 700 ~/.config/omrs/secrets
chmod 600 ~/.config/omrs/secrets/*.key
```

Rules the server applies:
- A literal key in `omrs.jsonc` is ignored. The log names the field and never shows the value.
- A `file://` path must resolve inside `secrets/`. Any other path is refused.
- A key file holds at most 4 KiB. The server strips surrounding whitespace.
- The server refuses a symlink that leaves the folder, and a file that is not a regular file.
- A key file looser than 0600, or a `secrets/` folder looser than 0700, is still read. The log shows one warning with the path and mode, never the content. Windows skips the check.
- A new `omrs.jsonc` gets mode 0600 and a new folder gets mode 0700. A page save keeps the mode of an existing file.
- A page save goes to a temporary file that replaces the original, so a stop during a save never leaves half a file.
- The server notices a hand edit before the next request that reads settings. A save from the page that was open before your edit is refused (409), and your edit stays. Reload the page to see it.

##### What the Settings page writes

Settings > Configuration lists every setting. Each row shows the value in force and its source. A row with Edit opens a control for its kind: an on/off switch, a number field with its range, a choice list or a text field. Save sends `PUT /v1/settings/configuration`. The server checks every change, then writes all of them in one save or none.

The page can write every setting that holds one plain value: a boolean, a number, a text or a fixed choice. This includes the retrieval, reranker, hybrid, chunking, ingestion, metadata, answer, OCR and server settings, and the three file-only keys. The list comes from the `Settings` model, so a new plain setting is editable with no list change.

The server checks each value against the rule of its setting before the write: the type, the lower and upper bound, and the accepted choices. A value that breaks its rule gets 400 with the rule. The file does not change.

These keys stay read-only. The row shows the reason and no Edit:

| Keys | Reason on the row |
|---|---|
| `embed_provider`, `embed_model`, `local_backend`, `cloud_backend`, `llamacpp_embed_url`, `llamacpp_embed_model`, `openrouter_embed_model`, every `embedding.*` key | The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest. |
| `vector_store`, `lancedb_uri`, `chroma_persist_dir`, `chroma_mode`, `collection_name` | Existing collections stay where they are. Change it in omrs.jsonc and restart. |
| `ocr_workers_dir` | The worker folder is set when the OCR workers are installed. |
| Every key field (`*_api_key`, `*_key`) | Keys are set on the provider cards as references. |
| `ingestion.ingest_extensions`, `metadata.keyword_rules` | Edit this in omrs.jsonc. |

More rules:

- A key that the environment or `.env` sets is read-only. The row names the variable, for example "Remove RETRIEVAL__TOP_K from the environment or .env to edit it here." A save of that key gets 409.
- An optional setting saved in the file has Clear. Clear sends `null`, which removes the key from the file. The default then applies.
- A chunking key is part of the index identity. After a restart, the next ingest can read existing files again.
- A restart-only key shows "Restart to apply" after a save. The row keeps the launch value until the restart.
- The Providers cards still write key references (`keychain://`, `env://`, `file://`). The Configuration save refuses key fields.

##### Problems in the file

A problem never stops the server. The server starts and lists each problem by key, never by value. `omrs config show` and `GET /v1/settings/configuration` show the list.

| Kind | When | What the server does |
|---|---|---|
| `broken` | The file is not valid JSON with comments. | Reads no value from the file. Logs one warning. A page save is refused (409) until you fix the file. |
| `invalid` | A value breaks its rule: the wrong type, out of range, a name that is not accepted, an address that is not `http` or `https`, or a literal key. | Ignores that value. The next source applies. The other values stay. |
| `unknown` | A key names no setting (a typo such as `retreival`). | Ignores the key. |
| `retired` | A key is an old flat name such as `top_k`. | Ignores the key. The message names the new key, here `retrieval.top_k`. |

An ignored value falls back to the next source. A typo in `embed_provider` therefore falls back to the default embedder. A collection that holds vectors from another model refuses to search until you restore the old model (ADR-051).

##### Settings that need a restart

`omrs web` applies these hand edits at once: provider addresses and keys, the Chat provider and model, the claim check judge provider and model (`answer.verify_provider`, `answer.verify_model`), reasoning levels (`answer.reasoning`, `answer.verify_reasoning`), context windows, llama.cpp server values, `web_max_upload_mib` and `mcp_http_enabled`. `web_port` and the engine settings (embedding, vector store, chunking, ingestion, retrieval, metadata, OCR and the other `answer` keys) apply at the next launch. `omrs web` keeps the values it started with and marks each changed key "Restart to apply".

**Limit.** These files are plaintext. File permissions do not stop another process of the same user, and an AI coding agent runs as that user. A `file://` or `env://` reference gives no security gain over `.env`. Use them on headless machines and in containers with a mounted folder. On a desktop, save keys in the keychain.

### Context windows

Ollama chat calls need an explicit context window. Without one, LlamaIndex read the model maximum (262,144 tokens for `qwen3:4b`) and sent it as `num_ctx`. Ollama then reserved about 43 GB, ran out of GPU memory and returned empty replies (TDR-036).

- `OLLAMA_CONTEXT_WINDOW` (or `ollama_context_window` in `omrs.jsonc`) sets the window. The default is 16,384 tokens. The range is 2,048 to 262,144.
- The first source wins, highest first: environment and `.env` (both lock), `omrs.jsonc`, the default. A page save writes `omrs.jsonc`.
- The Chat answer model and metadata extraction use it. A saved or hand-edited value applies to the next call. Ollama reloads the model at the new size.
- Embedding models are not covered. A different window can change how text is cut, and so the vectors.
- `LLAMACPP_CONTEXT_WINDOW` has the same range and default. It applies only to the llama.cpp server that `omrs web` starts.

### Local llama.cpp server

`omrs web` can start, stop and restart its own `llama-server` for Chat. Use the llama.cpp card in Settings > Providers, or set the values in the environment or in `omrs.jsonc`.

| Setting | Env | `omrs.jsonc` key |
|---|---|---|
| Program path | `LLAMACPP_SERVER_BINARY` | `llamacpp_server_binary` |
| Model | `LLAMACPP_SERVER_MODEL` | `llamacpp_server_model` |
| Context window | `LLAMACPP_CONTEXT_WINDOW` | `llamacpp_context_window` |
| Idle sleep | `LLAMACPP_IDLE_SLEEP_SECONDS` | `llamacpp_idle_sleep_seconds` |
| Port | `LLAMACPP_CHAT_URL` | `llamacpp_chat_url` |

The sources and locks are the same as for other provider values.

Guardrails:

1. The program is an absolute path to an executable file named exactly `llama-server`. The server checks it at save and before every launch.
2. The model is an existing `.gguf` file or a Hugging Face id `org/name[:tag]`. It never starts with `-`.
3. The port comes from `llamacpp_chat_url`. The URL must be `http` on a loopback host. The server binds to `127.0.0.1`.
4. The arguments are fixed: `-m` or `-hf`, `--host 127.0.0.1`, `--port` and `-c`. No shell runs. You cannot add other arguments.
5. The process gets a minimal environment with no API key.
6. omrs starts and stops only this server. It never touches a server you started yourself. It never finds or stops a process by name or port.
7. The output of the server goes to `llamacpp-server.log` in the workspace folder. The page and the routes never show it.

States are `stopped`, `starting`, `running` and `failed`. A failed start gives one reason: `binary-invalid`, `model-invalid`, `not-loopback`, `port-in-use`, `exited`, `timeout` or `not-configured`. The start waits up to 180 seconds for `GET /health`. Stop sends SIGTERM, waits 10 seconds, then sends SIGKILL. The server stops when `omrs web` exits. A save does not restart a running server. The card then says "Restart to apply".

Example `omrs.jsonc`:

```jsonc
{
  "llamacpp_chat_url": "http://localhost:8081/v1",
  "llamacpp_server_binary": "/opt/homebrew/bin/llama-server",
  "llamacpp_server_model": "Qwen/Qwen3-0.6B-GGUF:Q8_0",
  "llamacpp_context_window": 16384,
  "llamacpp_idle_sleep_seconds": 300,
}
```

Idle sleep. With the default of 300, the server frees the model after five idle minutes and reloads it on the next request, so that answer is slower. The process keeps running. Set 0 to keep the model loaded, or to run a `llama-server` build that has no sleep mode.

Limits. The program path is editable in the GUI by choice. The guardrails limit what can run to a file named `llama-server`. Anyone with the browser session and the `credentials` scope can still point the setting at any file with that name. The llama.cpp embedding server is not managed. The stdio MCP server and the CLI never start or stop the server.

Tests set `OMRS_CONFIG_DIR` to a temporary folder, so they never read your real folder.

### Chunking — `CHUNKING__*`

| Field | Default | What it does |
|---|---|---|
| `chunk_size` | `512` | Target chunk size for most files |
| `chunk_overlap` | `100` | Overlap between chunks. Calibrated ([ADR-018](../adr/018-balanced-retrieval-defaults.md)) — do not change casually |
| `markdown_chunk_size` | `1024` | Larger, because Markdown splits on headings |
| `markdown_heading_prepend` | `false` | Prepend the heading path to each chunk |
| `markdown_min_chunk_fraction` | `0.0` | Drop chunks below this fraction of the target |
| `strategy_fallback` | `markdown` | Strategy for file types we cannot identify. **Profile-owned**. Accepted values: inline `markdown`, or registered `code`, `config`, and `sentence` |

Known file types always use content-type dispatch — a `.py` file gets the code
splitter regardless of the fallback.

### Ingestion — `INGESTION__*`

| Field | Default | What it does |
|---|---|---|
| `embed_concurrency` | `4` | Parallel embedding requests. Machine-specific — lower it if the backend throttles |
| `embed_batch_size` | `100` | Documents per embedding call |
| `ingest_extensions` | the seven document extensions | File extensions ingestion collects. **Profile-owned** — the `codebase` profile adds source extensions. Env form is comma-separated (`.py,.ts`) or a JSON array string |
| `normalise_reader_output` (`INGESTION__NORMALISE_READER_OUTPUT`) | `true` | Remove reader markup (`<u>`, `<span>`, `<font>`, `<center>`, `<div>`, `<img>`, table styling) from PDF text before chunking, keeping every visible character. Part of the index identity: changing it reprocesses every source once. See [Ingestion guide](ingestion.md#reader-output-normalisation) |

### Embedding — `EMBEDDING__*`

Unit-norm guard for embedding vectors (see [ADR-053](../adr/053-embedding-norm-guard.md)). Dense
ranking treats L2 distance as cosine similarity; that is only rank-equivalent when vectors are
unit-normalised. The guard enforces the contract: fail-closed at ingest (a bad vector aborts the
file replacement before any write), warn-and-continue at query (results stay available, a
`norm_guard` diagnostic appears with diagnostics enabled).

The two `tokenizer_*` fields carry the Markdown chunking budget identity
([ADR-063](../adr/063-model-token-aware-markdown-chunking.md), promoted to packaged default
after experiment 25 passed all four frozen gates). The tokenizer is resolved from the local
Hugging Face cache only — it is independent of the embedding inference provider, and the
system never infers it from an Ollama, llama.cpp, or OpenRouter alias.

| Field | Default | What it does |
|---|---|---|
| `norm_guard_enabled` | `true` | Verify vector norms at both boundaries. Disabling is logged at startup |
| `norm_tolerance` | `0.001` | Maximum permitted `abs(norm − 1.0)`, inclusive. Must be positive |
| `tokenizer_model` | `Qwen/Qwen3-Embedding-4B` | Hugging Face identity used to budget Markdown chunks in real token units. Both fields empty → legacy character-budgeted path. Uncached revision → warning + the same legacy fallback |
| `tokenizer_revision` | `5cf2132abc99cad020ac570b19d031efec650f2b` | Pinned revision; must be present in the local cache for the model-token path to activate. Changing either field changes the source index identity, so Markdown sources re-chunk on the next ingest |
| `query_instruction` | empty | Instruction prefix applied to **queries only**. Empty preserves the raw query verbatim |

#### `EMBEDDING__QUERY_INSTRUCTION`

Some embedding models accept a task instruction that reshapes the query
vector. When this field is non-empty, the dense retrieval path embeds

```text
Instruct: <EMBEDDING__QUERY_INSTRUCTION>
Query: <the user's query>
```

instead of the raw query. Empty is the packaged default and preserves
today's behaviour exactly.

Four things to know before you set it:

1. **Queries only.** Document and chunk embeddings are never touched.
   You do not need to re-ingest anything to try an instruction, and you
   do not need to re-ingest anything to remove it.
2. **It changes query-vector semantics.** The same question maps to a
   different point in the embedding space, so results move. That is the
   point of the setting, and it is also its risk: an instruction that
   helps prose questions can dilute identifier tokens and hurt exact
   code lookups.
3. **Dense only.** The sparse (BM25) runner and the cross-encoder
   reranker receive the raw query, never the instructed one.
4. **The query-embedding cache keys on the prepared query.** Two
   identical raw queries under different instructions get separate cache
   entries and cannot collide.

Set it per model. A model that was not trained with instructions gains
nothing from one. Measure before you keep it: see the change record for
what the evaluated candidate instruction actually did on this workload.

### Retrieval — `RETRIEVAL__*`

| Field | Default | What it does |
|---|---|---|
| `top_k` | `10` | Results returned. **Profile-owned** |
| `similarity_threshold` | `0.0` | Minimum score to keep a result |
| `rerank_enabled` | `false` | Cross-encoder reranking. **Profile-owned** |
| `rerank_enabled_for_semantic` | `true` | Allow reranking on prose-like queries |
| `hard_technical_threshold` | `0.3` | Above this "technical" score, skip reranking |
| `rerank_fetch_multiplier` | `3` | Fetch `top_k × 3` candidates before reranking |
| `rerank_max_fetch` | `100` | Cap on that candidate pool |
| `rerank_model` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model |
| `rerank_backend` | `onnx` | Reranker inference backend (`onnx` or `torch`). `torch` requires `uv sync --extra torch`. See [ADR-038](../adr/038-pluggable-reranker-backend.md) |
| `hybrid_enabled` | `false` | Combine keyword and embedding search. **Profile-owned** |
| `hybrid_rrf_k` | `60` | Rank-fusion constant ([ADR-017](../adr/017-hybrid-retrieval-rrf.md)) |
| `hybrid_sparse_backend` | `bm25` | Sparse backend for hybrid search: `bm25`, `native`, or `auto`. Registry-owned validation at the composition boundary; unknown names fail startup listing `auto` plus the registered backends. See [Reranker](reranker.md#sparse-retrieval-backends-hybrid-search) |

### Answering — `ANSWER__*`

The grounded answering operation (`omrs answer`, the `answer_documents`
MCP tool, and the HTTP contract). It performs one or more completion calls at
query time. See [MCP tools](mcp-tools.md#answer_documents) and
[ADR-057](../adr/057-answering-is-additive-and-injected.md).

| Field | Default | What it does |
|---|---|---|
| `enabled` | `true` | Master switch. `false` makes the server model resolve to `None`; the answering tools then return an actionable error |
| `provider` | `ollama` | LLM provider, resolved through the same registry as metadata extraction. Unknown names fail startup. Besides `ollama`, `llamacpp` and `openrouter`, the registry holds `openai_compatible` and `anthropic` for answering only |
| `model` | `qwen3:4b` | Model tag, passed to the provider builder as an `answer_model` override so answering never reuses the small metadata-classification model |
| `timeout` | `120.0` | Seconds to wait for one completion round |
| `max_rounds` | `4` | Maximum COMPACT refinement rounds (1–8; the client-sampling path caps at 4). Later rounds widen the per-round budget up to a hard character ceiling (262,144); overflow evidence is dropped lowest-ranked first |
| `context_window` | `8192` | Per-round context budget in **characters** — a deterministic count, not a token estimate |
| `max_output_tokens` | `2048` | Reserved head-room for the model's reply inside one round's budget |
| `prefer_client_sampling` | `true` | Prefer the MCP client's model over the server model when the client advertises the sampling capability |
| `allow_legacy_sampling` | `true` | Allow the deprecated sampling back-channel only on a negotiated pre-2026-07-28 session. Never on a modern session |
| `verify_claims` | `false` | Opt-in claim-verification judge ([ADR-059](../adr/059-claim-verification-stage.md)). `true` adds one configured-judge call per cited prose sentence (~3.3 s P95 each on the tested GLM-5.3 cloud judge, experiment 20). An unavailable provider degrades to `verification_skipped`; the answer is never blocked |
| `verify_model` | `""` | Judge model. Empty derives it from the provider's default model (e.g. `OPENROUTER_LLM_MODEL`). The default cloud provider has no default model, so claim checks are skipped until you set one. Settings > Chat can set it; applies at once in `omrs web` |
| `verify_provider` | `cloud` | Judge provider. Aliases: `cloud` (or empty) resolves to the cloud backend, `local` to the local backend; anything else is a literal LLM-registry name. Unknown names fail startup. Settings > Chat can set it; applies at once in `omrs web` |
| `reasoning` | `""` | Reasoning level for the Chat model, for example `low`, `high` or `none`. Empty sends no reasoning field, so the provider default applies. 1 to 32 letters, digits, `-` and `_`. Settings > Chat can set it; applies at once in `omrs web` |
| `verify_reasoning` | `""` | Reasoning level for the claim check judge. Same rules as `reasoning`, set apart so the judge can think less than the Chat model. Settings > Chat can set it; applies at once in `omrs web` |

The three `verify_*` fields are the one answer-block group a profile
bundle may override per collection — a `documents` collection can opt
into the configured judge while a `codebase` collection stays
speed-first. The default judge provider is the cloud backend (the only
tested path); a local judge can be selected but is unmeasured.

In `omrs web`, Settings > Chat can save `provider` and `model` for Chat and for MCP clients of that server that cannot supply their own model. `ANSWER__PROVIDER` or `ANSWER__MODEL` in the environment or `.env` wins and locks the choice. A saved choice goes in `omrs.jsonc` as `answer.provider` and `answer.model`, and applies at once, with no restart. Metadata extraction keeps its own model. The judge has its own choice. The stdio MCP server and the CLI read the choice from `omrs.jsonc` when they start.

Settings > Chat also has a "Claim check judge" block. It saves `verify_provider` and `verify_model` together in `omrs.jsonc` as `answer.verify_provider` and `answer.verify_model`. Both apply at once in `omrs web`, with no restart. A hand edit of either key also applies at once. `ANSWER__VERIFY_PROVIDER` or `ANSWER__VERIFY_MODEL` in the environment or `.env` wins and locks the block. The page saves a registry name only, never the alias `cloud` or `local`. It refuses an empty model. The block sets the judge only. `verify_claims` stays a profile lever ("Check claims" in Studio), so the judge runs only for collections whose profile turns it on. A profile that sets its own judge overrides the saved choice. A cloud judge sends each claim and its cited passages off this machine.

Each provider sends the reasoning level in its own request field:

| Provider | Request field |
|---|---|
| `openrouter` | `reasoning: {"effort": <level>}` |
| `openai_compatible` | `reasoning_effort: <level>` |
| `ollama` | `think`: `low`, `medium` and `high` go as text, `none` sends `false`, any other level sends `true` |
| `llamacpp`, `anthropic` | Nothing. The level is saved, and Settings > Chat says the provider ignores it |

`ANSWER__REASONING` in the environment or `.env` wins and locks `answer.reasoning`. `ANSWER__VERIFY_REASONING` locks `answer.verify_reasoning`. Each level locks on its own; it does not lock the provider or model. A level is a server setting. A profile cannot change it.

With the defaults the judge cannot run. `verify_provider: cloud` resolves to OpenRouter, and `OPENROUTER_LLM_MODEL` is empty by default. An empty `verify_model` then leaves the judge with no model, and the answer reports `verification_skipped`. Set a judge model to turn claim checks on. Settings > Chat shows "Not set" and says that claim checks are skipped until you set one.
Environment variables still win over the profile:

```yaml
# config/profiles/documents.yaml — opt-in example (not enabled by default)
answer:
  verify_claims: true
  verify_model: ""          # empty = provider default model
  verify_provider: cloud
```

When verification runs, the result reports `verified: true` on success,
`unverified_claims` listing the failing claims on failure, or
`verification_skipped` with the reason when the judge could not run or had
no cited prose sentence to check. See
[MCP tools — claim verification](mcp-tools.md#claim-verification-optional).

### Metadata — `METADATA__*`

| Field | Default | What it does |
|---|---|---|
| `extraction_mode` | `llamaindex` | `disabled`, `keyword`, `local`, `llamaindex`, `ollama`, `llamacpp`, or `openrouter` |
| `keyword_rules` | — | JSON array of custom `{pattern, category}` rules |
| `taxonomy_mode` | `category` | `category` or `file_type`. **Profile-owned** |
| `ollama_classify_model` | `qwen3:0.6b` | Ollama model used for classification |
| `classify_max_attempts` | `3` | Maximum attempts **including** the initial request (all metadata LLM backends) |
| `classify_timeout` | `30.0` | Seconds per attempt (all metadata LLM backends) |
| `pipeline_timeout` | `180.0` | Seconds for the llamaindex pipeline (one attempt, three extractors per chunk) |
| `llamacpp_classify_timeout_override` | `None` | Per-provider override of `classify_timeout` for `llamacpp`. Falls back to the shared value when unset |
| `ollama_classify_timeout_override` | `None` | Per-provider override of `classify_timeout` for `ollama`. Falls back to the shared value when unset |
| `openrouter_classify_timeout_override` | `None` | Per-provider override of `classify_timeout` for `openrouter`. Falls back to the shared value when unset |
| `llamacpp_pipeline_timeout_override` | `None` | Per-provider override of `pipeline_timeout` for `llamacpp`. Falls back to the shared value when unset |
| `ollama_pipeline_timeout_override` | `None` | Per-provider override of `pipeline_timeout` for `ollama`. Falls back to the shared value when unset |
| `openrouter_pipeline_timeout_override` | `None` | Per-provider override of `pipeline_timeout` for `openrouter`. Falls back to the shared value when unset |

Set `extraction_mode=disabled` to skip classification entirely. This avoids
classification and category metadata. Details: [Metadata extraction](metadata-extraction.md),
including the six per-provider timeout overrides above and how
degradation from the configured mode is reported in the ingestion result.

### PDF reading

| Variable | Default | What it does |
|---|---|---|
| `PDF_READER` | `pdf_inspector` | `auto`, `pypdf`, `pypdfium2`, `liteparse`, or `pdf_inspector` |
| `LITEPARSE_OCR_ENABLED` | `false` | OCR for scanned PDFs |
| `LITEPARSE_NUM_WORKERS` | — | Parallel workers |

The packaged default `pdf_inspector` is a base dependency
([ADR-050](../adr/050-configure-pdf-inspector-as-default-reader.md)).
`auto` keeps the LiteParse → pypdfium2 → pypdf probe order. A configured
reader that is not importable logs an error and falls back to pypdf. Tests
pin `pypdf` for determinism.

`PDF_READER` is the host default. A Read document step in a pipeline can
choose another installed reader for that step only. The step setting does
not change the environment or the other pipelines. `auto` is a host policy
and is not a step choice. A step that names a reader whose package is not
installed fails validation with `option_unavailable`, and no node runs. See
[Pipeline graphs](pipelines.md#pdf-reader-on-the-read-document-step).

Each reader declares the text format it emits and whether it provides
page-level provenance. Downstream consumers route on the declared format
instead of the file extension, and search results carry `page_label` only
when the reader can observe pages. The registry descriptor
(`registry.describe(name)`) exposes the same matrix — the table below and
the registry must stay in agreement (a guard test enforces this).

| Reader | Declared text format | Page provenance |
| --- | --- | --- |
| `pdf_inspector` | `markdown` | No — one document per file; `page_count` in metadata instead |
| `liteparse` | `plain` | Yes — string `page_label` alongside the integer `page` |
| `pypdf` | `plain` | Yes |
| `pypdfium2` | `plain` | Yes |

### OCR fallback and isolated engines

The calibrated routing gate — which PDFs deserve OCR:

| Variable | Default | What it does |
|---|---|---|
| `OCR_FALLBACK_ENABLED` | `true` | Master switch. Off means no PDF reaches the worker |
| `OCR_FALLBACK_MIN_CONFIDENCE` | `0.5` | Confidence floor for text-based PDFs. `0.0` is the never-trigger sentinel |
| `OCR_FALLBACK_PAGE_FRACTION` | `0.10` | Flagged-page proportion that triggers OCR. `0.0` is the never-trigger sentinel |

Engine routes and operation:

| Variable | Default | What it does |
|---|---|---|
| `OCR_WORKERS_DIR` | empty | Absolute path to `ocr-workers`. Empty disables folder-based routes |
| `OCR_ENGINE_PRIMARY` | `dots-mocr` | Engine selected for every worker request |
| `OCR_ENGINE_FALLBACK` | `paddleocr-vl` | Engine selected when the primary is unavailable before dispatch. Empty disables this route |
| `OCR_WORKER_COMMAND` | empty | Explicit command overriding the primary route only. Empty uses the engine settings |
| `OCR_WORKER_ENV_DIR` | empty | Working directory for the explicit command |
| `OCR_WORKER_REQUEST_TIMEOUT` | `300.0` | Minimum timeout in seconds for one parse response |
| `OCR_WORKER_SECONDS_PER_PAGE` | `120.0` | Per-page timeout allowance in seconds |
| `OCR_MATHS_ROUTING_ENABLED` | `true` | Detect maths fonts on the pdf-inspector path and route affected pages |
| `OCR_MATHS_PAGE_FRACTION` | `0.10` | Maths-page fraction that routes a whole document. Range 0.0–1.0; `0.0` disables this condition |

These settings are flat, top-level fields beside `PDF_READER`, resolved
once at the composition root and injected. The timeout is
`max(OCR_WORKER_REQUEST_TIMEOUT, requested_pages * OCR_WORKER_SECONDS_PER_PAGE)`.
A 14-page request gets 1,680 seconds with the defaults.

An unknown or unprovisioned engine is unavailable. If both routes are
unavailable, the PDF keeps its available text. A worker failure after
dispatch fails that file without retrying on the other engine.

Maths pages skip local OCR under `OCR_ROUTING_UNIT=page`. Under
`document`, the maths fraction adds a condition to the existing gate.
`OCR_MATHS_PAGE_FRACTION=0.0` affects only the document unit. Use
`OCR_MATHS_ROUTING_ENABLED=false` to disable maths routing for either unit.
The master switch `OCR_FALLBACK_ENABLED=false` disables all OCR routing.

Each engine has its own environment under `ocr-workers/engines/<engine>`.
dots-mocr needs explicit model-licence acceptance. Over 257 pages,
Experiment 37 measured a peak of about 22 GiB of Apple Silicon GPU memory
through Metal Performance Shaders (MPS). One-page smoke tests showed only
7–9.5 GiB, so plan for the larger figure. PaddleOCR-VL peaked at about
15 GiB on CPU in the same run. CPU execution is slower. Set
`OCR_ENGINE_PRIMARY=paddleocr-vl` on machines with limited memory.
PyTorch and Paddle packages stay outside the OMRS environment.

**Migration:** re-provision the required engines, set `OCR_WORKERS_DIR`,
and clear `OCR_WORKER_COMMAND` to use named routes. An existing explicit
command continues to override the primary, even when
`OCR_ENGINE_PRIMARY=dots-mocr`. Update its executable, module and working
directory if retaining that override. See
[provisioning and migration](ingestion.md#provision-the-engines).

`OMRS_OCR_MODEL_CACHE` is a process-level variable read by the worker core.
When set, engine `<name>` uses `$OMRS_OCR_MODEL_CACHE/<name>/`; otherwise
it uses its own `.model-cache/` directory. Set it consistently for
provisioning and worker execution to preserve weights outside worktrees.

### OCR routing unit and the local OCR tier

The unit that OCR is decided on, and the local tier that runs first
under it (change `page-level-ocr-routing`,
[ADR-069](../adr/069-page-level-ocr-routing-and-the-pdfium-runtime.md)):

| Variable | Default | What it does |
|---|---|---|
| `OCR_ROUTING_UNIT` | `document` | `document` keeps whole-PDF routing. `page` (opt-in) OCRs only flagged pages |
| `OCR_LOCAL_MIN_CONFIDENCE` | `0.9` | Below this reported confidence a page escalates to the worker. Unreported confidence escalates too |
| `OCR_LOCAL_OFFLINE` | `false` | `true` forbids the model download; a missing cached model then degrades |
| `OCR_LOCAL_MODEL_DIRECTORY` | empty | Artifact directory (`<name>/<revision>` leaf) to load the model from. Empty means the library's default cache |

The default cut is 0.9, supported by Experiments 33, 37 and 39. On the
399 flagged pages re-scored in Experiment 39, 59.6% escalate and 2.5% of
kept pages have body recall below 0.5. Explicit operator values still apply.
Page-unit installs using the previous 0.8 default re-index once on their
next ingest. The `document` unit keeps its identity for this cut change.

These four names are **flat on purpose**. `pydantic-settings` resolves
its `__` delimiter only into nested settings blocks, and the OCR
fields are top-level — a nested spelling such as
`OCR__ROUTING_UNIT` matches nothing and is discarded in silence. The
never-shipped nested spellings are trapped in `config/legacy.py` with
an error naming the flat replacement, so a typo cannot pass unnoticed.

An invalid `OCR_ROUTING_UNIT` raises at startup rather than warning
and falling back: the unit feeds the index identity, and a fallback
would index a corpus under a unit nobody chose.

The local tier needs two process-level libraries that pdf-inspector
loads by environment variable: `PDFIUM_LIB_PATH` (LiteParse ships
`libpdfium.dylib` in its package directory) and `ORT_DYLIB_PATH`
(ONNX Runtime ships its dylib in `capi/`). Both may live in `.env`:
the composition root runs `load_dotenv()` before any read, which
exports them into the process environment the Rust library sees. On
first use the model (`pp-ocrv6-small@oar-ocr-v0.7.0`, about 31 MB)
downloads unless `OCR_LOCAL_OFFLINE=true` and a cache is present. A
missing library or model never fails a file: flagged pages keep
native text and count unresolved, with one warning naming what is
missing.

Identity consequences: an install that switches to `page` reindexes
its sources once — a different engine reads the pages — and the
payload additionally records the escalation threshold and the
resolved model identity. The modular-engine upgrade separately changes
identity for every source, including `document` installs: both route
fingerprints and the maths-routing settings participate. Sources
reprocess on their next ingestion; reading an index does not rebuild it.

The packaged default is the promoted gate validated by Experiment 29
([ADR-065](../adr/065-ocr-fallback-gate-promoted-to-packaged-default.md)):
enabled at `0.5` confidence and `0.10` page fraction, shipped together —
enabling the flag while leaving the thresholds at `0.0` silently misses
threshold-flagged documents. With no worker provisioned, an OCR-required
PDF keeps its partial extraction and the batch continues with an
actionable warning. Set `OCR_FALLBACK_ENABLED=false` to disable routing
entirely. For classification-only routing under `document`, set both
gate thresholds to `0.0` and disable maths routing. Only `scanned` and
`image_based` PDFs then route.

Full behaviour, including provisioning and OCR metadata, is in
[the ingestion guide](ingestion.md#ocr-fallback-for-scanned-pdfs).

### Document backend

| Variable | Default | What it does |
|---|---|---|
| `DOCUMENT_BACKEND` | `local` | `local` or `azure`. Unrecognised values fail startup |
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | — | Azure endpoint URL |
| `AZURE_DOC_INTELLIGENCE_KEY` | — | Azure key |
| `AZURE_DOC_INTELLIGENCE_MODEL` | `prebuilt-layout` | Azure model |

Azure is opt-in ([ADR-024](../adr/024-dual-deployment-modes.md)) and
degrades to local parsing when credentials are missing or unreachable,
or when the optional SDK is absent. Each warning names the missing
piece: the `AZURE_DOC_INTELLIGENCE_ENDPOINT` /
`AZURE_DOC_INTELLIGENCE_KEY` variables, or the
`azure-ai-documentintelligence` package with `uv sync --extra azure`.
Azure reads `.pdf`, `.docx`, and `.doc` only; every other file type
goes through the local backend whatever `DOCUMENT_BACKEND` is set to.
An unrecognised `DOCUMENT_BACKEND` value (not `local` or `azure`) fails
startup rather than silently falling back. The accepted names come from
the document-backend registry instead of a fixed config-time list.

### Codebase map

| Variable | Default | What it does |
|---|---|---|
| `MAGIKA_BINARY` | `magika` | File-type detection binary |
| `CODEBASE_MAP_CACHE_DIR` | `.opencode` | Cache location |
| `CODEBASE_MAP_MAX_FILES` | `5000` | File limit |
| `CODEBASE_MAP_MAX_DEPTH` | `10` | Directory depth limit |
| `DOC_SIMILARITY_THRESHOLD` | `0.85` | Similarity edge cutoff. Not yet calibrated |

The cache key is the git commit hash plus an owner context. The owner context
holds the map settings above (except the cache location), the community
settings, and the store's durable data version for `documents`. A cache with a
different or missing owner context is a miss, and the map rebuilds. If the
path is not a git repository, or the store has no durable data version, the
map rebuilds on every call.

### Community detection

Both graph subsystems, the codebase graph and the document similarity graph,
use the same configured strategy and seed.

| Variable | Default | What it does |
|---|---|---|
| `COMMUNITY_ALGORITHM` | `louvain` | `louvain` or `leiden`. Unknown names fail startup and list the available strategies |
| `COMMUNITY_SEED` | `0` | Seed for algorithm randomness. `0` keeps partitions deterministic |

`COMMUNITY_ALGORITHM` and `COMMUNITY_SEED` are cross-cutting, so their
environment variable names are flat. An empty value
(`COMMUNITY_ALGORITHM=`) resets to `louvain`.

There is no `auto`. Whether an optional package is installed must not change
graph output silently, so the algorithm is always explicit.

**Leiden.** `leiden` requires the optional `community-leiden` extra:

```bash
uv sync --extra community-leiden
```

Setting `COMMUNITY_ALGORITHM=leiden` without the extra fails startup with the
installation instruction above. There is no silent fallback to `louvain`: an
explicit algorithm selection is an operator contract. See
[ADR-044](../adr/044-pluggable-community-detection.md).

---

## Web workspace settings

`omrs web` has one setting of its own in `.env`, `WEB_MAX_UPLOAD_MIB`. It also reads the engine settings that other commands read. Its other options are command-line flags only: `--workspace`, `--port`, `--host`, `--root` and `--experiment-root`. The server builds its Engine from the same settings sources as the other commands. See [Web workspace](web-workspace.md).

| Variable | Default | Use |
|---|---|---|
| `WEB_MAX_UPLOAD_MIB` | unset | Per-file upload limit in whole MiB, 1 to 2048. Same as `--max-upload-mib`. |

The server uses the first upload limit it finds in this order:

1. `--max-upload-mib`.
2. `WEB_MAX_UPLOAD_MIB`, from the environment or `.env`.
3. `web_max_upload_mib` in `omrs.jsonc`, which the page writes from Settings > Workspace.
4. 50 MiB.

A launch value (step 1 or 2) locks the limit for that run. Settings then shows the limit and cannot change it. A hand edit of `web_max_upload_mib` in `omrs.jsonc` applies to the next upload. Any other value stops `omrs web` with exit code 2 before it binds a port. The name is flat, because `omrs web` options are not engine settings.

### Provider and Chat values

`omrs web` also lets you save LLM provider addresses, API keys, the Chat model and the claim check judge in Settings. The order is environment, `.env`, `omrs.jsonc`, the key file, then the default. Only the environment and `.env` lock the field (see [User config folder](#user-config-folder)). A saved key lives in the system keychain only, and `omrs.jsonc` holds a `keychain://` reference to it. A saved value applies at once with no restart. Details: [Providers](#providers), [Answering](#answering--answer__) and [Web workspace](web-workspace.md#provider-settings).

### Document reading values

Settings > Document reading edits nine keys in `omrs.jsonc`: `pdf_reader`, `ocr_fallback_enabled`, `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction`, `ocr_routing_unit`, `ocr_engine_primary`, `ocr_engine_fallback`, `ocr_maths_routing_enabled` and `ocr_maths_page_fraction`. See [PDF reading](#pdf-reading) and [OCR fallback and isolated engines](#ocr-fallback-and-isolated-engines).

- Each key applies after a restart only. Until then, the row shows the value in force and the saved value with "Restart to apply".
- Each key is part of the [index identity](#index-identity-and-re-ingestion). After the restart, the next ingest can read existing files again.
- A key in the environment or `.env` is locked. The row tells you which variable to remove.
- The page refuses a PDF reader that is not installed. It allows an OCR engine name that is valid but not provisioned yet, and marks it "Not provisioned".
- The page refuses blank text. "Use default" removes the key from the file.
- These checks run only when the page saves. At startup, an unknown `pdf_reader` from any source still logs a warning and falls back to `auto`.

The page cannot set "no fallback engine" yet. To turn the fallback route off, set `OCR_ENGINE_FALLBACK=` in the environment or `.env`. A blank `"ocr_engine_fallback": ""` in `omrs.jsonc` does not turn it off: the file reader treats blank text as not set, and the row shows "Not set".

---

## Index identity and re-ingestion

OMRS skips a source it has already indexed when the file bytes and the
index identity both match. Change the identity and every affected source
re-ingests on the next run, even if not one byte of the file changed.

These settings are part of the index identity:

| What | Why it counts |
| --- | --- |
| `PDF_READER`, as the **resolved** reader | It decides which reader produced the text. The resolved name is recorded, so `auto` counts as the reader it resolved to, and an uninstalled choice counts as `pypdf` |
| `EMBEDDING__TOKENIZER_MODEL` and `EMBEDDING__TOKENIZER_REVISION` | They set the Markdown token budget, so chunk boundaries move |
| The **resolved** Markdown splitter | Model-token-aware or legacy fallback. The resolved value is recorded, not the configured one, so a corpus chunked under the fallback does not stay "matching" forever once the tokenizer becomes loadable |
| `OCR_FALLBACK_ENABLED`, `OCR_FALLBACK_MIN_CONFIDENCE`, `OCR_FALLBACK_PAGE_FRACTION` | They decide which reader produced the text |
| `OCR_ROUTING_UNIT` and, under `page`, the escalation threshold and the resolved local model identity | They decide which engine reads each page. These local-tier fields are recorded only when the unit is not `document` |
| Both resolved OCR route fingerprints | Availability, protocol version, every package and exact version, pipeline identity and revision, model identity and revision, output-schema identity and version, and backend identifier |
| `OCR_MATHS_ROUTING_ENABLED`, `OCR_MATHS_PAGE_FRACTION` and the detector version | They decide whether maths pages reach OCR; recorded for every source |

Two consequences worth planning for:

1. **Provisioning either engine changes identity for previously indexed
   sources, including non-PDF sources.** Both route fingerprints belong
   to the shared identity payload. A previously unavailable route
   becoming available causes re-ingestion, including when it is the
   fallback route. Package, model, pipeline, protocol and output-schema
   changes have the same effect. Provision the required engines before
   building the corpus, or plan for re-ingestion.
2. **`EMBEDDING__QUERY_INSTRUCTION` deliberately does NOT count.** It
   changes query vectors only, never stored ones, so it is excluded from
   the identity on purpose. Set it, change it, or clear it freely: a
   byte-identical source still reports `skipped_unchanged`.

Transient process details — process ids, temporary paths, timings — are
excluded from the fingerprint. A missing, unusable, malformed, or
incompatible worker collapses to ONE stable unavailable fingerprint, so
"the worker is not installed" is a single identity rather than a
different one for every failure mode.

## How settings reach the code

Worth understanding if you are changing anything.

`config/` works out the values and produces a `Settings` object. It builds
nothing else.

`compose.py` takes those settings and constructs the real objects — embedder,
vector store, reranker. It is the only place that calls `get_settings()`.

Core operations receive a frozen `EffectiveSettings` as an argument. There is
no global to read and nothing to patch. Two searches running at once each hold
their own settings.

For tests, this means injecting rather than patching:

```python
def test_something(effective_settings):
    settings = effective_settings(top_k=20)
    results = search("query", effective_settings=settings)
```

More in [Architecture](architecture.md) and
[ADR-031](../adr/031-three-layer-config-compose-di.md).

---

## Adding a setting

**Belongs to one area** (chunking, ingestion, retrieval, metadata):

1. Add the field to that area's `settings.py`
2. Add it to `defaults.yaml` under the matching block

**Cross-cutting:**

1. Add the field to `Settings` in `config/__init__.py`
2. Add it to `defaults.yaml` at the top level

A test checks `defaults.yaml` agrees with the model defaults, so the two cannot
drift apart. If they disagree, that test tells you.
