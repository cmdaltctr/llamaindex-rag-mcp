"""LaunchAgent primitives for ``rag-mcp install-login-watcher``.

Owns the macOS installer mechanics (design.md D3): watch-path
validation, deterministic label generation, path layout, command
resolution, plist rendering, atomic plist writes, and ``launchctl``
command construction.

Pure logic only — prompts, output, and exit codes live in
``install_login_watcher.py``. Every path derives from an explicit
``home`` (defaulting to ``Path.home()``) so tests never touch the real
``~/Library`` tree.
"""

from __future__ import annotations

import hashlib
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from xml.parsers.expat import ExpatError

LABEL_PREFIX = "com.rag-mcp.watch."
_LAUNCHAGENTS_PARTS = ("Library", "LaunchAgents")
_LOG_PARTS = ("Library", "Logs", "rag-mcp")
_LABEL_SLUG_MAX = 40
_EMPTY_SLUG_FALLBACK = "watcher"


class InstallerError(Exception):
    """Installer failure carrying a user-facing message."""


class ExistingPlistError(InstallerError):
    """A plist already exists and overwrite was not allowed."""

    def __init__(self, plist_path: Path) -> None:
        super().__init__(f"LaunchAgent plist already exists: {plist_path}")
        self.plist_path = plist_path


@dataclass(frozen=True)
class LaunchAgentPlan:
    """Immutable installation plan for one watcher LaunchAgent."""

    label: str
    watch_path: Path
    collection: str
    debounce: float
    command_path: str
    plist_path: Path
    stdout_log: Path
    stderr_log: Path
    run_at_load: bool = True
    keep_alive: bool = False


def slugify_label_part(text: str, max_length: int = _LABEL_SLUG_MAX) -> str:
    """Reduce *text* to a LaunchAgent-safe slug of hyphens and alphanumerics.

    Returns a non-empty fallback when nothing survives sanitising, so a
    generated label can never end with a bare ``com.rag-mcp.watch.`` prefix.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:max_length].strip("-")
    return slug or _EMPTY_SLUG_FALLBACK


def generate_label(watch_path: Path, collection: str, custom: str | None = None) -> str:
    """Derive a deterministic LaunchAgent label.

    Default form: ``com.rag-mcp.watch.<slug>-<hash8>`` where *slug* comes
    from the watch directory name and *hash8* from the resolved path plus
    collection — same folder and collection always rebuild the same label,
    while a second collection on the same folder stays distinct.
    """
    if custom is not None:
        return LABEL_PREFIX + slugify_label_part(custom)
    digest = hashlib.sha256(f"{watch_path}|{collection}".encode()).hexdigest()[:8]
    slug = slugify_label_part(watch_path.name)
    return f"{LABEL_PREFIX}{slug}-{digest}"


def validate_watch_path(raw: str | Path) -> Path:
    """Validate and resolve a watch directory.

    Expands a leading ``~`` against ``Path.home()`` so the test seam
    applies, checks existence, and resolves symlinks. The LaunchAgent
    must persist the resolved absolute form (design.md D4 rationale).

    Args:
        raw: User-supplied path text.

    Returns:
        The absolute, symlink-resolved directory path.

    Raises:
        InstallerError: If the path is missing or not a directory.
    """
    text = str(raw)
    if text == "~":
        candidate = Path.home()
    elif text.startswith("~/"):
        candidate = Path.home() / text[2:].lstrip("/")
    elif text.startswith("~"):
        # `~user` names another user's home; guessing wrong here would
        # silently watch the wrong folder, so refuse instead (CodeRabbit).
        raise InstallerError(
            f"Only '~' and '~/...' expand; pass an absolute path instead of {text!r}."
        )
    else:
        candidate = Path(text)
    if not candidate.exists():
        raise InstallerError(f"Watch path does not exist: {text}")
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise InstallerError(f"Watch path is not a directory: {text}")
    return resolved


def compute_paths(label: str, home: Path | None = None) -> tuple[Path, Path, Path]:
    """Return ``(plist_path, stdout_log, stderr_log)`` under *home*.

    ``home`` defaults to ``Path.home()``; the layout is
    ``~/Library/LaunchAgents/<label>.plist`` and
    ``~/Library/Logs/rag-mcp/<label>.{out,err}.log`` (design.md D6).
    """
    base = Path.home() if home is None else home
    plist_path = base.joinpath(*_LAUNCHAGENTS_PARTS) / f"{label}.plist"
    log_dir = base.joinpath(*_LOG_PARTS)
    return plist_path, log_dir / f"{label}.out.log", log_dir / f"{label}.err.log"


def resolve_command_path(override: str | None = None) -> str:
    """Resolve the absolute ``rag-mcp`` console executable (task 1.5).

    An explicit override wins and is used verbatim (after ``~``
    expansion). Otherwise the executable is discovered via
    ``shutil.which`` — the install-time shell has the environment active —
    falling back to the script bin directory sibling of the running
    interpreter. Never ``sys.executable -m rag_mcp.cli``: that module was
    deleted in v2.0.0.

    Raises:
        InstallerError: When no executable can be located.
    """
    if override:
        resolved = Path(override).expanduser()
        if not resolved.is_absolute():
            # launchd starts agents with cwd "/" and a sparse PATH — a
            # relative executable would silently never start (audit F2).
            raise InstallerError(
                f"--command-path must be absolute (got {override!r}). "
                "Pass the full path to the rag-mcp console script."
            )
        return str(resolved)
    found = shutil.which("rag-mcp")
    if found:
        return str(Path(found))
    sibling = Path(sys.executable).parent / "rag-mcp"
    if sibling.exists():
        return str(sibling)
    raise InstallerError(
        "Could not locate the installed rag-mcp executable. Pass "
        "--command-path with the absolute path to the rag-mcp console script."
    )


def build_plan(
    watch_path_raw: str | Path,
    collection: str,
    debounce: float,
    *,
    label: str | None = None,
    command_path: str | None = None,
    home: Path | None = None,
) -> LaunchAgentPlan:
    """Validate inputs and assemble a complete :class:`LaunchAgentPlan`."""
    watch = validate_watch_path(watch_path_raw)
    generated = generate_label(watch, collection, custom=label)
    plist_path, stdout_log, stderr_log = compute_paths(generated, home=home)
    return LaunchAgentPlan(
        label=generated,
        watch_path=watch,
        collection=collection,
        debounce=float(debounce),
        command_path=resolve_command_path(command_path),
        plist_path=plist_path,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
    )


def build_program_arguments(plan: LaunchAgentPlan) -> list[str]:
    """Return the exact ``ProgramArguments`` argv for the watcher command.

    Argv form — never a shell string — so launchd execs the executable
    directly with no interpolation hazards.
    """
    return [
        plan.command_path,
        "watch",
        str(plan.watch_path),
        "--collection",
        plan.collection,
        "--debounce",
        str(plan.debounce),
    ]


def _plist_watches(plist_path: Path) -> Path | None:
    """Return the watch path persisted in a generated plist, if readable.

    Unreadable or non-installer plists return ``None`` — a slug-name
    match alone proves nothing (another folder may share the name
    prefix), so the persisted watch path is the only verdict.
    """
    try:
        data = plistlib.loads(plist_path.read_bytes())
        argv = data.get("ProgramArguments")
        if isinstance(argv, list) and len(argv) > 2 and argv[1] == "watch":
            return Path(str(argv[2]))
    # InvalidFileException subclasses ValueError; XML-shaped input that
    # passes the format sniff escapes as ExpatError (not a ValueError),
    # so both are named explicitly.
    except (OSError, AttributeError, TypeError, ValueError, ExpatError):
        return None
    return None


def find_existing_plist(plan: LaunchAgentPlan) -> Path | None:
    """Return a previously generated plist for this watch folder, if any.

    Checks the exact planned path first, then any generated label whose
    slug matches the watch directory. Slug candidates are verified via
    :func:`_plist_watches` — the slug glob is a shortlist, never the
    verdict, because ``docs`` also prefixes ``docs-backup``.
    """
    if plan.plist_path.exists():
        return plan.plist_path
    slug = slugify_label_part(plan.watch_path.name)
    for candidate in sorted(plan.plist_path.parent.glob(f"{LABEL_PREFIX}{slug}*.plist")):
        if _plist_watches(candidate) == plan.watch_path:
            return candidate
    return None


def render_plist(plan: LaunchAgentPlan) -> bytes:
    """Serialise the plan to plist XML bytes."""
    return plistlib.dumps(
        {
            "Label": plan.label,
            "ProgramArguments": build_program_arguments(plan),
            "RunAtLoad": plan.run_at_load,
            "KeepAlive": plan.keep_alive,
            "StandardOutPath": str(plan.stdout_log),
            "StandardErrorPath": str(plan.stderr_log),
        },
        sort_keys=True,
    )


def write_plist(plan: LaunchAgentPlan, content: bytes, *, overwrite: bool = False) -> Path:
    """Atomically write the plist, creating parent directories.

    Writes to a temporary file in the target directory and renames it
    into place, so a crashed install can never leave a truncated plist
    that launchd would load at login.

    Args:
        plan: Carries the destination path.
        content: Rendered plist bytes.
        overwrite: Allow replacing an existing plist.

    Returns:
        The written plist path.

    Raises:
        ExistingPlistError: When the target exists and *overwrite* is
            False; the existing file is left untouched.
    """
    target = plan.plist_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise ExistingPlistError(target)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return target


def bootstrap_command(uid: int, plist_path: Path) -> list[str]:
    """Return the argv that loads a plist into the user's GUI domain."""
    return ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)]


def bootout_command(uid: int, label: str) -> list[str]:
    """Return the argv that unloads a label from the user's GUI domain."""
    return ["launchctl", "bootout", f"gui/{uid}/{label}"]


def print_command(uid: int, label: str) -> list[str]:
    """Return the argv that reports whether a label is currently loaded.

    Exit 0 means loaded; non-zero means not loaded — used to
    disambiguate a failed bootout from an agent that never ran.
    """
    return ["launchctl", "print", f"gui/{uid}/{label}"]


def kickstart_command(uid: int, label: str) -> list[str]:
    """Return the argv that immediately starts a loaded label."""
    return ["launchctl", "kickstart", f"gui/{uid}/{label}"]


def run_launchctl(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a launchctl argv, platform-gated to macOS (task 2.4).

    Captures stdout/stderr so callers can surface diagnostics verbatim
    instead of swallowing them.

    Raises:
        InstallerError: On non-darwin platforms.
    """
    if sys.platform != "darwin":
        raise InstallerError("launchctl operations are only available on macOS.")
    return subprocess.run(list(cmd), capture_output=True, text=True, check=False)  # noqa: S603 - fixed argv, no shell
