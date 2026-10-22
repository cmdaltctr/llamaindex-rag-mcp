"""Search command group — ``omrs search``.

Semantic search over indexed documents with optional reranking,
hybrid retrieval, and metadata filtering.
"""

from __future__ import annotations

import json
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from io import StringIO

import typer
from click.core import ParameterSource
from rich.table import Table

from ... import compose
from ...compose_profile_setup import workspace_profile_catalogue
from . import _print_ollama_error, _sanitise_display_name, app, console


def _given(ctx: typer.Context, name: str) -> bool:
    """Whether the user typed the option, so a default never overrides a graph step."""
    return ctx.get_parameter_source(name) == ParameterSource.COMMANDLINE


@app.command()
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Natural language search query."),
    top_k: int | None = typer.Option(None, "--top-k", "-k", help="Max results to return."),
    threshold: float = typer.Option(0.0, "--threshold", "-t", help="Minimum similarity score."),
    rerank: bool | None = typer.Option(
        None,
        "--rerank/--no-rerank",
        help="Re-score with cross-encoder reranker (omit for policy default).",
    ),
    hybrid: bool = typer.Option(
        False,
        "--hybrid/--no-hybrid",
        help="Fuse dense vector search with sparse BM25 retrieval via RRF.",
    ),
    expand_window: int = typer.Option(
        0,
        "--expand-window",
        min=0,
        help="Neighbours added per side of each chunk during context assembly.",
    ),
    collection: str = typer.Option(
        "documents",
        "--collection",
        "-c",
        help="ChromaDB collection to search.",
    ),
    diagnostics: bool = typer.Option(
        False,
        "--diagnostics",
        help="Include core-produced retrieval diagnostics.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
) -> None:
    """Search indexed documents for semantically relevant chunks.

    A collection that follows a user profile runs that profile's Search
    pipeline (the default workspace is read, never written).
    """
    from ...core.retrieval import search as do_search

    try:
        resolver = compose.build_profile_resolver(catalogue=workspace_profile_catalogue())
        effective, binding = resolver.resolve_bound(collection)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from None

    if not binding.user and top_k is None:
        top_k = effective.top_k

    try:
        output_guard = redirect_stdout(StringIO()) if json_output else nullcontext()
        error_guard = redirect_stderr(StringIO()) if json_output else nullcontext()
        with output_guard, error_guard:
            if binding.user:
                # A value the user did not type must not replace a step setting
                # of the profile's graph (design D14).
                results = compose.runtime_engine().search(
                    query,
                    top_k=top_k,
                    similarity_threshold=threshold if _given(ctx, "threshold") else None,
                    rerank=rerank,
                    hybrid=hybrid if _given(ctx, "hybrid") else None,
                    expand_window=expand_window,
                    collection_name=collection,
                    include_diagnostics=diagnostics,
                )
            else:
                results = do_search(
                    query,
                    top_k=top_k,
                    similarity_threshold=threshold,
                    rerank=rerank,
                    hybrid=hybrid,
                    expand_window=expand_window,
                    collection_name=collection,
                    include_diagnostics=diagnostics,
                    effective_settings=effective,
                )
    except ConnectionError as exc:
        _print_ollama_error(str(exc), json_output)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        err_msg = str(exc)
        if "ollama" in err_msg.lower() or "embed" in err_msg.lower():
            _print_ollama_error(err_msg, json_output)
        else:
            console.print(f"[red]Error:[/red] {err_msg}")
        raise typer.Exit(code=1) from None

    if not results:
        if json_output:
            typer.echo("[]", err=True)
        else:
            console.print("[yellow]No results found.[/yellow]")
        return

    if json_output:
        # Gotcha #5: stdout is the MCP protocol channel — the JSON
        # payload goes to stderr.
        typer.echo(json.dumps(results, indent=2), err=True)
        return

    table = Table(title="Search Results")
    table.add_column("Score", style="cyan", justify="right")
    table.add_column("Source", style="green")
    # Page provenance is honest per reader (spec pdf-reader): rows from
    # readers without page boundaries carry no label, so the column is
    # hidden when no row has one rather than showing an empty column.
    show_pages = any(r.get("page_label") for r in results)
    if show_pages:
        table.add_column("Page", style="dim")
    table.add_column("Text", max_width=60)

    for r in results:
        # Rows added purely by neighbour expansion carry no retrieval
        # score (they were never ranked), so the column shows a dash.
        score = f"{r['score']:.4f}" if r.get("score") is not None else "-"
        source = _sanitise_display_name(r.get("source", "unknown"))
        text = r.get("text", "")[:100].replace("\n", " ")
        if show_pages:
            page = str(r.get("page_label") or "")
            table.add_row(score, source, page, text)
        else:
            table.add_row(score, source, text)

    console.print(table)
