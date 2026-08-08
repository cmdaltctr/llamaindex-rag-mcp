# Getting Started

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **[Ollama](https://ollama.com)** — local model runner:
  ```bash
  # macOS
  brew install ollama
  # Linux
  curl -fsSL https://ollama.com/install.sh | sh
  ```

## Install

```bash
# 1. Start Ollama
ollama serve &

# 2. Pull the embedding model used by .env.example
ollama pull qwen3-embedding:0.6b

# 3. Copy the example config
cp .env.example .env

# 4. Install Python dependencies
uv sync
```

## Verify it works

```bash
uv run rag-mcp
```

No output means it's working — it's waiting silently for MCP messages on stdin. Press Ctrl-C to stop.

To inspect the tools interactively:

```bash
npx @modelcontextprotocol/inspector uv run rag-mcp
```

## Reranker and hybrid search

The reranker is **off by default**. Experiment 10 measured a 19–27% degradation on technical/code workloads, so it is opt-in. The `documents` profile turns it on for semantic workloads; the `codebase` profile leaves it off for speed (ADR-018). It's a ~23 MB ONNX model that downloads once from HuggingFace and runs entirely locally.

1. Edit `.env` and set:
   ```
   RETRIEVAL__RERANK_ENABLED=true
   ```
2. Trigger the first download by running any search with `rerank=True`. The model caches in `~/.cache/huggingface/` — no repeat downloads.

See [Reranker](reranker.md) for details.

## Alternative providers

llama.cpp is the default, but you can also use [Ollama](https://ollama.com) for convenience or [OpenRouter](https://openrouter.ai) for cloud embeddings. See [Providers](providers.md) for setup instructions.

For rare terms, citations, error codes, and exact identifiers, try opt-in hybrid retrieval:

```bash
uv run rag-mcp search "What fixes MCP-1138?" --hybrid
```

MCP clients can pass `hybrid: true` to `search_documents`.

## Register in your AI client

See [MCP Client Setup](mcp-client-setup.md) to connect the server to OpenChamber, Claude Desktop, or any other MCP-compatible client.

## Verification checklist

- [ ] `ollama ps` shows `qwen3-embedding:0.6b` loaded
- [ ] `uv run rag-mcp` starts without errors and waits on stdin
- [ ] MCP Inspector can discover and call all five tools
- [ ] Your MCP client shows `rag-docs` as connected (green)
- [ ] "What documents do you have access to?" calls `list_indexed_documents`
- [ ] "What collections are available?" calls `list_collections`
- [ ] "Index /path/to/file.pdf into the research collection" calls `ingest_documents` with `collection`
- [ ] A question about document content calls `search_documents` and cites the source
- [ ] "Delete the chunks for /path/to/file.pdf" calls `delete_documents` with `path`
- [ ] "Drop the collection research" calls `delete_documents` with `collection`
