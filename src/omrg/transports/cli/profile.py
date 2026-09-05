"""Profile command group — ``omrg set-profile``.

Change the profile bound to a ChromaDB collection (non-destructive).
Profiles control retrieval behaviour: 'documents' (quality-first) or
'codebase' (speed-first).
"""

from __future__ import annotations

import json

import typer

from . import app, console


@app.command(name="set-profile")
def set_profile_cmd(
    collection: str = typer.Option(
        ...,
        "--collection",
        "-c",
        help="Name of the ChromaDB collection.",
    ),
    profile: str = typer.Option(
        ...,
        "--profile",
        "-p",
        help="Target profile: 'documents' or 'codebase'.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
) -> None:
    """Change the profile bound to a collection (non-destructive).

    Profiles control retrieval behaviour: 'documents' (quality-first,
    reranker on, dense-only) or 'codebase' (speed-first, reranker off,
    hybrid).  The change is non-destructive — existing chunks are NOT
    re-chunked or re-embedded.  Query-time levers apply immediately;
    ingest-time levers apply to future ingests only.
    """
    if profile not in ("documents", "codebase"):
        console.print(
            f"[red]Error:[/red] Invalid profile {profile!r}. Available: documents, codebase."
        )
        raise typer.Exit(code=1)

    from ... import compose
    from ...core.profiles import apply_profile_change, generate_safety_contract

    contract = generate_safety_contract(
        collection, profile, resolver=compose.build_profile_resolver()
    )

    if json_output:
        if yes:
            result = apply_profile_change(collection, profile)
            typer.echo(json.dumps(result, indent=2), err=True)
        else:
            typer.echo(json.dumps(contract, indent=2), err=True)
        return

    console.print(f"\n[bold]Profile change:[/bold] {collection} → {profile}")
    console.print(f"  Current chunks: [cyan]{contract['chunk_count']}[/cyan]")
    if contract["old_profile"]:
        console.print(f"  Old profile: [yellow]{contract['old_profile']}[/yellow]")
    else:
        console.print("  Old profile: [dim](none — inherits server default)[/dim]")

    console.print("\n[bold]Lever impacts:[/bold]")
    for impact in contract["lever_impacts"]:
        timing_colour = "green" if impact["timing"] == "query-time" else "yellow"
        console.print(
            f"  [{timing_colour}]{impact['timing']}[/{timing_colour}] "
            f"{impact['lever']}: {impact['change']}"
        )

    console.print(f"\n[dim]{contract['reingest_pointer']}[/dim]\n")

    if not yes:
        response = typer.confirm("Continue?", default=False)
        if not response:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(code=1)

    result = apply_profile_change(collection, profile)
    console.print(
        f"[green]✓[/green] Profile changed: {collection} → {profile} "
        f"({result['chunk_count_unchanged']} chunks unchanged)"
    )
