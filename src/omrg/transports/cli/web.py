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

import importlib
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
        int, typer.Option("--port", min=0, max=65535, help="TCP port. 0 picks a free port.")
    ] = 0,
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
) -> None:
    """Start the local web workspace on a loopback address."""
    _require_web_extra()
    from ..api.app import create_app
    from ..api.grants import RootGrants
    from ..api.lifespan import WebConfig, WorkspaceLock, WorkspaceLocked
    from ..api.runs_wiring import run_service_factory
    from ..api.security import AccessPolicy, validate_bind_host

    try:
        bind_host = validate_bind_host(host)
        roots = tuple(root or ())
        RootGrants.from_paths(roots)
        experiment_roots = tuple(experiment_root or ())
        _check_experiment_roots(experiment_roots)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {escape(str(exc))}", soft_wrap=True)
        raise typer.Exit(code=2) from None
    try:
        sock = _bind_socket(bind_host, port)
    except OSError as exc:
        console.print(f"[red]Error:[/red] Cannot listen on {bind_host}:{port}: {exc.strerror}")
        raise typer.Exit(code=1) from None

    workspace_dir = (workspace or default_workspace()).expanduser()
    try:
        # Probe only: the lifespan holds the lock for the server's lifetime.
        WorkspaceLock.acquire(workspace_dir).release()
    except WorkspaceLocked as exc:
        sock.close()
        console.print(f"[red]Error:[/red] {escape(str(exc))}", soft_wrap=True)
        raise typer.Exit(code=1) from None

    bound_port = sock.getsockname()[1]
    policy = AccessPolicy.for_launch(bind_host, bound_port)
    config = WebConfig(
        workspace=workspace_dir,
        host=bind_host,
        port=bound_port,
        roots=roots,
        experiment_roots=experiment_roots,
    )
    application = create_app(config, policy=policy, run_service_factory=run_service_factory)

    console.print("OMRG web workspace. Open this link in your browser (it works once):")
    console.print(policy.launch_url(), markup=False, highlight=False, soft_wrap=True)
    console.print("Press Ctrl+C to stop.")
    if _serve(application, sock) is False:
        console.print("[red]Error:[/red] The web server did not start. See the log above.")
        raise typer.Exit(code=1)
