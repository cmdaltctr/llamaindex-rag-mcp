"""Benchmark command group — ``rag-mcp benchmark``.

Measures end-to-end embedding throughput for the current EMBED_MODEL.
Accepts either inline ``--text`` or a ``--file`` path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from . import app, console, _print_ollama_error
from ...config import SUPPORTED_EXTENSIONS, get_settings


def _prepare_benchmark_chunks(text: str | None, file: str | None) -> list[str]:
    """Prepare chunks for benchmarking from inline text or file."""
    from llama_index.core import Document
    from llama_index.core.node_parser import SentenceSplitter

    if file:
        file_path = Path(file).expanduser().resolve()
        if not file_path.exists():
            console.print(f"[red]Error:[/red] File not found: {file}")
            raise typer.Exit(code=1)
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            console.print(
                f"[red]Error:[/red] Unsupported file extension: {file_path.suffix}"
            )
            raise typer.Exit(code=1)

        import asyncio

        from ...core.ingestion import read_and_chunk_file_async

        nodes = asyncio.run(
            read_and_chunk_file_async(
                file_path,
                chunk_size=get_settings().chunking.chunk_size,
                chunk_overlap=get_settings().chunking.chunk_overlap,
            )
        )
        return [n.get_content() for n in nodes]

    splitter = SentenceSplitter(
        chunk_size=get_settings().chunking.chunk_size, chunk_overlap=get_settings().chunking.chunk_overlap
    )
    doc = Document(text=text)
    nodes = splitter.get_nodes_from_documents([doc])
    return [n.get_content() for n in nodes]


@app.command()
def benchmark(
    text: Optional[str] = typer.Option(
        None, "--text", "-t", help="Inline text to embed for benchmarking.",
    ),
    file: Optional[str] = typer.Option(
        None, "--file", "-f", help="Path to a file to read, chunk, and embed.",
    ),
    iterations: int = typer.Option(
        3, "--iterations", "-n", help="Number of benchmark iterations (default 3).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
) -> None:
    """Benchmark embedding throughput (no ChromaDB writes)."""
    import time

    from llama_index.core import Settings as LISettings

    if not text and not file:
        console.print("[red]Error:[/red] Provide either --text or --file for benchmark input.")
        raise typer.Exit(code=1)

    if text and file:
        console.print("[red]Error:[/red] Provide either --text or --file, not both.")
        raise typer.Exit(code=1)

    chunks = _prepare_benchmark_chunks(text, file)

    if not chunks:
        console.print("[yellow]No chunks produced from input.[/yellow]")
        raise typer.Exit(code=1)

    embed_model = LISettings.embed_model
    model_name = get_settings().embed_model

    console.print(f"[dim]Warming up {model_name} with 1 chunk…[/dim]")
    try:
        embed_model.get_text_embedding(chunks[0])
    except Exception as exc:
        _print_ollama_error(str(exc), json_output)
        raise typer.Exit(code=1)

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
        "batch_size": get_settings().ingestion.embed_batch_size,
        "concurrency": get_settings().ingestion.embed_concurrency,
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
    table.add_row("Batch Size", str(get_settings().ingestion.embed_batch_size))
    table.add_row("Concurrency", str(get_settings().ingestion.embed_concurrency))
    table.add_row("Iterations", str(iterations))
    table.add_row("Avg Time (s)", f"{avg_time:.4f}")
    table.add_row("Chunks/sec", f"{throughput:.2f}")
    if vector_dim is not None:
        table.add_row("Vector Dim", str(vector_dim))

    console.print(table)
