"""Editor launch planning and supervision with a fake launcher (task 8.3)."""

from __future__ import annotations

import errno
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from tests.unit.test_plugin_manifest import valid_manifest
from tests.unit.test_plugin_registration import FakeRunner

from omrg.core.plugins import (
    NotebookEditorSupervisor,
    PluginConsentError,
    PluginLaunchError,
    PluginRegistry,
    build_launch_plan,
    parse_manifest,
)
from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository


@dataclass
class FakeLauncher:
    """Records launch requests. Ports in ``busy`` look taken by another program."""

    root: Path
    busy: set[int] = field(default_factory=set)
    race: set[int] = field(default_factory=set)  # free at check, taken at start
    started: list[dict] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)

    def create_launch_dir(self) -> Path:
        path = self.root / f"launch-{len(self.started)}-{len(self.stopped)}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def discard_launch_dir(self, workdir: Path) -> None:
        pass

    def port_available(self, host: str, port: int) -> bool:
        return port not in self.busy

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
        if port in self.race:
            raise OSError(errno.EADDRINUSE, "taken")
        self.started.append(
            {"argv": list(argv), "workdir": workdir, "host": host, "port": port,
             "files": dict(files), "secrets": list(secrets),
             "environment": dict(environment or {})}
        )  # fmt: skip
        return f"id-{len(self.started)}"

    def stop(self, launch_id: str) -> object:
        self.stopped.append(launch_id)
        return launch_id

    def stop_all(self) -> list[object]:
        return []


@pytest.fixture
def setup(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(valid_manifest()))
    exe = tmp_path / "fakeedit"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    notebook = tmp_path / "notes" / "nb.py"
    notebook.parent.mkdir()
    notebook.write_text("import marimo\n")
    registry = PluginRegistry(SqliteWorkspaceRepository(tmp_path / "ws.sqlite3"), FakeRunner())
    registry.register(manifest, exe, approved=True)
    launcher = FakeLauncher(tmp_path / "run")
    return registry, launcher, notebook, exe


def supervisor(registry, launcher, ports=(41001, 41002)) -> NotebookEditorSupervisor:
    return NotebookEditorSupervisor(registry, launcher, ports=ports, token_factory=lambda: "T0KEN")


def test_open_requires_consent(setup) -> None:
    registry, launcher, notebook, _ = setup
    with pytest.raises(PluginConsentError):
        supervisor(registry, launcher).open("fakeedit", notebook, consent=False)
    assert launcher.started == []


def test_open_rechecks_then_launches_loopback_with_token_file(setup) -> None:
    registry, launcher, notebook, exe = setup
    session = supervisor(registry, launcher).open("fakeedit", notebook, consent=True)
    call = launcher.started[0]
    argv = call["argv"]
    assert argv[0] == str(exe)
    assert call["host"] == "127.0.0.1" and argv[argv.index("--host") + 1] == "127.0.0.1"
    assert "--port=41001" in argv and str(notebook.resolve()) in argv
    assert not any("T0KEN" in arg for arg in argv)  # never in argv
    token_path = argv[argv.index("--token-password-file") + 1]
    assert Path(token_path).parent == call["workdir"]
    assert call["files"][Path(token_path).name] == "T0KEN"
    assert "auto_instantiate = false" in call["files"][".fakeedit.toml"]
    assert "--skip-update-check" in argv and "--no-sandbox" in argv
    assert call["secrets"] == ["T0KEN"]
    assert session.port == 41001 and session.token == "T0KEN"  # noqa: S105
    assert "T0KEN" not in repr(session)
    assert registry.state("fakeedit").status == "compatible"


def test_unrelated_port_is_skipped_not_adopted(setup) -> None:
    registry, launcher, notebook, _ = setup
    launcher.busy = {41001}
    launcher.race = {41002}
    sup = supervisor(registry, launcher, ports=(41001, 41002, 41003))
    session = sup.open("fakeedit", notebook, consent=True)
    assert session.port == 41003
    assert launcher.stopped == []  # nothing on the busy ports was touched


def test_all_ports_busy_fails_clearly(setup) -> None:
    registry, launcher, notebook, _ = setup
    launcher.busy = {41001, 41002}
    with pytest.raises(PluginLaunchError, match="41001, 41002.*not stop"):
        supervisor(registry, launcher).open("fakeedit", notebook, consent=True)
    assert launcher.started == [] and launcher.stopped == []


def test_incompatible_plugin_is_not_launched(setup) -> None:
    registry, launcher, notebook, _ = setup
    registry._runner.version = "fakeedit 9.0"  # updated outside OMRG
    with pytest.raises(PluginLaunchError, match="outside the tested range"):
        supervisor(registry, launcher).open("fakeedit", notebook, consent=True)
    assert launcher.started == []


def test_missing_notebook_is_refused(setup, tmp_path: Path) -> None:
    registry, launcher, _, _ = setup
    with pytest.raises(PluginLaunchError, match="notebook"):
        supervisor(registry, launcher).open("fakeedit", tmp_path / "x.py", consent=True)


def test_stop_only_targets_owned_sessions(setup) -> None:
    registry, launcher, notebook, _ = setup
    sup = supervisor(registry, launcher)
    session = sup.open("fakeedit", notebook, consent=True)
    with pytest.raises(KeyError):
        sup.stop("someone-else")
    sup.stop(session.launch_id)
    assert launcher.stopped == [session.launch_id]
    assert sup.sessions() == []


def test_build_launch_plan_rejects_non_loopback(tmp_path: Path) -> None:
    manifest = parse_manifest(json.dumps(valid_manifest()).encode())
    with pytest.raises(ValueError, match="loopback"):
        build_launch_plan(
            manifest, "/bin/x", notebook=tmp_path / "n.py", host="0.0.0.0",  # noqa: S104
            port=1, launch_dir=tmp_path, token="t",  # noqa: S106
        )  # fmt: skip


def test_supervisor_needs_a_port(setup) -> None:
    registry, launcher, _, _ = setup
    with pytest.raises(ValueError, match="port"):
        NotebookEditorSupervisor(registry, launcher, ports=())


def test_start_failure_other_than_port_is_reported(setup) -> None:
    registry, launcher, notebook, _ = setup

    def broken(**_: object) -> str:
        raise OSError(errno.ENOEXEC, "exec format error")

    launcher.start = broken  # type: ignore[method-assign]
    with pytest.raises(PluginLaunchError, match="failed to start"):
        supervisor(registry, launcher).open("fakeedit", notebook, consent=True)


def test_stop_all_stops_owned_sessions(setup) -> None:
    registry, launcher, notebook, _ = setup
    sup = supervisor(registry, launcher, ports=(41001,))
    first = sup.open("fakeedit", notebook, consent=True)
    assert sup.stop_all() == [first.launch_id]
    assert launcher.stopped == [first.launch_id] and sup.sessions() == []
