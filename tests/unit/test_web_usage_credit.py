"""``GET /v1/usage/credit`` (task 4.3).

Spec ``answer-reasoning-and-usage``, "Remaining credit is read only on
request". OpenRouter answers ``GET /api/v1/key`` with ``data.limit`` and
``data.limit_remaining``. No test reaches the network:
``httpx.AsyncClient.send`` is replaced by a recorder.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_connection_summary import SECRET, make_settings  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs import compose  # noqa: E402
from omrs.core.providers.llm.openrouter_catalogue import parse_credit  # noqa: E402

URL = "/v1/usage/credit"


class Network:
    """Stand-in for ``httpx.AsyncClient.send`` that records each request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.payload: Any = {"data": {"label": "k", "limit": 10, "limit_remaining": 2.81}}
        self.status = 200
        self.fail = False


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Network:
    fake = Network()

    async def send(client: Any, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        fake.requests.append(request)
        if fake.fail:
            # The text holds the key, as a real error message might.
            raise httpx.ConnectError(f"failed with {SECRET}", request=request)
        body = json.dumps(fake.payload).encode()
        return httpx.Response(fake.status, content=body, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    return fake


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch) -> Any:
    def apply(**overrides: Any) -> Any:
        settings = make_settings(**overrides)
        monkeypatch.setattr(compose, "get_settings", lambda: settings)
        return settings

    return apply


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any, configure: Any, network: Network):
    configure(answer_provider="openrouter", openrouter_api_key=SECRET)
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        client.policy = policy  # type: ignore[attr-defined]
        yield client


def test_key_with_a_limit(setup: Any, network: Network) -> None:
    response = setup.get(URL)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "ok",
        "available": True,
        "limit_usd": 10,
        "remaining_usd": 2.81,
    }
    assert len(network.requests) == 1
    request = network.requests[0]
    assert str(request.url) == "https://openrouter.ai/api/v1/key"
    assert request.headers["authorization"] == f"Bearer {SECRET}"


def test_key_without_a_limit_is_not_available(setup: Any, network: Network) -> None:
    network.payload = {"data": {"limit": None, "limit_remaining": None}}
    assert setup.get(URL).json() == {"status": "ok", "available": False}


@pytest.mark.parametrize("status", [401, 500])
def test_http_error_is_not_available(setup: Any, network: Network, status: int) -> None:
    network.status = status
    assert setup.get(URL).json() == {"status": "ok", "available": False}


def test_odd_payload_is_not_available(setup: Any, network: Network) -> None:
    network.payload = {"data": {"limit": "ten", "limit_remaining": 1}}
    assert setup.get(URL).json() == {"status": "ok", "available": False}


def test_key_never_in_the_response_or_the_log(
    setup: Any, network: Network, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    responses = [setup.get(URL)]
    network.fail = True
    responses.append(setup.get(URL))
    network.fail, network.status = False, 401
    responses.append(setup.get(URL))
    assert responses[1].json() == {"status": "ok", "available": False}
    for response in responses:
        assert SECRET not in response.text
    assert SECRET not in caplog.text
    assert len(network.requests) == 3


@pytest.mark.parametrize("provider", ["ollama", "llamacpp"])
def test_provider_without_credit_data_sends_no_request(
    setup: Any, configure: Any, network: Network, provider: str
) -> None:
    configure(answer_provider=provider, openrouter_api_key=SECRET)
    assert setup.get(URL).json() == {"status": "ok", "available": False}
    assert network.requests == []


def test_openrouter_without_a_key_sends_no_request(
    setup: Any, configure: Any, network: Network
) -> None:
    configure(answer_provider="openrouter")
    assert setup.get(URL).json() == {"status": "ok", "available": False}
    assert network.requests == []


def test_needs_read_scope(setup: Any) -> None:
    assert setup.get(URL, headers=bearer(setup.policy, "read")).status_code == 200
    assert setup.get(URL, headers=bearer(setup.policy, "graph")).status_code == 403
    setup.cookies.clear()
    assert setup.get(URL).status_code == 401


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"data": {"limit": 10, "limit_remaining": 2.81}},
            {"limit_usd": 10, "remaining_usd": 2.81},
        ),
        ({"data": {"limit": 10, "limit_remaining": None}}, None),
        ({"data": {"limit": True, "limit_remaining": 1}}, None),
        ({"data": None}, None),
        ([], None),
    ],
)
def test_parser(payload: Any, expected: Any) -> None:
    assert parse_credit(payload) == expected


def test_credit_responses_conform(setup: Any, configure: Any) -> None:
    check = ContractChecker()
    check.check(setup.get(URL), 200)
    configure(answer_provider="ollama")
    check.check(setup.get(URL), 200)
    assert "getUsageCredit" in check.operations
