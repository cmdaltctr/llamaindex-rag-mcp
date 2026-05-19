# ADR-004: Adopt MCP Protocol for Server Interface

**Date:** 2026-05-11
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Git Commits:** `5594176`

## Context

The RAG server needs a standardised interface so that AI assistants (Claude,
GPT, Cursor, etc.) can invoke document ingestion, search, and listing as tools.
The interface must support bidirectional JSON-RPC communication, tool discovery,
and schema validation. The server runs as a local subprocess (not a web service)
to maintain the fully-local, privacy-first design.

The server also needs to serve as a standalone tool that developers can invoke
directly from the command line.

## Decision

Adopt the **Model Context Protocol (MCP)** as the primary server interface,
implemented via the **FastMCP** Python library.

- Transport: `stdio` (JSON-RPC over stdin/stdout) — the server is spawned as a
  subprocess by MCP-compatible hosts
- Three tools exposed: `ingest_documents`, `search_documents`, `list_indexed_documents`
- Tool parameters use native Python types; FastMCP auto-generates JSON Schema
- All tool handlers return `dict` or `list` — never raise exceptions (error
  responses use `{"status": "error", "message": "..."}`)
- Logging and progress output go to **stderr** to keep stdout clean for MCP protocol
- The `rag-mcp` entry point doubles as a CLI (see ADR-007) when given subcommands

## Consequences

### Positive
- Standardised protocol: works with Claude Desktop, OpenCode, Cursor, Windsurf,
  and any MCP-compatible host without custom integration code
- FastMCP handles JSON-RPC framing, schema generation, and error wrapping
- stdio transport is simple, secure (no open ports), and firewall-friendly
- Tool descriptions (from Python docstrings) are auto-exposed to AI assistants

### Negative
- MCP is a relatively new protocol; breaking changes are possible
- stdio transport limits the server to a single host process (no web UI)
- Debugging requires the MCP Inspector (`npx @modelcontextprotocol/inspector`)

### Neutral
- All new MCP tool parameters must be optional with sensible defaults to
  preserve backward compatibility with existing clients

## Alternatives Considered

| Tool | Rejected Because |
|------|-----------------|
| **REST API (FastAPI)** | Requires running an HTTP server, open port, and custom client integration |
| **gRPC** | Over-engineered for a single-user local tool; complex setup |
| **CLI only** | No AI assistant integration; manual invocation required |
| **LangChain Tools** | Locks the project into the LangChain ecosystem |

## References

- `src/rag_mcp/server.py` — MCP server definition with three tool handlers
- `pyproject.toml` — `mcp[cli]` dependency and `rag-mcp` entry point
- `README.md` — registration instructions for OpenCode and Claude Desktop
