"""Command-line interface for the RAG MCP server.

Provides ``rag-mcp ingest``, ``rag-mcp search``, ``rag-mcp list``,
and ``rag-mcp watch`` subcommands.  When invoked with no arguments,
the MCP stdio server starts instead (backwards compatible).

Usage::

    rag-mcp ingest /path/to/docs/
    rag-mcp search "quantum computing"
    rag-mcp list
    rag-mcp watch /path/to/docs/
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Callable, Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
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

from .config import SUPPORTED_EXTENSIONS, TOP_K

_JSON_HELP = "Output results as JSON."

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


def _detect_gpu_acceleration() -> None:
    """Check Ollama runner type and log GPU acceleration status.

    Only runs when ``LOG_LEVEL=DEBUG``.  Inspects ``ollama ps --format json``
    to determine whether the embedding model is running on Metal GPU or
    CPU-only.  Never raises — logs a warning on any failure.
    """
    from .config import EMBED_MODEL_NAME

    logger = logging.getLogger(__name__)
    try:
        result = subprocess.run(
            ["ollama", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logger.debug(
                "Could not determine Ollama runner — ollama ps exited %d",
                result.returncode,
            )
            return

        import json as _json

        data = _json.loads(result.stdout)
        models = data.get("models", [])
        for model_info in models:
            name = model_info.get("name", "")
            if EMBED_MODEL_NAME in name:
                runner = model_info.get("details", {}).get(
                    "format", ""
                ) or model_info.get("details", {}).get("runner", "")
                vram = model_info.get("size", "")
                if "metal" in runner.lower() or "gpu" in runner.lower():
                    logger.debug(
                        "Ollama running %s on Metal GPU — VRAM: %s",
                        name,
                        vram,
                    )
                else:
                    logger.warning(
                        "Ollama running %s on CPU — consider enabling "
                        "Metal for faster embeddings",
                        name,
                    )
                return

        logger.debug(
            "Could not determine Ollama runner — %s not found in "
            "running models",
            EMBED_MODEL_NAME,
        )
    except FileNotFoundError:
        logger.debug(
            "Could not determine Ollama runner — ollama CLI not found"
        )
    except subprocess.TimeoutExpired:
        logger.debug(
            "Could not determine Ollama runner — ollama ps timed out"
        )
    except Exception as exc:
        logger.debug(
            "Could not determine Ollama runner — %s", exc
        )


def _setup_logging() -> None:
    """Configure Python logging for rag_mcp modules.

    All output goes to stderr to keep stdout clean for the MCP protocol.
    Controlled by LOG_LEVEL env var (default: INFO).

    Uses ``RichHandler`` for coloured, timestamped output when running
    interactively.  Falls back to plain format for the MCP server to
    avoid flooding the host's stderr capture.
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, level, logging.INFO)

    # RichHandler for coloured output (CLI mode).
    # The MCP server (server.py) configures its own basic WARNING logger
    # so this only affects CLI usage.
    handler = RichHandler(
        level=log_level,
        console=Console(stderr=True),
        show_time=True,
        show_path=False,
        markup=False,
    )
    logging.basicConfig(
        level=log_level,
        format="%(name)s: %(message)s",
        datefmt="[%X]",
        handlers=[handler],
        force=True,
    )

    # Log model configuration at INFO (task 1.3).
    from .config import EMBED_BATCH_SIZE, EMBED_CONCURRENCY, EMBED_MODEL_NAME

    logger = logging.getLogger(__name__)
    logger.info(
        "Embedding model: %s | batch_size: %d | concurrency: %d",
        EMBED_MODEL_NAME,
        EMBED_BATCH_SIZE,
        EMBED_CONCURRENCY,
    )

    # GPU detection at DEBUG level (task 1.2).
    if log_level <= logging.DEBUG:
        _detect_gpu_acceleration()


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


def _finalise_read_bar(progress: Progress, read_task_id: TaskID | None) -> None:
    """Ensure the reading progress bar is fully complete."""
    if read_task_id is not None:
        task = progress.tasks[read_task_id]
        if task.completed < task.total:
            progress.update(read_task_id, completed=task.total)


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
    import asyncio

    from .core.ingestion import ingest_path_async

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


def _write_report(
    report_path: str,
    result: dict,
    ingest_kwargs: dict,
    input_path: str,
) -> None:
    """Write an ingestion report to a file.

    Format is JSON if the path ends in ``.json``, otherwise Markdown.

    Args:
        report_path: Destination file path.
        result: The result dict from ``ingest_path()``.
        ingest_kwargs: The kwargs passed to ``ingest_path()``.
        input_path: The original input path argument.
    """
    from .config import (
        CHUNK_OVERLAP,
        CHUNK_SIZE,
        EMBED_BATCH_SIZE,
        EMBED_CONCURRENCY,
        EMBED_MODEL_NAME,
    )

    report_file = Path(report_path).expanduser().resolve()

    # Warn if overwriting
    if report_file.exists():
        logger = logging.getLogger(__name__)
        logger.warning("Overwriting existing report: %s", report_path)

    file_details = result.get("file_details", [])
    total_files = len(file_details)
    indexed = sum(1 for f in file_details if f["status"] == "indexed")
    failed = sum(1 for f in file_details if f["status"] == "failed")
    skipped = sum(1 for f in file_details if f["status"] == "skipped")

    timestamp = datetime.now(timezone.utc).isoformat()

    config_info = {
        "model": EMBED_MODEL_NAME,
        "batch_size": EMBED_BATCH_SIZE,
        "concurrency": EMBED_CONCURRENCY,
        "chunk_size": ingest_kwargs.get("chunk_size", CHUNK_SIZE),
        "chunk_overlap": ingest_kwargs.get("chunk_overlap", CHUNK_OVERLAP),
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
            json.dumps(report_data, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        lines = [
            "# Ingestion Report",
            "",
            f"**Timestamp**: {timestamp}",
            f"**Input**: `{input_path}`",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total files | {summary['total']} |",
            f"| Indexed | {summary['indexed']} |",
            f"| Failed | {summary['failed']} |",
            f"| Skipped | {summary['skipped']} |",
            f"| Total chunks | {summary['chunks']} |",
            "",
            "## Configuration",
            "",
            "| Setting | Value |",
            "|---------|-------|",
            f"| Model | {config_info['model']} |",
            f"| Batch size | {config_info['batch_size']} |",
            f"| Concurrency | {config_info['concurrency']} |",
            f"| Chunk size | {config_info['chunk_size']} |",
            f"| Chunk overlap | {config_info['chunk_overlap']} |",
            "",
            "## Per-File Details",
            "",
            "| File | Status | Chunks | Error |",
            "|------|--------|--------|-------|",
        ]
        for fd in file_details:
            error = fd.get("error", "")
            lines.append(
                f"| {fd['file']} | {fd['status']} | "
                f"{fd['chunks']} | {error} |"
            )
        lines.append("")
        report_file.write_text("\n".join(lines), encoding="utf-8")


def _install_sigint_handler():
    """Install SIGINT handler for graceful shutdown during ingestion."""
    from .core.ingestion._state import shutdown_requested as _shutdown_requested

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

    from .core.ingestion import ingest_path_async

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
        None,
        "--chunk-size",
        help="Override CHUNK_SIZE for this ingestion.",
    ),
    chunk_overlap: Optional[int] = typer.Option(
        None,
        "--chunk-overlap",
        help="Override CHUNK_OVERLAP for this ingestion.",
    ),
    collection: str = typer.Option(
        "documents",
        "--collection",
        "-c",
        help="ChromaDB collection to ingest into.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help=_JSON_HELP,
    ),
    report: Optional[str] = typer.Option(
        None,
        "--report",
        "-r",
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
    import asyncio

    from .core.ingestion._state import shutdown_requested as _shutdown_requested
    from .core.ingestion import ingest_path_async

    # Build kwargs for overrides
    ingest_kwargs: dict = {"collection_name": collection}
    if chunk_size is not None:
        ingest_kwargs["chunk_size"] = chunk_size
    if chunk_overlap is not None:
        ingest_kwargs["chunk_overlap"] = chunk_overlap

    _original_handler = _install_sigint_handler()

    try:
        result = _run_ingest(path, ingest_kwargs, json_output)
    except ConnectionError as exc:
        _print_ollama_error(str(exc), json_output)
        raise typer.Exit(code=1)
    except Exception as exc:
        _handle_ingest_error(exc, json_output)
        raise typer.Exit(code=1)
    finally:
        signal.signal(signal.SIGINT, _original_handler)

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

    if was_interrupted:
        _print_interrupt_result(result, total_files, json_output)
        raise typer.Exit(code=130)

    _print_ingest_result(result, json_output)

    if report:
        try:
            _write_report(report, result, ingest_kwargs, path)
            if not json_output:
                console.print(
                    f"[dim]Report written to {report}[/dim]"
                )
        except OSError as exc:
            console.print(
                f"[red]Warning:[/red] Failed to write report: {exc}"
            )


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language search query."),
    top_k: int = typer.Option(TOP_K, "--top-k", "-k", help="Max results to return."),
    threshold: float = typer.Option(
        0.0, "--threshold", "-t", help="Minimum similarity score."
    ),
    rerank: Optional[bool] = typer.Option(
        None, "--rerank/--no-rerank", help="Re-score with cross-encoder reranker (omit for policy default)."
    ),
    hybrid: bool = typer.Option(
        False,
        "--hybrid/--no-hybrid",
        help="Fuse dense vector search with sparse BM25 retrieval via RRF.",
    ),
    collection: str = typer.Option(
        "documents",
        "--collection",
        "-c",
        help="ChromaDB collection to search.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help=_JSON_HELP,
    ),
) -> None:
    """Search indexed documents for semantically relevant chunks."""
    from .core.retrieval import search as do_search

    try:
        output_guard = (
            redirect_stdout(StringIO()) if json_output else nullcontext()
        )
        error_guard = (
            redirect_stderr(StringIO()) if json_output else nullcontext()
        )
        with output_guard, error_guard:
            results = do_search(
                query,
                top_k=top_k,
                similarity_threshold=threshold,
                rerank=rerank,
                hybrid=hybrid,
                collection_name=collection,
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
    collection: str = typer.Option(
        "documents",
        "--collection",
        "-c",
        help="ChromaDB collection to list documents from.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help=_JSON_HELP,
    ),
) -> None:
    """List all indexed documents with their chunk counts."""
    from .core.ingestion import list_documents

    docs = list_documents(collection_name=collection)

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


def _prepare_benchmark_chunks(text: str | None, file: str | None) -> list[str]:
    """Prepare chunks for benchmarking from inline text or file."""
    from llama_index.core import Document
    from llama_index.core.node_parser import SentenceSplitter

    from .config import CHUNK_OVERLAP, CHUNK_SIZE

    if file:
        file_path = Path(file).expanduser().resolve()
        if not file_path.exists():
            console.print(f"[red]Error:[/red] File not found: {file}")
            raise typer.Exit(code=1)
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            console.print(
                f"[red]Error:[/red] Unsupported file extension: "
                f"{file_path.suffix}"
            )
            raise typer.Exit(code=1)

        import asyncio

        from .core.ingestion import read_and_chunk_file_async

        nodes = asyncio.run(
            read_and_chunk_file_async(
                file_path, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
            )
        )
        return [n.get_content() for n in nodes]

    # Split inline text into chunks using the same splitter.
    splitter = SentenceSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    doc = Document(text=text)
    nodes = splitter.get_nodes_from_documents([doc])
    return [n.get_content() for n in nodes]


@app.command()
def benchmark(
    text: Optional[str] = typer.Option(
        None,
        "--text",
        "-t",
        help="Inline text to embed for benchmarking.",
    ),
    file: Optional[str] = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to a file to read, chunk, and embed.",
    ),
    iterations: int = typer.Option(
        3,
        "--iterations",
        "-n",
        help="Number of benchmark iterations (default 3).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help=_JSON_HELP,
    ),
) -> None:
    """Benchmark embedding throughput (no ChromaDB writes).

    Measures end-to-end embedding speed for the current EMBED_MODEL.
    Accepts either inline ``--text`` or a ``--file`` path.  Results are
    printed to stderr as a Rich table (or JSON with ``--json``).
    """
    import time

    from llama_index.core import Settings as LISettings
    from llama_index.core.node_parser import SentenceSplitter

    from .config import (
        CHUNK_OVERLAP,
        CHUNK_SIZE,
        EMBED_BATCH_SIZE,
        EMBED_CONCURRENCY,
        EMBED_MODEL_NAME,
    )

    if not text and not file:
        console.print(
            "[red]Error:[/red] Provide either --text or --file for "
            "benchmark input."
        )
        raise typer.Exit(code=1)

    if text and file:
        console.print(
            "[red]Error:[/red] Provide either --text or --file, not both."
        )
        raise typer.Exit(code=1)

    chunks = _prepare_benchmark_chunks(text, file)

    if not chunks:
        console.print("[yellow]No chunks produced from input.[/yellow]")
        raise typer.Exit(code=1)

    embed_model = LISettings.embed_model
    model_name = EMBED_MODEL_NAME

    # Warm up: single embedding to ensure the model is loaded.
    console.print(
        f"[dim]Warming up {model_name} with 1 chunk…[/dim]"
    )
    try:
        embed_model.get_text_embedding(chunks[0])
    except Exception as exc:
        _print_ollama_error(str(exc), json_output)
        raise typer.Exit(code=1)

    # Run benchmark iterations.
    timings: list[float] = []
    vector_dim: int | None = None

    for _ in range(iterations):
        start = time.perf_counter()
        try:
            embeddings = embed_model.get_text_embedding_batch(chunks)
        except Exception as exc:
            _print_ollama_error(str(exc), json_output)
            raise typer.Exit(code=1)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

        if embeddings and vector_dim is None:
            vector_dim = len(embeddings[0])

    avg_time = sum(timings) / len(timings)
    total_chunks = len(chunks)
    throughput = total_chunks / avg_time

    result = {
        "model": model_name,
        "chunks": total_chunks,
        "batch_size": EMBED_BATCH_SIZE,
        "concurrency": EMBED_CONCURRENCY,
        "iterations": iterations,
        "avg_time_sec": round(avg_time, 4),
        "chunks_per_sec": round(throughput, 2),
        "vector_dim": vector_dim,
    }

    if json_output:
        typer.echo(json.dumps(result, indent=2))
        return

    table = Table(title="Embedding Benchmark Results")
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="cyan")

    table.add_row("Model", model_name)
    table.add_row("Chunks", str(total_chunks))
    table.add_row("Batch Size", str(EMBED_BATCH_SIZE))
    table.add_row("Concurrency", str(EMBED_CONCURRENCY))
    table.add_row("Iterations", str(iterations))
    table.add_row("Avg Time (s)", f"{avg_time:.4f}")
    table.add_row("Chunks/sec", f"{throughput:.2f}")
    if vector_dim is not None:
        table.add_row("Vector Dim", str(vector_dim))

    console.print(table)


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
        help="ChromaDB collection to route auto-ingested files into.",
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
    auto-ingests them into the ChromaDB index.  Includes SHA-256
    content-hash deduplication, per-file debouncing, ingestion
    throttling, and consecutive-error detection.

    \b
    IMPORTANT:
    • The watcher only detects changes after it starts.  Run
      ``rag-mcp ingest <path>`` first to catch up on existing files.
    • Do NOT run ``rag-mcp watch`` and ``rag-mcp ingest`` (or the MCP
      server) simultaneously on the same ChromaDB — two processes do
      not share the internal write lock.
    """
    from .watcher import watch_directory

    watch_directory(
        path, debounce=debounce, verbose=verbose,
        collection_name=collection,
    )


@app.command(name="list-collections")
def list_collections_cmd(
    json_output: bool = typer.Option(
        False,
        "--json",
        help=_JSON_HELP,
    ),
) -> None:
    """List all ChromaDB collections with document and chunk counts."""
    from .core.retrieval import list_collections

    collections = list_collections()

    if not collections:
        if json_output:
            typer.echo("[]")
        else:
            console.print("[yellow]No collections found.[/yellow]")
        return

    if json_output:
        typer.echo(json.dumps(collections, indent=2))
        return

    table = Table(title="ChromaDB Collections")
    table.add_column("Name", style="green")
    table.add_column("Documents", style="cyan", justify="right")
    table.add_column("Chunks", style="cyan", justify="right")

    total_docs = 0
    total_chunks = 0
    for coll in collections:
        total_docs += coll["document_count"]
        total_chunks += coll["chunk_count"]
        table.add_row(
            coll["name"],
            str(coll["document_count"]),
            str(coll["chunk_count"]),
        )

    console.print(table)
    console.print(
        f"\n[bold]{len(collections)} collection(s), "
        f"{total_docs} document(s), {total_chunks} chunk(s) total.[/bold]"
    )


# ── Delete subcommand ─────────────────────────────────────────────────────


def _delete_by_path(
    path: str,
    coll_name: str,
    dry_run: bool,
    preview_delete,
    remove_document,
) -> dict:
    """Delete chunks by source file path."""
    file_path = str(Path(path).expanduser().resolve())
    if dry_run:
        result = preview_delete(
            path=file_path, collection_name=coll_name,
        )
        result["path"] = file_path
    else:
        result = remove_document(file_path, collection_name=coll_name)
        result["mode"] = "path"
        result["path"] = file_path
    return result


def _delete_by_metadata(
    metadata: str,
    coll_name: str,
    dry_run: bool,
    preview_delete,
    remove_by_metadata,
) -> dict:
    """Delete chunks by metadata filter."""
    try:
        metadata_filter = json.loads(metadata)
    except json.JSONDecodeError as exc:
        console.print(
            f"[red]Error:[/red] Invalid JSON for --metadata: {exc}"
        )
        raise typer.Exit(code=1)

    if not isinstance(metadata_filter, dict):
        console.print(
            "[red]Error:[/red] --metadata must be a JSON object "
            "(e.g. '{\"category\":\"uncategorised\"}')."
        )
        raise typer.Exit(code=1)

    if dry_run:
        result = preview_delete(
            metadata_filter=metadata_filter,
            collection_name=coll_name,
        )
        result["metadata_filter"] = metadata_filter
    else:
        result = remove_by_metadata(
            metadata_filter, collection_name=coll_name
        )
        result["mode"] = "metadata"
        result["metadata_filter"] = metadata_filter
    return result


def _delete_by_collection(
    coll_name: str,
    dry_run: bool,
    yes: bool,
    preview_delete,
    remove_collection,
) -> dict:
    """Drop an entire collection with confirmation."""
    if not dry_run and not yes:
        from rich.prompt import Confirm

        confirmed = Confirm.ask(
            f"Delete entire collection '[bold]{coll_name}[/bold]'? "
            "This cannot be undone.",
            default=False,
        )
        if not confirmed:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(code=0)

    if dry_run:
        return preview_delete(collection_name=coll_name)
    result = remove_collection(coll_name)
    result["mode"] = "collection"
    return result


def _print_delete_result(
    result: dict,
    coll_name: str,
    json_output: bool,
    dry_run: bool,
) -> None:
    """Display delete command results."""
    if json_output:
        typer.echo(json.dumps(result, indent=2))
        return

    if result.get("status") == "error":
        console.print(
            f"[red]Error:[/red] {result.get('message', 'Unknown error')}"
        )
        raise typer.Exit(code=1)

    if dry_run:
        mode_label = result.get("mode", "unknown")
        would = result.get("would_delete", 0)
        console.print(
            f"[yellow]Dry run:[/yellow] Would delete [bold]{would}[/bold] "
            f"chunk(s) by {mode_label}."
        )
        return

    if result.get("mode") == "collection":
        console.print(
            f"[green]✓[/green] Collection '[bold]{coll_name}[/bold]' "
            "deleted."
        )
    else:
        removed = result.get("chunks_removed", 0)
        console.print(
            f"[green]✓[/green] Removed [bold]{removed}[/bold] chunk(s)."
        )


@app.command()
def delete(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="Source file path to delete chunks for.",
    ),
    metadata: Optional[str] = typer.Option(
        None,
        "--metadata",
        "-m",
        help=(
            "JSON string of metadata filter (e.g. "
            '{\\"category\\":\\"uncategorised\\"}).'
        ),
    ),
    collection: Optional[str] = typer.Option(
        None,
        "--collection",
        "-c",
        help=(
            "ChromaDB collection to operate on. When used without "
            "--path or --metadata, the entire collection is dropped."
        ),
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be deleted without modifying ChromaDB.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt for collection deletion.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help=_JSON_HELP,
    ),
) -> None:
    """Delete documents from the RAG vector store.

    Removes chunks by source file path (--path), by metadata filter
    (--metadata), or drops an entire collection (--collection without
    --path or --metadata). Each mode is mutually exclusive — provide
    exactly one.

    Only --collection requires a confirmation prompt. Pass --yes to skip it.
    """
    # ── Validate: exactly one of --path, --metadata, --collection ────────
    flags_provided = sum(1 for f in [path, metadata, collection] if f is not None)
    if flags_provided == 0:
        console.print(
            "[red]Error:[/red] Provide one of: --path, --metadata, "
            "--collection."
        )
        raise typer.Exit(code=1)
    if flags_provided > 1:
        console.print(
            "[red]Error:[/red] Flags --path, --metadata, and --collection "
            "are mutually exclusive."
        )
        raise typer.Exit(code=1)

    # Resolve collection name
    coll_name = "documents" if collection is None else collection

    from .core.ingestion import (
        preview_delete,
        remove_document,
        remove_by_metadata,
        remove_collection,
    )

    if path is not None:
        result = _delete_by_path(path, coll_name, dry_run, preview_delete, remove_document)
    elif metadata is not None:
        result = _delete_by_metadata(metadata, coll_name, dry_run, preview_delete, remove_by_metadata)
    else:
        result = _delete_by_collection(coll_name, dry_run, yes, preview_delete, remove_collection)

    _print_delete_result(result, coll_name, json_output, dry_run)


def run_cli() -> None:
    """Entry point for CLI mode — delegates to the Typer app."""
    _setup_logging()
    app()
