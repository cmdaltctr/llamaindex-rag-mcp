"""Consented, owned notebook-editor launches (design D10, task 8.3).

The supervisor turns a compatible registration into a launch plan and hands
it to an injected :class:`ProcessLauncher`. It always binds to loopback,
creates a fresh token per launch, passes the token in a private file (never
in argv), and writes the manifest's startup-safety configuration into the
launcher's private working directory. It never adopts or stops a process
that it did not start.

An open request can also carry an :class:`EditorConnection` (task 8.6).
The plan then adds two private files to the launch directory: the
connection file (API address, experiment context and token file path) and
a separate API token file. One per-launch variable,
``OMRG_CONNECTION_FILE``, names the connection file. This module only
renders the files; the injected launcher writes them.
"""

from __future__ import annotations

import errno
import json
import secrets
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from omrg.core.plugins.manifest import PluginManifest, substitute
from omrg.core.plugins.registration import PluginRegistry

LOOPBACK_HOST = "127.0.0.1"
TOKEN_FILE_NAME = "access-token"  # noqa: S105 - a file name, not a secret
#: Private file that tells a notebook how to reach the OMRG API.
CONNECTION_FILE_NAME = "omrg_connection.json"
#: Private file that holds the experiment-bound API bearer credential.
API_TOKEN_FILE_NAME = "omrg-api-token"  # noqa: S105 - a file name, not a secret
#: The one per-launch variable; its value is the connection file path.
CONNECTION_ENV = "OMRG_CONNECTION_FILE"


class PluginConsentError(PermissionError):
    """A launch was requested without the user's consent."""


class PluginLaunchError(RuntimeError):
    """A launch was refused or failed. The message says what to do."""


class ProcessLauncher(Protocol):
    """Owned-process control. ``omrg.integrations.process_launcher`` implements it."""

    def create_launch_dir(self) -> Path:
        """Create a private (0o700) directory for one launch."""
        ...

    def discard_launch_dir(self, workdir: Path) -> None:
        """Remove a launch directory that was not used."""
        ...

    def port_available(self, host: str, port: int) -> bool:
        """Return whether nothing listens on ``host:port``."""
        ...

    def start(
        self,
        *,
        argv: Sequence[str],
        workdir: Path,
        host: str,
        port: int,
        files: Mapping[str, str],
        secrets: Sequence[str],
        environment: Mapping[str, str] | None = None,
    ) -> str:
        """Write ``files`` (0o600) into ``workdir``, start ``argv`` and return a launch id.

        ``environment`` holds per-launch variables (only ``OMRG_CONNECTION_FILE``).

        Raises:
            OSError: With ``errno.EADDRINUSE`` if the port is taken by another program.
        """
        ...

    def stop(self, launch_id: str) -> object:
        """Stop one owned launch: graceful first, then bounded escalation."""
        ...

    def stop_all(self) -> list[object]:
        """Stop every owned launch."""
        ...


@dataclass(frozen=True)
class EditorConnection:
    """How a launched notebook reaches the OMRG API. The token stays out of ``repr``.

    Attributes:
        api_url: Loopback base address of the OMRG web server.
        experiment_context: Experiment context id the credential is bound to.
        token: A bearer credential bound to that context.
    """

    api_url: str
    experiment_context: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class LaunchPlan:
    """Concrete argv, private files and per-launch variables for one launch."""

    argv: tuple[str, ...]
    files: Mapping[str, str] = field(repr=False)
    host: str
    port: int
    environment: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EditorSession:
    """One owned editor launch. The token stays out of ``repr``."""

    launch_id: str
    plugin: str
    notebook: Path
    host: str
    port: int
    token: str = field(repr=False)


def build_launch_plan(
    manifest: PluginManifest,
    executable: str,
    *,
    notebook: Path,
    host: str,
    port: int,
    launch_dir: Path,
    token: str,
    connection: EditorConnection | None = None,
) -> LaunchPlan:
    """Render the manifest's ``launch_notebook`` recipe.

    With ``connection``, add the connection file, the API token file and
    the ``OMRG_CONNECTION_FILE`` variable (see the module docstring).

    Raises:
        ValueError: If ``host`` is not the loopback address.
    """
    if host != LOOPBACK_HOST:
        raise ValueError(f"editor launches bind to loopback {LOOPBACK_HOST} only, not {host}")
    values = {
        "notebook_path": str(notebook),
        "host": host,
        "port": str(port),
        "token_file": str(launch_dir / TOKEN_FILE_NAME),
    }
    files = {TOKEN_FILE_NAME: token}
    config = manifest.launch.config_file
    if config is not None:
        files[config.name] = config.render_toml()
    environment: dict[str, str] = {}
    if connection is not None:
        details = {
            "api_url": connection.api_url,
            "experiment_context": connection.experiment_context,
            "token_file": str(launch_dir / API_TOKEN_FILE_NAME),
        }
        files[CONNECTION_FILE_NAME] = json.dumps(details, indent=2)
        files[API_TOKEN_FILE_NAME] = connection.token
        environment[CONNECTION_ENV] = str(launch_dir / CONNECTION_FILE_NAME)
    argv = (executable, *substitute(manifest.launch.args, values))
    return LaunchPlan(argv, files, host, port, environment)


class NotebookEditorSupervisor:
    """Starts and stops editor launches that this host owns.

    Args:
        registry: Plugin registrations; every open rechecks compatibility.
        launcher: Owned-process launcher, injected by composition.
        ports: Permitted loopback ports, tried in order.
        token_factory: Creates one access token per launch.
    """

    def __init__(
        self,
        registry: PluginRegistry,
        launcher: ProcessLauncher,
        *,
        ports: Sequence[int],
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    ) -> None:
        if not ports:
            raise ValueError("at least one permitted port is required")
        self._registry = registry
        self._launcher = launcher
        self._ports = tuple(ports)
        self._token_factory = token_factory
        self._sessions: dict[str, EditorSession] = {}
        self._lock = threading.Lock()

    def open(
        self,
        name: str,
        notebook: Path,
        *,
        consent: bool,
        connection: EditorConnection | None = None,
    ) -> EditorSession:
        """Recheck the plugin, then launch it on a free permitted port.

        Args:
            name: Registered plugin name.
            notebook: Notebook file to open.
            consent: The user's consent for this launch.
            connection: Optional OMRG API connection for the notebook.

        Raises:
            PluginConsentError: If ``consent`` is false.
            PluginLaunchError: If the plugin is not launchable, the notebook
                is missing, or no permitted port is free.
        """
        if not consent:
            raise PluginConsentError(
                "opening a notebook runs its Python with your permissions; consent is required"
            )
        path = Path(notebook).resolve()
        if not path.is_file():
            raise PluginLaunchError(f"notebook not found: {path}")
        state = self._registry.recheck(name)
        if not state.launchable or state.manifest is None:
            raise PluginLaunchError(f"{name} cannot start: {state.message}")
        for port in self._ports:
            session = self._try_port(name, state.manifest, state.executable, path, port, connection)
            if session is not None:
                return session
        tried = ", ".join(str(port) for port in self._ports)
        raise PluginLaunchError(
            f"no permitted port is free ({tried}). OMRG does not stop other programs; "
            f"close the program that uses the port or permit another port."
        )

    def _try_port(
        self,
        name: str,
        manifest: PluginManifest,
        exe: str,
        notebook: Path,
        port: int,
        connection: EditorConnection | None,
    ) -> EditorSession | None:
        if not self._launcher.port_available(LOOPBACK_HOST, port):
            return None
        token = self._token_factory()
        workdir = self._launcher.create_launch_dir()
        plan = build_launch_plan(
            manifest,
            exe,
            notebook=notebook,
            host=LOOPBACK_HOST,
            port=port,
            launch_dir=workdir,
            token=token,
            connection=connection,
        )
        secret_values = (token,) if connection is None else (token, connection.token)
        try:
            launch_id = self._launcher.start(
                argv=plan.argv,
                workdir=workdir,
                host=plan.host,
                port=plan.port,
                files=plan.files,
                secrets=secret_values,
                environment=plan.environment,
            )
        except OSError as exc:
            self._launcher.discard_launch_dir(workdir)
            if exc.errno == errno.EADDRINUSE:
                return None
            raise PluginLaunchError(f"{name} failed to start: {exc}") from exc
        session = EditorSession(launch_id, name, notebook, LOOPBACK_HOST, port, token)
        with self._lock:
            self._sessions[launch_id] = session
        return session

    def sessions(self) -> list[EditorSession]:
        """Return the owned sessions that have not been stopped."""
        with self._lock:
            return list(self._sessions.values())

    def stop(self, launch_id: str) -> object:
        """Stop one owned session. Notebook files are not touched.

        Raises:
            KeyError: If this supervisor did not start ``launch_id``.
        """
        with self._lock:
            if launch_id not in self._sessions:
                raise KeyError(f"not an owned editor launch: {launch_id}")
            del self._sessions[launch_id]
        return self._launcher.stop(launch_id)

    def stop_all(self) -> list[object]:
        """Stop every owned session (for example at agreed application shutdown)."""
        with self._lock:
            ids = list(self._sessions)
            self._sessions.clear()
        return [self._launcher.stop(launch_id) for launch_id in ids]
