## Context

The RAG MCP server currently operates on a single ChromaDB collection named `documents`. All ingested content — research papers, code documentation, philosophy notes, marketing materials — lands in the same vector space. While semantic search works regardless of content type, users cannot scope searches to a specific domain or isolate content types. The existing `COLLECTION_NAME` env var is a single global, and there is no metadata on chunks beyond file path.

ChromaDB natively supports multiple named collections within the same `chroma_db` directory. Each collection maintains its own embedding dimension (same model, same dim — no mismatch risk) and metadata schema. The challenge is threading collection selection through every layer of the existing pipeline.

Key constraints:
- **No breaking changes** — existing `rag-mcp ingest ./docs` must keep working unchanged
- **No new Python dependencies** — keyword mode uses `re` (stdlib), Ollama mode uses `requests` (already transitively depended via httpx)
- **No PyTorch** — ONNX Runtime only, per project boundaries
- **British English** — all docs, comments, log messages

## Goals / Non-Goals

**Goals:**
- Allow users to specify which collection documents are ingested into (`--collection research`)
- Allow users to search a specific collection (`--collection research`)
- List all available collections (`rag-mcp list-collections`)
- Auto-categorise documents during ingestion using a configurable extraction mode
- Store extracted metadata as ChromaDB metadata on every chunk
- Allow search filtering by metadata fields (`--filter '{"category":"AI"}'`)
- Keep the default behaviour (no `--collection` flag) unchanged

**Non-Goals:**
- RouterQueryEngine or LLM-based query routing (user explicitly chooses collection)
- Multi-collection cross-search (querying two collections at once)
- Persistent metadata across chunks of the same file (metadata is set once per file, attached to all chunks)
- Changing the embedding model per collection (all collections share the same model from `config.py`)
- User-configurable metadata schema beyond `category` (v1 — single tag per document)
- LlamaIndex MetadataExtractor full integration (stubbed for future, not wired in v1)

## Decisions

### 1. Collection routing: parameter threading (not global singleton)

**Choice**: Add `collection_name: str = "documents"` parameter to every function in the ingestion/retrieval/watcher chain, defaulting to the current `COLLECTION_NAME` default.

**Alternatives considered**:
- *`Settings.collection_name` global (like `Settings.embed_model`)*: Rejected — global state conflicts with the MCP server's concurrent-request model. Two MCP clients could set different collections and stomp on each other.
- *Env var per command*: Rejected — requires shell-level config switching, which is worse UX than a `--collection` flag.

**Rationale**: Threading a parameter through the call chain is verbose but gives the safest concurrency guarantee — each call can target a different collection independently. The default `"documents"` ensures backward compatibility.

### 2. Collection-aware ChromaDB access: dynamic collection lookup

**Choice**: Change `_get_chroma_collection()` from taking no arguments to accepting `collection_name: str = "documents"`. No global state mutation.

**Changed signature**:
```python
def _get_chroma_collection(collection_name: str = "documents") -> chromadb.Collection:
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return db.get_or_create_collection(collection_name)
```

**Rationale**: ChromaDB's `get_or_create_collection()` is idempotent — first call creates, subsequent calls return existing. No migration needed. The `PersistentClient` is cheap to construct (connects to existing SQLite file).

### 3. Metadata extraction: toggleable, tiered fallback

**Choice**: Single env var `METADATA_EXTRACTION_MODE` with four values controlling the extraction strategy. A new `metadata_extractor.py` module encapsulates all extraction logic behind a single `extract_metadata(file_text, file_name) -> dict` function.

| Mode         | What happens                                       | Requires                       |
| ------------ | -------------------------------------------------- | ------------------------------ |
| `disabled`     | Returns `{}` — no metadata                             | Nothing                        |
| `keyword`      | Regex pattern matching against user-defined rules  | Nothing (stdlib `re`)            |
| `ollama`       | Single Ollama chat API call per file               | Ollama serving a chat model    |
| `llamaindex`   | LlamaIndex `MetadataExtractor` pipeline (stubbed)    | Ollama serving a chat model + LlamaIndex LLM config |

**Alternatives considered**:
- *Always use Ollama*: Rejected — adds 2s per file for users who don't have a chat model or don't want the overhead.
- *Always use keyword matching*: Rejected — less accurate than an SLM for unexpected content types.
- *Separate toggle for each mode*: Rejected — over-engineered. One enum is sufficient.

**Rationale**: The `keyword` mode is the sensible default (zero deps, instant). The `ollama` mode upgrades accuracy for users who have a chat model. The `llamaindex` mode is stubbed for future — it requires configuring `Settings.llm`, which is a larger change.

### 4. Keyword rules: env-var overridable JSON

**Choice**: Default keyword rules are hardcoded in `metadata_extractor.py`. Users can override by setting `METADATA_KEYWORD_RULES` to a JSON string of `[{"pattern": "...", "category": "..."}, ...]` in `.env`.

Default rules (cover the user's known domains):
```
AI:          attention|transformer|token|embedding|llm|rag|neural|deep.learning
Philosophy:  mantiq|logic|reasoning|ontology|epistemology|ghazali|usul
Biology:     crispr|genome|protein|cell|biology|cancer|gene
Marketing:   marketing|seo|campaign|brand|pricing|funnel|conversion
Programming: javascript|python|rust|api|frontend|backend|compiler
```

**Alternatives considered**:
- *YAML config file*: Rejected — env var is simpler and matches the project's existing `.env`-only pattern.
- *Configurable via CLI*: Rejected — keyword rules are set once, not per-invocation.

### 5. Metadata attachment point: file level, after loading

**Choice**: In `_read_and_chunk_file()`, after `SimpleDirectoryReader.load_data()`, extract the full text and call `extract_metadata()` once. Attach the resulting dict to every node's `.metadata` before returning.

```
file_text = documents[0].text
doc_metadata = extract_metadata(file_text, file_path.name)
for node in nodes:
    node.metadata.update(doc_metadata)
```

**Rationale**: One extraction per file (not per chunk) minimises overhead. The same category applies to all chunks of a single document. ChromaDB stores `.metadata` alongside each vector embryo automatically.

### 6. Search filtering: ChromaDB `where` clause passthrough

**Choice**: Add optional `metadata_filter: dict | None` parameter to `search_documents()` in `retrieval.py`. Passed directly to ChromaDB's `collection.query(where=...)` for server-side filtering.

**Rationale**: ChromaDB already supports `where` filtering on metadata fields. No need for post-query client-side filtering. The filter syntax is ChromaDB's native `{"field": {"$eq": "value"}}` or simpler `{"field": "value"}`.

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Collection dimension mismatch** | Low | High | All collections use the same embedding model from `config.py` — same dimension guaranteed. Risk only if user changes `EMBED_MODEL` between ingest and search, which already breaks single-collection mode. |
| **Ollama classification slow for large batches** | Medium | Medium | One Ollama call per file adds ~2s per file. For 100 files, that's ~3 minutes. Mitigation: `keyword` mode is the default (instant). Users opt into `ollama` mode explicitly. |
| **Ollama chat model not pulled** | Medium | Low | If `ollama` mode is selected but no chat model exists, the Ollama call fails gracefully → returns `{"category": "uncategorised"}` and logs a warning. |
| **Keyword rules too narrow** | Medium | Low | Users can override rules via `METADATA_KEYWORD_RULES` env var. The default set covers the user's known domains. |
| **ChromaDB metadata migration** | None | N/A | New fields are additive — existing chunks without `category` metadata remain searchable (just not filterable by that field). No migration needed. |

## Resolved Questions

| Question | Decision |
|----------|----------|
| Watcher `--collection` default | `"documents"`. When no `--collection` flag is passed, the watcher only watches and auto-ingests into the `"documents"` collection. To watch Zotero papers, explicitly run `rag-mcp watch ~/Zotero/storage --collection research`. |
| Keyword rules | The 5 default categories (AI, Philosophy, Biology, Marketing, Programming) are approved. Users who know the content domain at ingest time can set `--collection research` explicitly; metadata tags are auto-detected within the collection based on `METADATA_EXTRACTION_MODE`. |
| `list-collections` with counts | Yes — include per-collection document count and chunk count in the output. ChromaDB's `collection.count()` provides this cheaply. |
