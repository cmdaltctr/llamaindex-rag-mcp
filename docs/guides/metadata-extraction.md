# Metadata Extraction

During ingestion, the server can automatically extract metadata from documents and attach it to every chunk as ChromaDB metadata. This metadata can then be used to **filter search results** — for example, searching only chunks categorised as `"AI"` or `"Biology"`.

Extraction runs **once per file** (not per chunk), so overhead is O(files), not O(chunks).

## Modes

Set `METADATA__EXTRACTION_MODE` in `.env`:

| Mode                | What it does                                                                                                                                                                                   | Speed       | Status |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | ------ |
| `keyword` (default) | Regex pattern matching against built-in rules. Scans the first ~2000 chars for keywords.                                                                                                       | Instant     | Ready  |
| `local`             | Sends the first 3000 chars to a lightweight chat model via the configured `METADATA_LLM_PROVIDER` (default `local` + `LOCAL_BACKEND=llamacpp`). Returns `category`, `keywords`, and `summary`. | ~2s/file    | Ready  |
| `llamaindex`        | Uses LlamaIndex's `IngestionPipeline` with `TitleExtractor`, `KeywordExtractor`, and `SummaryExtractor`. Per-chunk enrichment. Requires `uv sync --extra metadata`.                            | ~5–30s/file | Ready  |
| `disabled`          | No metadata extracted. No `category` field written to chunks.                                                                                                                                  | N/A         | Ready  |

```bash
# In .env
METADATA__EXTRACTION_MODE=keyword   # default
METADATA__EXTRACTION_MODE=local
METADATA__EXTRACTION_MODE=disabled

# Or inline for a single run
METADATA__EXTRACTION_MODE=disabled uv run rag-mcp ingest /path/to/docs/
```

## Local mode

Uses a **separate chat model** (not the embedding model) set via `METADATA_LLM_PROVIDER` (default `local`). The sub-provider is selected by `LOCAL_BACKEND` (default `llamacpp`) or `CLOUD_BACKEND` (default `openrouter`).

When `METADATA_LLM_PROVIDER=local` and `LOCAL_BACKEND=ollama`, the model is configured via `METADATA__OLLAMA_CLASSIFY_MODEL` (default `qwen3:0.6b`). Pull it first:

```bash
ollama pull qwen3:0.6b
```

This tiny 0.6B model is purpose-built for fast classification. It only sees the first 2000 characters per file — good enough for category classification, not comprehensive content extraction.

> **Other sub-providers:** When `LOCAL_BACKEND=llamacpp`, this mode routes to llama.cpp's `/v1/chat/completions` endpoint using `LLAMACPP_CHAT_URL` and `LLAMACPP_CHAT_MODEL`. When `METADATA_LLM_PROVIDER=cloud` and `CLOUD_BACKEND=openrouter`, it routes to OpenRouter's chat API using `OPENROUTER_API_KEY` and `OPENROUTER_LLM_MODEL`. See [Providers](providers.md) for setup.

Rich metadata output example:

```json
{ "category": "ai", "keywords": ["transformer", "attention"], "summary": "..." }
```

## Built-in keyword rules

| Category    | Keywords matched (case-insensitive)                                                       |
| ----------- | ----------------------------------------------------------------------------------------- |
| AI          | `attention`, `transformer`, `token`, `embedding`, `llm`, `rag`, `neural`, `deep learning` |
| Philosophy  | `mantiq`, `logic`, `reasoning`, `ontology`, `epistemology`, `ghazali`, `usul`             |
| Biology     | `crispr`, `genome`, `protein`, `cell`, `biology`, `cancer`, `gene`                        |
| Marketing   | `marketing`, `seo`, `campaign`, `brand`, `pricing`, `funnel`, `conversion`                |
| Programming | `javascript`, `python`, `rust`, `api`, `frontend`, `backend`, `compiler`                  |

If no keywords match, the category is `"uncategorised"`.

## Custom keyword rules

Override the built-in rules entirely by setting `METADATA__KEYWORD_RULES` in `.env` to a JSON string:

```bash
METADATA__KEYWORD_RULES='[{"pattern": "f1|grand.?prix|motorsport", "category": "Motorsport"}, {"pattern": "football|goal|stadium", "category": "Sport"}]'
```

## Timeouts

Two shared timeouts govern LLM-backed extraction:

| Setting                       | Default | Governs                                                                                          |
| ------------------------------ | ------- | -------------------------------------------------------------------------------------------------- |
| `METADATA__CLASSIFY_TIMEOUT`   | `30.0`s | Per-attempt HTTP timeout for the `local` mode's direct-chat classification call (retried up to `METADATA__CLASSIFY_MAX_ATTEMPTS` times). |
| `METADATA__PIPELINE_TIMEOUT`   | `180.0`s | Timeout for the `llamaindex` mode's `IngestionPipeline` run (three extractors per chunk, one attempt, no retry). |

Each also has three optional **per-provider overrides**, all `None` (unset) by default — an unset override falls back to the shared value above, so behaviour is unchanged until you set one:

```bash
METADATA__LLAMACPP_CLASSIFY_TIMEOUT=45.0
METADATA__OLLAMA_CLASSIFY_TIMEOUT=45.0
METADATA__OPENROUTER_CLASSIFY_TIMEOUT=45.0
METADATA__LLAMACPP_PIPELINE_TIMEOUT=300.0
METADATA__OLLAMA_PIPELINE_TIMEOUT=300.0
METADATA__OPENROUTER_PIPELINE_TIMEOUT=300.0
```

Use these when different machines run different backends at different speeds — e.g. a slow local box wants a longer `llamacpp` pipeline budget without loosening the fast-fail classify budget everywhere else. `LOCAL_BACKEND` (`llamacpp`/`ollama`) or `CLOUD_BACKEND` (`openrouter`) selects which override, if any, applies at runtime.

## Degradation reporting

If the LLM call backing `llamaindex` or `local` mode fails — the required package isn't installed, the backend is unreachable, a call times out, or the response can't be parsed — extraction falls back to a lower tier (`llamaindex` → `local` → `keyword`) and logs a `WARNING`. As of this change, that fallback is also reported in the ingestion result, not just the logs:

```json
{
  "status": "ok",
  "files_indexed": 3,
  "metadata_degraded": 1,
  "file_details": [
    { "file": "slow_doc.pdf", "status": "indexed", "chunks": 12, "metadata_degraded": true },
    { "file": "fast_doc.pdf", "status": "indexed", "chunks": 4 }
  ]
}
```

`metadata_degraded` counts files whose metadata came from a fallback tier rather than the configured mode; only affected `file_details` entries carry the `metadata_degraded: true` marker. `keyword` and `disabled` as the *configured* mode never degrade — there's no LLM call to fall back from. The chunk metadata written to ChromaDB is unaffected: `category`, `keywords`, and `summary` keep their usual shape, with no extra key added.

## Filtering search results

Use the `metadata_filter` parameter on the `search_documents` MCP tool:

```json
{
  "query": "deep learning architectures",
  "collection": "research",
  "metadata_filter": { "category": "AI" }
}
```

The filter is applied **server-side** via ChromaDB's native `where` clause — only matching chunks leave the vector store. This is more efficient than fetching everything and filtering client-side.
