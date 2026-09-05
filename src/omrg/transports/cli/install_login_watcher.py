"""Install command group — ``rag-mcp install-login-watcher``.

Interactive wizard and non-interactive installer for a macOS per-user
LaunchAgent that starts ``rag-mcp watch`` at login (OpenSpec change
``add-login-watcher-installer``). Prompts, output, and exit codes live
here; plist and launchctl mechanics live in ``_launchagent``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer

from . import _launchagent, app, console


def _is_macos() -> bool:
    """Return True when running on macOS (darwin)."""
    return sys.platform == "darwin"


def _stdin_is_interactive() -> bool:
    """Return True when standard input is an interactive terminal."""
    return sys.stdin.isatty()


def _contention_warning(collection: str) -> str | None:
    """Return the duplicate-watcher warning for the active adapter.

    The internal ingestion write lock is process-local: a watcher
    process and any other rag-mcp process never share it.  No backend
    currently claims cross-process write safety — any such claim needs
    a two-process concurrent-write experiment — so the warning fires
    for every registered backend today.  Wording is vector-store
    neutral.
    """
    from ...config import get_settings
    from ...core.vectordb import registry as vectordb_registry

    adapter = get_settings().vector_store
    if vectordb_registry.describe(adapter).get("cross_process_writes_safe"):
        return None
    return (
        f"Separate processes do not share rag-mcp's internal write lock, "
        f"and concurrent writes from separate processes are unverified for "
        f"the {adapter} vector-store backend. Running this watcher alongside "
        f"rag-mcp ingest or the MCP server can contend for collection "
        f"{collection!r}."
    )


def _gate_same_label_replacement(existing: Path, force: bool, interactive: bool, yes: bool) -> None:
    """Overwrite gate for a re-run that regenerates the same label.

    The existing plist is the exact file this run would write, so plain
    replacement semantics apply: confirm interactively or pass --force.
    """
    if not force:
        if interactive and not yes:
            if not typer.confirm(f"Overwrite existing watcher plist {existing}?", default=False):
                console.print("Aborted — existing plist left unchanged.")
                raise typer.Exit(code=1)
        else:
            console.print(
                f"[red]Error:[/red] LaunchAgent plist already exists: "
                f"{existing}. Pass --force to replace it."
            )
            raise typer.Exit(code=1)
    console.print(f"[yellow]Replacing existing watcher: {existing}[/yellow]")


def _confirm_different_label_removal(
    existing: Path, force: bool, interactive: bool, yes: bool
) -> bool:
    """Obtain consent for removing a differently-labelled watcher.

    The old watcher is a live duplicate (it starts at login alongside the
    new one), so it must go — but the installer never deletes another
    label's plist without explicit consent. Consent is an interactive
    confirmation or --force; anything else stops with the exact removal
    commands so the user can do it manually.

    Performs NO mutation: the removal itself is deferred until every
    later abort gate (wizard summary, ingest failure) has passed, so an
    abort always leaves the old watcher installed.
    """
    label = existing.stem
    uid = os.getuid()
    confirmed = force
    if not confirmed and interactive and not yes:
        confirmed = typer.confirm(
            f"A different watcher label already exists for this folder:\n"
            f"  {existing}\n"
            f"Remove it and install the new watcher?",
            default=False,
        )
    if not confirmed:
        console.print(
            f"[red]Error:[/red] a different watcher label already exists for "
            f"this folder:\n"
            f"  label: {label}\n"
            f"  plist: {existing}\n"
            f"Remove it first:\n"
            f"  launchctl bootout gui/{uid} {label}\n"
            f"  rm '{existing}'\n"
            f"Or re-run with --force to remove it automatically."
        )
        raise typer.Exit(code=1)
    return True


def _remove_old_watcher(existing: Path) -> None:
    """Boot out and delete an old watcher, after all abort gates passed.

    A failed bootout is ambiguous: usually the label was simply never
    loaded (the default install never calls --load), in which case
    deleting the plist is correct. But if ``launchctl print`` says the
    agent is still loaded, deleting the plist would leave two live
    watchers — so the install stops with the manual commands instead.
    """
    label = existing.stem
    uid = os.getuid()
    console.print(f"[yellow]Removing existing watcher: {label}[/yellow]")
    boot = _launchagent.run_launchctl(_launchagent.bootout_command(uid, label))
    if boot.returncode != 0:
        probe = _launchagent.run_launchctl(_launchagent.print_command(uid, label))
        if probe.returncode == 0:
            console.print(
                f"[red]Error:[/red] could not boot out the old watcher "
                f"(still loaded). The install was stopped and the old "
                f"watcher is unchanged.\n"
                f"Remove it manually, then re-run:\n"
                f"  launchctl bootout gui/{uid} {label}\n"
                f"  rm '{existing}'"
            )
            raise typer.Exit(code=1)
        console.print(f"[dim]Label {label} was not loaded; removing its plist only.[/dim]")
    existing.unlink(missing_ok=True)


def _prompt_watch_path() -> Path:
    """Prompt for a watch directory until validation passes."""
    while True:
        raw = typer.prompt("Folder to watch")
        try:
            return _launchagent.validate_watch_path(raw)
        except _launchagent.InstallerError as exc:
            console.print(f"[yellow]✗ {exc}[/yellow]")


def _print_launchctl_failure(operation: str, completed: subprocess.CompletedProcess) -> None:
    """Show a launchctl failure without hiding stdout/stderr (task 2.5)."""
    console.print(f"[red]Error:[/red] launchctl {operation} failed (exit {completed.returncode}).")
    if completed.stdout.strip():
        console.print(f"[dim]stdout: {completed.stdout.strip()}[/dim]")
    if completed.stderr.strip():
        console.print(f"[dim]stderr: {completed.stderr.strip()}[/dim]")


def _print_plan(
    plan: _launchagent.LaunchAgentPlan,
    *,
    initial_ingest: bool,
    load: bool,
    start: bool,
    dry_run: bool = False,
) -> None:
    """Print the installation plan — the wizard summary and dry-run body."""
    command = " ".join(_launchagent.build_program_arguments(plan))
    console.print("[bold]LaunchAgent plan[/bold]")
    console.print(f"  Label:          {plan.label}")
    console.print(f"  Watch folder:   {plan.watch_path}")
    console.print(f"  Collection:     {plan.collection}")
    console.print(f"  Debounce:       {plan.debounce}s")
    console.print(f"  Command:        {command}")
    console.print(f"  Plist path:     {plan.plist_path}")
    console.print(f"  Stdout log:     {plan.stdout_log}")
    console.print(f"  Stderr log:     {plan.stderr_log}")
    console.print(f"  RunAtLoad:      {plan.run_at_load}   KeepAlive: {plan.keep_alive}")
    console.print(f"  Catch-up ingest first: {'yes' if initial_ingest else 'no'}")
    console.print(f"  Load now: {'yes' if load else 'no'}   Start now: {'yes' if start else 'no'}")
    if dry_run:
        console.print("[dim]Dry run — no files written, launchctl not invoked.[/dim]")


def _run_catchup_ingest(watch_path: Path, collection: str) -> dict:
    """Run the initial catch-up ingest, mirroring ``rag-mcp ingest``.

    Resolves the collection's profile ONCE via the composition root and
    injects the resulting effective settings (design.md D5). Fails
    closed on resolution errors (design.md D8): an unresolvable profile
    aborts installation instead of silently ingesting under default
    settings — the running watcher tolerates that fallback per-file, but
    an install must not bake a broken baseline into a login-time agent.
    """
    import asyncio

    from ... import compose
    from ...core.ingestion import ingest_path_async

    try:
        effective = compose.build_profile_resolver().resolve(collection)
    except ValueError as exc:
        console.print(
            f"[red]Error:[/red] Cannot resolve the profile for collection {collection!r}: {exc}"
        )
        console.print("Fix the collection's profile configuration, then retry the installation.")
        raise typer.Exit(code=1) from None

    return asyncio.run(
        ingest_path_async(
            str(watch_path),
            collection_name=collection,
            effective_settings=effective,
        )
    )


@app.command()
def install_login_watcher(
    path: str | None = typer.Option(
        None, "--path", "-p", help="Directory to watch (required non-interactively)."
    ),
    collection: str | None = typer.Option(
        None,
        "--collection",
        "-c",
        help="Vector-store collection to ingest into (default: documents).",
    ),
    debounce: float | None = typer.Option(
        None, "--debounce", "-d", help="Debounce interval in seconds (default: 2.0)."
    ),
    label: str | None = typer.Option(
        None, "--label", help="Custom LaunchAgent label (default: derived)."
    ),
    command_path: str | None = typer.Option(
        None,
        "--command-path",
        help="Absolute path to the rag-mcp executable (overrides resolution).",
    ),
    initial_ingest: bool = typer.Option(
        False, "--initial-ingest", help="Run a catch-up ingest before installing."
    ),
    load: bool = typer.Option(False, "--load", help="Load the LaunchAgent after installation."),
    start: bool = typer.Option(
        False,
        "--start",
        help="Load and immediately start the watcher (implies --load).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview the plan without writing or calling launchctl."
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite an existing watcher plist and continue after ingest failure.",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Assume yes; skip interactive confirmations."
    ),
) -> None:
    """Install a macOS LaunchAgent that runs `rag-mcp watch` at login.

    Interactive terminals guide you through the setup; scripts pass
    options directly (add --yes to skip confirmations). Preview any
    platform with --dry-run; writing and launchctl are macOS-only.
    """
    from ...daemon.watcher import MIN_DEBOUNCE_SECONDS

    if not _is_macos() and not dry_run:
        console.print(
            "[red]Error:[/red] LaunchAgent installation is macOS-only. "
            "Use --dry-run to preview the plan on other platforms."
        )
        raise typer.Exit(code=1)

    interactive = _stdin_is_interactive()

    # ── Watch path: option, wizard prompt, or non-interactive error ──
    if path is not None:
        try:
            watch_path = _launchagent.validate_watch_path(path)
        except _launchagent.InstallerError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from None
    elif interactive:
        watch_path = _prompt_watch_path()
    else:
        console.print("[red]Error:[/red] --path is required in non-interactive mode.")
        raise typer.Exit(code=1)

    # ── Remaining values: wizard prompts or defaults ──
    if collection is None:
        collection = (
            typer.prompt("Vector-store collection", default="documents")
            if interactive
            else "documents"
        )
    if collection.startswith("-"):
        # A dash-prefixed name would be parsed as an option by the
        # generated `watch` argv at login (audit F4).
        console.print(
            f"[red]Error:[/red] Collection name must not start with '-' (got {collection!r})."
        )
        raise typer.Exit(code=1)
    if debounce is None:
        debounce = 2.0
    if debounce < MIN_DEBOUNCE_SECONDS:
        console.print(
            f"[red]Error:[/red] --debounce must be >= {MIN_DEBOUNCE_SECONDS}s (got {debounce}s)"
        )
        raise typer.Exit(code=1)
    if interactive and not initial_ingest and not yes:
        initial_ingest = typer.confirm(
            "Run an initial catch-up ingest of the folder?", default=False
        )

    # ── Plan: resolve executable, label, paths ──
    try:
        plan = _launchagent.build_plan(
            watch_path,
            collection,
            debounce,
            label=label,
            command_path=command_path,
        )
    except _launchagent.InstallerError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from None

    if dry_run:
        _print_plan(plan, initial_ingest=initial_ingest, load=load, start=start, dry_run=True)
        raise typer.Exit()

    # ── Existing watcher safety ──
    # A different-label removal is only *consented* to here; the actual
    # bootout/delete is deferred to just before write_plist so every
    # later abort gate leaves the old watcher installed.
    pending_removal: Path | None = None
    existing = _launchagent.find_existing_plist(plan)
    if existing is not None:
        warning = _contention_warning(collection)
        if warning:
            console.print(f"[yellow]⚠ An existing watcher was detected. {warning}[/yellow]")
        if existing == plan.plist_path:
            _gate_same_label_replacement(existing, force, interactive, yes)
        elif _confirm_different_label_removal(existing, force, interactive, yes):
            pending_removal = existing

    # ── Wizard summary confirmation before any mutation ──
    if interactive and not yes:
        _print_plan(plan, initial_ingest=initial_ingest, load=load, start=start)
        if not typer.confirm("Install with these settings?", default=False):
            console.print("Aborted — nothing was written.")
            raise typer.Exit(code=1)

    # ── Catch-up ingest runs before any write or load (spec) ──
    if initial_ingest:
        console.print("Running initial catch-up ingest…")
        try:
            result = _run_catchup_ingest(watch_path, collection)
        except typer.Exit:
            raise
        except Exception as exc:  # noqa: BLE001 - surface every ingest failure
            result = {"status": "error", "message": str(exc)}
        if result.get("status") == "error":
            message = result.get("message", "unknown error")
            console.print(f"[red]Error:[/red] Initial ingest failed: {message}")
            proceed = force or (
                interactive
                and not yes
                and typer.confirm("Continue installing anyway?", default=False)
            )
            if not proceed:
                console.print(
                    "Installation stopped — no LaunchAgent was installed. The "
                    "failed catch-up ingest may have written partial results."
                )
                raise typer.Exit(code=1)
            console.print("[yellow]Continuing after ingest failure (--force).[/yellow]")
        else:
            files = result.get("files_indexed", 0)
            chunks = result.get("chunks_created", 0)
            console.print(
                f"[green]✓[/green] Catch-up ingest complete: {files} file(s) "
                f"indexed, {chunks} chunk(s) created."
            )

    # ── Write, report, and optionally load/start ──
    # Deferred different-label removal executes here: every abort gate
    # (summary confirmation, ingest failure) has now passed, so removing
    # the old watcher can no longer strand the user with none.
    if pending_removal is not None:
        _remove_old_watcher(pending_removal)
    _launchagent.write_plist(plan, _launchagent.render_plist(plan), overwrite=True)
    console.print(f"[green]✓[/green] LaunchAgent installed: {plan.label}")
    console.print(f"  Plist: {plan.plist_path}")
    console.print(f"  Logs:  {plan.stdout_log}")
    console.print(f"         {plan.stderr_log}")

    if load or start:
        uid = os.getuid()
        # Best-effort bootout first: replaces a previously loaded agent
        # and is harmless (failure ignored) when none is loaded.
        _launchagent.run_launchctl(_launchagent.bootout_command(uid, plan.label))
        boot = _launchagent.run_launchctl(_launchagent.bootstrap_command(uid, plan.plist_path))
        if boot.returncode != 0:
            _print_launchctl_failure("bootstrap", boot)
            raise typer.Exit(code=1)
        console.print(f"[green]✓[/green] Loaded into gui/{uid} (starts at login).")
        if start:
            kick = _launchagent.run_launchctl(_launchagent.kickstart_command(uid, plan.label))
            if kick.returncode != 0:
                _print_launchctl_failure("kickstart", kick)
                raise typer.Exit(code=1)
            console.print("[green]✓[/green] Watcher started now.")
    else:
        console.print(
            "The watcher will start at your next login. Start it now with "
            "--load (or --start), or run: launchctl bootstrap "
            f"gui/{os.getuid()} {plan.plist_path}"
        )
