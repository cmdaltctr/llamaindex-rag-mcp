"""Unit tests for the power control argv builders and runner (design D1, D2, D6).

The tests never run ``launchctl``. ``subprocess.run`` is replaced where a
test needs to see how the runner calls it.
"""

from __future__ import annotations

import ast
import asyncio
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from omrg.transports.api import power_control  # noqa: E402
from omrg.transports.api.power_control import (  # noqa: E402
    ACTIONS,
    PowerControl,
    build_argv,
    run_argv,
)
from omrg.transports.cli import _launchagent  # noqa: E402

LABEL = "com.omrg.web"
UID = 501


def test_restart_argv_equals_the_cli_kill_command() -> None:
    """D6: the API copy cannot drift from the helper that ``omrg web restart`` uses."""
    assert build_argv("restart", UID, LABEL) == _launchagent.kill_command(UID, LABEL, "SIGTERM")


def test_off_argv_equals_the_cli_bootout_command() -> None:
    assert build_argv("off", UID, LABEL) == _launchagent.bootout_command(UID, LABEL)


def test_the_two_actions_are_the_closed_set() -> None:
    assert set(ACTIONS) == {"restart", "off"}


def test_unknown_action_has_no_argv() -> None:
    with pytest.raises(ValueError):
        build_argv("sleep", UID, LABEL)


def test_kickstart_is_never_used() -> None:
    """ADR-085 rejected ``kickstart -k``: it can skip the clean shutdown."""
    for action in ACTIONS:
        assert "kickstart" not in build_argv(action, UID, LABEL)


def test_control_builds_argv_from_its_label_and_uid() -> None:
    control = PowerControl(label=LABEL, uid=UID)
    assert control.argv("restart") == _launchagent.kill_command(UID, LABEL, "SIGTERM")
    assert control.argv("off") == _launchagent.bootout_command(UID, LABEL)


def test_the_module_does_not_import_the_cli_package() -> None:
    """The API must not import from ``transports/cli`` (design D6)."""
    tree = ast.parse(Path(power_control.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom):
            names = [("." * node.level) + (node.module or "")]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        assert not any("cli" in name.split(".") for name in names), names


# ── Runner ───────────────────────────────────────────────────────────────


class FakeRun:
    """Stands in for ``subprocess.run`` and records how it was called."""

    def __init__(self, result: Any = None) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.result = result if result is not None else subprocess.CompletedProcess([], 0, "", "")

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        self.calls.append((argv, kwargs))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> FakeRun:
    fake = FakeRun()
    monkeypatch.setattr(power_control.subprocess, "run", fake)
    return fake


def test_runner_passes_the_argv_with_no_shell_and_a_timeout(fake_run: FakeRun) -> None:
    argv = build_argv("off", UID, LABEL)
    run_argv(argv)
    [(called, kwargs)] = fake_run.calls
    assert called == argv
    assert isinstance(called, list)
    assert not kwargs.get("shell", False)
    assert isinstance(kwargs["timeout"], (int, float)) and 0 < kwargs["timeout"] <= 60
    assert kwargs["check"] is False


def test_runner_returns_the_exit_status(fake_run: FakeRun) -> None:
    fake_run.result = subprocess.CompletedProcess([], 113, "", "no such service")
    assert run_argv(["launchctl", "x"]) == 113


def test_runner_logs_and_swallows_a_nonzero_exit(
    fake_run: FakeRun, caplog: pytest.LogCaptureFixture
) -> None:
    fake_run.result = subprocess.CompletedProcess([], 3, "", "boom")
    with caplog.at_level("WARNING", logger=power_control.__name__):
        run_argv(["launchctl", "x"])
    assert any("exit 3" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    "error",
    [subprocess.TimeoutExpired(["launchctl"], 10), FileNotFoundError("launchctl")],
)
def test_runner_never_raises(fake_run: FakeRun, error: BaseException) -> None:
    fake_run.result = error
    assert run_argv(["launchctl", "x"]) is None


# ── Act after a delay ────────────────────────────────────────────────────


def test_act_waits_for_the_delay_then_runs_the_argv() -> None:
    order: list[Any] = []

    async def sleeper(seconds: float) -> None:
        order.append(("sleep", seconds))

    def runner(argv: list[str]) -> int:
        order.append(("run", argv))
        return 0

    control = PowerControl(label=LABEL, uid=UID, runner=runner, delay=0.5, sleep=sleeper)
    asyncio.run(control.act("restart"))
    assert order == [("sleep", 0.5), ("run", control.argv("restart"))]


def test_act_swallows_a_runner_failure(caplog: pytest.LogCaptureFixture) -> None:
    def runner(argv: list[str]) -> int:
        raise RuntimeError("boom")

    control = PowerControl(label=LABEL, uid=UID, runner=runner, delay=0)
    with caplog.at_level("ERROR", logger=power_control.__name__):
        asyncio.run(control.act("off"))
    assert any("off" in record.getMessage() for record in caplog.records)


def test_default_delay_lets_the_response_leave_first() -> None:
    """Design D2: half a second."""
    assert PowerControl(label=LABEL, uid=UID).delay == 0.5
