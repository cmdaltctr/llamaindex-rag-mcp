"""``omrg web`` as a command group (add-web-login-item, group 1).

``omrg web`` keeps starting the server in the foreground. The five login
item subcommands sit beside it. These cases pin that the conversion from
one command to a group did not change how the old form parses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from typer.testing import CliRunner  # noqa: E402

from omrg.transports.cli import app as cli_app  # noqa: E402

runner = CliRunner()

SUBCOMMANDS = ("install", "uninstall", "status", "restart", "open")


def _invoke_foreground(workspace: Path, *args: str) -> tuple[Any, MagicMock]:
    """Run ``omrg web`` with the bind and the server replaced."""
    sock = MagicMock()
    sock.getsockname.return_value = ("127.0.0.1", 4242)
    with (
        patch("omrg.transports.cli.web._bind_socket", return_value=sock),
        patch("omrg.transports.cli.web._serve", return_value=True) as serve,
    ):
        result = runner.invoke(cli_app, ["web", "--workspace", str(workspace), *args])
    return result, serve


def test_help_lists_the_login_item_subcommands() -> None:
    result = runner.invoke(cli_app, ["web", "--help"])

    assert result.exit_code == 0
    for name in SUBCOMMANDS:
        assert name in result.output


def test_old_form_still_reaches_the_server_start(tmp_path: Path) -> None:
    result, serve = _invoke_foreground(tmp_path / "ws", "--port", "0")

    assert result.exit_code == 0, result.output
    serve.assert_called_once()


def test_subcommand_help_prints_help() -> None:
    result = runner.invoke(cli_app, ["web", "install", "--help"])

    assert result.exit_code == 0
    assert "omrg web install" in result.output


def test_a_subcommand_does_not_start_the_server() -> None:
    # Click runs the group callback before it parses the subcommand, so a
    # missing guard would bind a port here.
    with (
        patch("omrg.transports.cli.web._bind_socket") as bind,
        patch("omrg.transports.cli.web._serve") as serve,
    ):
        result = runner.invoke(cli_app, ["web", "install", "--help"])

    assert "omrg web install" in result.output
    bind.assert_not_called()
    serve.assert_not_called()


def test_login_item_refuses_a_free_port(tmp_path: Path) -> None:
    result, serve = _invoke_foreground(tmp_path / "ws", "--login-item", "--port", "0")

    assert result.exit_code == 2
    assert "--login-item" in result.output
    assert "--port 0" in result.output
    serve.assert_not_called()


def test_login_item_is_hidden_from_help() -> None:
    result = runner.invoke(cli_app, ["web", "--help"])

    assert "--login-item" not in result.output
