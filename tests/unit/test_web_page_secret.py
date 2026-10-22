"""Persistent workspace sign-in secret (persistent-web-auth-token).

Covers the ``local-web-workspace`` scenarios: the secret file is private
and reused, the server puts the secret only into its own page, a page that
the server served signs in again after a restart without a launch link,
and the secret never reaches a log, an API body or the terminal.
"""

from __future__ import annotations

import logging
import re
import stat
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from omrs.transports.api.app import create_app  # noqa: E402
from omrs.transports.api.launch_link import LINK_FILE_NAME, RearmingAccessPolicy  # noqa: E402
from omrs.transports.api.lifespan import WebConfig  # noqa: E402
from omrs.transports.api.page_secret import (  # noqa: E402
    PAGE_SECRET_FILE_NAME,
    PageSecret,
)
from omrs.transports.api.security import MAX_BOOTSTRAP_FAILURES, AccessPolicy  # noqa: E402
from omrs.transports.cli import app as cli_app  # noqa: E402

BASE = "http://127.0.0.1:8765"
ORIGIN = {"Origin": BASE}
_META = re.compile(r'<meta name="omrs-page-secret" content="([^"]+)"')
runner = CliRunner()


class FakeEngine:
    def close(self) -> None:
        return None


def _static(tmp_path: Path) -> Path:
    static = tmp_path / "static"
    static.mkdir(exist_ok=True)
    (static / "index.html").write_text(
        "<!doctype html><html><head><title>OMRS</title></head>"
        "<body><div id=root></div></body></html>",
        encoding="utf-8",
    )
    return static


def _app(
    tmp_path: Path,
    policy: AccessPolicy | None = None,
    *,
    extra_origins: tuple[str, ...] = (),
) -> tuple[Any, AccessPolicy, PageSecret]:
    """Build an app the way ``omrs web`` does: a fresh policy, the workspace secret."""
    workspace = tmp_path / "ws"
    config = WebConfig(
        workspace=workspace, host="127.0.0.1", port=8765, static_dir=_static(tmp_path)
    )
    if policy is None:
        policy = AccessPolicy.for_launch(config.host, config.port, extra_origins=extra_origins)
    secret = PageSecret.load_or_create(workspace)
    app = create_app(config, policy=policy, engine_factory=FakeEngine, page_secret=secret)
    return app, policy, secret


def _served_secret(html: str) -> str | None:
    match = _META.search(html)
    return None if match is None else match.group(1)


# ── The secret file ────────────────────────────────────────────────────


def test_first_start_creates_a_private_secret_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"

    secret = PageSecret.load_or_create(workspace)

    path = workspace / PAGE_SECRET_FILE_NAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
    assert path.read_text(encoding="utf-8").strip() == secret.value
    assert secret.value.startswith("omrs_bs_")
    assert len(secret.value) >= 40
    assert secret.value not in repr(secret)


def test_later_starts_reuse_the_secret(tmp_path: Path) -> None:
    first = PageSecret.load_or_create(tmp_path / "ws")
    second = PageSecret.load_or_create(tmp_path / "ws")
    other = PageSecret.load_or_create(tmp_path / "other")

    assert second.value == first.value
    assert other.value != first.value


def test_a_loose_mode_is_tightened_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    first = PageSecret.load_or_create(tmp_path / "ws")
    path = tmp_path / "ws" / PAGE_SECRET_FILE_NAME
    path.chmod(0o644)

    with caplog.at_level(logging.WARNING, logger="omrs"):
        again = PageSecret.load_or_create(tmp_path / "ws")

    assert again.value == first.value
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "0600" in caplog.text
    assert first.value not in caplog.text


def test_a_broken_file_is_replaced_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir(mode=0o700)
    path = workspace / PAGE_SECRET_FILE_NAME
    path.write_text("not a secret\n", encoding="utf-8")
    path.chmod(0o600)

    with caplog.at_level(logging.WARNING, logger="omrs"):
        secret = PageSecret.load_or_create(workspace)

    assert secret.value.startswith("omrs_bs_")
    assert path.read_text(encoding="utf-8").strip() == secret.value
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "not a valid" in caplog.text


def test_matches_only_the_exact_secret(tmp_path: Path) -> None:
    secret = PageSecret.load_or_create(tmp_path / "ws")

    assert secret.matches(secret.value)
    assert not secret.matches(secret.value + "x")
    assert not secret.matches("")


# ── The page carries the secret only to its own origin ─────────────────


def test_two_app_instances_on_one_workspace_serve_the_same_secret(tmp_path: Path) -> None:
    first_app, _, _ = _app(tmp_path)
    second_app, _, _ = _app(tmp_path)

    with TestClient(first_app, base_url=BASE) as client:
        first = _served_secret(client.get("/").text)
    with TestClient(second_app, base_url=BASE) as client:
        second = _served_secret(client.get("/library").text)

    assert first is not None
    assert first == second
    assert first == (tmp_path / "ws" / PAGE_SECRET_FILE_NAME).read_text("utf-8").strip()


def test_the_page_with_the_secret_is_not_cached(tmp_path: Path) -> None:
    app, _, _ = _app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        page = client.get("/")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert "<div id=root>" in page.text


def test_a_foreign_host_never_gets_the_page(tmp_path: Path) -> None:
    """DNS rebinding: a foreign name that resolves to loopback is refused."""
    app, _, secret = _app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        response = client.get("/", headers={"Host": "evil.example:8765"})
    assert response.status_code == 400
    assert secret.value not in response.text


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "http://evil.example"},
        {"Origin": "http://127.0.0.1:9999"},
        {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "no-cors"},
        {"Sec-Fetch-Site": "same-site", "Sec-Fetch-Mode": "cors"},
    ],
)
def test_a_foreign_reader_gets_the_page_without_the_secret(
    tmp_path: Path, headers: dict[str, str]
) -> None:
    app, _, secret = _app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        response = client.get("/", headers=headers)
    assert response.status_code == 200
    assert "<div id=root>" in response.text
    assert secret.value not in response.text
    assert _served_secret(response.text) is None


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate"},
        {"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "navigate"},
        {"Origin": BASE},
    ],
)
def test_an_own_page_load_gets_the_secret(tmp_path: Path, headers: dict[str, str]) -> None:
    app, _, secret = _app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        response = client.get("/", headers=headers)
    assert _served_secret(response.text) == secret.value


def test_an_approved_preview_origin_gets_the_secret_and_signs_in(tmp_path: Path) -> None:
    preview = "http://app.orca.localhost:57977"
    app, _, secret = _app(tmp_path, extra_origins=(preview,))
    with TestClient(app, base_url=BASE) as client:
        page = client.get("/", headers={"Origin": preview})
        session = client.post(
            "/v1/session", json={"bootstrap": secret.value}, headers={"Origin": preview}
        )
    assert _served_secret(page.text) == secret.value
    assert session.status_code == 200


def test_sign_in_with_the_secret_needs_an_allowed_origin(tmp_path: Path) -> None:
    app, _, secret = _app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        refused = client.post(
            "/v1/session",
            json={"bootstrap": secret.value},
            headers={"Origin": "http://evil.example"},
        )
    assert refused.status_code == 403
    assert "set-cookie" not in refused.headers


# ── Restart acceptance ─────────────────────────────────────────────────


def test_an_open_tab_signs_in_again_after_a_restart_without_a_launch_link(
    tmp_path: Path,
) -> None:
    """The core acceptance case: same workspace, new process, no bootstrap link."""
    before, policy_before, _ = _app(tmp_path)
    with TestClient(before, base_url=BASE) as tab:
        held = _served_secret(tab.get("/").text)
        assert held is not None
        assert tab.post("/v1/session", json={"bootstrap": held}, headers=ORIGIN).status_code == 200
        assert tab.get("/v1/session").status_code == 200
        cookie_name = policy_before.cookie_name
        old_cookie = tab.cookies.get(cookie_name)
    assert old_cookie is not None

    # The server restarts: a new process, a new policy, the same workspace.
    after, policy_after, _ = _app(tmp_path)
    assert policy_after.bootstrap_secret != policy_before.bootstrap_secret
    with TestClient(after, base_url=BASE) as tab:
        tab.cookies.set(cookie_name, old_cookie)
        assert tab.get("/v1/session").status_code == 401
        renewed = tab.post("/v1/session", json={"bootstrap": held}, headers=ORIGIN)
        assert renewed.status_code == 200
        assert tab.get("/v1/session").status_code == 200


def test_the_secret_keeps_working_after_many_wrong_guesses(tmp_path: Path) -> None:
    app, policy, secret = _app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        for _ in range(MAX_BOOTSTRAP_FAILURES + 1):
            client.post("/v1/session", json={"bootstrap": "omrs_bs_guess"}, headers=ORIGIN)
        assert policy.exchange_bootstrap(policy.bootstrap_secret) is None
        again = client.post("/v1/session", json={"bootstrap": secret.value}, headers=ORIGIN)
    assert again.status_code == 200


def test_the_one_time_link_still_signs_in_once(tmp_path: Path) -> None:
    app, policy, _ = _app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        first = client.post(
            "/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers=ORIGIN
        )
        second = client.post(
            "/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers=ORIGIN
        )
    assert first.status_code == 200
    assert second.status_code == 401


def test_sign_in_with_the_secret_leaves_the_login_item_link_unused(tmp_path: Path) -> None:
    """A silent sign-in must not renew the link that 'omrs web open --print' showed."""
    link_file = tmp_path / "ws" / LINK_FILE_NAME
    (tmp_path / "ws").mkdir(mode=0o700)
    policy = RearmingAccessPolicy.for_launch("127.0.0.1", 8765, link_file=link_file)
    policy.publish()
    link = link_file.read_text(encoding="utf-8")
    app, _, secret = _app(tmp_path, policy)

    with TestClient(app, base_url=BASE) as client:
        signed = client.post("/v1/session", json={"bootstrap": secret.value}, headers=ORIGIN)

    assert signed.status_code == 200
    assert link_file.read_text(encoding="utf-8") == link
    assert policy.exchange_bootstrap(link.strip().split("#bootstrap=", 1)[1]) is not None


# ── The secret stays out of logs, API bodies and the terminal ──────────


def test_the_secret_never_reaches_a_log_or_an_api_body(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        app, _, secret = _app(tmp_path)
        with TestClient(app, base_url=BASE) as client:
            bodies = [
                client.post("/v1/session", json={"bootstrap": secret.value}, headers=ORIGIN).text,
                client.get("/v1/session").text,
                client.get("/v1/health").text,
                client.post("/v1/session", json={"bootstrap": "wrong"}, headers=ORIGIN).text,
            ]
    assert all(secret.value not in body for body in bodies)
    assert secret.value not in caplog.text


def test_omrs_web_loads_the_secret_and_prints_nothing_of_it(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_serve(app: Any, sock: Any) -> None:
        captured["secret"] = app.state.page_secret
        sock.close()

    workspace = tmp_path / "ws"
    with patch("omrs.transports.cli.web._serve", side_effect=fake_serve):
        result = runner.invoke(cli_app, ["web", "--port", "0", "--workspace", str(workspace)])

    assert result.exit_code == 0, result.output
    secret = captured["secret"]
    assert isinstance(secret, PageSecret)
    path = workspace / PAGE_SECRET_FILE_NAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text(encoding="utf-8").strip() == secret.value
    assert secret.value not in result.output
