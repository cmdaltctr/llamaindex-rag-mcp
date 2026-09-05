"""List command group — ``omrg list`` and ``omrg list-collections``.

Read-only inspection of indexed documents and ChromaDB collections.
"""

from __future__ import annotations

import json

import typer
from rich.table import Table

from . import _sanitise_display_name, app, console


@app.command(name="list")
def list_cmd(
    collection: str = typer.Option(
        "documents",
        "--collection",
        "-c",
        help="ChromaDB collection to list documents from.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
) -> None:
    """List indexed documents and show sources missing on this machine."""
    from ...core.ingestion import list_documents

    docs = list_documents(collection_name=collection)

    if not docs:
        if json_output:
            typer.echo("[]", err=True)
        else:
            console.print("[yellow]No indexed documents.[/yellow]")
        return

    if json_output:
        typer.echo(json.dumps(docs, indent=2), err=True)
        return

    table = Table(title="Indexed Documents")
    table.add_column("Source", style="green")
    table.add_column("Chunks", style="cyan", justify="right")
    table.add_column("Orphaned", style="yellow")

    total_chunks = 0
    for doc in docs:
        source = _sanitise_display_name(doc["source"])
        chunks = doc["chunks"]
        total_chunks += chunks
        orphaned = doc["orphaned"]
        orphaned_label = "Yes" if orphaned is True else "No" if orphaned is False else "Unknown"
        table.add_row(source, str(chunks), orphaned_label)

    console.print(table)
    console.print(f"\n[bold]{len(docs)} document(s), {total_chunks} chunk(s) total.[/bold]")


@app.command(name="list-collections")
def list_collections_cmd(
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
) -> None:
    """List all ChromaDB collections with document and chunk counts."""
    from ...core.retrieval import list_collections

    collections = list_collections()

    if not collections:
        if json_output:
            typer.echo("[]", err=True)
        else:
            console.print("[yellow]No collections found.[/yellow]")
        return

    if json_output:
        typer.echo(json.dumps(collections, indent=2), err=True)
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
