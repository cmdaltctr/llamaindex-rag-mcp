# MCP Client Setup

## Register in OpenChamber

### Method A — Via UI (recommended)

1. Open **OpenChamber → Settings → MCP**
2. Click **"+ New MCP Server"**
3. Fill in:
   - Name: `rag-docs`
   - Transport: **Local / stdio**
   - Command (one token per line): `uv` / `run` / `--project` / `/absolute/path/to/llamaindex-rag-mcp` / `rag-mcp`
4. Environment variables:
   - `EMBED_MODEL` = `nomic-embed-text`
   - `OLLAMA_BASE_URL` = `http://localhost:11434`
   - `CHROMA_PERSIST_DIR` = `/absolute/path/to/llamaindex-rag-mcp/chroma_db`
5. Click **Create** — the server should connect immediately (green indicator).

### Method B — Direct JSON edit

Add this block to `~/.opencode/opencode.json` (available in all projects) or `<project>/.opencode/opencode.json` (project-scoped):

```json
{
  "mcp": {
    "rag-docs": {
      "type": "local",
      "command": ["uv", "run", "--project", "/absolute/path/to/llamaindex-rag-mcp", "rag-mcp"],
      "environment": {
        "EMBED_MODEL": "nomic-embed-text",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "CHROMA_PERSIST_DIR": "/absolute/path/to/llamaindex-rag-mcp/chroma_db"
      },
      "enabled": true
    }
  }
}
```

Then refresh in **OpenChamber → Settings → MCP**.

---

## Multi-project setup

By default the server uses one flat ChromaDB — every chat and every project searches the same store. Here are your options.

### Option 1 — One shared store (simplest)

The global `~/.opencode/opencode.json` points at one ChromaDB. Anything you index is visible from any chat, any project. Best for general reference docs you want everywhere.

### Option 2 — Project-scoped stores (recommended for isolation)

Put a per-project `opencode.json` inside each project with its own `CHROMA_PERSIST_DIR`:

```json
{
  "mcp": {
    "rag-docs": {
      "type": "local",
      "command": ["uv", "run", "--project", "/absolute/path/to/llamaindex-rag-mcp", "rag-mcp"],
      "environment": {
        "EMBED_MODEL": "nomic-embed-text",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "CHROMA_PERSIST_DIR": "/absolute/path/to/my-project/rag-store/chroma_db"
      },
      "enabled": true
    }
  }
}
```

No init needed — just set `CHROMA_PERSIST_DIR` to any path. The first `ingest_documents` call creates the directory, database, and collection automatically.

### Option 3 — Per-project only, no global

Remove `rag-docs` from `~/.opencode/opencode.json` entirely and only configure it per project. The server only spins up when you're inside a project that has an `opencode.json`. Cleaner, but you configure each project manually.

### Option 4 — Named collections in one ChromaDB

Use the built-in `collection` parameter to keep different projects isolated within the same ChromaDB:

```bash
rag-mcp ingest /path/to/project-a/docs/ --collection project-a
rag-mcp ingest /path/to/project-b/docs/ --collection project-b

rag-mcp search "quantum computing" --collection project-a
rag-mcp list-collections
```

Collections are created automatically on first ingest. No extra directories or environment configs needed.

> **Naming conflict note:** If both a global and a project-level config use the server name `rag-docs` and your client complains about a duplicate, give the project-scoped one a unique name like `rag-docs-myproject`.

---

## AI agent quickstart

If you are an AI agent setting this server up for a user, follow these steps:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Ollama (macOS)
brew install ollama
# Install Ollama (Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama and pull the embedding model
ollama serve &
ollama pull nomic-embed-text

# Set up the server
cd /path/to/llamaindex-rag-mcp
cp .env.example .env
uv sync

# Verify
uv run rag-mcp
# No output = working. Ctrl-C to stop.
```

Then add the JSON config block above to the user's MCP client config file.

---

## Recommended agent prompt

If you create a dedicated agent in your MCP client, use this system prompt:

```
You have access to a document RAG system via MCP tools:

- Use ingest_documents when the user asks you to index or load a file or folder.
  You can specify a collection to isolate content (defaults to "documents").
- Use search_documents before answering any question that might be answered by
  the user's documents. Always search before saying you don't know.
  Scope to a specific collection when relevant. Use metadata_filter to filter
  by auto-detected categories, e.g. {"category": "AI"}.
- Use list_indexed_documents when the user asks what documents are available
  in a specific collection.
- Use list_collections to show all available collections and their sizes.
- Use delete_documents to remove documents by file path, by metadata filter,
  or to drop an entire collection. Always confirm before dropping a collection.

Always cite the source file and page when quoting from retrieved chunks.
```
