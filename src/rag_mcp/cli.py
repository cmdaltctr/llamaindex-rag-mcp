"""Command-line interface for the RAG MCP server.

Provides ``rag-mcp ingest``, ``rag-mcp search``, and ``rag-mcp list``
subcommands.  When invoked with no arguments, the MCP stdio server starts
instead (backward compatible).

Usage::

    rag-mcp ingest /path/to/docs/
    rag-mcp search "quantum computing"
    rag-mcp list
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from .config import INGEST_WORKERS

app = typer.Typer(
    name="rag-mcp",
    help=(
        "LlamaIndex RAG MCP server — document ingestion and semantic "
        "retrieval. Run with no arguments to start the MCP stdio server."
    ),
    no_args_is_help=False,
    add_completion=True,
)

console = Console(stderr=True)

# ── Ollama base URL for error messages ────────────────────────────────────
_OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def _print_ollama_error(detail: str, json_output: bool = False) -> None:
    """Print a friendly Ollama connection error message."""
    msg = (
        f"Cannot connect to Ollama at {_OLLAMA_URL}. "
        "Is Ollama running? Start it with: ollama serve"
    )
    if detail:
        msg += f"\n  Detail: {detail}"
    if json_output:
        typer.echo(json.dumps({"status": "error", "message": msg}))
    else:
        console.print(f"[red]Error:[/red] {msg}")


def _sanitise_display_name(name: str) -> str:
    """Remove ANSI escape sequences from display strings."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", name)


def _version(value: bool) -> None:
    """Print version and exit."""
    if value:
        from . import __version__

        typer.echo(f"rag-mcp {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=_version,
        is_eager=True,
    ),
) -> None:
    """Run with no arguments to start the MCP stdio server."""
    if ctx.invoked_subcommand is None:
        # No subcommand — start MCP stdio server
        from .server import main as mcp_main

        mcp_main()


def _run_ingest_with_rich_progress(
    path: str,
    ingest_kwargs: dict,
) -> dict:
    """Run ingestion with dual Rich progress bars (TTY mode).

    Shows two progress tasks:
      1. File reading (advances per file)
      2. Chunk embedding (advances once embedding completes)

    Both bars include elapsed time and ETA via Rich columns.
    """
    from .ingestion import ingest_path

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        read_task_id: TaskID | None = None
        embed_task_id: TaskID | None = None

        def on_progress(phase: str, current: int, total: int) -> None:
            nonlocal read_task_id, embed_task_id

            if phase == "read":
                if read_task_id is None:
                    read_task_id = progress.add_task(
                        "[green]Reading files…", total=total
                    )
                progress.update(read_task_id, completed=current)

            elif phase == "embed_start":
                # Ensure the reading bar is fully complete.
                if read_task_id is not None:
                    task = progress.tasks[read_task_id]
                    if task.completed < task.total:
                        progress.update(read_task_id, completed=task.total)
                embed_task_id = progress.add_task(
                    f"[cyan]Embedding {total} chunks…", total=total
                )

            elif phase == "embed":
                if embed_task_id is not None:
                    progress.update(embed_task_id, completed=total)

        return ingest_path(
            path, progress_callback=on_progress, **ingest_kwargs
        )


def _make_plain_callback() -> Callable[[str, int, int], None]:
    """Create a plain-text progress callback for non-TTY output.

    Prints ``"Reading file N/M…"`` and ``"Embedding K chunks…"`` to stderr
    with no ANSI escape codes — safe for pipes, CI, and redirected output.
    """

    def on_progress(phase: str, current: int, total: int) -> None:
        if phase == "read":
            print(
                f"Reading file {current}/{total}…",
                file=sys.stderr,
            )
        elif phase == "embed_start":
            print(
                f"Embedding {total} chunks…",
                file=sys.stderr,
            )
        elif phase == "embed":
            print(
                f"Embedding complete: {total} chunks written.",
                file=sys.stderr,
            )

    return on_progress


@app.command()
def ingest(
    path: str = typer.Argument(..., help="Path to a file or directory to ingest."),
    workers: int = typer.Option(
        None,
        "--workers",
        "-w",
        help=(
            "Number of parallel file readers. Clamped to ≥1. "
            f"Default: {INGEST_WORKERS} (from INGEST_WORKERS env var)."
        ),
    ),
    chunk_size: Optional[int] = typer.Option(
        None,
        "--chunk-size",
        help="Override CHUNK_SIZE for this ingestion.",
    ),
    chunk_overlap: Optional[int] = typer.Option(
        None,
        "--chunk-overlap",
        help="Override CHUNK_OVERLAP for this ingestion.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON.",
    ),
) -> None:
    """Index a file or directory into the RAG vector store."""
    from .ingestion import _shutdown_requested, ingest_path

    # Clamp workers
    if workers is None:
        workers = INGEST_WORKERS
    if workers < 1:
        workers = 1

    # Build kwargs for overrides
    ingest_kwargs: dict = {"workers": workers}
    if chunk_size is not None:
        ingest_kwargs["chunk_size"] = chunk_size
    if chunk_overlap is not None:
        ingest_kwargs["chunk_overlap"] = chunk_overlap

    # Register SIGINT handler for graceful shutdown.
    # The first Ctrl+C sets the shutdown flag so workers finish their
    # current file and stop.  A second Ctrl+C raises KeyboardInterrupt
    # for an immediate abort.
    _sigint_count = 0
    _original_handler = signal.getsignal(signal.SIGINT)

    def _on_sigint(signum: int, frame: object) -> None:
        nonlocal _sigint_count
        _sigint_count += 1
        if _sigint_count == 1:
            _shutdown_requested.set()
            console.print(
                "\n[yellow]Interrupt received — finishing current "
                "file, then stopping…[/yellow] "
                "(Ctrl+C again to force quit)"
            )
        else:
            # Second interrupt: restore default and re-raise
            signal.signal(signal.SIGINT, _original_handler)
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)

    try:
        # Select progress display mode.
        # JSON mode: suppress progress entirely.
        # TTY mode: Rich dual progress bars.
        # Non-TTY (piped/CI): plain-text lines to stderr.
        if json_output:
            result = ingest_path(path, **ingest_kwargs)
        elif console.is_terminal:
            result = _run_ingest_with_rich_progress(
                path, ingest_kwargs
            )
        else:
            result = ingest_path(
                path,
                progress_callback=_make_plain_callback(),
                **ingest_kwargs,
            )
    except ConnectionError as exc:
        _print_ollama_error(str(exc), json_output)
        raise typer.Exit(code=1)
    except Exception as exc:
        # Catch-all for unexpected errors (e.g. ChromaDB corruption).
        err_msg = str(exc)
        if "ollama" in err_msg.lower() or "embed" in err_msg.lower():
            _print_ollama_error(err_msg, json_output)
        else:
            console.print(f"[red]Error:[/red] {err_msg}")
        raise typer.Exit(code=1)
    finally:
        # Always restore original SIGINT handler
        signal.signal(signal.SIGINT, _original_handler)

    # Check if we were interrupted
    was_interrupted = _shutdown_requested.is_set()
    total_files = (
        result.get("files_indexed", 0)
        + len(result.get("warnings", []))
    )

    if result["status"] == "error" and not was_interrupted:
        msg = result.get(
            "message", "Ingestion failed — no files were indexed."
        )
        console.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    # Print interrupt message if applicable
    if was_interrupted:
        files_done = result.get("files_indexed", 0)
        if json_output:
            result["interrupted"] = True
            result["message"] = (
                f"Ingestion interrupted after "
                f"{files_done}/{total_files} files"
            )
            typer.echo(json.dumps(result, indent=2))
        else:
            console.print(
                f"[yellow]⚠ Ingestion interrupted after "
                f"{files_done}/{total_files} files.[/yellow]"
            )
            chunks = result.get("chunks_created", 0)
            if chunks > 0:
                console.print(
                    f"  [dim]{chunks} chunk(s) were written before "
                    f"interruption.[/dim]"
                )
        raise typer.Exit(code=130)  # 128 + SIGINT(2)

    if json_output:
        typer.echo(json.dumps(result, indent=2))
    else:
        files = result.get("files_indexed", 0)
        chunks = result.get("chunks_created", 0)
        console.print(
            f"[green]✓[/green] Indexed {files} file(s), "
            f"{chunks} chunk(s) created."
        )


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language search query."),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Max results to return."),
    threshold: float = typer.Option(
        0.0, "--threshold", "-t", help="Minimum similarity score."
    ),
    rerank: bool = typer.Option(
        False, "--rerank", help="Re-score with cross-encoder reranker."
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON.",
    ),
) -> None:
    """Search indexed documents for semantically relevant chunks."""
    from .retrieval import search as do_search

    try:
        results = do_search(
            query,
            top_k=top_k,
            similarity_threshold=threshold,
            rerank=rerank,
        )
    except ConnectionError as exc:
        _print_ollama_error(str(exc), json_output)
        raise typer.Exit(code=1)
    except Exception as exc:
        err_msg = str(exc)
        if "ollama" in err_msg.lower() or "embed" in err_msg.lower():
            _print_ollama_error(err_msg, json_output)
        else:
            console.print(f"[red]Error:[/red] {err_msg}")
        raise typer.Exit(code=1)

    if not results:
        if json_output:
            typer.echo("[]")
        else:
            console.print("[yellow]No results found.[/yellow]")
        return

    if json_output:
        typer.echo(json.dumps(results, indent=2))
        return

    table = Table(title="Search Results")
    table.add_column("Score", style="cyan", justify="right")
    table.add_column("Source", style="green")
    table.add_column("Page", style="dim")
    table.add_column("Text", max_width=60)

    for r in results:
        score = f"{r['score']:.4f}"
        source = _sanitise_display_name(r.get("source", "unknown"))
        page = str(r.get("page_label") or "")
        text = r.get("text", "")[:100].replace("\n", " ")
        table.add_row(score, source, page, text)

    console.print(table)


@app.command(name="list")
def list_cmd(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON.",
    ),
) -> None:
    """List all indexed documents with their chunk counts."""
    from .ingestion import list_documents

    docs = list_documents()

    if not docs:
        if json_output:
            typer.echo("[]")
        else:
            console.print("[yellow]No indexed documents.[/yellow]")
        return

    if json_output:
        typer.echo(json.dumps(docs, indent=2))
        return

    table = Table(title="Indexed Documents")
    table.add_column("Source", style="green")
    table.add_column("Chunks", style="cyan", justify="right")

    total_chunks = 0
    for doc in docs:
        source = _sanitise_display_name(doc["source"])
        chunks = doc["chunks"]
        total_chunks += chunks
        table.add_row(source, str(chunks))

    console.print(table)
    console.print(
        f"\n[bold]{len(docs)} document(s), {total_chunks} chunk(s) total.[/bold]"
    )


def run_cli() -> None:
    """Entry point for CLI mode — delegates to the Typer app."""
    app()
