"""Web runtime ownership through the FastAPI lifespan (design D6, D8).

Startup creates the private workspace, canonicalises the approved roots,
prepares upload storage, builds ONE Engine through the injected factory
(``compose.build_engine`` by default) and, when given, starts the run
service. It also builds the per-launch experiment engines (only when
``--experiment-root`` approved a root) and the plugin host (registry and
editor supervisor). Building them starts no process and builds no
context Engine. Nothing is installed as a process default.

Shutdown (:func:`shutdown_runtime`) stops admission, lets the run service
shut down (cancel queued work, request cooperative cancellation, wait for
safe boundaries), waits for admitted requests, stops the owned notebook
editors (this removes their private launch directories), revokes their
notebook credentials, closes the experiment Engines, and only then closes
the live Engine. Long-lived streams must end when ``runtime.admission.is_open``
becomes false, or shutdown waits for them.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Request

from ...core.ingestion.settings import DEFAULT_INGEST_EXTENSIONS
from ...core.workspace import WorkspaceLayout
from ...integrations.workspace_sqlite.schema import make_private_dirs

# Re-exported: both names lived here before the move to ``admission.py``.
from .admission import Admission as Admission
from .admission import AdmissionClosed as AdmissionClosed
from .grants import RootGrants
from .install_job import InstallJob
from .live_settings import initial_upload_limit
from .provider_state import build_engine, load_providers
from .settings_launch import prepare_settings
from .uploads import DEFAULT_MAX_UPLOAD_BYTES, UploadStore

logger = logging.getLogger(__name__)

#: Built frontend assets inside the installed package.
PACKAGED_STATIC_DIR = Path(__file__).resolve().parent / "static"
#: The marimo manifest shipped beside the source tree (not in the wheel).
SHIPPED_PLUGIN_MANIFESTS: tuple[Path, ...] = (
    Path(__file__).resolve().parents[4] / "plugins" / "marimo" / "manifest.json",
)
#: Loopback ports a notebook editor may use, tried in order.
DEFAULT_PLUGIN_PORTS: tuple[int, ...] = (2719, 2720, 2721)


@dataclass(frozen=True)
class WebConfig:
    """Launch options for one web server.

    Attributes:
        workspace: Directory for application records and managed uploads.
        host: Loopback address the server binds.
        port: Bound TCP port (needed for Host and Origin checks).
        roots: Operator-approved directories (``--root``).
        max_upload_bytes: Per-file upload limit when no launch option or
            ``web_max_upload_mib`` value applies.
        launch_upload_limit_mib: Per-file upload limit in MiB from
            ``--max-upload-mib`` or ``WEB_MAX_UPLOAD_MIB``, or ``None``. It
            wins over the ``web_max_upload_mib`` file value and locks it for
            this launch.
        static_dir: Built frontend assets, or ``None`` for API only.
        upload_extensions: Ingestible extensions accepted for upload. The
            default is the existing ``ingestion.ingest_extensions`` default;
            ingestion still applies the target collection's profile set.
        experiment_roots: Operator-approved experiment roots
            (``--experiment-root``). Requests never add a root.
        plugin_ports: Loopback ports a notebook editor may use.
        plugin_runtime_dir: Private parent of editor launch directories
            (default ``<workspace>/run/editors``).
        experiments_factory: Builds the experiment engines; tests pass a
            fake. ``None`` uses :func:`default_experiments_factory`.
        plugins_factory: Builds the plugin host; tests pass fakes.
            ``None`` uses :func:`default_plugins_factory`.
    """

    workspace: Path
    host: str = "127.0.0.1"
    port: int = 0
    roots: tuple[Path, ...] = ()
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    launch_upload_limit_mib: int | None = None
    static_dir: Path | None = PACKAGED_STATIC_DIR
    upload_extensions: tuple[str, ...] = DEFAULT_INGEST_EXTENSIONS
    experiment_roots: tuple[Path, ...] = ()
    plugin_ports: tuple[int, ...] = DEFAULT_PLUGIN_PORTS
    plugin_runtime_dir: Path | None = None
    experiments_factory: Callable[[WebConfig], Any] | None = field(default=None, compare=False)
    plugins_factory: Callable[[WebConfig], PluginHost] | None = field(default=None, compare=False)


@dataclass
class PluginHost:
    """Plugin registrations and owned editor launches of one launch.

    Attributes:
        repository: Workspace records that hold the registrations.
        registry: ``PluginRegistry`` over those records.
        editors: ``NotebookEditorSupervisor``; it starts nothing until a
            consented open request.
        manifests: Approved manifest files (the shipped marimo manifest).
        manifest_dir: Directory whose manifests the operator approved
            (``<workspace>/plugins``).
        executable_dirs: Directories an executable may come from: the
            server's ``PATH`` at launch and ``<workspace>/plugins``.
        editor_contexts: Launch id to experiment context id.
        editor_cleanups: Launch id to the call that revokes the editor's
            notebook credential. Stop and shutdown run it.
    """

    repository: Any
    registry: Any
    editors: Any
    manifests: tuple[Path, ...]
    manifest_dir: Path
    executable_dirs: tuple[Path, ...]
    editor_contexts: dict[str, str] = field(default_factory=dict)
    editor_cleanups: dict[str, Callable[[], object]] = field(default_factory=dict)


class RunServiceHook(Protocol):
    """Lifecycle the workspace run service must offer.

    ``omrs.core.workspace.RunService`` has this shape. ``shutdown`` must
    stop admission, cancel queued work, request cooperative cancellation of
    the active run, and return when it reached a safe boundary. The Engine
    stays open until ``shutdown`` returns.
    """

    async def start(self) -> object:
        """Begin accepting runs (for example, mark interrupted runs)."""

    async def shutdown(self) -> object:
        """Stop, cancel and wait for safe boundaries as described above."""


#: Builds the run service from the started runtime.
RunServiceFactory = Callable[["WebRuntime"], RunServiceHook]


class WorkspaceLocked(RuntimeError):
    """Another process holds the workspace."""


class WorkspaceLock:
    """Exclusive, advisory lock on ``<workspace>/.lock``.

    The operating system releases the lock when the process ends, so a
    crash never leaves a stale lock.
    """

    def __init__(self, path: Path, fd: int) -> None:
        """Keep the open lock file; use :meth:`acquire`."""
        self.path = path
        self._fd: int | None = fd

    @classmethod
    def acquire(cls, workspace: Path) -> WorkspaceLock:
        """Lock *workspace* for this process.

        Raises:
            WorkspaceLocked: Another process holds the lock.
        """
        workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = WorkspaceLayout(workspace).lock
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise WorkspaceLocked(
                f"Another OMRS web server is using the workspace {workspace}. "
                "Stop it, or start this one with a different --workspace."
            ) from None
        return cls(path, fd)

    def release(self) -> None:
        """Release the lock. Safe to call more than once."""
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None


@dataclass
class WebRuntime:
    """Resources owned by one running web server.

    ``upload_limit_source`` names where the limit in force came from:
    ``launch``, ``config-file`` or ``default``.
    """

    config: WebConfig
    engine: Any
    grants: RootGrants
    uploads: UploadStore
    admission: Admission = field(default_factory=Admission)
    installs: InstallJob = field(default_factory=InstallJob)
    run_service: RunServiceHook | None = None
    loop: asyncio.AbstractEventLoop | None = None
    experiments: Any | None = None
    plugins: PluginHost | None = None
    profiles: Any | None = None
    chats: Any | None = None
    providers: Any | None = None
    upload_limit_source: str = "default"
    _shut_down: bool = False


def default_engine_factory(catalogue: Any = None, provider_source: Any = None) -> Any:
    """Build the Engine through the composition root (no process default).

    Args:
        catalogue: Where user profile tags resolve. ``omrs web`` passes the
            catalogue of its own workspace.
        provider_source: Returns saved LLM provider values (design D3), or ``None``.
    """
    from ... import compose

    extra = {} if provider_source is None else {"provider_source": provider_source}
    return compose.build_engine(catalogue=catalogue, **extra)


def default_experiments_factory(config: WebConfig) -> Any | None:
    """Build ``ExperimentEngines`` for the approved roots, or ``None`` without roots.

    The base settings come from the composition root
    (``compose_engine.experiment_base_settings``). No context Engine is
    built here; each one is built on its first admission.
    """
    if not config.experiment_roots:
        return None
    from ...compose_engine import experiment_base_settings
    from ...compose_experiments import ExperimentEngines, experiment_registry

    registry = experiment_registry(config.experiment_roots)
    return ExperimentEngines(registry, experiment_base_settings())


def default_plugins_factory(config: WebConfig) -> PluginHost:
    """Build the plugin registry and editor supervisor. Starts no process."""
    from ...core.plugins import NotebookEditorSupervisor, PluginRegistry
    from ...integrations.process_launcher import OwnedProcessLauncher, SubprocessProbeRunner
    from ...integrations.workspace_sqlite import SqliteWorkspaceRepository

    repository = SqliteWorkspaceRepository(WorkspaceLayout(config.workspace).records)
    registry = PluginRegistry(repository, SubprocessProbeRunner())
    runtime_dir = config.plugin_runtime_dir or config.workspace / "run" / "editors"
    editors = NotebookEditorSupervisor(
        registry, OwnedProcessLauncher(runtime_dir), ports=config.plugin_ports
    )
    plugin_dir = config.workspace / "plugins"
    path_dirs = tuple(Path(item) for item in os.environ.get("PATH", "").split(os.pathsep) if item)
    return PluginHost(
        repository,
        registry,
        editors,
        manifests=tuple(path for path in SHIPPED_PLUGIN_MANIFESTS if path.is_file()),
        manifest_dir=plugin_dir,
        executable_dirs=(*path_dirs, plugin_dir),
    )


async def shutdown_runtime(runtime: WebRuntime) -> None:
    """Stop admission, drain the run service and requests, then close the Engine.

    Safe to call more than once.

    Args:
        runtime: The runtime to shut down.
    """
    if runtime._shut_down:
        return
    runtime._shut_down = True
    runtime.admission.close()
    if runtime.run_service is not None:
        try:
            await runtime.run_service.shutdown()
        except Exception:
            logger.exception("Run service shutdown failed; closing the engine anyway.")
    await runtime.admission.wait_idle()
    if runtime.plugins is not None:
        try:
            # Graceful stop with bounded escalation can take seconds.
            await asyncio.to_thread(runtime.plugins.editors.stop_all)
        except Exception:
            logger.exception("Stopping notebook editors failed during web shutdown.")
        _revoke_editor_credentials(runtime.plugins)
    if runtime.experiments is not None:
        try:
            runtime.experiments.close()
        except Exception:
            logger.exception("Experiment engines did not close during web shutdown.")
    try:
        runtime.engine.close()
    except Exception:
        logger.exception("Engine close failed during web shutdown.")


def _revoke_editor_credentials(plugins: PluginHost) -> None:
    """Revoke every notebook credential that an editor of this launch held."""
    while plugins.editor_cleanups:
        _, cleanup = plugins.editor_cleanups.popitem()
        try:
            cleanup()
        except Exception:
            logger.exception("Revoking a notebook editor credential failed during web shutdown.")
    plugins.editor_contexts.clear()


def build_lifespan(
    config: WebConfig,
    *,
    engine_factory: Callable[..., Any],
    run_service_factory: RunServiceFactory | None = None,
) -> Callable[[FastAPI], Any]:
    """Return the lifespan context that owns the web runtime.

    Args:
        config: Launch options.
        engine_factory: Builds the Engine; tests pass a fake. A ``provider_source``
            parameter receives the saved values.
        run_service_factory: Optional run-service hook (see :class:`RunServiceHook`).

    Returns:
        A FastAPI lifespan callable.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        make_private_dirs(config.workspace)
        lock = WorkspaceLock.acquire(config.workspace)
        try:
            async with _owned_runtime(app, config, engine_factory, run_service_factory):
                yield
        finally:
            lock.release()

    return lifespan


@asynccontextmanager
async def _owned_runtime(
    app: FastAPI,
    config: WebConfig,
    engine_factory: Callable[..., Any],
    run_service_factory: RunServiceFactory | None,
) -> AsyncIterator[None]:
    """Build, publish and finally shut down the runtime of one launch."""
    layout = WorkspaceLayout(config.workspace)
    mcp_http = getattr(app.state, "mcp_http", None)
    await asyncio.to_thread(prepare_settings, app, layout.records, config.port)
    if mcp_http is not None:
        mcp_http.prepare()
    providers = await asyncio.to_thread(load_providers, app, mcp_http)
    max_bytes, source = initial_upload_limit(config, getattr(mcp_http, "store", None))
    uploads = UploadStore(layout.uploads, max_bytes=max_bytes)
    uploads.prepare()
    grants = RootGrants.from_paths(config.roots).with_root(uploads.directory, "managed")
    engine = build_engine(engine_factory, providers.source if providers else None)
    runtime = WebRuntime(config, engine, grants, uploads, upload_limit_source=source)
    runtime.providers, runtime.loop = providers, asyncio.get_running_loop()
    try:
        runtime.experiments = (config.experiments_factory or default_experiments_factory)(config)
        runtime.plugins = (config.plugins_factory or default_plugins_factory)(config)
        runtime.profiles = await _start_profiles(config, runtime.engine)
        runtime.chats = _build_chats(config)
        if run_service_factory is not None:
            runtime.run_service = run_service_factory(runtime)
            await runtime.run_service.start()
        app.state.runtime = runtime
        # The MCP session manager runs after the Engine exists and stops
        # before ``shutdown_runtime`` closes it (design D3).
        async with mcp_http.session_manager.run() if mcp_http else contextlib.nullcontext():
            yield
    finally:
        app.state.runtime = None
        await shutdown_runtime(runtime)


def _build_chats(config: WebConfig) -> Any:
    """Build the chat store. It runs after the profile service has migrated the file."""
    from ...compose_profile_setup import build_chat_repository

    return build_chat_repository(config.workspace)


async def _start_profiles(config: WebConfig, engine: Any) -> Any:
    """Build the profile service and turn saved Studio pipelines into profiles (D10).

    The upgrade step handles only pipelines that belong to no profile, so it does
    nothing on later starts. A failure is logged and does not stop the server:
    the pipelines stay as they are and the next start tries again.
    """
    from ...compose_profile_setup import build_profile_service

    service = build_profile_service(engine, config.workspace)
    try:
        created = await asyncio.to_thread(service.upgrade_saved_pipelines)
    except Exception:
        logger.exception("Turning saved pipelines into profiles failed; the next start retries.")
    else:
        if created:
            logger.info("Turned %d saved pipeline(s) into profiles.", len(created))
    return service


def request_shutdown(app: FastAPI) -> None:
    """Close admission from a signal handler, before the server drains.

    Uvicorn waits for open connections before the lifespan shutdown runs,
    so open event streams must end first. They end when admission closes.
    The call is thread-safe and does nothing before startup.

    Args:
        app: The application whose runtime stops admitting work.
    """
    runtime = getattr(app.state, "runtime", None)
    if runtime is None or runtime.loop is None:
        return
    with contextlib.suppress(RuntimeError):  # the loop already closed
        runtime.loop.call_soon_threadsafe(runtime.admission.close)


def get_runtime(request: Request) -> WebRuntime:
    """Route dependency returning the running :class:`WebRuntime`.

    Raises:
        HTTPException: 503 when the runtime is not started or is shutting down.
    """
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None or not runtime.admission.is_open:
        raise HTTPException(503, "The server is starting or shutting down.")
    return runtime
