"""Integrations catalogue route: ``GET /v1/integrations`` (tasks 6.1, 6.2).

The route lists every installable extra plus the always-on magika
integration. Availability comes from the runtime probes; a probe that
raises gives the ``unknown`` state and never a 500. Responses are
validated against ``openapi.yaml``. No model, LLM or network call happens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

import omrs.capabilities as capabilities  # noqa: E402
from omrs.transports.api.integrations_catalogue import CATALOGUE  # noqa: E402

DECLARED = (
    "chroma",
    "hybrid",
    "pdf-pypdfium2",
    "pdf-inspector",
    "community-leiden",
    "azure",
    "llamacpp",
    "openrouter",
    "anthropic",
    "torch",
    "web",
)


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any):
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        yield client, policy


def _by_id(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/v1/integrations")
    assert response.status_code == 200, response.text
    return {entry["id"]: entry for entry in response.json()["integrations"]}


def test_catalogue_lists_every_declared_extra_and_magika(setup: Any) -> None:
    client, _ = setup
    entries = _by_id(client)
    assert list(entries) == [*DECLARED, "magika"]
    for entry in entries.values():
        assert entry["name"] and entry["purpose"]
        assert entry["availability"] in {"available", "not-installed", "unknown"}


def test_catalogue_matches_pyproject_extras() -> None:
    import tomllib

    root = Path(__file__).resolve().parents[2]
    extras = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]
    assert {item.extra for item in CATALOGUE if item.extra} == set(extras)


def test_install_commands_use_the_exact_forms(setup: Any) -> None:
    client, _ = setup
    entries = _by_id(client)
    assert entries["azure"]["extra"] == "azure"
    assert entries["azure"]["install_command"] == "uv sync --extra azure"
    assert entries["azure"]["pip_command"] == 'pip install "omrs[azure]"'
    assert entries["magika"]["extra"] is None
    assert entries["magika"]["install_command"] is None
    assert entries["magika"]["pip_command"] is None


def test_available_and_not_installed_states(setup: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = setup
    missing = {"rank_bm25", "azure.ai.documentintelligence"}
    monkeypatch.setattr(capabilities, "module_installed", lambda name: name not in missing)
    monkeypatch.setattr("omrs.core.vectordb.registry.availability", lambda name: "absent")
    monkeypatch.setattr("omrs.integrations.pdf.registry.probe", lambda name: None)
    entries = _by_id(client)
    assert entries["chroma"]["availability"] == "not-installed"
    assert entries["hybrid"]["availability"] == "not-installed"
    assert entries["azure"]["availability"] == "not-installed"
    assert entries["pdf-inspector"]["availability"] == "available"
    assert entries["pdf-pypdfium2"]["availability"] == "available"
    assert entries["torch"]["availability"] == "available"


def test_a_missing_pdf_reader_dependency_is_not_installed(
    setup: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = setup

    def probe(name: str) -> None:
        if name == "pypdfium2":
            raise ImportError("no pypdfium2")

    monkeypatch.setattr("omrs.integrations.pdf.registry.probe", probe)
    entries = _by_id(client)
    assert entries["pdf-pypdfium2"]["availability"] == "not-installed"
    assert entries["pdf-inspector"]["availability"] == "available"


def test_leiden_follows_its_registered_availability_probe(
    setup: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = setup

    def absent(name: str) -> None:
        raise ImportError("install leidenalg")

    monkeypatch.setattr("omrs.core.community.registry.verify_available", absent)
    assert _by_id(client)["community-leiden"]["availability"] == "not-installed"
    monkeypatch.setattr("omrs.core.community.registry.verify_available", lambda name: None)
    assert _by_id(client)["community-leiden"]["availability"] == "available"


def test_a_probe_that_raises_gives_unknown_not_a_500(
    setup: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = setup
    real = capabilities.module_installed

    def flaky(name: str) -> bool:
        if name == "rank_bm25":
            raise RuntimeError("probe exploded: secret-detail")
        return real(name)

    monkeypatch.setattr(capabilities, "module_installed", flaky)
    response = client.get("/v1/integrations")
    assert response.status_code == 200
    entries = {entry["id"]: entry for entry in response.json()["integrations"]}
    assert entries["hybrid"]["availability"] == "unknown"
    assert "secret-detail" not in response.text
    assert entries["web"]["availability"] in {"available", "not-installed"}


def test_a_broken_chroma_install_is_unknown(setup: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = setup
    monkeypatch.setattr("omrs.core.vectordb.registry.availability", lambda name: "broken")
    assert _by_id(client)["chroma"]["availability"] == "unknown"


def test_route_needs_read_scope(setup: Any) -> None:
    client, policy = setup
    client.cookies.clear()
    assert client.get("/v1/integrations").status_code == 401
    only_graph = bearer(policy, "graph")
    assert client.get("/v1/integrations", headers=only_graph).status_code == 403
    assert client.get("/v1/integrations", headers=bearer(policy, "read")).status_code == 200


def test_integration_responses_conform(setup: Any) -> None:
    client, policy = setup
    check = ContractChecker()
    body = check.check(client.get("/v1/integrations"), 200)
    assert body["status"] == "ok"
    client.cookies.clear()
    check.check(client.get("/v1/integrations", headers=bearer(policy, "read")), 200)
    check.check(client.get("/v1/integrations", headers=bearer(policy, "graph")), 403)
    check.check(client.get("/v1/integrations"), 401)
    assert check.operations >= FAMILIES["integrations"]
