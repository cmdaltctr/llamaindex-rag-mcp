"""Transport layer — thin wrappers over the shared core.

This package contains the delivery mechanisms for the RAG framework:
``mcp/`` (MCP server, split by tool), ``cli/`` (CLI split by command group),
and ``api/`` (OpenAPI 3.1 contract for the future REST transport).

No transport file contains business logic. Each validates input,
delegates to ``core/``, and formats output.
"""
