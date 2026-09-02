"""Delete command group — ``rag-mcp delete``.

Remove documents by path, metadata filter, or drop an entire collection.
Each mode is mutually exclusive. Collection drops require confirmation.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from . import app, console


def _delete_by_path(path, coll_name, dry_run, preview_delete, remove_document) -> dict:
    """Delete chunks by source file path."""
    try:
        file_path = str(Path(path).expanduser().resolve())
    except ValueError as exc:
        # A path value such as one containing a NUL byte makes pathlib
        # raise before any core call; report it like every other invalid
        # flag value instead of crashing with a traceback.
        console.print(f"[red]Error:[/red] Invalid --path value: {exc}")
        raise typer.Exit(code=1) from None
    if dry_run:
        result = preview_delete(path=file_path, collection_name=coll_name)
        result["path"] = file_path
    else:
        result = remove_document(file_path, collection_name=coll_name)
        result["mode"] = "path"
        result["path"] = file_path
    return result


def _delete_by_metadata(metadata, coll_name, dry_run, preview_delete, remove_by_metadata) -> dict:
    """Delete chunks by metadata filter."""
    try:
        metadata_filter = json.loads(metadata)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Error:[/red] Invalid JSON for --metadata: {exc}")
        raise typer.Exit(code=1) from None

    if not isinstance(metadata_filter, dict):
        console.print(
            "[red]Error:[/red] --metadata must be a JSON object "
            '(e.g. \'{"category":"uncategorised"}\').'
        )
        raise typer.Exit(code=1)

    if dry_run:
        result = preview_delete(
            metadata_filter=metadata_filter,
            collection_name=coll_name,
        )
        result["metadata_filter"] = metadata_filter
    else:
        result = remove_by_metadata(metadata_filter, collection_name=coll_name)
        result["mode"] = "metadata"
        result["metadata_filter"] = metadata_filter
    return result


def _delete_by_collection(coll_name, dry_run, yes, preview_delete, remove_collection) -> dict:
    """Drop an entire collection with confirmation."""
    if not dry_run and not yes:
        from rich.prompt import Confirm

        confirmed = Confirm.ask(
            f"Delete entire collection '[bold]{coll_name}[/bold]'? This cannot be undone.",
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


def _print_delete_result(result, coll_name, json_output, dry_run) -> None:
    """Display delete command results."""
    if json_output:
        typer.echo(json.dumps(result, indent=2), err=True)
        return

    if result.get("status") == "error":
        console.print(f"[red]Error:[/red] {result.get('message', 'Unknown error')}")
        raise typer.Exit(code=1)

    if dry_run:
        mode_label = result.get("mode", "unknown")
        would = result.get("would_delete", 0)
        console.print(
            f"[yellow]Dry run:[/yellow] Would delete [bold]{would}[/bold] chunk(s) by {mode_label}."
        )
        return

    if result.get("mode") == "collection":
        console.print(f"[green]✓[/green] Collection '[bold]{coll_name}[/bold]' deleted.")
    else:
        removed = result.get("chunks_removed", 0)
        console.print(f"[green]✓[/green] Removed [bold]{removed}[/bold] chunk(s).")


@app.command()
def delete(
    path: str | None = typer.Option(
        None,
        "--path",
        "-p",
        help="Source file path to delete chunks for.",
    ),
    metadata: str | None = typer.Option(
        None,
        "--metadata",
        "-m",
        help='JSON string of metadata filter (e.g. \'{\\"category\\":\\"uncategorised"}\').',
    ),
    collection: str | None = typer.Option(
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
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
) -> None:
    """Delete documents from the RAG vector store.

    Removes chunks by source file path (--path), by metadata filter
    (--metadata), or drops an entire collection (--collection without
    --path or --metadata). Each mode is mutually exclusive — provide
    exactly one.

    Only --collection requires a confirmation prompt. Pass --yes to skip it.
    """
    flags_provided = sum(1 for f in [path, metadata, collection] if f is not None)
    if flags_provided == 0:
        console.print("[red]Error:[/red] Provide one of: --path, --metadata, --collection.")
        raise typer.Exit(code=1)
    if flags_provided > 1:
        console.print(
            "[red]Error:[/red] Flags --path, --metadata, and --collection are mutually exclusive."
        )
        raise typer.Exit(code=1)

    coll_name = "documents" if collection is None else collection

    from ...core.ingestion import (
        preview_delete,
        remove_by_metadata,
        remove_collection,
        remove_document,
    )

    if path is not None:
        result = _delete_by_path(path, coll_name, dry_run, preview_delete, remove_document)
    elif metadata is not None:
        result = _delete_by_metadata(
            metadata, coll_name, dry_run, preview_delete, remove_by_metadata
        )
    else:
        result = _delete_by_collection(coll_name, dry_run, yes, preview_delete, remove_collection)

    _print_delete_result(result, coll_name, json_output, dry_run)
