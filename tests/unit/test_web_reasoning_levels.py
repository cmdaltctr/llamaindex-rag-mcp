"""``GET /v1/settings/chat/reasoning-levels`` (task 4.2).

Spec ``answer-reasoning-and-usage``, "The level list comes from the provider
catalogue". The OpenRouter catalogue is a recorded excerpt of the public
``GET /api/v1/models`` answer (2026-10-23). No test reaches the network:
``httpx.AsyncClient.send`` is replaced by a recorder that answers from the
excerpt or fails.
"""

from __future__ import annotations

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
from omrs.core.providers.llm.openrouter_catalogue import parse_reasoning_levels  # noqa: E402
from omrs.transports.api.routes import chat_reasoning  # noqa: E402

URL = "/v1/settings/chat/reasoning-levels"

#: Excerpt of the OpenRouter model catalogue recorded on 2026-10-23.
CATALOGUE: dict[str, Any] = {
    "data": [
        {
            "id": "z-ai/glm-5.3-flash",
            "reasoning": {
                "mandatory": True,
                "default_enabled": True,
                "supported_efforts": ["max", "high", "low"],
                "default_effort": "max",
            },
        },
        {
            "id": "deepseek/deepseek-v4.1-flash",
            "reasoning": {
                "mandatory": False,
                "default_enabled": True,
                "supported_efforts": ["max", "high", "low", "none"],
                "default_effort": "high",
            },
        },
        {"id": "openai/gpt-4o-mini", "reasoning": None},
        {"id": "meta/no-reasoning-key"},
    ]
}


class Network:
    """Stand-in for ``httpx.AsyncClient.send`` that records each request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.payload: Any = CATALOGUE
        self.status = 200
        self.fail = False

    async def send(self, client: Any, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            raise httpx.ConnectError("no route to host", request=request)
        import json

        return httpx.Response(
            self.status, content=json.dumps(self.payload).encode(), request=request
        )


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Network:
    fake = Network()

    async def send(client: Any, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        return await fake.send(client, request, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    chat_reasoning.clear_catalogue_cache()
    yield fake
    chat_reasoning.clear_catalogue_cache()


@pytest.fixture
def setup(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch, network: Network
):
    settings = make_settings(answer_provider="openrouter", openrouter_api_key=SECRET)
    monkeypatch.setattr(compose, "get_settings", lambda: settings)
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        client.policy = policy  # type: ignore[attr-defined]
        yield client


def levels(client: TestClient, provider: str, model: str) -> Any:
    return client.get(URL, params={"provider": provider, "model": model})


def test_mandatory_model_lists_its_levels(setup: Any, network: Network) -> None:
    response = levels(setup, "openrouter", "z-ai/glm-5.3-flash")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "ok",
        "known": True,
        "levels": ["max", "high", "low"],
        "default": "max",
        "mandatory": True,
        "ignored": False,
    }


def test_model_that_can_turn_reasoning_off_lists_none(setup: Any) -> None:
    body = levels(setup, "openrouter", "deepseek/deepseek-v4.1-flash").json()
    assert body["known"] is True
    assert "none" in body["levels"]
    assert (body["default"], body["mandatory"]) == ("high", False)


@pytest.mark.parametrize(
    "model", ["vendor/not-listed", "openai/gpt-4o-mini", "meta/no-reasoning-key"]
)
def test_unknown_or_non_reasoning_model_is_not_known(setup: Any, model: str) -> None:
    assert levels(setup, "openrouter", model).json() == {
        "status": "ok",
        "known": False,
        "ignored": False,
    }


def test_fetch_failure_is_not_known(setup: Any, network: Network) -> None:
    network.fail = True
    body = levels(setup, "openrouter", "z-ai/glm-5.3-flash").json()
    assert (body["known"], body["ignored"]) == (False, False)


@pytest.mark.parametrize("status", [500, 429])
def test_http_error_is_not_known(setup: Any, network: Network, status: int) -> None:
    network.status = status
    assert levels(setup, "openrouter", "z-ai/glm-5.3-flash").json()["known"] is False


def test_odd_payload_is_not_known(setup: Any, network: Network) -> None:
    network.payload = ["not", "a", "catalogue"]
    assert levels(setup, "openrouter", "z-ai/glm-5.3-flash").json()["known"] is False


def test_provider_without_a_catalogue_sends_no_request(setup: Any, network: Network) -> None:
    body = levels(setup, "llamacpp", "chat-gguf").json()
    assert body == {"status": "ok", "known": False, "ignored": True}
    body = levels(setup, "ollama", "qwen3:4b").json()
    assert body == {"status": "ok", "known": False, "ignored": False}
    assert network.requests == []


def test_unknown_provider_sends_no_request(setup: Any, network: Network) -> None:
    assert levels(setup, "gemini", "m").json() == {"status": "ok", "known": False, "ignored": True}
    assert network.requests == []


def test_catalogue_request_sends_no_key(setup: Any, network: Network) -> None:
    levels(setup, "openrouter", "z-ai/glm-5.3-flash")
    assert len(network.requests) == 1
    request = network.requests[0]
    assert str(request.url) == "https://openrouter.ai/api/v1/models"
    assert "authorization" not in {k.lower() for k in request.headers}
    assert SECRET not in str(request.headers)


def test_catalogue_is_cached_for_ten_minutes(
    setup: Any, network: Network, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [1000.0]
    monkeypatch.setattr(chat_reasoning, "_clock", lambda: now[0])
    levels(setup, "openrouter", "z-ai/glm-5.3-flash")
    levels(setup, "openrouter", "deepseek/deepseek-v4.1-flash")
    now[0] += 599
    levels(setup, "openrouter", "vendor/not-listed")
    assert len(network.requests) == 1
    now[0] += 2
    levels(setup, "openrouter", "z-ai/glm-5.3-flash")
    assert len(network.requests) == 2


def test_a_failure_is_not_cached(setup: Any, network: Network) -> None:
    network.fail = True
    assert levels(setup, "openrouter", "z-ai/glm-5.3-flash").json()["known"] is False
    network.fail = False
    assert levels(setup, "openrouter", "z-ai/glm-5.3-flash").json()["known"] is True
    assert len(network.requests) == 2


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"provider": "openrouter"},
        {"model": "m"},
        {"provider": "openrouter", "model": "x" * 201},
    ],
)
def test_bad_query_is_400(setup: Any, params: dict[str, str]) -> None:
    assert setup.get(URL, params=params).status_code == 400


def test_needs_read_scope(setup: Any) -> None:
    params = {"provider": "llamacpp", "model": "m"}
    assert setup.get(URL, params=params, headers=bearer(setup.policy, "read")).status_code == 200
    assert setup.get(URL, params=params, headers=bearer(setup.policy, "graph")).status_code == 403
    setup.cookies.clear()
    assert setup.get(URL, params=params).status_code == 401


def test_parser_drops_bad_levels_and_a_default_outside_the_list() -> None:
    parsed = parse_reasoning_levels(
        {
            "data": [
                {
                    "id": "a/b",
                    "reasoning": {
                        "supported_efforts": ["low", "bad level", 3, "high"],
                        "default_effort": "max",
                        "mandatory": "yes",
                    },
                },
                {"id": "c/d", "reasoning": {"supported_efforts": []}},
                {"reasoning": {"supported_efforts": ["low"]}},
            ]
        }
    )
    assert parsed == {"a/b": {"levels": ["low", "high"], "default": None, "mandatory": False}}


def test_levels_responses_conform(setup: Any, network: Network) -> None:
    check = ContractChecker()
    check.check(levels(setup, "openrouter", "z-ai/glm-5.3-flash"), 200)
    check.check(levels(setup, "llamacpp", "m"), 200)
    check.check(setup.get(URL), 400)
    assert "getReasoningLevels" in check.operations
