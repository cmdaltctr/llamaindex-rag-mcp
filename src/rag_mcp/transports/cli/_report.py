"""Ingestion report writer — JSON or Markdown output.

Extracted from ``ingest.py`` so the ingest command group stays focused.
Writes a structured summary of an ingestion run to a file, inferring the
format from the extension (``.json`` for machine-readable, Markdown otherwise).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def write_report(
    report_path: str, result: dict, ingest_kwargs: dict, input_path: str
) -> None:
    """Write an ingestion report to a file (JSON or Markdown).

    Args:
        report_path: Destination file path. ``.json`` extension produces a
            JSON report; any other extension produces a Markdown table.
        result: The ingestion result dict from ``ingest_path_async``.
        ingest_kwargs: The kwargs passed to ingestion (for config echo).
        input_path: The original input path (for the report header).
    """
    from ...config import settings

    report_file = Path(report_path).expanduser().resolve()

    if report_file.exists():
        logger.warning("Overwriting existing report: %s", report_path)

    file_details = result.get("file_details", [])
    total_files = len(file_details)
    indexed = sum(1 for f in file_details if f["status"] == "indexed")
    failed = sum(1 for f in file_details if f["status"] == "failed")
    skipped = sum(1 for f in file_details if f["status"] == "skipped")

    timestamp = datetime.now(timezone.utc).isoformat()

    config_info = {
        "model": settings.embed_model,
        "batch_size": settings.embed_batch_size,
        "concurrency": settings.embed_concurrency,
        "chunk_size": ingest_kwargs.get("chunk_size", settings.chunk_size),
        "chunk_overlap": ingest_kwargs.get("chunk_overlap", settings.chunk_overlap),
    }

    summary = {
        "total": total_files,
        "indexed": indexed,
        "failed": failed,
        "skipped": skipped,
        "chunks": result.get("chunks_created", 0),
    }

    if report_file.suffix.lower() == ".json":
        report_data = {
            "timestamp": timestamp,
            "config": config_info,
            "input_path": str(input_path),
            "summary": summary,
            "files": file_details,
        }
        report_file.write_text(
            json.dumps(report_data, indent=2) + "\n", encoding="utf-8"
        )
    else:
        lines = [
            "# Ingestion Report", "",
            f"**Timestamp**: {timestamp}",
            f"**Input**: `{input_path}`", "",
            "## Summary", "",
            "| Metric | Value |", "|--------|-------|",
            f"| Total files | {summary['total']} |",
            f"| Indexed | {summary['indexed']} |",
            f"| Failed | {summary['failed']} |",
            f"| Skipped | {summary['skipped']} |",
            f"| Total chunks | {summary['chunks']} |", "",
            "## Configuration", "",
            "| Setting | Value |", "|---------|-------|",
            f"| Model | {config_info['model']} |",
            f"| Batch size | {config_info['batch_size']} |",
            f"| Concurrency | {config_info['concurrency']} |",
            f"| Chunk size | {config_info['chunk_size']} |",
            f"| Chunk overlap | {config_info['chunk_overlap']} |", "",
            "## Per-File Details", "",
            "| File | Status | Chunks | Error |",
            "|------|--------|--------|-------|",
        ]
        for fd in file_details:
            error = fd.get("error", "")
            lines.append(
                f"| {fd['file']} | {fd['status']} | {fd['chunks']} | {error} |"
            )
        lines.append("")
        report_file.write_text("\n".join(lines), encoding="utf-8")
