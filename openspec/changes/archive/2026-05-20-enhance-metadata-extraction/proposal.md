## Why

The metadata extraction system currently has an asymmetry: `ollama` mode returns only a single `{"category": "..."}` field despite being powered by a capable LLM, and `llamaindex` mode is a stub that falls back to keyword regex. Users with moderate hardware (running Ollama) should get richer metadata — keywords + summary alongside category — without needing to switch to a heavier pipeline. Users with more capable hardware who want deep per-chunk enrichment via LlamaIndex's formal extractor pipeline currently have no working option. Both gaps are addressed in two incremental stages.

## What Changes

- **Stage 1: Enrich `ollama` mode output** — Change the Ollama API prompt to request structured JSON output (`category`, `keywords`, `summary`) instead of a single category string. The transport stays the same (`urllib.request` to Ollama's `/api/generate` endpoint). No new dependencies. Existing `ollama` mode behaviour is a superset — `category` remains present, new fields are additive.
- **Stage 2: Implement real `llamaindex` mode** — Replace the stub `_extract_llamaindex()` with LlamaIndex's formal extractor pipeline (`TitleExtractor`, `KeywordExtractor`, `SummaryExtractor`). Configure `Settings.llm` via Ollama for LLM-backed extraction. Leverage `IngestionPipeline` to run extractors per-chunk rather than per-file. Add `llama-index-llms-ollama` as an optional dependency. Gracefully fall back to keyword mode if the LLM is not configured or the extraction fails.
- **Update defaults and docs** — The ollama mode prompt is updated to request richer output. The `OLLAMA_CLASSIFY_MODEL` env var continues to control which model is used. A new `LLAMANDEX_EXTRACTOR_MAX_CHUNKS` env var caps the number of chunks processed in the llamaindex pipeline.
- **Test coverage** — New tests validate JSON parsing of richer ollama output, fallback when JSON is malformed, pipeline integration for llamaindex mode, and graceful degradation when `Settings.llm` is unset.

## Capabilities

### Modified Capabilities

- **`metadata-extraction`**: The Ollama LLM-based categorisation requirement is updated to SHALL return structured JSON (`category`, `keywords`, `summary`) instead of a flat category string. The LlamaIndex MetadataExtractor requirement is updated from a stub (falling back to keyword) to SHALL use LlamaIndex's `IngestionPipeline` with `TitleExtractor`, `KeywordExtractor`, and `SummaryExtractor` per-chunk, falling back only on extraction failure.

## Impact

- Affected code: `src/rag_mcp/metadata_extractor.py` (new prompt + JSON parsing for ollama; real extraction body for llamaindex), `src/rag_mcp/config.py` (new `Settings.llm` configuration and `LLAMANDEX_EXTRACTOR_MAX_CHUNK_CHARS` env var), `pyproject.toml` (optional `llama-index-llms-ollama` dependency)
- Affected tests: `tests/test_metadata_extractor.py` (new tests for richer output, JSON fallback, pipeline integration)
- Docs: `README.md` (updated mode table — ollama: richer output; llamaindex: implemented)
- No breaking changes: existing `ollama` mode callers still receive `category` in the dict; `llamaindex` mode changes from stub fallback to real behaviour but both return dicts
