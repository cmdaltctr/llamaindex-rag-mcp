"""``omrs web start`` (add-web-power-menu, group 3).

Every case runs on the fakes in ``test_web_login_item_support``: a
temporary home, a fake ``launchctl`` runner, a fake health check and a
fake clock. No test runs the real ``launchctl``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.unit.test_web_login_item_support import Harness, flat

#: ``launchctl print`` exit code for an agent that is not loaded.
_NOT_LOADED = 113


@pytest.fixture
def h(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(tmp_path, monkeypatch)


def _bootstrap_call(h: Harness) -> list[str]:
    return ["launchctl", "bootstrap", f"gui/{h.uid}", str(h.plist)]


def test_start_after_turn_off_loads_the_agent_and_waits_for_the_app(h: Harness) -> None:
    """The agent is unloaded and the plist stays: start loads it and waits."""
    h.install_real_plist()
    h.launchctl_rc["print"] = _NOT_LOADED
    h.serve("2.5.0", after=5.0)

    result = h.invoke("start")

    assert result.exit_code == 0, result.output
    assert _bootstrap_call(h) in h.launchctl_calls
    assert h.now >= 5.0
    text = flat(result.output)
    assert "2.5.0" in text
    assert "omrs web open" in text


def test_start_when_already_running_says_so_and_loads_nothing(h: Harness) -> None:
    h.install_real_plist()
    h.serve()

    result = h.invoke("start")

    assert result.exit_code == 0, result.output
    assert "Nothing to start" in flat(result.output)
    assert "Waiting" not in result.output
    assert h.launchctl_calls == []


def test_start_when_not_installed_names_install_and_exits_1(h: Harness) -> None:
    result = h.invoke("start")

    assert result.exit_code == 1
    assert "omrs web install" in flat(result.output)
    assert h.launchctl_calls == []


def test_start_on_another_platform_prints_a_message_and_exits_1(h: Harness) -> None:
    h.install_real_plist()
    h.macos = False

    result = h.invoke("start")

    assert result.exit_code == 1
    assert "macOS" in flat(result.output)
    assert h.launchctl_calls == []


def test_start_does_not_load_an_agent_that_is_loaded_but_still_starting(h: Harness) -> None:
    """A second bootstrap of a loaded agent fails, so start only waits."""
    h.install_real_plist()
    h.serve(after=3.0)

    result = h.invoke("start")

    assert result.exit_code == 0, result.output
    assert "bootstrap" not in h.verbs()
    assert h.now >= 3.0


def test_start_reports_a_failed_load_and_exits_1(h: Harness) -> None:
    h.install_real_plist()
    h.launchctl_rc["print"] = _NOT_LOADED
    h.launchctl_rc["bootstrap"] = 5

    result = h.invoke("start")

    assert result.exit_code == 1
    assert "bootstrap" in flat(result.output)


def test_start_exits_1_when_the_app_never_answers(h: Harness) -> None:
    h.install_real_plist()
    h.launchctl_rc["print"] = _NOT_LOADED

    result = h.invoke("start")

    assert result.exit_code == 1
    assert "60 seconds" in flat(result.output)
    assert str(h.error_log) in flat(result.output)
