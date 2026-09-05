# Library Usage

The public `omrg` library API for use in your own Python code.

---

## Import

```python
from omrg import Engine, EffectiveSettings
```

Importing the package constructs nothing. No settings are resolved, no
providers or stores are built, and no process-global state is mutated.

`__version__` comes from package metadata, not a hard-coded constant:

```python
import omrg

print(omrg.__version__)  # e.g. "2.3.0"
```

---

## Engine construction

An `Engine` owns its vector store, embedder, reranker and settings for
its own lifetime. Two engines with different configurations coexist in
one process without interfering.

### From the environment

The simplest path reads `.env` and `defaults.yaml`. It delegates to
`compose.build_engine()` and installs nothing as a process default:

```python
from omrg import Engine

engine = Engine.from_environment()
```

### With explicit dependencies

For tests or multi-engine setups, pass already-composed dependencies:

```python
from omrg import Engine, EffectiveSettings
from omrg.core.vectordb.lancedb import LanceVectorStore

settings = EffectiveSettings(...)
store = LanceVectorStore(uri="/path/to/lancedb")
engine = Engine(settings, store=store, embed_model=my_embedder)
```

The constructor accepts the dependencies and constructs nothing itself.
See [Configuration](configuration.md) for the full settings schema.

---

## Operations

**`ingest` (async)** — index a file or directory into the store. Returns
a result dict. `chunk_size` and `chunk_overlap` are optional overrides:

```python
result = await engine.ingest("./docs", collection_name="documents")
```

**`search` (sync)** — run a semantic similarity search. Each hit is a
dict with score, text and metadata. Optional arguments: `rerank`,
`hybrid`, `metadata_filter`, `include_diagnostics`:

```python
hits = engine.search("how does caching work?", top_k=10)
```

**`answer` (async)** — answer a question from retrieved evidence with
verifiable citations. Returns a dict with the answer text, cited sources
and diagnostics:

```python
result = await engine.answer("what is the reranker threshold?")
```

**`list_collections` (sync)** — return every collection name in the
store. **`delete_collection` (sync)** — permanently delete a collection
and all of its rows. This operation cannot be undone:

```python
names = engine.list_collections()
engine.delete_collection("old_data")
```

**`close` (sync)** — release the engine's resources. See
[Lifecycle](#lifecycle) below.

---

## Two engines in one process

Construct two engines with different stores and embedders. They do not share state:

```python
from omrg import Engine, EffectiveSettings
from omrg.core.vectordb.lancedb import LanceVectorStore

docs = Engine(EffectiveSettings(...), store=LanceVectorStore(uri="./docs.lance"), embed_model=doc_embedder)
code = Engine(EffectiveSettings(...), store=LanceVectorStore(uri="./code.lance"), embed_model=code_embedder)
```

Each engine owns its own store, embedder and query cache. Ingesting into
one does not affect the other. Searches on one see only its own data.

---

## Lifecycle

Call `close()` to release an engine's resources:

```python
engine.close()
```

`close()` performs three actions:

1. Drops the engine-owned query embedding cache.
2. Evicts only the BM25 cache entries in this store's identity namespace.
3. Closes the owned store.

Closing one engine does not affect another. The process-wide ingestion
lock is never touched. After `close()`, further operations on that
engine are not valid.

---

## Settings injection

`EffectiveSettings` is passed explicitly to the engine, not read from a
global. The engine stores the settings you give it. Operations thread
the resolved settings down to `core/` as a parameter — nothing in
`core/` or `integrations/` imports a settings singleton.

You control configuration at construction time. Two engines with
different settings coexist because each holds its own copy.
`EffectiveSettings` and all of its blocks are frozen; mutation raises a
`ValidationError`. To change behaviour, construct new settings and a new
engine. For the full settings schema and precedence rules, see
[Configuration](configuration.md).
