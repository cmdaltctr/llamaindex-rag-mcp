"""Search command group — ``rag-mcp search``.

Semantic search over indexed documents with optional reranking,
hybrid retrieval, and metadata filtering.
"""

from __future__ import annotations

import json
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from io import StringIO
from typing import Optional

import typer
from rich.table import Table

from . import app, console, _sanitise_display_name, _print_ollama_error
from ...config import settings


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language search query."),
    top_k: int = typer.Option(settings.top_k, "--top-k", "-k", help="Max results to return."),
    threshold: float = typer.Option(
        0.0, "--threshold", "-t", help="Minimum similarity score."
    ),
    rerank: Optional[bool] = typer.Option(
        None, "--rerank/--no-rerank",
        help="Re-score with cross-encoder reranker (omit for policy default)."
    ),
    hybrid: bool = typer.Option(
        False, "--hybrid/--no-hybrid",
        help="Fuse dense vector search with sparse BM25 retrieval via RRF.",
    ),
    collection: str = typer.Option(
        "documents", "--collection", "-c", help="ChromaDB collection to search.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
) -> None:
    """Search indexed documents for semantically relevant chunks."""
    from ... import compose
    from ...core.retrieval import search as do_search

    try:
        effective = compose.build_profile_resolver().resolve(collection)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    try:
        output_guard = redirect_stdout(StringIO()) if json_output else nullcontext()
        error_guard = redirect_stderr(StringIO()) if json_output else nullcontext()
        with output_guard, error_guard:
            results = do_search(
                query,
                top_k=top_k,
                similarity_threshold=threshold,
                rerank=rerank,
                hybrid=hybrid,
                collection_name=collection,
                effective_settings=effective,
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
