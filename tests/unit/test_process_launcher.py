"""Owned-process launcher against fake executables (task 8.3)."""

from __future__ import annotations

import errno
import json
import os
import stat
import time
from pathlib import Path

import pytest
from tests.unit.test_process_launcher_support import (
    alive,
    file_digest,
    free_port,
    make_fake_editor,
    make_script,
    read_record,
    unrelated_listener,
    wait_gone,
)

from omrs.integrations.process_launcher import (
    LaunchError,
    OwnedProcessLauncher,
    PortInUseError,
    SubprocessProbeRunner,
)

HOST = "127.0.0.1"
TOKEN = "s3cret-token-value"  # noqa: S105 - test value


@pytest.fixture
def launcher(tmp_path: Path):
    owned = OwnedProcessLauncher(
        tmp_path / "runtime", grace_seconds=1.0, kill_wait_seconds=3.0, ready_timeout=10.0
    )
    yield owned
    owned.stop_all()


@pytest.fixture
def tool(tmp_path: Path) -> Path:
    return make_fake_editor(tmp_path / "tool")


@pytest.fixture
def notebook(tmp_path: Path) -> Path:
    path = tmp_path / "notebooks" / "nb.py"
    path.parent.mkdir()
    path.write_text("import marimo\napp = marimo.App()\n")
    return path


def start(
    launcher: OwnedProcessLauncher, tool: Path, notebook: Path, port: int
) -> tuple[str, Path]:
    workdir = launcher.create_launch_dir()
    argv = [
        str(tool), "edit", str(notebook), "--headless", "--host", HOST, "--port", str(port),
        "--token-password-file", str(workdir / "access-token"),
    ]  # fmt: skip
    files = {"access-token": TOKEN, ".marimo.toml": "[runtime]\nauto_instantiate = false\n"}
    launch_id = launcher.start(
        argv=argv, workdir=workdir, host=HOST, port=port, files=files, secrets=[TOKEN]
    )
    return launch_id, workdir


# --- probe runner -----------------------------------------------------------


def test_probe_runner_returns_output(tool: Path) -> None:
    output = SubprocessProbeRunner().run([str(tool), "--version"], timeout=10)
    assert output.returncode == 0 and output.stdout.strip() == "0.25.1"


def test_probe_runner_times_out_and_kills(tmp_path: Path) -> None:
    script = make_script(tmp_path, "slow", "import time\ntime.sleep(30)\n")
    began = time.monotonic()
    with pytest.raises(TimeoutError):
        SubprocessProbeRunner().run([str(script)], timeout=0.5)
    assert time.monotonic() - began < 5


def test_probe_runner_missing_executable_raises_os_error(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        SubprocessProbeRunner().run([str(tmp_path / "missing")], timeout=1)


def test_probe_runner_bounds_output(tmp_path: Path) -> None:
    script = make_script(tmp_path, "loud", "print('x' * 500000)\n")
    output = SubprocessProbeRunner(max_output=1000).run([str(script)], timeout=10)
    assert len(output.stdout) <= 1000


# --- launch rules -----------------------------------------------------------


def test_launch_dir_and_files_are_private(launcher, tool, notebook) -> None:
    launch_id, workdir = start(launcher, tool, notebook, free_port())
    assert stat.S_IMODE(workdir.stat().st_mode) == 0o700
    record = read_record(tool.parent)
    assert record["token_mode"] == 0o600 and record["token_length"] == len(TOKEN)
    assert stat.S_IMODE((workdir / ".marimo.toml").stat().st_mode) == 0o600
    assert record["cwd"] == os.path.realpath(workdir)
    assert "auto_instantiate = false" in record["config"]
    assert launcher.is_running(launch_id)


def test_token_never_in_argv_and_output_is_redacted(launcher, tool, notebook) -> None:
    launch_id, _ = start(launcher, tool, notebook, free_port())
    record = read_record(tool.parent)
    assert not any(TOKEN in arg for arg in record["argv"])
    deadline = time.monotonic() + 5
    while not launcher.recent_output(launch_id) and time.monotonic() < deadline:
        time.sleep(0.02)
    output = "\n".join(launcher.recent_output(launch_id))
    assert "access_token=[redacted]" in output and TOKEN not in output


def test_secret_in_argv_is_refused(launcher, tool, notebook) -> None:
    workdir = launcher.create_launch_dir()
    with pytest.raises(ValueError, match="secret"):
        launcher.start(
            argv=[str(tool), "edit", f"--token-password={TOKEN}"], workdir=workdir,
            host=HOST, port=free_port(), files={}, secrets=[TOKEN],
        )  # fmt: skip
    assert launcher.owned_ids() == []


def test_environment_is_allow_listed(launcher, tool, notebook, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "should-not-leak")
    start(launcher, tool, notebook, free_port())
    env = read_record(tool.parent)["env"]
    assert "OPENROUTER_API_KEY" not in env
    assert env.get("PATH") == os.environ["PATH"]


@pytest.mark.parametrize("host", ["0.0.0.0", "localhost", "192.168.1.2"])  # noqa: S104
def test_non_loopback_host_is_refused(launcher, tool, host: str) -> None:
    workdir = launcher.create_launch_dir()
    with pytest.raises(ValueError, match="loopback"):
        launcher.start(argv=[str(tool)], workdir=workdir, host=host, port=1, files={}, secrets=[])


def test_foreign_workdir_and_bad_file_names_are_refused(launcher, tool, tmp_path) -> None:
    with pytest.raises(ValueError, match="launch directory"):
        launcher.start(
            argv=[str(tool)], workdir=tmp_path, host=HOST, port=free_port(), files={}, secrets=[]
        )
    workdir = launcher.create_launch_dir()
    with pytest.raises(ValueError, match="file name"):
        launcher.start(
            argv=[str(tool)], workdir=workdir, host=HOST, port=free_port(),
            files={"../escape": "x"}, secrets=[],
        )  # fmt: skip


def test_unrelated_listener_is_refused_and_left_running(launcher, tool, notebook) -> None:
    port = free_port()
    with unrelated_listener(port) as other:
        assert not launcher.port_available(HOST, port)
        with pytest.raises(PortInUseError) as caught:
            start(launcher, tool, notebook, port)
        assert caught.value.errno == errno.EADDRINUSE
        assert launcher.owned_ids() == []
        launcher.stop_all()
        assert other.poll() is None and alive(other.pid)
    assert not (tool.parent / "record.json").exists()  # the editor never started


# --- stop and cleanup -------------------------------------------------------


def test_stop_cleans_the_whole_owned_group(launcher, tool, notebook) -> None:
    before = file_digest(notebook)
    port = free_port()
    launch_id, workdir = start(launcher, tool, notebook, port)
    record = read_record(tool.parent)
    assert record["pgid"] == record["pid"]  # its own process group
    assert alive(record["child_pid"])
    result = launcher.stop(launch_id)
    assert result.stopped and not result.escalated
    assert wait_gone(record["pid"]) and wait_gone(record["child_pid"])
    assert not workdir.exists()  # token file removed with the launch directory
    assert file_digest(notebook) == before
    assert launcher.port_available(HOST, port)
    assert launcher.owned_ids() == []


def test_stop_escalates_after_bounded_wait(launcher, tool, notebook) -> None:
    (tool.parent / "ignore_term").write_text("")
    launch_id, _ = start(launcher, tool, notebook, free_port())
    record = read_record(tool.parent)
    began = time.monotonic()
    result = launcher.stop(launch_id)
    assert result.stopped and result.escalated
    assert time.monotonic() - began < 6
    assert wait_gone(record["pid"]) and wait_gone(record["child_pid"])


def test_stop_unknown_id_touches_nothing(launcher) -> None:
    with pytest.raises(KeyError):
        launcher.stop("not-mine")


def test_early_exit_is_reported_and_cleaned(launcher, tool, notebook) -> None:
    (tool.parent / "exit_early").write_text("")
    with pytest.raises(LaunchError, match="code 7"):
        start(launcher, tool, notebook, free_port())
    record = read_record(tool.parent)
    assert wait_gone(record["child_pid"])
    assert launcher.owned_ids() == []
    assert list((launcher.runtime_dir).iterdir()) == []


def test_ready_timeout_stops_the_process(tmp_path, tool, notebook) -> None:
    (tool.parent / "never_listen").write_text("")
    # The fake writes its record before it waits. Under parallel load a 1 s
    # limit could stop it before that write, so the limit leaves room for it.
    owned = OwnedProcessLauncher(
        tmp_path / "rt", grace_seconds=0.5, kill_wait_seconds=2.0, ready_timeout=5.0
    )
    with pytest.raises(LaunchError, match="did not listen"):
        start(owned, tool, notebook, free_port())
    record = read_record(tool.parent)
    assert wait_gone(record["pid"]) and wait_gone(record["child_pid"])
    assert owned.owned_ids() == []


def test_stop_all_stops_every_owned_launch(launcher, tmp_path, notebook) -> None:
    tools = [make_fake_editor(tmp_path / f"tool{i}") for i in range(2)]
    for item in tools:
        start(launcher, item, notebook, free_port())
    pids = [read_record(item.parent)["pid"] for item in tools]
    results = launcher.stop_all()
    assert len(results) == 2 and all(r.stopped for r in results)
    assert all(wait_gone(pid) for pid in pids)


def test_launcher_runs_without_shell(tmp_path) -> None:
    marker = tmp_path / "pwned"
    script = make_script(
        tmp_path / "t", "echoargs",
        "import sys, json, pathlib\n"
        "pathlib.Path(sys.argv[0]).with_name('args.json').write_text(json.dumps(sys.argv[1:]))\n"
        "sys.exit(3)\n",
    )  # fmt: skip
    # The script exits after it writes args.json, so the launch fails only
    # after that write. A ready timeout could stop it before the write.
    owned = OwnedProcessLauncher(tmp_path / "rt2", ready_timeout=30.0, grace_seconds=0.2)
    payload = f"; touch {marker}"
    with pytest.raises(LaunchError, match="code 3"):
        owned.start(
            argv=[str(script), payload], workdir=owned.create_launch_dir(), host=HOST,
            port=free_port(), files={}, secrets=[],
        )  # fmt: skip
    assert not marker.exists()
    assert json.loads((script.parent / "args.json").read_text()) == [payload]


def test_discard_launch_dir_removes_only_unused_owned_dirs(launcher, tmp_path) -> None:
    workdir = launcher.create_launch_dir()
    launcher.discard_launch_dir(workdir)
    assert not workdir.exists()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    launcher.discard_launch_dir(foreign)
    assert foreign.exists()


def test_empty_argv_is_refused(launcher) -> None:
    with pytest.raises(ValueError, match="argv"):
        launcher.start(
            argv=[], workdir=launcher.create_launch_dir(), host=HOST, port=free_port(),
            files={}, secrets=[],
        )  # fmt: skip
