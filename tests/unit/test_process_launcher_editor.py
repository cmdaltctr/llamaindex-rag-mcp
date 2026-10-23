"""End-to-end owned editor launch with the shipped manifest and a fake marimo (task 8.3)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from tests.unit.test_plugin_marimo_manifest import MANIFEST
from tests.unit.test_process_launcher_support import (
    alive,
    file_digest,
    free_port,
    make_fake_editor,
    read_record,
    unrelated_listener,
    wait_gone,
)

from omrs.core.plugins import NotebookEditorSupervisor, PluginLaunchError, PluginRegistry
from omrs.integrations.process_launcher import OwnedProcessLauncher, SubprocessProbeRunner
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository

TOKEN = "per-launch-token-for-test"  # noqa: S105 - test value


@pytest.fixture
def parts(tmp_path: Path):
    exe = make_fake_editor(tmp_path / "tool")
    registry = PluginRegistry(
        SqliteWorkspaceRepository(tmp_path / "workspace.sqlite3"), SubprocessProbeRunner()
    )
    registry.register(MANIFEST, exe, approved=True)
    launcher = OwnedProcessLauncher(tmp_path / "rt", grace_seconds=1.0, ready_timeout=10.0)
    notebook = tmp_path / "notebooks" / "experiment.py"
    notebook.parent.mkdir()
    notebook.write_text("import marimo\napp = marimo.App()\n")
    yield registry, launcher, exe, notebook
    launcher.stop_all()


def supervisor(registry, launcher, ports) -> NotebookEditorSupervisor:
    return NotebookEditorSupervisor(registry, launcher, ports=ports, token_factory=lambda: TOKEN)


def test_open_and_stop_owned_editor(parts) -> None:
    registry, launcher, exe, notebook = parts
    before = file_digest(notebook)
    sup = supervisor(registry, launcher, [free_port()])
    session = sup.open("marimo", notebook, consent=True)
    record = read_record(exe.parent)
    argv = record["argv"]
    # Loopback, headless, update check and sandbox installs disabled.
    assert argv[argv.index("--host") + 1] == "127.0.0.1" and session.host == "127.0.0.1"
    assert int(argv[argv.index("--port") + 1]) == session.port
    for flag in ("--headless", "--skip-update-check", "--no-sandbox"):
        assert flag in argv
    # Authentication: a per-launch token in a private file, never in argv or env.
    assert not any(TOKEN in arg for arg in argv)
    assert TOKEN not in str(record["env"])
    assert record["token_mode"] == 0o600 and record["token_length"] == len(TOKEN)
    token_file = Path(argv[argv.index("--token-password-file") + 1])
    assert token_file.parent == Path(record["cwd"]) or os.path.realpath(
        token_file.parent
    ) == os.path.realpath(record["cwd"])
    # Startup execution is disabled through the cwd config file.
    assert "auto_instantiate = false" in record["config"]
    assert 'on_cell_change = "lazy"' in record["config"]
    # Stop removes the owned group (leader and its child) and the token file.
    sup.stop(session.launch_id)
    assert wait_gone(record["pid"]) and wait_gone(record["child_pid"])
    assert not token_file.exists()
    assert file_digest(notebook) == before


def test_unrelated_editor_on_port_is_not_adopted(parts) -> None:
    registry, launcher, exe, notebook = parts
    busy, spare = free_port(), free_port()
    with unrelated_listener(busy) as other:
        session = supervisor(registry, launcher, [busy, spare]).open(
            "marimo", notebook, consent=True
        )
        assert session.port == spare
        launcher.stop_all()
        assert other.poll() is None and alive(other.pid)


def test_only_busy_ports_fail_clearly(parts) -> None:
    registry, launcher, _, notebook = parts
    busy = free_port()
    with unrelated_listener(busy) as other:
        with pytest.raises(PluginLaunchError, match="does not stop other programs"):
            supervisor(registry, launcher, [busy]).open("marimo", notebook, consent=True)
        assert alive(other.pid)
    assert launcher.owned_ids() == []
