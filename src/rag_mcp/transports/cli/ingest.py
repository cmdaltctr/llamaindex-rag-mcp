"""Ingest command group — ``rag-mcp ingest``.

Handles file/directory ingestion with progress display (Rich for TTY,
plain text for pipes), SIGINT handling, and report generation.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from typing import Callable, Optional

import typer
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

from . import app, console
from ._report import write_report

logger = logging.getLogger(__name__)


def _finalise_read_bar(progress: Progress, read_task_id: TaskID | None) -> None:
    """Ensure the reading progress bar is fully complete."""
    if read_task_id is not None:
        task = progress.tasks[read_task_id]
        if task.completed < task.total:
            progress.update(read_task_id, completed=task.total)


def _run_ingest_with_rich_progress(path: str, ingest_kwargs: dict) -> dict:
    """Run ingestion with dual Rich progress bars (TTY mode)."""
    import asyncio

    from ...core.ingestion import ingest_path_async

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
                _finalise_read_bar(progress, read_task_id)
                embed_task_id = progress.add_task(
                    f"[cyan]Embedding {total} chunks…", total=total
                )
            elif phase == "embed" and embed_task_id is not None:
                progress.update(embed_task_id, completed=total)

        return asyncio.run(
            ingest_path_async(
                path, progress_callback=on_progress, **ingest_kwargs
            )
        )



def _make_plain_callback() -> Callable[[str, int, int], None]:
    """Create a plain-text progress callback for non-TTY output."""

    def on_progress(phase: str, current: int, total: int) -> None:
        if phase == "read":
            print(f"Reading file {current}/{total}…", file=sys.stderr)
        elif phase == "embed_start":
            print(f"Embedding {total} chunks…", file=sys.stderr)
        elif phase == "embed":
            print(f"Embedding complete: {total} chunks written.", file=sys.stderr)

    return on_progress


def _install_sigint_handler():
    """Install SIGINT handler for graceful shutdown during ingestion."""
    from ...core.ingestion._state import shutdown_requested as _shutdown_requested

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
            signal.signal(signal.SIGINT, _original_handler)
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)
    return _original_handler


def _run_ingest(path: str, ingest_kwargs: dict, json_output: bool) -> dict:
    """Execute ingestion with the appropriate progress display mode."""
    import asyncio

    from ...core.ingestion import ingest_path_async

    if json_output:
        return asyncio.run(ingest_path_async(path, **ingest_kwargs))
    elif console.is_terminal:
        return _run_ingest_with_rich_progress(path, ingest_kwargs)
    else:
        return asyncio.run(
            ingest_path_async(
                path,
                progress_callback=_make_plain_callback(),
                **ingest_kwargs,
            )
        )


def _handle_ingest_error(exc: Exception, json_output: bool) -> None:
    """Handle unexpected errors during ingestion."""
    from . import _print_ollama_error

    err_msg = str(exc)
    if "ollama" in err_msg.lower() or "embed" in err_msg.lower():
        _print_ollama_error(err_msg, json_output)
    else:
        console.print(f"[red]Error:[/red] {err_msg}")


def _print_interrupt_result(result: dict, total_files: int, json_output: bool) -> None:
    """Print interruption message for interrupted ingestion."""
    files_done = result.get("files_indexed", 0)
    if json_output:
        result["interrupted"] = True
        result["message"] = (
            f"Ingestion interrupted after {files_done}/{total_files} files"
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
                f"  [dim]{chunks} chunk(s) were written before interruption.[/dim]"
            )


def _print_ingest_result(result: dict, json_output: bool) -> None:
    """Print the final ingestion result."""
    if json_output:
        typer.echo(json.dumps(result, indent=2))
    else:
        files = result.get("files_indexed", 0)
        chunks = result.get("chunks_created", 0)
        removed = result.get("chunks_removed", 0)
        if removed > 0:
            console.print(
                f"[green]✓[/green] Indexed {files} file(s), "
                f"{chunks} chunk(s) created, "
                f"{removed} chunk(s) replaced."
            )
        else:
            console.print(
                f"[green]✓[/green] Indexed {files} file(s), "
                f"{chunks} chunk(s) created."
            )



@app.command()
def ingest(
    path: str = typer.Argument(..., help="Path to a file or directory to ingest."),
    chunk_size: Optional[int] = typer.Option(
        None, "--chunk-size", help="Override CHUNK_SIZE for this ingestion.",
    ),
    chunk_overlap: Optional[int] = typer.Option(
        None, "--chunk-overlap", help="Override CHUNK_OVERLAP for this ingestion.",
    ),
    collection: str = typer.Option(
        "documents", "--collection", "-c",
        help="ChromaDB collection to ingest into.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
    report: Optional[str] = typer.Option(
        None, "--report", "-r",
        help=(
            "Write an ingestion report to this path. "
            "Format: JSON if path ends in .json, otherwise Markdown."
        ),
    ),
) -> None:
    """Index a file or directory into the RAG vector store.

    File reading is sequential. Tune ingestion throughput with the
    EMBED_BATCH_SIZE and EMBED_CONCURRENCY environment variables.
    """
    from ...core.ingestion._state import shutdown_requested as _shutdown_requested
    from ... import compose

    try:
        effective = compose.build_profile_resolver().resolve(collection)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    ingest_kwargs: dict = {"collection_name": collection, "effective_settings": effective}
    if chunk_size is not None:
        ingest_kwargs["chunk_size"] = chunk_size
    if chunk_overlap is not None:
        ingest_kwargs["chunk_overlap"] = chunk_overlap

    _original_handler = _install_sigint_handler()

    try:
        result = _run_ingest(path, ingest_kwargs, json_output)
    except ConnectionError as exc:
        from . import _print_ollama_error
        _print_ollama_error(str(exc), json_output)
        raise typer.Exit(code=1)
    except Exception as exc:
        _handle_ingest_error(exc, json_output)
        raise typer.Exit(code=1)
    finally:
        signal.signal(signal.SIGINT, _original_handler)

    was_interrupted = _shutdown_requested.is_set()
    total_files = (
        result.get("files_indexed", 0) + len(result.get("warnings", []))
    )

    if result["status"] == "error" and not was_interrupted:
        msg = result.get("message", "Ingestion failed — no files were indexed.")
        console.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    if was_interrupted:
        _print_interrupt_result(result, total_files, json_output)
        raise typer.Exit(code=130)

    _print_ingest_result(result, json_output)

    if report:
        try:
            write_report(report, result, ingest_kwargs, path)
            if not json_output:
                console.print(f"[dim]Report written to {report}[/dim]")
        except OSError as exc:
            console.print(f"[red]Warning:[/red] Failed to write report: {exc}")
