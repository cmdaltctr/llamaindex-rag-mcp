"""The OpenAI-compatible and Anthropic providers over HTTP (design D5, D6).

Keys are fake. The keychain is a fake in memory and every provider request
goes through ``httpx.MockTransport``, so no test reads a real keychain or
contacts a real provider.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_connection_summary import make_settings  # noqa: E402
from tests.unit.test_web_connections_edit import (  # noqa: E402
    FakeKeychain,
    Harness,
    _mock_embed,
    windows,
)
from tests.unit.test_web_documents_support import BASE, ORIGIN, lance_store, login  # noqa: E402

from omrg import compose  # noqa: E402
from omrg.engine import Engine  # noqa: E402
from omrg.transports.api import connection_probe  # noqa: E402
from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.security import AccessPolicy, SecretSet  # noqa: E402

ANT_KEY = "sk-ant-api03-" + "a1B2c3D4e5F6g7H8" * 3 + "Zz9"  # gitleaks:allow
OAI_KEY = "sk-oai-" + "q1W2e3R4t5Y6u7I8" * 3 + "Oo0"  # gitleaks:allow
OAI_URL = "http://localhost:1234/v1"


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Any]:
    @contextmanager
    def build(**overrides: Any) -> Iterator[Harness]:
        overrides.setdefault("local_backend", "llamacpp")
        settings = make_settings(**overrides)
        monkeypatch.setattr(compose, "get_settings", lambda: settings)
        secrets = SecretSet()
        keychain = FakeKeychain(True, secrets)
        engines: list[Any] = []

        def factory(provider_source: Any) -> Any:
            engine = Engine(
                compose.settings_to_effective(settings),
                store=lance_store(tmp_path),
                embed_model=_mock_embed(),
                # The model is built from the Engine's current settings, as the
                # real composition root does, so a save shows in the next build.
                answer_llm_factory=lambda: compose.build_answer_llm(engines[0]._gen.effective),
            )
            engines.append(engine)
            return engine

        config = WebConfig(
            workspace=tmp_path / "ws", host="127.0.0.1", port=8765, roots=(), static_dir=None
        )
        policy = AccessPolicy.for_launch(config.host, config.port)
        app = create_app(
            config, policy=policy, engine_factory=factory, secrets=secrets, keychain=keychain
        )
        with TestClient(app, base_url=BASE) as client:
            login(client, policy)
            yield Harness(
                client, policy, keychain=keychain, secrets=secrets, engines=engines, app=app
            )

    return build


@pytest.fixture
def mock_http(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Route every provider request through a handler; return the request log."""
    seen: list[httpx.Request] = []
    state: dict[str, Any] = {"handler": lambda request: httpx.Response(200, json={"data": []})}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return state["handler"](request)

    real = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        connection_probe.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw)
    )
    return SimpleNamespace(seen=seen, set=lambda fn: state.__setitem__("handler", fn))


def key_route(h: Harness, provider: str) -> str:
    return f"/v1/connections/{provider}/key"


def put_key(h: Harness, provider: str, key: str) -> Any:
    return h.client.put(key_route(h, provider), json={"api_key": key}, headers=ORIGIN)


def put_chat(h: Harness, provider: str, model: str) -> Any:
    return h.client.put(
        "/v1/settings/chat", json={"provider": provider, "model": model}, headers=ORIGIN
    )


def effective(h: Harness) -> Any:
    return h.engines[0]._gen.effective


# ── Key routes ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("provider", "key", "field"),
    [
        ("anthropic", ANT_KEY, "anthropic_api_key"),
        ("openai_compatible", OAI_KEY, "openai_compatible_api_key"),
    ],
)
def test_a_key_is_saved_applied_live_and_removed(
    harness: Any, provider: str, key: str, field: str
) -> None:
    with harness() as h:
        assert put_key(h, provider, key).status_code == 200
        assert h.keychain.data == {provider: key}
        assert key in list(h.secrets)  # redacted from now on
        state = h.field(provider, "api_key")
        assert (state["set"], state["source"], state["last4"]) == (True, "keychain", key[-4:])
        assert getattr(effective(h), field) == key  # the running Engine took it, no restart
        assert h.engines[0].redact(f"failed with {key}") == "failed with ***"
        assert h.client.delete(key_route(h, provider), headers=ORIGIN).status_code == 200
        assert h.keychain.data == {}
        assert getattr(effective(h), field) == ""
        assert key in list(h.secrets)  # a removed key stays redacted
        assert h.engines[0].redact(f"late failure {key}") == "late failure ***"


def test_a_new_key_does_not_touch_another_providers_key(harness: Any) -> None:
    with harness() as h:
        put_key(h, "anthropic", ANT_KEY)
        put_key(h, "openai_compatible", OAI_KEY)
        assert h.keychain.data == {"anthropic": ANT_KEY, "openai_compatible": OAI_KEY}
        assert effective(h).anthropic_api_key == ANT_KEY
        assert effective(h).openai_compatible_api_key == OAI_KEY
        assert effective(h).openrouter_api_key == ""


def test_an_environment_key_locks_the_new_key_routes(harness: Any) -> None:
    with harness(explicit=frozenset({"anthropic_api_key"}), anthropic_api_key=ANT_KEY) as h:
        response = put_key(h, "anthropic", OAI_KEY)
        assert response.status_code == 409
        assert "ANTHROPIC_API_KEY" in response.json()["message"]
        assert h.keychain.data == {}


def test_no_response_holds_five_consecutive_characters_of_a_new_key(
    harness: Any, mock_http: SimpleNamespace
) -> None:
    with harness() as h:
        texts = [put_key(h, "anthropic", ANT_KEY).text, h.client.get("/v1/connections").text]
        for provider in ("anthropic", "openai_compatible"):
            texts.append(h.client.post(f"/v1/connections/{provider}/test", headers=ORIGIN).text)
            texts.append(h.client.post(f"/v1/connections/{provider}/models", headers=ORIGIN).text)
        texts.append(put_chat(h, "anthropic", "claude-x").text)
        texts.append(h.client.get("/v1/settings/chat").text)
        texts.append(h.client.delete(key_route(h, "anthropic"), headers=ORIGIN).text)
        for text in texts:
            assert windows(text, ANT_KEY) == []


def test_a_short_new_key_shows_no_characters(harness: Any) -> None:
    with harness() as h:
        assert put_key(h, "openai_compatible", "short-key-1").status_code == 200
        field = h.field("openai_compatible", "api_key")
        assert field["set"] is True and field["last4"] is None


def test_the_anthropic_card_has_no_address_to_save(harness: Any) -> None:
    with harness() as h:
        response = h.put("anthropic", {"base_url": OAI_URL})
        assert response.status_code == 404  # no such field


# ── Tests and model lists ─────────────────────────────────────────────────


def test_anthropic_test_sends_the_two_headers_to_the_fixed_address(
    harness: Any, mock_http: SimpleNamespace
) -> None:
    with harness() as h:
        put_key(h, "anthropic", ANT_KEY)
        response = h.client.post("/v1/connections/anthropic/test", headers=ORIGIN)
        assert response.json() == {"status": "ok", "reachable": True, "reason": None}
        (request,) = mock_http.seen
        assert str(request.url) == "https://api.anthropic.com/v1/models"
        assert request.headers["x-api-key"] == ANT_KEY
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert "authorization" not in request.headers


def test_anthropic_without_a_key_sends_nothing(harness: Any, mock_http: SimpleNamespace) -> None:
    with harness() as h:
        test = h.client.post("/v1/connections/anthropic/test", headers=ORIGIN)
        models = h.client.post("/v1/connections/anthropic/models", headers=ORIGIN)
        assert test.json()["reason"] == "not-configured"
        assert models.json()["reason"] == "not-configured"
        assert mock_http.seen == []


def test_anthropic_typed_key_is_sent_and_not_saved(
    harness: Any, mock_http: SimpleNamespace
) -> None:
    with harness() as h:
        response = h.client.post(
            "/v1/connections/anthropic/test", json={"fields": {"api_key": ANT_KEY}}, headers=ORIGIN
        )
        assert response.json()["reachable"] is True
        assert mock_http.seen[0].headers["x-api-key"] == ANT_KEY
        assert h.keychain.data == {}
        assert ANT_KEY in list(h.secrets)


def test_anthropic_models_are_parsed_sorted_and_the_key_is_not_returned(
    harness: Any, mock_http: SimpleNamespace
) -> None:
    mock_http.set(
        lambda request: httpx.Response(200, json={"data": [{"id": "claude-b"}, {"id": "claude-a"}]})
    )
    with harness() as h:
        put_key(h, "anthropic", ANT_KEY)
        response = h.client.post("/v1/connections/anthropic/models", headers=ORIGIN)
        body = response.json()
        assert body["models"] == ["claude-a", "claude-b"]
        assert ANT_KEY not in response.text


def test_anthropic_wrong_key_is_unauthorised(harness: Any, mock_http: SimpleNamespace) -> None:
    mock_http.set(lambda request: httpx.Response(401, json={"error": ANT_KEY}))
    with harness() as h:
        put_key(h, "anthropic", ANT_KEY)
        response = h.client.post("/v1/connections/anthropic/test", headers=ORIGIN)
        assert response.json() == {"status": "ok", "reachable": False, "reason": "unauthorised"}
        assert ANT_KEY not in response.text


def test_openai_compatible_with_a_key_sends_a_bearer_to_its_own_address(
    harness: Any, mock_http: SimpleNamespace
) -> None:
    with harness() as h:
        put_key(h, "openai_compatible", OAI_KEY)
        assert h.client.post("/v1/connections/openai_compatible/test", headers=ORIGIN).json()[
            "reachable"
        ]
        (request,) = mock_http.seen
        assert str(request.url) == "https://api.openai.com/v1/models"
        assert request.headers["authorization"] == f"Bearer {OAI_KEY}"
        assert "x-api-key" not in request.headers


def test_openai_compatible_without_a_key_sends_no_credential(
    harness: Any, mock_http: SimpleNamespace
) -> None:
    with harness(openai_compatible_base_url=OAI_URL) as h:
        response = h.client.post("/v1/connections/openai_compatible/test", headers=ORIGIN)
        assert response.json()["reachable"] is True
        (request,) = mock_http.seen
        assert str(request.url) == f"{OAI_URL}/models"
        assert "authorization" not in request.headers


def test_a_typed_address_gets_the_key_and_a_save_is_not_made(
    harness: Any, mock_http: SimpleNamespace
) -> None:
    typed = "http://gpu-box.local:8000/v1"
    with harness() as h:
        put_key(h, "openai_compatible", OAI_KEY)
        response = h.client.post(
            "/v1/connections/openai_compatible/models",
            json={"fields": {"base_url": typed}},
            headers=ORIGIN,
        )
        assert response.json()["reachable"] is True
        (request,) = mock_http.seen
        assert str(request.url) == f"{typed}/models"
        assert request.headers["authorization"] == f"Bearer {OAI_KEY}"
        assert h.field("openai_compatible", "base_url")["source"] == "default"


def test_the_openai_compatible_key_never_goes_to_another_provider(
    harness: Any, mock_http: SimpleNamespace
) -> None:
    with harness() as h:
        put_key(h, "openai_compatible", OAI_KEY)
        for provider in ("ollama", "llamacpp", "openrouter", "anthropic"):
            h.client.post(f"/v1/connections/{provider}/test", headers=ORIGIN)
            h.client.post(f"/v1/connections/{provider}/models", headers=ORIGIN)
        assert not any(OAI_KEY in json.dumps(dict(r.headers)) for r in mock_http.seen)
        assert not any(OAI_KEY in str(r.url) for r in mock_http.seen)


@pytest.mark.parametrize(
    "bad", ["file:///etc/passwd", "http://user:pass@host/v1", "http://host/v1?token=abc", ""]
)
def test_a_bad_openai_compatible_address_is_400(harness: Any, bad: str) -> None:
    with harness() as h:
        assert h.put("openai_compatible", {"base_url": bad}).status_code == 400
        assert h.field("openai_compatible", "base_url")["source"] == "default"


# ── Live apply ────────────────────────────────────────────────────────────


def test_a_saved_openai_compatible_address_applies_without_a_restart(harness: Any) -> None:
    with harness() as h:
        assert h.put("openai_compatible", {"base_url": OAI_URL}).status_code == 200
        assert effective(h).openai_compatible_base_url == OAI_URL
        assert put_chat(h, "openai_compatible", "local-model").status_code == 200
        llm = h.engines[0]._get_answer_llm()
        assert (llm.api_base, llm.model) == (OAI_URL, "local-model")
        assert h.put("openai_compatible", {"base_url": None}).status_code == 200
        assert effective(h).openai_compatible_base_url == "https://api.openai.com/v1"
        assert h.engines[0]._get_answer_llm().api_base == "https://api.openai.com/v1"


def test_a_saved_anthropic_choice_and_key_apply_without_a_restart(harness: Any) -> None:
    with harness() as h:
        put_key(h, "anthropic", ANT_KEY)
        assert put_chat(h, "anthropic", "claude-x").status_code == 200
        current = effective(h)
        assert (current.answer.provider, current.answer.model) == ("anthropic", "claude-x")


def test_the_embedding_guard_does_not_refuse_the_new_fields(harness: Any) -> None:
    with harness() as h:
        # Every save above would be a 409 if the Engine counted these fields as embedding fields.
        assert put_key(h, "openai_compatible", OAI_KEY).status_code == 200
        assert h.put("openai_compatible", {"base_url": OAI_URL}).status_code == 200
        assert put_key(h, "anthropic", ANT_KEY).status_code == 200


# ── Chat readiness ────────────────────────────────────────────────────────


def chat(h: Harness) -> dict[str, Any]:
    return h.client.get("/v1/settings/chat").json()


@pytest.mark.usefixtures("installed")
def test_anthropic_chat_is_not_configured_until_a_key_is_saved(harness: Any) -> None:
    with harness(answer_provider="anthropic") as h:
        assert (chat(h)["ready"], chat(h)["reason"]) == (False, "not-configured")
        put_key(h, "anthropic", ANT_KEY)
        assert (chat(h)["ready"], chat(h)["reason"]) == (True, None)


def test_openai_compatible_chat_is_ready_without_a_key(harness: Any) -> None:
    with harness(answer_provider="openai_compatible", openai_compatible_base_url=OAI_URL) as h:
        assert (chat(h)["ready"], chat(h)["reason"]) == (True, None)
        assert h.keychain.data == {}


@pytest.mark.usefixtures("installed")
def test_chat_test_route_uses_the_new_providers(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrg.core.providers.llm import registry

    built: list[tuple[str, Any]] = []

    class Fake:
        async def acomplete(self, prompt: str) -> Any:
            return SimpleNamespace(text="OK")

    def fake_build(provider: str) -> Any:
        def build(settings: Any, **kwargs: Any) -> Any:
            built.append((provider, kwargs["answer_model"]))
            return Fake()

        return build

    monkeypatch.setattr(registry, "get", fake_build)
    with harness() as h:
        no_key = h.client.post(
            "/v1/settings/chat/test",
            json={"provider": "anthropic", "model": "claude-x"},
            headers=ORIGIN,
        ).json()
        assert (no_key["ok"], no_key["reason"]) == (False, "not-configured")
        assert built == []  # nothing was built, so nothing was sent
        put_key(h, "anthropic", ANT_KEY)
        good = h.client.post(
            "/v1/settings/chat/test",
            json={"provider": "anthropic", "model": "claude-x"},
            headers=ORIGIN,
        ).json()
        assert good["ok"] is True and built == [("anthropic", "claude-x")]
        local = h.client.post(
            "/v1/settings/chat/test",
            json={"provider": "openai_compatible", "model": "m"},
            headers=ORIGIN,
        ).json()
        assert local["ok"] is True


# ── Readiness rules, read from the descriptors ────────────────────────────


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> None:
    from omrg.transports.api.routes import chat_settings

    monkeypatch.setattr(chat_settings, "module_installed", lambda name: True)


def reason(settings: Any, provider: str, model: str = "m") -> str | None:
    from omrg.transports.api.routes.chat_settings import _not_ready_reason

    return _not_ready_reason(settings, provider, model)


@pytest.mark.usefixtures("installed")
def test_an_optional_key_does_not_block_chat() -> None:
    settings = make_settings(openai_compatible_base_url=OAI_URL, openai_compatible_api_key="")
    assert reason(settings, "openai_compatible") is None


@pytest.mark.usefixtures("installed")
def test_openai_compatible_needs_an_address_and_a_model() -> None:
    assert reason(make_settings(), "openai_compatible") is None  # the default address is set
    assert reason(make_settings(), "openai_compatible", " ") == "not-configured"
    blank = make_settings(openai_compatible_base_url=" ")
    assert reason(blank, "openai_compatible") == "not-configured"


@pytest.mark.usefixtures("installed")
def test_a_required_key_blocks_chat() -> None:
    assert reason(make_settings(), "anthropic") == "not-configured"
    assert reason(make_settings(anthropic_api_key=ANT_KEY), "anthropic") is None
    assert reason(make_settings(anthropic_api_key=ANT_KEY), "anthropic", "") == "not-configured"


def test_a_missing_package_is_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    from omrg.transports.api.routes import chat_settings

    monkeypatch.setattr(chat_settings, "module_installed", lambda name: False)
    assert reason(make_settings(anthropic_api_key=ANT_KEY), "anthropic") == "not-installed"


def test_a_third_provider_with_an_optional_key_is_ready_without_it() -> None:
    """A fake provider registered in a test needs no change to the readiness check."""
    import sys
    import types

    from omrg.core.providers.llm import registry
    from omrg.core.providers.llm.connection import (
        ConnectionDescriptor,
        ConnectionField,
        ConnectionTarget,
    )
    from omrg.transports.api.routes import chat_settings

    module = types.ModuleType("fake_third_ready")
    module.build = lambda settings, **_: None  # type: ignore[attr-defined]
    module.CONNECTION = ConnectionDescriptor(  # type: ignore[attr-defined]
        display_name="Third",
        locality="cloud",
        requires_module="json",
        extra=None,
        fields=(
            ConnectionField("api_key", "Key", "secret", "anthropic_api_key", "X_KEY", False),
            ConnectionField("api_key2", "Key 2", "secret", "openai_compatible_api_key", "X2"),
        ),
        read_only=lambda settings: [],
        test_targets=lambda s: ConnectionTarget(("http://x/ping",)),
        models_target=lambda s: ConnectionTarget(()),
        parse_models=lambda payload: [],
    )
    sys.modules["fake_third_ready"] = module
    before = dict(registry._registry)
    registry.register("third", "fake_third_ready:build")
    try:
        both_empty = make_settings()
        assert chat_settings._not_ready_reason(both_empty, "third", "m") == "not-configured"
        required_set = make_settings(openai_compatible_api_key=OAI_KEY)
        assert chat_settings._not_ready_reason(required_set, "third", "m") is None
    finally:
        registry._registry.clear()
        registry._registry.update(before)
        sys.modules.pop("fake_third_ready", None)
