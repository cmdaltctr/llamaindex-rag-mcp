"""Azure Document Intelligence reader — optional hybrid document parsing backend.

When ``DOCUMENT_BACKEND=azure`` is configured in ``config.py``, this module
provides an alternative PDF/document parser using Azure Document Intelligence.
The Azure SDK is imported lazily at runtime — it is never a top-level import,
so the module loads even when ``azure-ai-documentintelligence`` is not installed.

All settings are read from ``config.py``. No cross-imports with ``retrieval.py``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from ..config import settings

logger = logging.getLogger(__name__)


class AzureDocReader:
    """Azure Document Intelligence reader for PDF and document parsing.

    Sends documents to Azure Document Intelligence for structured parsing,
    returning LlamaIndex Documents with paragraphs, tables, and heading
    hierarchy metadata.

    The Azure SDK is imported lazily — calling ``read()`` without the
    ``azure-ai-documentintelligence`` package installed raises ImportError.

    Attributes:
        endpoint: Azure Document Intelligence endpoint URL.
        key: Azure Document Intelligence API key.
        model: Azure model ID (default: "prebuilt-layout").
    """

    def __init__(
        self,
        endpoint: str | None = None,
        key: str | None = None,
        model: str | None = None,
    ) -> None:
        """Initialise the Azure Document Intelligence reader.

        Args:
            endpoint: Azure Document Intelligence endpoint URL.
            key: Azure Document Intelligence API key.
            model: Azure model ID (default: "prebuilt-layout").
        """
        if endpoint is None:
            endpoint = settings.azure_doc_intelligence_endpoint
        if key is None:
            key = settings.azure_doc_intelligence_key
        if model is None:
            model = settings.azure_doc_intelligence_model
        self.endpoint = endpoint
        self.key = key
        self.model = model

    def _get_client(self):
        """Lazily import and create the Azure Document Intelligence client.

        Returns:
            ``DocumentIntelligenceClient`` instance.

        Raises:
            ImportError: If ``azure-ai-documentintelligence`` is not installed.
        """
        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise ImportError(
                "azure-ai-documentintelligence is not installed. "
                "Install with: uv sync --extra azure"
            ) from exc

        return DocumentIntelligenceClient(
            self.endpoint, AzureKeyCredential(self.key),
        )

    def read(self, file_path: Path) -> list:
        """Send a document to Azure and receive LlamaIndex Documents.

        Args:
            file_path: Path to the document file (PDF, DOCX, etc.).

        Returns:
            List of LlamaIndex ``Document`` objects with paragraphs, tables,
            and heading metadata.

        Raises:
            ImportError: If Azure SDK is not installed.
            Exception: If Azure API call fails after retry.
        """
        client = self._get_client()

        with open(file_path, "rb") as f:
            poller = client.begin_analyze_document(
                self.model, body=f,
            )

        # Wait for completion (Azure handles async polling).
        result = poller.result()
        return parse_azure_response(result, file_path)


def parse_azure_response(result, file_path: Path) -> list:
    """Convert Azure Document Intelligence result to LlamaIndex Documents.

    Extracts paragraphs, tables, and heading hierarchy from the Azure
    structured JSON response. Tables are kept as intact chunks with
    ``content_type: "table"`` metadata. Large tables (>50 rows) are split
    into row groups.

    Args:
        result: Azure ``AnalyzeResult`` object.
        file_path: Path to the source file (for metadata).

    Returns:
        List of LlamaIndex ``Document`` objects.
    """
    from llama_index.core import Document

    documents: list[Document] = []

    # Extract paragraphs with heading roles.
    paragraphs = getattr(result, "paragraphs", None) or []
    for para in paragraphs:
        role = getattr(para, "role", None) or ""
        content = getattr(para, "content", "") or ""
        if not content:
            continue

        metadata = {
            "file_path": str(file_path),
            "content_type": "document/azure",
            "header_path": role,
        }

        # Build heading path from role.
        if role and role.startswith("heading"):
            metadata["heading_role"] = role

        documents.append(Document(text=content, metadata=metadata))

    # Extract tables as intact chunks.
    tables = getattr(result, "tables", None) or []
    for i, table in enumerate(tables):
        table_text = _format_table(table)
        if not table_text:
            continue

        row_count = getattr(table, "row_count", 0) or 0
        if row_count > 50:
            # Split large tables into row groups.
            row_groups = _split_table_rows(table, group_size=50)
            for j, group_text in enumerate(row_groups):
                documents.append(Document(
                    text=group_text,
                    metadata={
                        "file_path": str(file_path),
                        "content_type": "table",
                        "table_index": i,
                        "row_group": j,
                    },
                ))
        else:
            documents.append(Document(
                text=table_text,
                metadata={
                    "file_path": str(file_path),
                    "content_type": "table",
                    "table_index": i,
                },
            ))

    # If no paragraphs or tables, try raw content.
    if not documents:
        content = getattr(result, "content", "") or ""
        if content:
            documents.append(Document(
                text=content,
                metadata={
                    "file_path": str(file_path),
                    "content_type": "document/azure",
                },
            ))

    return documents


def _format_table(table) -> str:
    """Format an Azure table object as markdown.

    Args:
        table: Azure table object with cells.

    Returns:
        Markdown-formatted table string.
    """
    cells = getattr(table, "cells", None) or []
    if not cells:
        return ""

    # Build a grid of cell values.
    row_count = getattr(table, "row_count", 0) or 0
    col_count = getattr(table, "column_count", 0) or 0

    if row_count == 0 or col_count == 0:
        return ""

    grid: list[list[str]] = [[""] * col_count for _ in range(row_count)]
    for cell in cells:
        row_idx = getattr(cell, "row_index", 0) or 0
        col_idx = getattr(cell, "column_index", 0) or 0
        content = getattr(cell, "content", "") or ""
        if row_idx < row_count and col_idx < col_count:
            grid[row_idx][col_idx] = content.strip()

    # Format as markdown table.
    lines: list[str] = []
    # Header row.
    lines.append("| " + " | ".join(grid[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in range(col_count)) + " |")
    # Data rows.
    for row in grid[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def _split_table_rows(table, group_size: int = 50) -> list[str]:
    """Split a large table into row groups as markdown strings.

    Args:
        table: Azure table object with cells.
        group_size: Maximum rows per group.

    Returns:
        List of markdown-formatted table strings, one per row group.
    """
    cells = getattr(table, "cells", None) or []
    row_count = getattr(table, "row_count", 0) or 0
    col_count = getattr(table, "column_count", 0) or 0

    if row_count == 0 or col_count == 0:
        return []

    grid: list[list[str]] = [[""] * col_count for _ in range(row_count)]
    for cell in cells:
        row_idx = getattr(cell, "row_index", 0) or 0
        col_idx = getattr(cell, "column_index", 0) or 0
        content = getattr(cell, "content", "") or ""
        if row_idx < row_count and col_idx < col_count:
            grid[row_idx][col_idx] = content.strip()

    groups: list[str] = []
    for start in range(0, row_count, group_size):
        end = min(start + group_size, row_count)
        subset = grid[start:end]
        lines: list[str] = []
        lines.append("| " + " | ".join(subset[0]) + " |")
        lines.append("| " + " | ".join("---" for _ in range(col_count)) + " |")
        for row in subset[1:]:
            lines.append("| " + " | ".join(row) + " |")
        groups.append("\n".join(lines))

    return groups


async def read_with_azure_fallback(
    file_path: Path,
    max_retries: int = 1,
    retry_delay: float = 5.0,
) -> list:
    """Read a document using Azure with graceful fallback to local readers.

    Attempts Azure Document Intelligence first. On network error, retries
    once after ``retry_delay`` seconds. On persistent failure, falls back
    to the local reader chain (LiteParse → pypdfium2 → pypdf).

    Args:
        file_path: Path to the document file.
        max_retries: Number of retry attempts before fallback.
        retry_delay: Delay between retries in seconds.

    Returns:
        List of LlamaIndex ``Document`` objects.

    Raises:
        Exception: If both Azure and local readers fail.
    """
    reader = AzureDocReader()

    for attempt in range(max_retries + 1):
        try:
            # Run Azure read in a thread to avoid blocking the event loop.
            documents = await asyncio.to_thread(reader.read, file_path)
            logger.info(
                "Azure Document Intelligence parsed %s (%d chunks)",
                file_path.name, len(documents),
            )
            return documents
        except ImportError as exc:
            logger.warning("Azure SDK not available: %s — falling back to local", exc)
            break
        except Exception as exc:
            if attempt < max_retries:
                logger.warning(
                    "Azure read attempt %d failed for %s: %s — retrying in %.1fs",
                    attempt + 1, file_path.name, exc, retry_delay,
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.warning(
                    "Azure read failed for %s after %d attempts: %s — falling back to local",
                    file_path.name, max_retries + 1, exc,
                )

    # Fallback to local reader chain.
    return await _read_with_local_chain(file_path)


async def _read_with_local_chain(file_path: Path) -> list:
    """Read a document using the local reader chain (LiteParse → pypdfium2 → pypdf).

    Args:
        file_path: Path to the document file.

    Returns:
        List of LlamaIndex ``Document`` objects.
    """
    from llama_index.core import SimpleDirectoryReader
    from .pdf import get_pdf_reader

    def _read_sync() -> list:
        reader = SimpleDirectoryReader(
            input_files=[str(file_path)],
            filename_as_id=True,
            file_extractor={".pdf": get_pdf_reader()},
        )
        return reader.load_data()

    return await asyncio.to_thread(_read_sync)
