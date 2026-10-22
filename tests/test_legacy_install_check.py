"""Startup check for an old OMRG install (change ``rename-omrg-to-omrs``).

Spec: ``legacy-install-migration``, requirement "An old OMRG install is
detected and refused". Every test runs against a temporary ``HOME``. The real
``~/.omrg`` and ``~/.config/omrg`` are never read.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from omrs.config.legacy_install import (
    LegacyInstallError,
    ensure_no_legacy_install,
    find_legacy_signs,
)
from omrs.transports.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _skip_legacy_install_check() -> None:
    """Override the conftest fixture: this module tests the real check."""


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return an empty temporary HOME with every old-install sign cleared."""
    import os

    for name in list(os.environ):
        if name.startswith(("OMRG_", "OMRS_")):
            monkeypatch.delenv(name)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _plant_plist(home: Path, label: str) -> Path:
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    plist = agents / f"{label}.plist"
    plist.write_text("<plist/>", encoding="utf-8")
    return plist


# ── Detection ─────────────────────────────────────────────────────────


def test_clean_install_has_no_signs(home: Path) -> None:
    assert find_legacy_signs(env={}, home=home) == []
    ensure_no_legacy_install(env={}, home=home)  # does not raise


def test_environment_variable_is_a_sign(home: Path) -> None:
    signs = find_legacy_signs(env={"OMRG_CONFIG_DIR": "/x", "PATH": "/bin"}, home=home)
    assert [(s.found, s.replacement) for s in signs] == [("OMRG_CONFIG_DIR", "OMRS_CONFIG_DIR")]


def test_data_folder_is_a_sign(home: Path) -> None:
    (home / ".omrg").mkdir()
    signs = find_legacy_signs(env={}, home=home)
    assert [(s.found, s.replacement) for s in signs] == [("~/.omrg", "~/.omrs")]


def test_config_folder_is_a_sign(home: Path) -> None:
    (home / ".config" / "omrg").mkdir(parents=True)
    signs = find_legacy_signs(env={}, home=home)
    assert [(s.found, s.replacement) for s in signs] == [("~/.config/omrg", "~/.config/omrs")]


def test_xdg_config_folder_is_a_sign(home: Path) -> None:
    xdg = home / "xdg"
    (xdg / "omrg").mkdir(parents=True)
    signs = find_legacy_signs(env={"XDG_CONFIG_HOME": str(xdg)}, home=home)
    assert [(s.found, s.replacement) for s in signs] == [("~/xdg/omrg", "~/xdg/omrs")]


def test_launchd_plist_is_a_sign(home: Path) -> None:
    _plant_plist(home, "com.omrg.web")
    _plant_plist(home, "com.omrg.watch.docs-1a2b3c4d")
    _plant_plist(home, "com.other.tool")
    signs = find_legacy_signs(env={}, home=home)
    assert [(s.found, s.replacement) for s in signs] == [
        ("com.omrg.watch.docs-1a2b3c4d", "com.omrs.watch.docs-1a2b3c4d"),
        ("com.omrg.web", "com.omrs.web"),
    ]


def test_new_names_are_not_signs(home: Path) -> None:
    (home / ".omrs").mkdir()
    (home / ".config" / "omrs").mkdir(parents=True)
    _plant_plist(home, "com.omrs.web")
    assert find_legacy_signs(env={"OMRS_CONFIG_DIR": "/x"}, home=home) == []


def test_keychain_alone_is_not_a_sign_and_is_never_read(home: Path) -> None:
    """Design D2a: no keychain call at startup."""
    with patch(
        "omrs.integrations.keychain._current_backend",
        side_effect=AssertionError("the startup check must not call the keychain"),
    ):
        assert find_legacy_signs(env={}, home=home) == []


def test_refusal_names_every_sign_and_the_command(home: Path) -> None:
    (home / ".omrg").mkdir()
    with pytest.raises(LegacyInstallError) as caught:
        ensure_no_legacy_install(env={"OMRG_TOKEN_FILE": "/t"}, home=home)
    text = str(caught.value)
    for expected in ("OMRG_TOKEN_FILE", "OMRS_TOKEN_FILE", "~/.omrg", "~/.omrs", "omrs migrate"):
        assert expected in text


def test_check_only_reads(home: Path) -> None:
    (home / ".omrg").mkdir()
    before = sorted(p.relative_to(home) for p in home.rglob("*"))
    find_legacy_signs(env={}, home=home)
    assert sorted(p.relative_to(home) for p in home.rglob("*")) == before


# ── Every transport refuses ───────────────────────────────────────────


def test_variable_stops_web_start(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(home / "cfg"))
    with patch(
        "omrs.transports.cli.web_login_item._installed_plan",
        side_effect=AssertionError("the command must not start"),
    ):
        result = runner.invoke(app, ["web", "start"])
    assert result.exit_code != 0
    output = result.stdout + result.stderr
    for expected in ("OMRG_CONFIG_DIR", "OMRS_CONFIG_DIR", "omrs migrate"):
        assert expected in output


def test_data_folder_stops_the_stdio_server(home: Path) -> None:
    (home / ".omrg").mkdir()
    with patch(
        "omrs.transports.mcp.main",
        side_effect=AssertionError("the server must not start"),
    ):
        result = runner.invoke(app, [])
    assert result.exit_code != 0
    assert result.stdout == ""  # stdout is the protocol channel
    assert "~/.omrg" in result.stderr
    assert "omrs migrate" in result.stderr


def test_direct_mcp_main_refuses_on_stderr(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from omrs.transports import mcp

    (home / ".omrg").mkdir()
    with pytest.raises(SystemExit) as exit_info:
        mcp.main()
    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "omrs migrate" in captured.err


def test_old_login_item_stops_a_cli_command(home: Path) -> None:
    _plant_plist(home, "com.omrg.web")
    result = runner.invoke(app, ["list"])
    assert result.exit_code != 0
    assert "com.omrs.web" in result.stdout + result.stderr


def test_clean_install_passes_the_check(home: Path) -> None:
    with (
        patch("omrs.transports.cli.web_login_item._is_macos", return_value=True),
        patch("omrs.transports.cli.web_login_item._installed_plan", return_value=(None, None)),
    ):
        result = runner.invoke(app, ["web", "start"])
    # The command ran past the check and stopped for its own reason.
    assert "migrate" not in result.stdout + result.stderr


def test_help_and_version_skip_the_check(home: Path) -> None:
    (home / ".omrg").mkdir()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert runner.invoke(app, ["--version"]).exit_code == 0


# ── Watcher installer recognises the old label (design D2) ────────────


def test_installer_finds_a_watcher_plist_with_the_old_label(home: Path) -> None:
    """``install-login-watcher`` treats a ``com.omrg.watch.*`` plist as the same watcher."""
    import plistlib

    from omrs.transports.cli import _launchagent

    watch = home / "docs"
    watch.mkdir()
    plan = _launchagent.build_plan(watch, "docs", 2.0, command_path="/bin/echo", home=home)
    old = _plant_plist(home, "com.omrg.watch.docs-1a2b3c4d")
    old.write_bytes(
        plistlib.dumps({"ProgramArguments": ["/x/omrg", "watch", str(plan.watch_path)]})
    )

    assert _launchagent.find_existing_plist(plan) == old
