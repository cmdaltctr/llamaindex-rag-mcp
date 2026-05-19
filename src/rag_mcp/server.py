"""MCP server exposing RAG document tools over stdio.

Start with:
    uv run rag-mcp

Tools
-----
- ingest_documents       – index a file / directory into the RAG store
- search_documents       – semantic search over the indexed documents
- list_indexed_documents – show what's currently in the store
"""

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .ingestion import ingest_path, list_documents as _list_documents
from .retrieval import search

# Load .env from the working directory (project root when run via `uv run`)
load_dotenv()

mcp = FastMCP("rag-mcp", log_level="WARNING")


# ── Tool 1: Ingest ----------------------------------------------------------

@mcp.tool(
    description=(
        "Index one or more documents or a directory into the RAG store. "
        "Accepts a file path or directory path. Supported formats: PDF, "
        "DOCX, PPTX, TXT, Markdown, HTML, CSV."
    )
)
def ingest_documents(path: str) -> dict:
    """Index documents into the RAG vector store."""
    return ingest_path(path)


# ── Tool 2: Search ----------------------------------------------------------

@mcp.tool(
    description=(
        "Search the indexed documents using semantic similarity. "
        "Returns the most relevant text chunks with their source file "
        "and relevance score. Optionally re-score results with a "
        "cross-encoder reranker for better precision, or filter by "
        "a minimum similarity threshold."
    )
)
def search_documents(
    query: str,
    top_k: int = 5,
    similarity_threshold: float = 0.0,
    rerank: bool = False,
) -> list[dict]:
    """Search indexed documents for semantically relevant chunks.

    Args:
        query: Natural language search query.
        top_k: Maximum number of chunks to return (default 5).
        similarity_threshold: Minimum relevance score to include a
            result. 0.0 means no filtering (default).
        rerank: If True, re-score results with the cross-encoder
            reranker for better precision (default False).
    """
    return search(
        query,
        top_k=top_k,
        similarity_threshold=similarity_threshold,
        rerank=rerank,
    )


# ── Tool 3: List indexed documents ------------------------------------------

@mcp.tool(
    description=(
        "List all documents currently indexed in the RAG store, "
        "with their source paths and chunk counts."
    )
)
def list_indexed_documents() -> list[dict]:
    """List all documents that have been indexed so far."""
    return _list_documents()


# ── Entry point --------------------------------------------------------------

def main() -> None:
    """Start the MCP server on stdio transport."""
    import logging
    import sys

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
