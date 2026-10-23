"""``omrs web`` sets the power control only for the login item (design D3).

The server is never started: ``_serve`` and the socket are replaced, and the
test reads the application state at the moment the fake server runs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from typer.testing import CliRunner  # noqa: E402

from omrs.transports.api.power_control import PowerControl  # noqa: E402
from omrs.transports.cli import app as cli_app  # noqa: E402

runner = CliRunner()


def _state_when_served(workspace: Path, *args: str) -> Any:
    seen: dict[str, Any] = {}

    def fake_serve(application: Any, sock: Any, **kwargs: Any) -> bool:
        seen["control"] = getattr(application.state, "power_control", None)
        return True

    sock = MagicMock()
    sock.getsockname.return_value = ("127.0.0.1", 4242)
    with (
        patch("omrs.transports.cli.web._bind_socket", return_value=sock),
        patch("omrs.transports.cli.web._serve", side_effect=fake_serve),
    ):
        result = runner.invoke(cli_app, ["web", "--workspace", str(workspace), *args])
    assert result.exit_code == 0, result.output
    return seen["control"]


def test_the_login_item_carries_a_power_control(tmp_path: Path) -> None:
    control = _state_when_served(tmp_path / "ws", "--login-item")
    assert isinstance(control, PowerControl)
    assert control.label == "com.omrs.web"
    assert control.uid == os.getuid()


def test_a_foreground_server_carries_none(tmp_path: Path) -> None:
    assert _state_when_served(tmp_path / "ws", "--port", "4242") is None
