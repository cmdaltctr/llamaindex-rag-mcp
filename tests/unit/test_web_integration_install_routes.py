"""Install routes and the install fields of ``GET /v1/integrations`` (tasks 1.3, 3.1, 3.2).

Each test replaces the runtime's install detection with a fake ``uv tool``
install whose ``uv`` is a shell script in ``tmp_path``. The script records
that it ran, so a refused request can show it started no process. No test
reaches the network or installs a package.
"""

from __future__ import annotations

import shlex
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

import omrs.capabilities as capabilities  # noqa: E402
from omrs.transports.api.install_environment import InstallEnvironment  # noqa: E402

STATUS = "/v1/integrations/install"
ANTHROPIC = "/v1/integrations/anthropic/install"
MISSING = {
    "llama_index.llms.anthropic",
    "llama_index.llms.openai_like",
    "azure.ai.documentintelligence",
}


class Harness:
    """A logged-in client, its policy and the runtime's install job."""

    def __init__(self, client: TestClient, policy: Any, tmp_path: Path) -> None:
        self.client = client
        self.policy = policy
        self.tmp_path = tmp_path
        self.job = client.app.state.runtime.installs  # type: ignore[attr-defined]
        self.job.python = "/env/bin/python"
        self.ran = tmp_path / "ran.txt"
        self.gate = tmp_path / "gate"

    def install_as(self, install_type: str = "uv-tool", *, uv: bool = True, body: str = "") -> None:
        """Make the server look like *install_type*, with a fake ``uv`` running *body*."""
        script = self.tmp_path / "bin" / "uv"
        script.parent.mkdir(parents=True, exist_ok=True)
        # ``uv pip check`` passes at once; only the install records that it ran.
        check = 'if [ "$2" = check ]; then exit 0; fi'
        script.write_text(f"#!/bin/sh\n{check}\necho ran >> {shlex.quote(str(self.ran))}\n{body}\n")
        script.chmod(0o755)
        env = InstallEnvironment(
            install_type=install_type,  # type: ignore[arg-type]
            receipt_extras=("web", "hybrid") if install_type == "uv-tool" else (),
            receipt_source="~/src/omrs" if install_type == "uv-tool" else None,
            uv=str(script) if uv else None,
        )
        self.job.detect = lambda: env

    def held(self) -> str:
        """A ``uv`` body that waits for the gate file, then succeeds."""
        return f"while [ ! -f {shlex.quote(str(self.gate))} ]; do sleep 0.02; done\nexit 0"

    def settle(self) -> dict[str, Any]:
        """Poll the status route until the install leaves ``running``."""
        deadline = time.monotonic() + 10
        while True:
            install = self.client.get(STATUS).json()["install"]
            if install["state"] != "running":
                return install
            assert time.monotonic() < deadline, install
            time.sleep(0.02)

    def entries(self) -> dict[str, dict[str, Any]]:
        response = self.client.get("/v1/integrations")
        assert response.status_code == 200, response.text
        return {entry["id"]: entry for entry in response.json()["integrations"]}


@pytest.fixture
def harness(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Harness]:
    real = capabilities.module_installed
    monkeypatch.setattr(
        capabilities, "module_installed", lambda name: name not in MISSING and real(name)
    )
    monkeypatch.setattr("omrs.core.vectordb.registry.availability", lambda name: "absent")
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        yield Harness(client, policy, tmp_path)


# ── Catalogue fields ─────────────────────────────────────────────────────


def test_a_uv_tool_install_offers_the_button_and_the_lasting_command(harness: Harness) -> None:
    harness.install_as("uv-tool")
    body = harness.client.get("/v1/integrations").json()
    assert body["install_type"] == "uv-tool"
    entry = {item["id"]: item for item in body["integrations"]}["anthropic"]
    assert entry["installable"] is True and entry["install_reason"] is None
    assert entry["packages"] == ["llama-index-llms-anthropic>=0.11.0"]
    assert entry["install_command"] == (
        'uv tool install --reinstall "omrs[web,hybrid,anthropic] @ ~/src/omrs"'
    )
    assert entry["pip_command"] == 'pip install "omrs[anthropic]"'


def test_anthropic_carries_an_install_caution_and_others_none(harness: Harness) -> None:
    harness.install_as("uv-tool")
    entries = harness.entries()
    caution = entries["anthropic"]["install_caution"]
    assert "python-dateutil" in caution and "botocore" in caution
    assert entries["chroma"]["install_caution"] is None
    assert entries["magika"]["install_caution"] is None


def test_excluded_and_always_on_entries_are_not_installable(harness: Harness) -> None:
    harness.install_as("uv-tool")
    entries = harness.entries()
    for name in ("web", "torch", "magika"):
        assert entries[name]["installable"] is False
        assert entries[name]["install_reason"] == "not-installable-here"
    assert entries["magika"]["packages"] == [] and entries["magika"]["install_command"] is None


def test_a_checkout_shows_the_sync_command_and_no_button(harness: Harness) -> None:
    harness.install_as("checkout")
    body = harness.client.get("/v1/integrations").json()
    assert body["install_type"] == "checkout"
    entry = {item["id"]: item for item in body["integrations"]}["azure"]
    assert entry["install_command"] == "uv sync --extra azure"
    assert entry["installable"] is False and entry["install_reason"] == "not-uv-tool"


def test_uv_not_found_blocks_every_missing_allowed_extra(harness: Harness) -> None:
    harness.install_as("uv-tool", uv=False)
    entries = harness.entries()
    for name in ("anthropic", "azure", "chroma"):
        assert entries[name]["installable"] is False
        assert entries[name]["install_reason"] == "uv-not-found"


# ── Starting an install ──────────────────────────────────────────────────


def test_status_is_idle_before_any_install(harness: Harness) -> None:
    response = harness.client.get(STATUS)
    assert response.status_code == 200
    assert response.json()["install"]["state"] == "idle"


def test_install_answers_202_then_reports_restart_needed(harness: Harness) -> None:
    harness.install_as("uv-tool", body="echo Installed 1 package")
    response = harness.client.post(ANTHROPIC, headers=ORIGIN)
    assert response.status_code == 202, response.text
    assert response.json()["install"]["state"] == "running"
    assert response.json()["install"]["extra"] == "anthropic"
    install = harness.settle()
    assert install["state"] == "succeeded" and install["output"] == ["Installed 1 package"]
    entry = harness.entries()["anthropic"]
    assert entry["availability"] == "restart-needed"
    assert entry["installable"] is False and entry["install_reason"] == "already-installed"


def test_a_failed_install_leaves_the_entry_not_installed(harness: Harness) -> None:
    harness.install_as("uv-tool", body="echo 'error: no solution'\nexit 1")
    assert harness.client.post(ANTHROPIC, headers=ORIGIN).status_code == 202
    install = harness.settle()
    assert install["state"] == "failed" and install["reason"] == "exit-code"
    assert install["output"] == ["error: no solution"]
    assert harness.entries()["anthropic"]["availability"] == "not-installed"


@pytest.mark.parametrize("extra", ["anthropic; rm -rf ~", "no-such-extra", "magika"])
def test_an_unknown_extra_is_404_and_starts_nothing(harness: Harness, extra: str) -> None:
    harness.install_as("uv-tool")
    url = f"/v1/integrations/{quote(extra, safe='')}/install"
    response = harness.client.post(url, headers=ORIGIN)
    assert response.status_code == 404, response.text
    assert response.json()["status"] == "error"
    assert not harness.ran.exists()
    assert harness.client.get(STATUS).json()["install"]["state"] == "idle"


@pytest.mark.parametrize(
    ("install_type", "uv", "extra", "reason"),
    [
        ("uv-tool", True, "torch", "not-installable-here"),
        ("uv-tool", True, "web", "not-installable-here"),
        ("uv-tool", True, "llamacpp", "no-requirements"),
        ("checkout", True, "anthropic", "not-uv-tool"),
        ("other", True, "anthropic", "not-uv-tool"),
        ("uv-tool", False, "anthropic", "uv-not-found"),
    ],
)
def test_a_listed_extra_that_cannot_be_installed_is_409(
    harness: Harness, install_type: str, uv: bool, extra: str, reason: str
) -> None:
    harness.install_as(install_type, uv=uv)
    response = harness.client.post(f"/v1/integrations/{extra}/install", headers=ORIGIN)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["status"] == "error" and body["reason"] == reason and body["message"]
    assert not harness.ran.exists()


def test_an_entry_whose_probe_fails_is_409_status_unknown(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.install_as("uv-tool")

    def broken(name: str) -> bool:
        if name.startswith("azure"):
            raise RuntimeError("probe broke")
        return name not in MISSING

    monkeypatch.setattr(capabilities, "module_installed", broken)
    entry = harness.entries()["azure"]
    assert entry["availability"] == "unknown"
    assert entry["installable"] is False and entry["install_reason"] == "status-unknown"
    response = harness.client.post("/v1/integrations/azure/install", headers=ORIGIN)
    assert response.status_code == 409 and response.json()["reason"] == "status-unknown"
    assert response.json()["message"]
    assert not harness.ran.exists()


def test_an_installed_extra_is_409_already_installed(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.install_as("uv-tool")
    monkeypatch.setattr(capabilities, "module_installed", lambda name: True)
    response = harness.client.post(ANTHROPIC, headers=ORIGIN)
    assert response.status_code == 409 and response.json()["reason"] == "already-installed"
    assert not harness.ran.exists()


def test_a_second_install_is_409_and_the_first_continues(harness: Harness) -> None:
    harness.install_as("uv-tool", body=harness.held())
    first = harness.client.post("/v1/integrations/azure/install", headers=ORIGIN)
    assert first.status_code == 202
    second = harness.client.post("/v1/integrations/chroma/install", headers=ORIGIN)
    assert second.status_code == 409 and second.json()["reason"] == "install-running"
    install = harness.client.get(STATUS).json()["install"]
    assert install["state"] == "running" and install["extra"] == "azure"
    harness.gate.write_text("", encoding="utf-8")
    assert harness.settle()["state"] == "succeeded"
    assert harness.ran.read_text(encoding="utf-8").count("ran") == 1


# ── Access ───────────────────────────────────────────────────────────────


def test_a_bearer_credential_is_refused_and_starts_nothing(harness: Harness) -> None:
    harness.install_as("uv-tool")
    harness.client.cookies.clear()
    header = bearer(harness.policy, "read", "graph", "run")
    assert harness.client.post(ANTHROPIC, headers={**ORIGIN, **header}).status_code == 403
    assert harness.client.get(STATUS, headers=header).status_code == 403
    assert harness.client.post(ANTHROPIC, headers=ORIGIN).status_code == 401
    assert not harness.ran.exists()


def test_install_responses_conform(harness: Harness) -> None:
    check = ContractChecker()
    harness.install_as("uv-tool", body="echo done")
    check.check(harness.client.get(STATUS), 200)
    check.check(harness.client.get("/v1/integrations"), 200)
    check.check(harness.client.post("/v1/integrations/no-such/install", headers=ORIGIN), 404)
    check.check(harness.client.post("/v1/integrations/torch/install", headers=ORIGIN), 409)
    check.check(harness.client.post(ANTHROPIC, headers=ORIGIN), 202)
    harness.settle()
    check.check(harness.client.get(STATUS), 200)
    check.check(harness.client.get("/v1/integrations"), 200)
    harness.client.cookies.clear()
    read = bearer(harness.policy, "read")
    check.check(harness.client.get(STATUS, headers=read), 403)
    check.check(harness.client.post(ANTHROPIC, headers={**ORIGIN, **read}), 403)
    check.check(harness.client.get(STATUS), 401)
    assert check.operations >= FAMILIES["integration_install"]
