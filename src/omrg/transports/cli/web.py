"""Web command — ``omrg web``.

Starts the local web workspace in one Uvicorn process with reload off.
The server binds to a loopback address only and picks a free port unless
``--port`` is given. The command does NOT run the CLI's legacy
process-default installer: the application lifespan builds and owns one
Engine. FastAPI is imported only inside the command, so ``omrg --help``
and the other commands work without the optional ``web`` extra. All
messages go to stderr (gotcha #5).
"""

from __future__ import annotations

import errno
import importlib
import logging
import socket
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.markup import escape

from ... import compose
from . import app, console

INSTALL_HINT = (
    'The web workspace needs the optional "web" extra. Install it with: '
    'pip install "omrg[web]"  (or, in a checkout: uv sync --extra web)'
)


#: Port used when neither ``--port`` nor a saved port names one.
DEFAULT_PORT = 8765


def resolve_port(given: int | None, saved: int | None) -> int:
    """Return the port to bind: ``--port``, else the saved port, else 8765.

    ``0`` from ``--port`` is kept: it asks for a free port.
    """
    if given is not None:
        return given
    return saved if saved is not None else DEFAULT_PORT


def _check_upload_mib(value: str | None) -> str | None:
    """Refuse a launch upload limit that is not a whole number from 1 to 2048.

    Typer then stops with a usage error (exit code 2) that names the
    option and its environment variable.
    """
    if value is None:
        return None
    # Imported here: a bare ``omrg`` call must not load workspace modules.
    from ...integrations.workspace_sqlite.settings import MAX_UPLOAD_LIMIT_MIB, MIN_UPLOAD_LIMIT_MIB

    low, high = MIN_UPLOAD_LIMIT_MIB, MAX_UPLOAD_LIMIT_MIB
    if not (value.isascii() and value.isdigit() and low <= int(value) <= high):
        raise typer.BadParameter(f"{value!r} is not a whole number from {low} to {high}.")
    return value


def default_workspace() -> Path:
    """Return the default workspace directory, ``~/.omrg/workspace``."""
    return Path.home() / ".omrg" / "workspace"


def _require_web_extra() -> None:
    """Exit with an install instruction when FastAPI or Uvicorn is missing."""
    for module in ("fastapi", "uvicorn"):
        try:
            importlib.import_module(module)
        except ImportError:
            console.print(f"[red]Error:[/red] {escape(INSTALL_HINT)}", soft_wrap=True)
            raise typer.Exit(code=1) from None


def _bind_socket(host: str, port: int) -> socket.socket:
    """Bind a listening socket now, so the real port is known before startup."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(128)
    except OSError:
        sock.close()
        raise
    sock.set_inheritable(True)
    return sock


def _serve(application: Any, sock: socket.socket) -> bool:
    """Run Uvicorn on *sock* in this process. Returns whether it started."""
    import uvicorn

    from ..api.lifespan import request_shutdown
    from ..api.security import RedactingFilter, install_log_redaction

    # Uvicorn logs request lines and startup tracebacks; scrub credentials
    # (including configured provider secrets) before any handler writes.
    install_log_redaction(RedactingFilter(_redaction_values()))

    config = uvicorn.Config(
        application,
        log_config=None,  # propagate to the CLI's stderr handlers
        reload=False,
        workers=1,
        lifespan="on",
        # An MCP client keeps a server-sent-events stream open. Without a
        # limit, Ctrl+C would wait for it to close.
        timeout_graceful_shutdown=5,
        proxy_headers=False,
        server_header=False,
        access_log=True,
    )

    class _Server(uvicorn.Server):
        def handle_exit(self, sig: int, frame: Any) -> None:
            # Close admission first: open event streams then end, so the
            # connection drain can finish and the lifespan shutdown runs.
            request_shutdown(application)
            super().handle_exit(sig, frame)

    server = _Server(config)
    server.run(sockets=[sock])
    return server.started


def _redaction_values() -> list[str]:
    """Return configured provider secrets for log redaction, if resolvable."""
    try:
        return [value for value in compose.redaction_values().values() if value]
    except Exception:
        return []


def _install_log_buffer() -> Any:
    """Attach the in-memory server log buffer to the root logger.

    The buffer keeps the last 1,000 records for Settings > Server log. Its
    redacting filter removes configured provider keys and credentials.
    """
    from ..api.log_buffer import LogBuffer

    buffer = LogBuffer(_redaction_values())
    logging.getLogger().addHandler(buffer)
    return buffer


def _check_experiment_roots(roots: tuple[Path, ...]) -> None:
    """Refuse an experiment root that is not an existing directory.

    Raises:
        ValueError: A root is missing or not a directory.
    """
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Experiment root {str(root)!r} is not an existing directory.")


@app.command()
def web(
    workspace: Annotated[
        Path | None,
        typer.Option(
            "--workspace",
            help="Directory for workspace records and uploads (default: ~/.omrg/workspace).",
        ),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(
            "--port",
            min=0,
            max=65535,
            help=(
                "TCP port. 0 picks a free port. Without it the saved port "
                f"(Settings > MCP) is used, else {DEFAULT_PORT}."
            ),
        ),
    ] = None,
    root: Annotated[
        list[Path] | None,
        typer.Option(
            "--root", help="Approve a directory for file access. Repeat for more directories."
        ),
    ] = None,
    host: Annotated[
        str,
        typer.Option("--host", help="Loopback address to bind (127.0.0.1, ::1 or localhost)."),
    ] = "127.0.0.1",
    experiment_root: Annotated[
        list[Path] | None,
        typer.Option(
            "--experiment-root",
            help=(
                "Approve a directory below which experiment workspaces may be registered. "
                "Repeat for more directories."
            ),
        ),
    ] = None,
    allow_origin: Annotated[
        list[str] | None,
        typer.Option(
            "--allow-origin",
            metavar="ORIGIN",
            help=(
                "Approve one extra loopback browser origin for this run, for example the "
                "address of an embedded preview (http://name.orca.localhost:57977). "
                "Repeat for more origins."
            ),
        ),
    ] = None,
    max_upload_mib: Annotated[
        str | None,
        typer.Option(
            "--max-upload-mib",
            envvar="WEB_MAX_UPLOAD_MIB",
            metavar="MIB",
            callback=_check_upload_mib,
            help=(
                "Per-file upload limit in MiB, 1 to 2048. Wins over the limit saved in "
                "Settings and locks it for this run. Without it the saved limit applies, "
                "else 50."
            ),
        ),
    ] = None,
) -> None:
    """Start the local web workspace on a loopback address."""
    _require_web_extra()
    from ..api.app import create_app
    from ..api.grants import RootGrants
    from ..api.lifespan import WebConfig, WorkspaceLock, WorkspaceLocked
    from ..api.origins import parse_extra_origin
    from ..api.runs_wiring import run_service_factory
    from ..api.security import AccessPolicy, validate_bind_host

    try:
        bind_host = validate_bind_host(host)
        roots = tuple(root or ())
        RootGrants.from_paths(roots)
        experiment_roots = tuple(experiment_root or ())
        _check_experiment_roots(experiment_roots)
        extra_origins = tuple(dict.fromkeys(parse_extra_origin(v) for v in allow_origin or ()))
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {escape(str(exc))}", soft_wrap=True)
        raise typer.Exit(code=2) from None
    workspace_dir = (workspace or default_workspace()).expanduser()
    from ...core.workspace import WorkspaceLayout
    from ...integrations.workspace_sqlite.settings import read_saved_web_port

    wanted_port = resolve_port(port, read_saved_web_port(WorkspaceLayout(workspace_dir).records))
    try:
        sock = _bind_socket(bind_host, wanted_port)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            console.print(
                f"[red]Error:[/red] Port {wanted_port} is in use. Start with --port <n> to "
                "choose another port, then save it in Settings > MCP.",
                soft_wrap=True,
            )
        else:
            console.print(
                f"[red]Error:[/red] Cannot listen on {bind_host}:{wanted_port}: {exc.strerror}"
            )
        raise typer.Exit(code=1) from None
    try:
        # Probe only: the lifespan holds the lock for the server's lifetime.
        WorkspaceLock.acquire(workspace_dir).release()
    except WorkspaceLocked as exc:
        sock.close()
        console.print(f"[red]Error:[/red] {escape(str(exc))}", soft_wrap=True)
        raise typer.Exit(code=1) from None

    bound_port = sock.getsockname()[1]
    policy = AccessPolicy.for_launch(bind_host, bound_port, extra_origins=extra_origins)
    config = WebConfig(
        workspace=workspace_dir,
        host=bind_host,
        port=bound_port,
        roots=roots,
        experiment_roots=experiment_roots,
        launch_upload_limit_mib=None if max_upload_mib is None else int(max_upload_mib),
    )
    log_buffer = _install_log_buffer()
    application = create_app(
        config, policy=policy, run_service_factory=run_service_factory, log_buffer=log_buffer
    )

    for origin in extra_origins:
        console.print(f"Approved extra origin: {origin}", markup=False, highlight=False)
    console.print("OMRG web workspace. Open this link in your browser (it works once):")
    console.print(policy.launch_url(), markup=False, highlight=False, soft_wrap=True)
    console.print("Press Ctrl+C to stop.")
    try:
        started = _serve(application, sock)
    finally:
        logging.getLogger().removeHandler(log_buffer)
    if started is False:
        console.print("[red]Error:[/red] The web server did not start. See the log above.")
        raise typer.Exit(code=1)
