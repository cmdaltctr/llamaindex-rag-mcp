"""Explicit plugin registration and compatibility probing (design D10).

Registration is an operator trust decision. It stores the manifest hash and
the executable reference, and it runs nothing. A probe runs only the
manifest's ``probe`` recipe through an injected runner, so this package
never imports ``subprocess``. A changed manifest needs a new registration.
A changed executable (size, modification time or content) needs a recheck.
OMRG never installs, upgrades or replaces the tool.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from omrg.core.plugins.manifest import (
    PluginManifest,
    format_version,
    parse_manifest,
    parse_version,
)
from omrg.core.workspace.records import PluginRecord
from omrg.core.workspace.repository import WorkspaceRepository

DEFAULT_PROBE_TIMEOUT = 15.0
MAX_EXECUTABLE_HASH_BYTES = 256 * 1024 * 1024

# Plugin states. The repository stores the last three; the first two are
# derived from files on disk at read time.
NEEDS_APPROVAL = "needs_approval"
UNAVAILABLE = "unavailable"
UNCHECKED = "unchecked"
COMPATIBLE = "compatible"
INCOMPATIBLE = "incompatible"


class PluginTrustError(PermissionError):
    """Registration lacks approval, or its executable cannot be trusted."""


class ProbeOutput(Protocol):
    """Result of one probe command."""

    returncode: int
    stdout: str
    stderr: str


class ProbeRunner(Protocol):
    """Runs one probe argv without a shell. Implemented in integrations."""

    def run(self, argv: Sequence[str], *, timeout: float) -> ProbeOutput:
        """Run ``argv`` and return its output.

        Raises:
            OSError: If the executable cannot start.
            TimeoutError: If it does not finish within ``timeout`` seconds.
        """
        ...


@dataclass(frozen=True)
class ExecutableIdentity:
    """What the operator approved: path, resolved path, size, time and hash."""

    path: str
    real_path: str
    size: int
    mtime_ns: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class PluginState:
    """The current, derived state of one registration."""

    name: str
    status: str
    message: str
    executable: str
    version: str | None = None
    manifest: PluginManifest | None = None

    @property
    def launchable(self) -> bool:
        """Return whether a launch may proceed (after consent)."""
        return self.status == COMPATIBLE and self.manifest is not None


def inspect_executable(path: Path) -> ExecutableIdentity:
    """Return the identity of an operator-chosen executable.

    Raises:
        PluginTrustError: If the path is relative, missing, not a regular
            file, not executable, or writable by other users.
    """
    if not path.is_absolute():
        raise PluginTrustError(f"executable path must be absolute: {path}")
    real = Path(os.path.realpath(path))
    try:
        info = real.stat()
    except OSError as exc:
        raise PluginTrustError(f"executable not found: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or not os.access(real, os.X_OK):
        raise PluginTrustError(f"not an executable file: {path}")
    if info.st_mode & stat.S_IWOTH:
        raise PluginTrustError(f"executable is writable by other users: {path}")
    digest = hashlib.sha256()
    with real.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            if handle.tell() > MAX_EXECUTABLE_HASH_BYTES:
                break
    return ExecutableIdentity(
        str(path), str(real), info.st_size, info.st_mtime_ns, digest.hexdigest()
    )


class PluginRegistry:
    """Registers external-tool plugins and checks their compatibility.

    Args:
        repository: Workspace records (plugin registrations).
        runner: Runs probe commands; the composition root injects it.
        probe_timeout: Seconds allowed for each probe command.
    """

    def __init__(
        self,
        repository: WorkspaceRepository,
        runner: ProbeRunner,
        *,
        probe_timeout: float = DEFAULT_PROBE_TIMEOUT,
    ) -> None:
        self._repository = repository
        self._runner = runner
        self._timeout = probe_timeout

    def register(self, manifest_path: Path, executable: Path, *, approved: bool) -> PluginRecord:
        """Record an approved manifest and executable. Runs no process.

        Raises:
            PluginTrustError: If ``approved`` is false or the executable is unsafe.
            ManifestError: If the manifest is invalid.
            OSError: If the manifest cannot be read.
        """
        if not approved:
            raise PluginTrustError("registering a plugin needs the operator's explicit approval")
        manifest = parse_manifest(Path(manifest_path).read_bytes())
        identity = inspect_executable(Path(executable))
        name = manifest.plugin_id
        self._repository.register_plugin(
            name,
            manifest_ref=str(Path(manifest_path).resolve()),
            executable_ref=identity.path,
            manifest_hash=manifest.sha256,
        )
        detail = {"approved": True, "executable": identity.to_dict(), "message": _UNCHECKED}
        return self._repository.set_plugin_compatibility(name, UNCHECKED, detail=detail)

    def state(self, name: str) -> PluginState:
        """Return the derived state without running a process.

        Raises:
            KeyError: If ``name`` is not registered.
        """
        record = self._repository.get_plugin(name)
        manifest, problem = _load_approved(record)
        exe = record["executable_ref"]
        if manifest is None:
            return PluginState(name, NEEDS_APPROVAL, problem, exe)
        try:
            identity = inspect_executable(Path(exe))
        except PluginTrustError as exc:
            return PluginState(name, UNAVAILABLE, _unavailable(manifest, str(exc)), exe)
        detail = record["detail"]
        if not _same_identity(detail.get("executable"), identity):
            message = f"{exe} changed since it was last checked; recheck it before launch"
            return PluginState(name, UNCHECKED, message, exe, manifest=manifest)
        message = str(detail.get("message", ""))
        version = detail.get("version")
        return PluginState(name, record["compatibility_status"], message, exe, version, manifest)

    def list_states(self) -> list[PluginState]:
        """Return the derived state of every registration."""
        return [self.state(record["name"]) for record in self._repository.list_plugins()]

    def recheck(self, name: str) -> PluginState:
        """Probe the registered executable and record the result.

        A manifest that changed since approval, or a missing executable,
        is reported without running anything.

        Raises:
            KeyError: If ``name`` is not registered.
        """
        current = self.state(name)
        if current.status in (NEEDS_APPROVAL, UNAVAILABLE) or current.manifest is None:
            return current
        manifest, exe = current.manifest, current.executable
        identity = inspect_executable(Path(exe))
        version, problem = self._probe(manifest, exe)
        status = INCOMPATIBLE if problem else COMPATIBLE
        message = problem or f"{manifest.tool_name} {version} is compatible"
        detail = {
            "approved": True,
            "executable": identity.to_dict(),
            "version": version,
            "tested_versions": manifest.tested_versions.describe(),
            "message": message,
        }
        self._repository.set_plugin_compatibility(name, status, detail=detail)
        return PluginState(name, status, message, exe, version, manifest)

    # --- probing ------------------------------------------------------

    def _probe(self, manifest: PluginManifest, exe: str) -> tuple[str | None, str | None]:
        output, problem = self._run(exe, manifest.probe.version_args)
        if problem:
            return None, problem
        parsed = parse_version(f"{output.stdout}\n{output.stderr}")
        if parsed is None:
            return (
                None,
                f"could not read a version from {exe}; check that it is {manifest.tool_name}",
            )
        version = format_version(parsed)
        tested = manifest.tested_versions
        if not tested.contains(parsed):
            return version, (
                f"{manifest.tool_name} {version} is outside the tested range {tested.describe()}. "
                f"Install a supported version outside OMRG, or update the plugin manifest, "
                f"then recheck."
            )
        if manifest.missing_capabilities:
            missing = ", ".join(manifest.missing_capabilities)
            return version, f"the manifest does not declare required capabilities: {missing}"
        return version, self._check_help(manifest, exe, version)

    def _check_help(self, manifest: PluginManifest, exe: str, version: str) -> str | None:
        if manifest.probe.help_args is None:
            return None
        output, problem = self._run(exe, manifest.probe.help_args)
        if problem:
            return problem
        text = f"{output.stdout}\n{output.stderr}"
        missing = [
            f"{cap.name} ({cap.argument})"
            for cap in manifest.capabilities.values()
            if cap.argument is not None and cap.argument not in text
        ]
        if missing:
            return (
                f"{manifest.tool_name} {version} does not offer required launch options: "
                f"{', '.join(missing)}"
            )
        return None

    def _run(self, exe: str, args: Sequence[str]) -> tuple[Any, str | None]:
        argv = (exe, *args)
        try:
            output = self._runner.run(argv, timeout=self._timeout)
        except (OSError, TimeoutError) as exc:
            return None, f"probe failed for {exe}: {exc}"
        if output.returncode != 0:
            return None, f"probe {' '.join(args)} exited with code {output.returncode}"
        return output, None


_UNCHECKED = "registered; run a compatibility check before launch"


def _load_approved(record: Mapping[str, Any]) -> tuple[PluginManifest | None, str]:
    ref = record["manifest_ref"]
    try:
        raw = Path(ref).read_bytes()
    except OSError:
        return None, f"manifest {ref} is missing; register the plugin again"
    if hashlib.sha256(raw).hexdigest() != record["manifest_hash"]:
        return None, f"manifest {ref} changed since approval; review it and register it again"
    return parse_manifest(raw), ""


def _same_identity(saved: Any, current: ExecutableIdentity) -> bool:
    return isinstance(saved, Mapping) and dict(saved) == current.to_dict()


def _unavailable(manifest: PluginManifest, reason: str) -> str:
    return (
        f"{reason}. Install or update {manifest.tool_name} outside OMRG, "
        f"then register its executable path again or recheck."
    )
