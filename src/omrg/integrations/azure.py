"""Azure Document Intelligence reader — optional hybrid document parsing backend.

When ``DOCUMENT_BACKEND=azure`` is configured, this module provides the
registered ``azure`` document-backend adapter (see
``core/ingestion/backends/registry.py``) using Azure Document
Intelligence. The Azure SDK is imported lazily at runtime — it is never
a top-level import, so the module loads even when
``azure-ai-documentintelligence`` is not installed.

Retry and local-fallback policy is owned by the orchestrator
(``core/ingestion/backends/orchestrator.py``); this adapter only reads
(design D1). Adapters receive the frozen ``EffectiveSettings`` value
object and import no ingestion business logic (design D4).
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from pathlib import Path

from ..core.settings import EffectiveSettings

logger = logging.getLogger(__name__)


class AzureDocReader:
    """Azure Document Intelligence reader for PDF and document parsing.

    Sends documents to Azure Document Intelligence for structured parsing,
    returning LlamaIndex Documents with paragraphs, tables, and heading
    hierarchy metadata.

    The Azure SDK is imported lazily — calling ``read()`` without the
    ``azure-ai-documentintelligence`` package installed raises ImportError.

    Construction is explicit (ADR-037): the adapter reads no settings
    singleton; callers — the registered ``read_documents`` adapter —
    inject the resolved values.

    Attributes:
        endpoint: Azure Document Intelligence endpoint URL.
        key: Azure Document Intelligence API key.
        model: Azure model ID (default: "prebuilt-layout").
    """

    def __init__(
        self,
        endpoint: str,
        key: str,
        model: str = "prebuilt-layout",
    ) -> None:
        """Initialise the Azure Document Intelligence reader.

        Args:
            endpoint: Azure Document Intelligence endpoint URL.
            key: Azure Document Intelligence API key.
            model: Azure model ID (default: "prebuilt-layout").
        """
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
            self.endpoint,
            AzureKeyCredential(self.key),
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
                self.model,
                body=f,
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
                documents.append(
                    Document(
                        text=group_text,
                        metadata={
                            "file_path": str(file_path),
                            "content_type": "table",
                            "table_index": i,
                            "row_group": j,
                        },
                    )
                )
        else:
            documents.append(
                Document(
                    text=table_text,
                    metadata={
                        "file_path": str(file_path),
                        "content_type": "table",
                        "table_index": i,
                    },
                )
            )

    # If no paragraphs or tables, try raw content.
    if not documents:
        content = getattr(result, "content", "") or ""
        if content:
            documents.append(
                Document(
                    text=content,
                    metadata={
                        "file_path": str(file_path),
                        "content_type": "document/azure",
                    },
                )
            )

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


def require_azure_installed() -> None:
    """Availability probe for the document-backend registry.

    Raises:
        ImportError: When ``azure-ai-documentintelligence`` is not
            installed; the message carries the installation instruction.
    """
    try:
        importlib.import_module("azure.ai.documentintelligence")
    except ImportError as exc:
        raise ImportError(
            "azure-ai-documentintelligence is not installed. Install with: uv sync --extra azure"
        ) from exc


async def read_documents(file_path: Path, *, settings: EffectiveSettings) -> list:
    """Read *file_path* through Azure Document Intelligence (registered backend).

    Runs the SDK call in a worker thread so the event loop stays
    responsive. Retry and local fallback are owned by the orchestrator,
    NOT this adapter (design D1): exceptions propagate for the
    orchestrator to retry or degrade.

    Args:
        file_path: Path to the document file (PDF, DOCX, etc.).
        settings: Injected effective settings carrying the Azure
            endpoint, key, and model.

    Returns:
        List of LlamaIndex ``Document`` objects with paragraphs, tables,
        and heading metadata.

    Raises:
        ImportError: If the Azure SDK is not installed.
        Exception: If the Azure API call fails.
    """
    reader = AzureDocReader(
        endpoint=settings.azure_doc_intelligence_endpoint,
        key=settings.azure_doc_intelligence_key,
        model=settings.azure_doc_intelligence_model,
    )
    documents = await asyncio.to_thread(reader.read, file_path)
    logger.info(
        "Azure Document Intelligence parsed %s (%d chunks)",
        file_path.name,
        len(documents),
    )
    return documents
