"""``omrg migrate`` — move an old OMRG install to the OMRS names.

OpenSpec change ``rename-omrg-to-omrs``, capability ``legacy-install-migration``.
A thin wrapper: it builds the plan, prints it, asks, applies and prints the
report. The move logic lives in ``integrations/legacy_migration.py``. This
command is the one command that runs while an old install exists.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import typer
from rich.markup import escape

from ...integrations import legacy_migration as lm
from . import app, console


def _context() -> lm.Context:
    """Build the real context: the home folder, the environment and the system ports."""
    mac = lm.is_macos()
    return lm.Context(
        home=Path.home(),
        env=os.environ,
        keychain=lm.SystemKeychain() if mac else None,
        launchd=lm.SystemLaunchd(os.getuid()) if mac else None,
        executable=shutil.which("omrs"),
    )


def _print_variables(plan: lm.Plan) -> None:
    if not plan.variables:
        return
    console.print("\nOld variables are still set. Rename them in your shell profile:")
    for old, new, where in plan.variables:
        console.print(f"  {escape(old)}  ->  {escape(new)}  (found in {escape(where)})")
    console.print("This command does not edit shell profiles.")


@app.command()
def migrate(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the plan and change nothing."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply the plan without asking."),
) -> None:
    """Move an install from before the rename to the OMRS names.

    Run with --dry-run first. The command renames the data and config folders,
    copies keychain entries (the old entries stay), and replaces login items.
    It never prints a secret value. Running it again changes nothing.
    """
    plan = lm.build_plan(_context())

    if plan.conflicts:
        console.print("[red]Cannot migrate. Nothing was changed:[/red]")
        for conflict in plan.conflicts:
            console.print(f"  {escape(conflict)}")
        console.print("Move or remove the new target by hand, then run this command again.")
        raise typer.Exit(code=1)

    if not plan.steps:
        console.print("Nothing left to migrate. The install already uses the OMRS names.")
        _print_variables(plan)
        return

    console.print("Plan:")
    for number, step in enumerate(plan.steps, start=1):
        console.print(f"  {number}. {escape(step.description)}")
    if any(step.kind == "keychain" for step in plan.steps):
        console.print("macOS may ask for permission to read the keychain.")
    if dry_run:
        console.print("Dry run: nothing was changed.")
        _print_variables(plan)
        return
    if not yes and not typer.confirm("Apply these steps?"):
        raise typer.Abort()

    failed = False
    for result in lm.apply_plan(plan):
        mark = "ok" if result.status == "done" else "[red]failed[/red]"
        console.print(f"  {mark}: {escape(result.step.description)} - {escape(result.detail)}")
        failed = failed or result.status == "failed"
    _print_variables(plan)
    if failed:
        console.print("\n[red]Migration stopped.[/red] Fix the problem and run the command again.")
        raise typer.Exit(code=1)
    console.print(
        "\nDone. Rename the MCP client key to 'omrs' and restart the client. "
        "Create new bearer tokens if you used any."
    )
