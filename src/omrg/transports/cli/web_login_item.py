"""Login item commands — ``omrg web install | uninstall | status | restart | open``.

Keeps the web app running on a Mac as a per-user LaunchAgent
(OpenSpec change ``add-web-login-item``). Prompts, output and exit codes
live here; plan and plist mechanics live in ``_web_login_item``.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from rich.markup import escape

from . import _launchagent, console
from . import _web_login_item as core
from .web import resolve_port, web_app

#: Seconds ``install`` and ``restart`` wait for the app to answer (design D8).
START_TIMEOUT = 60.0
#: Seconds ``restart`` waits for the old process to stop (design D8).
STOP_TIMEOUT = 15.0
#: Seconds between two health requests while waiting.
_POLL_SECONDS = 1.0
_HOST = "127.0.0.1"

# Seams: tests replace these, so no test touches the real machine.
_clock = time.monotonic
_sleep = time.sleep


def _is_macos() -> bool:
    """Return True when running on macOS (darwin)."""
    return sys.platform == "darwin"


def _stdin_is_interactive() -> bool:
    """Return True when standard input is an interactive terminal."""
    return sys.stdin.isatty()


def _port_in_use(host: str, port: int) -> bool:
    """Return True when something accepts connections on *host*:*port*."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) == 0


def _open_url(url: str) -> int:
    """Open *url* in the default browser with the macOS ``open`` command."""
    return subprocess.run(["open", url], check=False).returncode  # noqa: S603,S607 - fixed argv, no shell


def _say(text: str) -> None:
    console.print(text, markup=False, highlight=False, soft_wrap=True)


def _fail(message: str, code: int = 1) -> NoReturn:
    console.print(f"[red]Error:[/red] {escape(message)}", soft_wrap=True)
    raise typer.Exit(code=code)


def _target_port(plan: core.WebLoginItemPlan) -> int:
    """Return the port the server will bind: ``--port``, else the saved port, else 8765."""
    from ...core.workspace import WorkspaceLayout
    from ...integrations.workspace_sqlite.settings import read_saved_web_port

    saved = read_saved_web_port(WorkspaceLayout(core.workspace_dir(plan)).records)
    return resolve_port(plan.port, saved)


def _wait_for_health(
    port_of: Callable[[], int], timeout: float = START_TIMEOUT
) -> dict[str, Any] | None:
    """Poll ``GET /v1/health`` until the app answers or *timeout* seconds pass.

    *port_of* is called at each poll, because a restart can move the app to a
    port that was changed in Settings.
    """
    deadline = _clock() + timeout
    while True:
        body = core.fetch_health(_HOST, port_of())
        if body is not None:
            return body
        if _clock() >= deadline:
            return None
        _sleep(_POLL_SECONDS)


def _agent_running(uid: int) -> bool:
    """Return True when launchd still has a live process for the login item.

    ``launchctl print`` shows ``pid = N`` at the first indent level only while
    the process lives. Health is not enough: Uvicorn closes its socket first and
    finishes the cleanup after that.
    """
    done = _launchctl(_launchagent.print_command(uid, core.LABEL))
    return done.returncode == 0 and re.search(r"^\tpid = \d+$", done.stdout, re.M) is not None


def _wait_until_stopped(port: int, uid: int, timeout: float = STOP_TIMEOUT) -> bool:
    """Poll until nothing answers health on *port* and the process has gone."""
    deadline = _clock() + timeout
    while core.fetch_health(_HOST, port) is not None or _agent_running(uid):
        if _clock() >= deadline:
            return False
        _sleep(_POLL_SECONDS)
    return True


def _wait_for_login_item(plan: core.WebLoginItemPlan, port: int) -> tuple[bool, bool]:
    """Wait until the login item itself is up on *port*.

    Health alone is not proof: a hand-run ``omrg web`` on the same port also
    answers. Only a login-item server writes the link file, so the file must
    name this port too. Returns ``(started, something_answers)``.
    """
    deadline = _clock() + START_TIMEOUT
    answered = False
    while True:
        if core.fetch_health(_HOST, port) is not None:
            answered = True
            info = _read_link(plan)
            if info is not None and info.port == port:
                return True, True
        if _clock() >= deadline:
            return False, answered
        _sleep(_POLL_SECONDS)


def _report_launchctl_failure(operation: str, done: subprocess.CompletedProcess[str]) -> NoReturn:
    console.print(f"[red]Error:[/red] launchctl {operation} failed (exit {done.returncode}).")
    for name, text in (("stdout", done.stdout), ("stderr", done.stderr)):
        if text.strip():
            _say(f"{name}: {text.strip()}")
    raise typer.Exit(code=1)


def _plan_warnings(plan: core.WebLoginItemPlan, port: int) -> list[str]:
    """Return the messages ``install`` shows with the plan."""
    warnings: list[str] = []
    checkout = core.checkout_warning(plan.command_path)
    if checkout:
        warnings.append(checkout)
    settings = core.settings_message(plan.home, Path.cwd())
    if settings:
        warnings.append(settings)
    if _port_in_use(_HOST, port):
        warnings.append(
            f"Port {port} is already in use. Something else may be running 'omrg web'. "
            "Stop that process first, or the login item cannot start."
        )
    return warnings


def _print_plan(plan: core.WebLoginItemPlan, warnings: list[str], *, dry_run: bool) -> None:
    console.print("[bold]Web login item plan[/bold]")
    _say(f"  Label:        {plan.label}")
    _say(f"  Command:      {' '.join(core.build_program_arguments(plan))}")
    _say(f"  Plist path:   {plan.plist_path}")
    _say(f"  Runs in:      {plan.working_directory}")
    _say(f"  Stdout log:   {plan.stdout_log}")
    _say(f"  Stderr log:   {plan.stderr_log}")
    for warning in warnings:
        console.print(f"[yellow]Warning:[/yellow] {escape(warning)}", soft_wrap=True)
    if dry_run:
        console.print("[dim]Dry run: no files written, launchctl not called.[/dim]")


@web_app.command()
def install(
    workspace: Annotated[
        Path | None,
        typer.Option("--workspace", help="Workspace folder (default: ~/.omrg/workspace)."),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(
            "--port",
            min=1,
            max=65535,
            help="TCP port. Without it the saved port (Settings > MCP) is used, else 8765.",
        ),
    ] = None,
    root: Annotated[
        list[Path] | None,
        typer.Option("--root", help="Approve a directory for file access. Repeat for more."),
    ] = None,
    experiment_root: Annotated[
        list[Path] | None,
        typer.Option(
            "--experiment-root",
            help="Approve a directory for experiment workspaces. Repeat for more.",
        ),
    ] = None,
    command_path: Annotated[
        str | None,
        typer.Option(
            "--command-path",
            help="Absolute path to the omrg executable (default: the one on your PATH).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show the plan without writing or calling launchctl."),
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing login item.")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmations.")] = False,
) -> None:
    """Install the web app as a macOS login item and start it.

    The login item starts at every login, restarts after a crash, and
    reads its settings from ~/.omrg/.env.
    """
    if not _is_macos() and not dry_run:
        _fail("Login items are macOS-only. Use --dry-run to preview the plan on other platforms.")
    try:
        plan = core.build_plan(
            workspace=workspace,
            port=port,
            roots=tuple(root or ()),
            experiment_roots=tuple(experiment_root or ()),
            command_path=command_path,
        )
    except _launchagent.InstallerError as exc:
        _fail(str(exc))
    target_port = _target_port(plan)
    warnings = _plan_warnings(plan, target_port)
    _print_plan(plan, warnings, dry_run=dry_run)
    if dry_run:
        raise typer.Exit()

    if plan.plist_path.exists() and not force:
        _fail(
            f"A login item already exists: {plan.plist_path}. Pass --force to replace it, "
            "or run 'omrg web uninstall' first."
        )
    interactive = _stdin_is_interactive()
    if core.checkout_warning(plan.command_path) and not yes:
        if not interactive:
            _fail("The executable sits in a source checkout. Pass --yes to accept that.")
        if not typer.confirm("Install a login item that depends on this checkout?", default=False):
            _fail("Aborted. Nothing was written.")
    if interactive and not yes and not typer.confirm("Install with these settings?", default=False):
        _fail("Aborted. Nothing was written.")

    plan.working_directory.mkdir(parents=True, exist_ok=True)
    plan.stdout_log.parent.mkdir(parents=True, exist_ok=True)
    _launchagent.write_plist_atomic(plan.plist_path, core.render_plist(plan), force)
    console.print(f"[green]✓[/green] Login item written: {escape(str(plan.plist_path))}")

    uid = os.getuid()
    # Unload a copy that is already loaded; it is harmless when none is.
    _launchagent.run_launchctl(_launchagent.bootout_command(uid, plan.label))
    booted = _launchagent.run_launchctl(_launchagent.bootstrap_command(uid, plan.plist_path))
    if booted.returncode != 0:
        _report_launchctl_failure("bootstrap", booted)
    console.print(f"[green]✓[/green] Loaded into gui/{uid}. It starts at every login.")

    _say(
        f"Waiting up to {int(START_TIMEOUT)} seconds for the app to answer on port {target_port}..."
    )
    started, answered = _wait_for_login_item(plan, target_port)
    if not started and answered:
        _fail(
            f"Something answers on port {target_port}, but it is not the login item: it wrote "
            "no sign-in link. Another 'omrg web' may hold the port. Stop that process. "
            f"launchd retries every {core.THROTTLE_SECONDS} seconds. Read the error log: "
            f"{plan.stderr_log}"
        )
    if not started:
        _fail(
            f"The app did not answer within {int(START_TIMEOUT)} seconds. The login item stays "
            f"installed. Read the error log: {plan.stderr_log}. "
            "Run 'omrg web status' to check again."
        )
    body = core.fetch_health(_HOST, target_port) or {}
    console.print(
        f"[green]✓[/green] The app is running (version {escape(str(body.get('version', '?')))})."
    )
    _say("Open it in your browser with: omrg web open")


def _launchctl(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a launchctl argv; a non-macOS platform stops the command with a message."""
    try:
        return _launchagent.run_launchctl(cmd)
    except _launchagent.InstallerError as exc:
        _fail(str(exc))


@web_app.command()
def uninstall(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation.")] = False,
) -> None:
    """Stop the login item and remove its LaunchAgent file.

    The workspace, the logs and your data stay where they are.
    """
    plist_path, _, _ = _launchagent.compute_paths(core.LABEL)
    if not plist_path.exists():
        _say(f"Nothing is installed: there is no login item file at {plist_path}.")
        raise typer.Exit()
    if not yes and not typer.confirm("Stop the app and remove the login item?", default=False):
        _fail("Aborted. The login item is unchanged.")

    uid = os.getuid()
    # bootout sends SIGTERM, so the app shuts down in a clean way.
    done = _launchctl(_launchagent.bootout_command(uid, core.LABEL))
    if done.returncode != 0:
        # A failed bootout usually means the agent was never loaded. If it is
        # still loaded, keep the plist so nothing runs without a file.
        still_loaded = _launchctl(_launchagent.print_command(uid, core.LABEL)).returncode == 0
        if still_loaded:
            _fail(
                f"launchctl bootout failed (exit {done.returncode}) and the agent is still "
                f"loaded. The login item file is kept. "
                f"Run: launchctl bootout gui/{uid}/{core.LABEL}"
            )
    plist_path.unlink(missing_ok=True)
    console.print("[green]✓[/green] Login item removed. Your workspace and logs are kept.")


def _installed_plan() -> tuple[Path, core.WebLoginItemPlan | None]:
    """Return the plist path and the plan that its content describes.

    The plan is ``None`` when no plist exists. A plist that ``install``
    did not write stops the command.
    """
    plist_path, _, _ = _launchagent.compute_paths(core.LABEL)
    if not plist_path.exists():
        return plist_path, None
    item = core.read_installed(plist_path)
    try:
        if item is None:
            raise _launchagent.InstallerError(
                f"{plist_path} was not written by 'omrg web install'. "
                "Remove it by hand, then run 'omrg web install'."
            )
        plan = core.build_plan(
            workspace=item.workspace, port=item.port, command_path=item.command_path
        )
    except _launchagent.InstallerError as exc:
        _fail(str(exc))
    return plist_path, plan


def _read_link(plan: core.WebLoginItemPlan) -> core.LinkInfo | None:
    """Parse the sign-in link file of the running server, if it exists."""
    try:
        return core.parse_link(core.link_file(plan).read_text(encoding="utf-8"))
    except OSError:
        return None


def _current_port(plan: core.WebLoginItemPlan) -> int:
    """Return the port of the running server (design D6): the link file, else the saved rule."""
    info = _read_link(plan)
    return info.port if info is not None else _target_port(plan)


@web_app.command()
def status(
    json_output: Annotated[
        bool, typer.Option("--json", help="Print one JSON object instead of text.")
    ] = False,
) -> None:
    """Show whether the login item is installed, running and answering.

    Exits 0 when the app answers and 1 otherwise.
    """
    plist_path, plan = _installed_plan()
    if plan is None:
        if json_output:
            typer.echo(json.dumps({"installed": False, "plist": str(plist_path)}), err=True)
        else:
            _say("The login item is not installed. Run 'omrg web install' to install it.")
        raise typer.Exit(code=1)

    uid = os.getuid()
    loaded = _launchctl(_launchagent.print_command(uid, plan.label)).returncode == 0
    port = _current_port(plan)
    body = core.fetch_health(_HOST, port)
    running_version = None if body is None else body.get("version")
    installed_version = core.installed_version(plan.command_path)
    restart_needed = (
        running_version is not None
        and installed_version is not None
        and running_version != installed_version
    )
    facts = {
        "installed": True,
        "loaded": loaded,
        "running": body is not None,
        "running_version": running_version,
        "installed_version": installed_version,
        "restart_needed": restart_needed,
        "workspace": str(core.workspace_dir(plan)),
        "port": port,
        "address": f"http://{_HOST}:{port}/",
        "plist": str(plan.plist_path),
        "stdout_log": str(plan.stdout_log),
        "stderr_log": str(plan.stderr_log),
    }
    if json_output:
        typer.echo(json.dumps(facts, indent=2), err=True)
    else:
        console.print("[bold]Web login item[/bold]")
        for line in core.status_lines(facts):
            _say(line)
    raise typer.Exit(code=0 if body is not None else 1)


@web_app.command()
def restart() -> None:
    """Restart the login item, for example after installing a newer copy.

    A restart signs the browser out. Run 'omrg web open' to sign in again.
    """
    _, plan = _installed_plan()
    if plan is None:
        _fail("The login item is not installed. Run 'omrg web install' first.")
    uid = os.getuid()
    port = _current_port(plan)
    if core.fetch_health(_HOST, port) is not None or _agent_running(uid):
        # SIGTERM lets the app shut down in a clean way. kickstart -k would
        # send an unspecified signal and could skip the clean shutdown.
        done = _launchctl(_launchagent.kill_command(uid, plan.label, "SIGTERM"))
        if done.returncode != 0:
            _report_launchctl_failure("kill", done)
        if not _wait_until_stopped(port, uid):
            _fail(
                f"The app did not stop within {int(STOP_TIMEOUT)} seconds. "
                "Run 'omrg web status' to see its state."
            )
    # A clean exit does not trigger KeepAlive, so start the app by hand.
    done = _launchctl(_launchagent.kickstart_command(uid, plan.label))
    if done.returncode != 0:
        _report_launchctl_failure("kickstart", done)

    _say(f"Waiting up to {int(START_TIMEOUT)} seconds for the app to answer...")
    body = _wait_for_health(lambda: _current_port(plan))
    if body is None:
        _fail(
            f"The app did not answer within {int(START_TIMEOUT)} seconds. "
            f"Read the error log: {plan.stderr_log}. Run 'omrg web status' to check again."
        )
    version = escape(str(body.get("version", "?")))
    console.print(f"[green]✓[/green] The app is running (version {version}).")
    _say("The browser is signed out. Run 'omrg web open' to sign in.")


@web_app.command(name="open")
def open_app(
    print_link: Annotated[
        bool,
        typer.Option(
            "--print",
            help="Print the full sign-in link to stderr and open no browser.",
        ),
    ] = False,
) -> None:
    """Open the app in the browser with a fresh sign-in link.

    The command reads the link that the running login item wrote. It never
    starts a server. It prints the address without the secret; use --print
    for a browser that this command cannot reach.
    """
    _, plan = _installed_plan()
    info = None if plan is None else _read_link(plan)
    # A crash leaves an old link file behind, so check that the app answers.
    if info is None or core.fetch_health(info.host, info.port) is None:
        _fail("The login item is not running. Run 'omrg web status' to see why.")
    if print_link:
        _say(info.url)
        return
    if _open_url(info.url) != 0:
        _fail(f"Could not open the browser. Run 'omrg web open --print' and open {info.address}.")
    _say(f"Opened {info.address} in your browser.")
