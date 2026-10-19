"""Plan and plist of the web login item (design D2, D3, D6, D7).

Pure logic for ``omrg web install | uninstall | status | restart | open``:
the LaunchAgent plan, plist rendering, the checkout and settings checks,
and the health, version and link helpers. Prompts, output and exit codes
live in ``web_login_item``.

This module imports no web code, so ``omrg --help`` works without the
optional ``web`` extra. Every path derives from an explicit ``home``
(default ``Path.home()``), so tests never touch the real ``~/Library``.
"""

from __future__ import annotations

import http.client
import json
import plistlib
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from xml.parsers.expat import ExpatError

from ._launchagent import InstallerError, compute_paths, resolve_command_path

#: One web app per user, so one fixed label.
LABEL = "com.omrg.web"
#: Name of the sign-in link file in the workspace. The server writes it
#: (``transports/api/launch_link.py``); a test pins that both names match.
LINK_FILE_NAME = "launch-link"
#: launchd gives agents a sparse ``PATH``; the app starts tools such as
#: ``llama-server``.
LAUNCH_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
#: Seconds launchd waits between starts, so a start that fails at once
#: (port in use, workspace locked) retries once a minute.
THROTTLE_SECONDS = 60
#: Seconds one health request may take.
HEALTH_TIMEOUT = 2.0
#: Seconds to wait for ``omrg --version`` of the installed executable.
_VERSION_TIMEOUT = 30

_VERSION_LINE = re.compile(r"omrg (\S+)")


@dataclass(frozen=True)
class WebLoginItemPlan:
    """Immutable installation plan for the web login item.

    ``workspace``, ``port``, ``roots`` and ``experiment_roots`` hold only
    what the user gave; the plist argument list repeats nothing else.
    """

    label: str
    command_path: str
    plist_path: Path
    stdout_log: Path
    stderr_log: Path
    working_directory: Path
    home: Path
    workspace: Path | None = None
    port: int | None = None
    roots: tuple[Path, ...] = ()
    experiment_roots: tuple[Path, ...] = ()


@dataclass(frozen=True)
class LinkInfo:
    """A parsed sign-in link.

    ``address`` is the page address without the secret; ``url`` is the
    full link and holds the secret, so print it only on request.
    """

    host: str
    port: int
    address: str
    url: str


@dataclass(frozen=True)
class InstalledItem:
    """What an installed plist says about the login item."""

    command_path: str
    workspace: Path | None
    port: int | None


def _absolute(path: Path) -> Path:
    """Expand ``~`` and resolve against the current folder.

    launchd starts the agent in ``~/.omrg``, so a relative option would
    point at the wrong folder.
    """
    return Path(path).expanduser().resolve()


def build_plan(
    *,
    workspace: Path | None = None,
    port: int | None = None,
    roots: tuple[Path, ...] = (),
    experiment_roots: tuple[Path, ...] = (),
    command_path: str | None = None,
    home: Path | None = None,
) -> WebLoginItemPlan:
    """Assemble the plan from the options the user gave to ``install``.

    Raises:
        InstallerError: *command_path* is relative, or no ``omrg``
            executable can be found.
    """
    base = Path.home() if home is None else home
    plist_path, stdout_log, stderr_log = compute_paths(LABEL, home=base)
    return WebLoginItemPlan(
        label=LABEL,
        command_path=resolve_command_path(command_path),
        plist_path=plist_path,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
        working_directory=base / ".omrg",
        home=base,
        workspace=None if workspace is None else _absolute(workspace),
        port=port,
        roots=tuple(_absolute(root) for root in roots),
        experiment_roots=tuple(_absolute(root) for root in experiment_roots),
    )


def build_program_arguments(plan: WebLoginItemPlan) -> list[str]:
    """Return the ``ProgramArguments`` argv: an argument list, never a shell string."""
    argv = [plan.command_path, "web", "--login-item"]
    if plan.workspace is not None:
        argv += ["--workspace", str(plan.workspace)]
    if plan.port is not None:
        argv += ["--port", str(plan.port)]
    for root in plan.roots:
        argv += ["--root", str(root)]
    for root in plan.experiment_roots:
        argv += ["--experiment-root", str(root)]
    return argv


def render_plist(plan: WebLoginItemPlan) -> bytes:
    """Serialise the plan to plist XML bytes (design D2 table)."""
    return plistlib.dumps(
        {
            "Label": plan.label,
            "ProgramArguments": build_program_arguments(plan),
            "RunAtLoad": True,
            # Restart after a crash or kill; a clean exit stays stopped.
            "KeepAlive": {"SuccessfulExit": False},
            "ThrottleInterval": THROTTLE_SECONDS,
            "EnvironmentVariables": {"PATH": LAUNCH_PATH},
            # Settings come from the .env in the working folder (D7).
            "WorkingDirectory": str(plan.working_directory),
            "StandardOutPath": str(plan.stdout_log),
            "StandardErrorPath": str(plan.stderr_log),
        },
        sort_keys=True,
    )


def read_installed(plist_path: Path) -> InstalledItem | None:
    """Read the executable, workspace and port from an installed plist.

    Returns ``None`` when the file is missing or is not a plist written by
    ``install``.
    """
    try:
        argv = plistlib.loads(plist_path.read_bytes())["ProgramArguments"]
        if argv[1:3] != ["web", "--login-item"]:
            return None
        options = dict(zip(argv[3::2], argv[4::2], strict=False))
        port = options.get("--port")
        return InstalledItem(
            command_path=str(argv[0]),
            workspace=Path(options["--workspace"]) if "--workspace" in options else None,
            port=int(port) if port is not None else None,
        )
    except (OSError, KeyError, IndexError, TypeError, ValueError, ExpatError):
        return None


def workspace_dir(plan: WebLoginItemPlan) -> Path:
    """Return the workspace folder the server will use.

    Mirrors ``core.workspace.default_workspace``; a test pins that they agree.
    """
    return plan.workspace or plan.home / ".omrg" / "workspace"


def link_file(plan: WebLoginItemPlan) -> Path:
    """Return the path of the sign-in link file the server writes."""
    return workspace_dir(plan) / LINK_FILE_NAME


def checkout_warning(command_path: str) -> str | None:
    """Warn when the executable sits in a ``.venv`` of a source checkout (D3).

    Deleting the checkout, or a feature worktree, would stop the app. A
    worktree holds a ``.git`` file, a clone a ``.git`` folder; ``exists``
    accepts both.
    """
    for parent in Path(command_path).parents:
        if parent.name == ".venv" and (parent.parent / ".git").exists():
            return (
                f"{command_path} sits inside the source checkout {parent.parent}. "
                "If you delete that checkout or worktree, the app stops. Install a copy "
                "that does not depend on it with 'uv tool install' (see "
                "docs/guides/cli-reference.md), then run 'omrg web install' again."
            )
    return None


def settings_message(home: Path, cwd: Path) -> str | None:
    """Name the settings file the login item reads, when it is missing (D7).

    The command only checks that files exist. It never reads, copies or
    moves a ``.env`` file.
    """
    settings = home / ".omrg" / ".env"
    if settings.is_file():
        return None
    message = (
        f"The login item reads ~/.omrg/.env ({settings}). That file does not exist, "
        "so the login item starts with the code defaults."
    )
    if (cwd / ".env").is_file():
        message += " Copy your settings there before you start it."
    return message


def parse_link(text: str) -> LinkInfo | None:
    """Parse the content of the link file, or return ``None`` if it is not a link."""
    link = text.strip()
    try:
        parts = urlsplit(link)
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname
    if parts.scheme != "http" or host is None or port is None:
        return None
    if not parts.fragment.startswith("bootstrap="):
        return None
    shown = f"[{host}]" if ":" in host else host
    return LinkInfo(host=host, port=port, address=f"http://{shown}:{port}/", url=link)


def _http_get(host: str, port: int, path: str, timeout: float) -> bytes:
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request("GET", path)
        return connection.getresponse().read()
    finally:
        connection.close()


def fetch_health(
    host: str,
    port: int,
    *,
    timeout: float = HEALTH_TIMEOUT,
    get: Callable[[str, int, str, float], bytes] = _http_get,
) -> dict[str, Any] | None:
    """Return the body of ``GET /v1/health``, or ``None`` when the app does not answer."""
    try:
        body = json.loads(get(host, port, "/v1/health", timeout))
    except (OSError, http.client.HTTPException, ValueError):
        return None
    if isinstance(body, dict) and body.get("status") == "ok":
        return body
    return None


def installed_version(
    command_path: str,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str | None:
    """Return the version that ``<command_path> --version`` prints, or ``None``."""
    try:
        done = run(
            [command_path, "--version"],
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = _VERSION_LINE.fullmatch(done.stdout.strip()) if done.returncode == 0 else None
    return match.group(1) if match else None


__all__ = [
    "HEALTH_TIMEOUT",
    "LABEL",
    "LAUNCH_PATH",
    "LINK_FILE_NAME",
    "THROTTLE_SECONDS",
    "InstalledItem",
    "InstallerError",
    "LinkInfo",
    "WebLoginItemPlan",
    "build_plan",
    "build_program_arguments",
    "checkout_warning",
    "fetch_health",
    "installed_version",
    "link_file",
    "parse_link",
    "read_installed",
    "render_plist",
    "settings_message",
    "workspace_dir",
]
