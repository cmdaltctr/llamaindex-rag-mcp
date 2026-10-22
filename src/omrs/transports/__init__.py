"""Transport layer — thin wrappers over the shared core.

This package contains the delivery mechanisms for the RAG framework:
``mcp/`` (MCP server, split by tool), ``cli/`` (CLI split by command group),
and ``api/`` (optional local HTTP transport for ``omrs web``, needs the
``web`` extra, with its OpenAPI 3.1 contract).

No transport file contains business logic. Each validates input,
delegates to ``core/``, and formats output.
"""
