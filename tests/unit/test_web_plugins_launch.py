"""Default plugin host end to end with a fake marimo executable (task 8.6).

The application builds its plugin host with the production factory
(``PluginRegistry`` + ``SubprocessProbeRunner`` and
``NotebookEditorSupervisor`` + ``OwnedProcessLauncher``). The executable
is the fake editor script from the launcher tests; marimo is not
installed. Startup launches nothing, and application shutdown stops the
owned editor process group.
"""

from __future__ import annotations

import contextlib
import os
import signal
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_plugin_marimo_manifest import MANIFEST  # noqa: E402
from tests.unit.test_process_launcher_support import (  # noqa: E402
    free_port,
    make_fake_editor,
    read_record,
    wait_gone,
)
from tests.unit.test_web_experiments_support import (  # noqa: E402
    BASE,
    ORIGIN,
    build_experiment_app,
    login,
    register,
)
from tests.unit.test_web_runs_support import make_engine  # noqa: E402

from omrg.transports.api import lifespan  # noqa: E402


def test_shipped_manifest_is_the_approved_default() -> None:
    assert MANIFEST.resolve() in [path.resolve() for path in lifespan.SHIPPED_PLUGIN_MANIFESTS]


def test_editor_runs_until_app_shutdown_and_starts_nothing_at_startup(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = make_fake_editor(tmp_path / "tool")
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ.get('PATH', '')}")
    parts = build_experiment_app(
        tmp_path, make_engine(effective_settings), effective_settings, plugin_ports=(free_port(),)
    )
    try:
        _open_and_shut_down(parts, exe)
    finally:
        _kill_leftover(exe.parent)


def _kill_leftover(directory: Path) -> None:
    """Kill the fake editor group if a failed test left it running."""
    record_file = directory / "record.json"
    if record_file.exists():
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(read_record(directory)["pgid"], signal.SIGKILL)


def _open_and_shut_down(parts: Any, exe: Path) -> None:
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        assert not (exe.parent / "record.json").exists()  # nothing launched at startup
        assert client.get("/v1/plugins").json()["plugins"] == []
        created = client.post(
            "/v1/plugins",
            json={"manifest_path": str(MANIFEST), "executable_path": str(exe), "approved": True},
            headers=ORIGIN,
        )
        assert created.status_code == 201, created.text
        checked = client.post("/v1/plugins/marimo/recheck", headers=ORIGIN).json()["plugin"]
        assert checked["status"] == "compatible" and checked["launchable"] is True
        context_id = register(client, parts.root)["experiment"]["context_id"]
        notebook = parts.root / "exp-a" / "study.py"
        notebook.write_text("import marimo\napp = marimo.App()\n")
        opened = client.post(
            "/v1/plugins/marimo/editors",
            json={"notebook": "study.py", "experiment_context": context_id, "consent": True},
            headers=ORIGIN,
        )
        assert opened.status_code == 201, opened.text
        token = opened.json()["token_delivery"]["token"]
        record = read_record(exe.parent)
        assert not any(token in arg for arg in record["argv"])
        assert record["token_length"] == len(token)
    # Application shutdown stopped the owned group; the notebook stays.
    assert wait_gone(record["pid"]) and wait_gone(record["child_pid"])
    assert notebook.exists()
