"""Watch command group — ``rag-mcp watch``.

File-watching daemon trigger from the CLI. Delegates to
``daemon/watcher.py`` for the actual watching logic.
"""

from __future__ import annotations

import typer

from . import app


@app.command()
def watch(
    path: str = typer.Argument(
        ...,
        help="Directory to watch recursively for document changes.",
    ),
    debounce: float = typer.Option(
        2.0,
        "--debounce",
        "-d",
        help=(
            "Debounce interval in seconds (minimum 0.5). "
            "Controls how long to wait after the last file event "
            "before triggering ingestion."
        ),
    ),
    collection: str = typer.Option(
        "documents",
        "--collection",
        "-c",
        help="Vector-store collection to route auto-ingested files into.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable DEBUG-level logging for the watcher.",
    ),
) -> None:
    """Watch a directory for new/changed documents and auto-ingest them.

    Monitors the given directory tree for supported document files and
    auto-ingests them into the vector-store index.  Includes SHA-256
    content-hash deduplication, per-file debouncing, ingestion
    throttling, and consecutive-error detection.

    \\b
    IMPORTANT:
    • The watcher only detects changes after it starts.  Run
      ``rag-mcp ingest <path>`` first to catch up on existing files.
    • Do NOT run ``rag-mcp watch`` and ``rag-mcp ingest`` (or the MCP
      server) simultaneously on the same vector-store collection —
      whether concurrent writers are safe depends on the selected
      vector-store backend.
    """
    from ...daemon.runner import watch_directory

    watch_directory(
        path,
        debounce=debounce,
        verbose=verbose,
        collection_name=collection,
    )
