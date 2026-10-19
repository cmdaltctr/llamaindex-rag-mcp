"""The web workspace guide matches the real command and API (task 6.9).

The guide's option table must equal the options of ``omrg web --help``.
Its missing-extra message must equal the message the command prints.
Every repository path, ``/v1`` route and relative link it cites must
exist. The API must answer unknown ``/v1`` paths and unexpected errors with
the JSON envelope, never with the application HTML, even when built
assets are present.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

import typer  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_guides_support import (  # noqa: E402
    GUIDES,
    REPO,
    broken_links,
    links_to,
    missing_repository_paths,
    undeclared_routes,
)
from typer.testing import CliRunner  # noqa: E402

from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.security import AccessPolicy  # noqa: E402
from omrg.transports.cli import app as cli_app  # noqa: E402
from omrg.transports.cli.web import INSTALL_HINT  # noqa: E402

GUIDE = GUIDES / "web-workspace.md"
BASE = "http://127.0.0.1:8765"
ORIGIN = {"Origin": BASE}
_OPTIONS_TABLE = re.compile(r"<!-- web-options -->(.*?)<!-- /web-options -->", re.S)
_MISSING_EXTRA = re.compile(r"<!-- web-missing-extra -->\s*```text\n(.*?)\n```", re.S)
_OPTION = re.compile(r"--[a-z][a-z-]*")
runner = CliRunner()


def _text() -> str:
    return GUIDE.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _guide_options() -> set[str]:
    table = _OPTIONS_TABLE.search(_text())
    assert table is not None, "the guide has no web-options table"
    rows = [line for line in table.group(1).splitlines() if line.startswith("| `--")]
    return {_OPTION.match(row[3:]).group() for row in rows}  # type: ignore[union-attr]


def test_guide_options_equal_the_web_command_options() -> None:
    """Every documented option exists, and every visible option is documented.

    ``--login-item`` is hidden on purpose: only the login item runs it.
    """
    result = runner.invoke(cli_app, ["web", "--help"], env={"COLUMNS": "200", "NO_COLOR": "1"})
    assert result.exit_code == 0, result.output
    in_help = set(_OPTION.findall(result.output)) - {"--help"}
    command = typer.main.get_command(cli_app).commands["web"]  # type: ignore[attr-defined]
    declared = {
        name
        for param in command.params
        if not getattr(param, "hidden", False)
        for name in param.opts
    } - {"--help"}
    assert _guide_options() == declared
    assert declared <= in_help


def test_missing_extra_message_matches_the_guide(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guide quotes the exact message that ``omrg web`` prints."""
    block = _MISSING_EXTRA.search(_text())
    assert block is not None, "the guide does not quote the missing-extra message"
    assert block.group(1).strip() == INSTALL_HINT
    monkeypatch.setitem(sys.modules, "fastapi", None)
    result = runner.invoke(cli_app, ["web"])
    assert result.exit_code == 1
    assert _flat(INSTALL_HINT) in _flat(result.output)


def test_documented_install_commands_name_the_real_extra() -> None:
    """``uv sync --extra web`` and ``omrg[web]`` refer to an existing extra."""
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r"^web = \[", pyproject, re.M)
    for command in ("uv sync --extra web", 'pip install "omrg[web]"'):
        assert command in _text()
        assert command in INSTALL_HINT


def test_cited_paths_routes_and_links_exist() -> None:
    text = _text()
    assert missing_repository_paths(text) == []
    assert undeclared_routes(text) == []
    assert broken_links(GUIDE) == []


def test_guide_is_linked_from_the_reference_documents() -> None:
    for document in (
        GUIDES / "cli-reference.md",
        GUIDES / "configuration.md",
        REPO / "README.md",
    ):
        assert links_to(document, "web-workspace.md"), document


# ── API fallback never serves HTML ──────────────────────────────────────


class _BrokenStore:
    """A store whose listing fails with an unexpected error."""

    def list_collections(self) -> list[str]:
        raise ZeroDivisionError("unexpected")


class _FakeEngine:
    store = _BrokenStore()

    def close(self) -> None:
        return None


def _app_with_assets(tmp_path: Path) -> tuple[Any, AccessPolicy]:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><html><div id=root></div>", "utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=static)
    policy = AccessPolicy.for_launch(config.host, config.port)
    return create_app(config, policy=policy, engine_factory=_FakeEngine), policy


def _assert_envelope(response: Any, status: int) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert "<html" not in response.text.lower()
    assert "id=root" not in response.text
    body = response.json()
    assert body["status"] == "error" and isinstance(body["message"], str)
    return body


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/no-such-route"),
        ("GET", "/v1/collections/x/nothing/here"),
        ("POST", "/v1/no-such-route"),
        ("DELETE", "/v1/runs/x/unknown"),
    ],
)
def test_unknown_api_paths_return_the_envelope_with_assets_built(
    tmp_path: Path, method: str, path: str
) -> None:
    """A signed-in browser gets the envelope for unknown ``/v1`` paths."""
    app, policy = _app_with_assets(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert "id=root" in client.get("/library").text  # the SPA fallback is live
        client.post("/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers=ORIGIN)
        response = client.request(method, path, headers=ORIGIN)
    _assert_envelope(response, 404)


def test_unexpected_server_error_returns_the_envelope(tmp_path: Path) -> None:
    """A 500 has the envelope, the fixed message and no detail."""
    app, policy = _app_with_assets(tmp_path)
    with TestClient(app, base_url=BASE, raise_server_exceptions=False) as client:
        client.post("/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers=ORIGIN)
        response = client.get("/v1/collections")
    body = _assert_envelope(response, 500)
    assert body["message"] == "Internal server error."
    assert body["error_type"] == "internal"
    assert "ZeroDivisionError" not in response.text and "unexpected" not in body["message"]
