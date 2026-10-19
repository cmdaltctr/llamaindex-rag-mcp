"""Saved provider addresses, keys, typed tests and model lists over HTTP (tasks 7.1 to 7.7).

The keychain is a fake in memory. Settings are built in memory (no ``.env``)
and patched into the composition root. No test reads a real keychain, calls
a real provider or sends a cloud request.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_connection_summary import SECRET, make_settings  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    lance_store,
    login,
)

from omrg import compose  # noqa: E402
from omrg.config.settings_file_write import write_settings  # noqa: E402
from omrg.engine import Engine  # noqa: E402
from omrg.integrations.keychain import KeychainUnavailableError, Secret  # noqa: E402
from omrg.transports.api import connection_probe  # noqa: E402
from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.security import AccessPolicy, SecretSet  # noqa: E402

KEY64 = "sk-or-v1-" + "a1B2c3D4e5F6g7H8" * 3 + "Zz9Yy8X"  # 64 characters, fake
NEW_URL = "http://gpu-box.local:11434"


class FakeKeychain:
    """A keychain in memory with the surface of ``KeychainStore``."""

    def __init__(self, available: bool = True, secrets: SecretSet | None = None) -> None:
        self.available = available
        self.data: dict[str, str] = {}
        self.fail_save = False
        self.secrets = secrets
        self.known_before_save: list[bool] = []

    def load(self, providers: Any) -> dict[str, Secret]:
        return {p: Secret(self.data[p]) for p in providers if p in self.data}

    def get(self, provider: str) -> Secret | None:
        return Secret(self.data[provider]) if provider in self.data else None

    def read(self, provider: str) -> Secret | None:
        return self.get(provider)

    def save(self, provider: str, key: str) -> None:
        if self.secrets is not None:
            self.known_before_save.append(key in list(self.secrets))
        if not self.available or self.fail_save:
            raise KeychainUnavailableError("no keychain")
        self.data[provider] = key

    def delete(self, provider: str) -> None:
        if not self.available:
            raise KeychainUnavailableError("no keychain")
        self.data.pop(provider, None)

    def state(self, provider: str, saved: bool) -> str:
        if provider in self.data:
            return "ok"
        return "keychain-missing" if saved else "unset"


class RefusingEngine(Engine):
    """An Engine that refuses every provider change."""

    def use_provider_settings(self, effective: Any) -> None:
        raise ValueError("refused")


class Harness:
    """A running app plus the objects the tests inspect."""

    def __init__(self, client: TestClient, policy: AccessPolicy, **parts: Any) -> None:
        self.client = client
        self.policy = policy
        self.__dict__.update(parts)

    def connections(self) -> dict[str, Any]:
        return self.client.get("/v1/connections").json()

    def field(self, provider: str, field_id: str) -> dict[str, Any]:
        entry = next(c for c in self.connections()["connections"] if c["provider"] == provider)
        return next(f for f in entry["fields"] if f["id"] == field_id)

    def put(self, provider: str, fields: dict[str, Any], **extra: Any) -> Any:
        return self.client.put(
            f"/v1/connections/{provider}", json={"fields": fields, **extra}, headers=ORIGIN
        )

    @property
    def store(self) -> Any:
        return self.app.state.mcp_http.store

    def file_text(self) -> str:
        """The text of ``omrg.jsonc`` (empty when the file does not exist)."""
        path = self.store.path
        return path.read_text(encoding="utf-8") if path.exists() else ""


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    @contextmanager
    def build(
        *,
        keychain_available: bool = True,
        engine_cls: type = Engine,
        stored: dict[str, str] | None = None,
        sources: dict[str, str] | None = None,
        **overrides: Any,
    ):
        overrides.setdefault("local_backend", "llamacpp")  # Ollama makes no embeddings
        settings = make_settings(**overrides)
        if sources is not None:  # the source word of each launch setting (``dotenv``, ...)
            object.__setattr__(settings, "setting_sources", dict(sources))
        monkeypatch.setattr(compose, "get_settings", lambda: settings)
        secrets = SecretSet()
        keychain = FakeKeychain(keychain_available, secrets)
        keychain.data.update(stored or {})
        if stored:  # a key is used only through its keychain:// reference in omrg.jsonc
            write_settings(
                {f"{name}_api_key": f"keychain://{name}" for name in stored}, revision=None
            )
        engines: list[Any] = []

        def factory(provider_source: Any) -> Any:
            engine = engine_cls(
                compose.settings_to_effective(settings),
                store=lance_store(tmp_path),
                embed_model=_mock_embed(),
                answer_llm_factory=lambda: SimpleNamespace(
                    url=provider_source().values.get("ollama_base_url")
                ),
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


def _mock_embed() -> Any:
    from llama_index.core.embeddings import MockEmbedding

    return MockEmbedding(embed_dim=2)


def answer_url(h: Harness) -> str | None:
    return h.engines[0]._get_answer_llm().url


# ── 7.1 PUT /v1/connections/{provider} ───────────────────────────────────


def test_save_and_clear_an_address_with_no_restart(harness: Any) -> None:
    with harness() as h:
        assert answer_url(h) is None
        response = h.put("ollama", {"base_url": NEW_URL})
        assert response.status_code == 200, response.text
        assert response.json()["revision"] == h.store.read().revision
        field = h.field("ollama", "base_url")
        assert (field["value"], field["source"]) == (NEW_URL, "config-file")
        assert field["locked"] is False
        assert f'"ollama_base_url": "{NEW_URL}"' in h.file_text()
        assert answer_url(h) == NEW_URL  # the next answer uses it, no restart
        assert h.put("ollama", {"base_url": None}).status_code == 200
        field = h.field("ollama", "base_url")
        assert (field["value"], field["source"]) == ("http://ollama.test:11434", "default")
        assert "ollama_base_url" not in h.file_text()
        assert answer_url(h) is None


@pytest.mark.parametrize(
    "bad",
    [
        "file:///etc/passwd",
        "ftp://host/x",
        "http://user:pass@host:11434",
        "http://host:11434/?token=abc",
        "http://host:11434/#frag",
        "http://" + "h" * 2050,
        "",
        "not a url",
        "http://",
    ],
)
def test_a_bad_address_is_400_and_saves_nothing(harness: Any, bad: str) -> None:
    with harness() as h:
        response = h.put("ollama", {"base_url": bad})
        assert response.status_code == 400
        assert bad not in response.text or bad == ""
        assert "absolute http or https" in response.json()["message"]
        assert h.field("ollama", "base_url")["source"] == "default"
        assert h.file_text() == ""


def test_unknown_provider_and_field_are_404(harness: Any) -> None:
    with harness() as h:
        assert h.put("mystery", {"base_url": NEW_URL}).status_code == 404
        assert h.put("ollama", {"nope": NEW_URL}).status_code == 404


def test_a_key_field_is_not_saved_through_the_address_route(harness: Any) -> None:
    with harness() as h:
        assert h.put("openrouter", {"api_key": "k" * 20}).status_code == 400


def test_an_address_set_by_the_environment_is_409(harness: Any) -> None:
    with harness(explicit=frozenset({"llamacpp_chat_url"})) as h:
        response = h.put("llamacpp", {"chat_url": "http://other:8081/v1"})
        assert response.status_code == 409
        assert "LLAMACPP_CHAT_URL" in response.json()["message"]
        field = h.field("llamacpp", "chat_url")
        assert (field["value"], field["source"]) == ("http://llama.test:8081/v1", "env")


def test_the_ollama_address_is_409_while_embeddings_use_ollama(harness: Any) -> None:
    with harness(local_backend="ollama") as h:
        response = h.put("ollama", {"base_url": NEW_URL})
        assert response.status_code == 409
        assert "Embeddings" in response.json()["message"]
        assert h.field("ollama", "base_url")["value"] == "http://ollama.test:11434"


def test_a_bearer_credential_cannot_save_an_address(harness: Any) -> None:
    with harness() as h:
        h.client.cookies.clear()
        header = bearer(h.policy, "read", "graph", "run")
        response = h.client.put(
            "/v1/connections/ollama", json={"fields": {"base_url": NEW_URL}}, headers=header
        )
        assert response.status_code == 403


def test_when_the_engine_refuses_the_row_and_values_return(harness: Any) -> None:
    with harness(engine_cls=RefusingEngine) as h:
        response = h.put("ollama", {"base_url": NEW_URL})
        assert response.status_code == 409
        assert h.field("ollama", "base_url")["source"] == "default"
        assert "ollama_base_url" not in h.file_text()
        assert h.app.state.runtime.providers.values.values == {}


def test_a_saved_address_survives_a_restart(harness: Any, tmp_path: Path) -> None:
    with harness() as h:
        assert h.put("ollama", {"base_url": NEW_URL}).status_code == 200
    with harness() as h:
        assert h.field("ollama", "base_url")["source"] == "config-file"
        assert answer_url(h) == NEW_URL


# ── 5.5 Lifespan wiring ──────────────────────────────────────────────────


def test_launch_loads_keychain_keys_into_the_secret_set_and_the_engine_source(
    harness: Any,
) -> None:
    with harness(stored={"openrouter": KEY64}) as h:
        assert KEY64 in list(h.secrets)
        runtime = h.app.state.runtime
        assert runtime.providers.values.values["openrouter_api_key"] == KEY64
        field = h.field("openrouter", "api_key")
        assert (field["set"], field["source"]) == (True, "keychain")


def test_a_factory_that_takes_no_argument_still_works(tmp_path: Path) -> None:
    config = WebConfig(workspace=tmp_path / "ws", host="127.0.0.1", port=8765, static_dir=None)
    engine = Engine(
        compose.settings_to_effective(make_settings()),
        store=lance_store(tmp_path),
        embed_model=_mock_embed(),
    )
    app = create_app(config, engine_factory=lambda: engine, keychain=FakeKeychain())
    with TestClient(app, base_url=BASE):
        assert app.state.runtime.engine is engine
        assert app.state.runtime.providers is not None


# ── 7.3 PUT and DELETE /v1/connections/{provider}/key ────────────────────


def put_key(h: Harness, key: str = KEY64, provider: str = "openrouter") -> Any:
    return h.client.put(f"/v1/connections/{provider}/key", json={"api_key": key}, headers=ORIGIN)


def test_a_key_goes_to_the_keychain_after_the_secret_set(harness: Any) -> None:
    with harness() as h:
        response = put_key(h)
        assert response.status_code == 200, response.text
        assert h.keychain.data == {"openrouter": KEY64}
        assert h.keychain.known_before_save == [True]  # secrets.add came first
        field = h.field("openrouter", "api_key")
        assert (field["set"], field["source"], field["last4"]) == (True, "keychain", KEY64[-4:])
        assert "saved_at" not in field
        assert '"openrouter_api_key": "keychain://openrouter"' in h.file_text()
        assert KEY64 not in h.file_text()
        assert KEY64 in list(h.secrets)


def test_a_key_is_removed_and_the_flag_cleared(harness: Any) -> None:
    with harness() as h:
        put_key(h)
        response = h.client.delete("/v1/connections/openrouter/key", headers=ORIGIN)
        assert response.status_code == 200
        assert h.keychain.data == {}
        field = h.field("openrouter", "api_key")
        assert (field["set"], field["source"]) == (False, "none")
        assert "openrouter_api_key" not in h.file_text()
        assert KEY64 in list(h.secrets)  # a replaced or removed key stays redacted


def test_a_saved_key_is_loaded_at_launch_and_redacted(harness: Any) -> None:
    with harness() as h:
        put_key(h)
    with harness() as h:  # same config folder; the fake keychain is new, so the key is missing
        field = h.field("openrouter", "api_key")
        assert field["state"] == "keychain-missing" and field["set"] is False


def test_key_routes_need_the_credentials_scope_and_a_session(harness: Any) -> None:
    with harness() as h:
        h.client.cookies.clear()
        header = bearer(h.policy, "read", "graph", "run")
        body = {"api_key": KEY64}
        assert (
            h.client.put("/v1/connections/openrouter/key", json=body, headers=header).status_code
            == 403
        )
        assert h.client.delete("/v1/connections/openrouter/key", headers=header).status_code == 403
        assert h.keychain.data == {}


def test_a_key_from_the_environment_is_409(harness: Any) -> None:
    with harness(explicit=frozenset({"openrouter_api_key"}), openrouter_api_key=SECRET) as h:
        assert put_key(h).status_code == 409
        assert h.client.delete("/v1/connections/openrouter/key", headers=ORIGIN).status_code == 409
        assert h.keychain.data == {}
        assert h.field("openrouter", "api_key")["source"] == "env"


def test_no_keychain_means_409_and_nothing_written(harness: Any) -> None:
    with harness(keychain_available=False) as h:
        response = put_key(h)
        assert response.status_code == 409
        assert "OPENROUTER_API_KEY" in response.json()["message"]
        assert h.keychain.data == {}
        assert h.file_text() == ""


def test_a_failed_keychain_call_is_409_and_writes_nothing(harness: Any) -> None:
    with harness() as h:
        h.keychain.fail_save = True
        assert put_key(h).status_code == 409
        assert h.file_text() == ""


@pytest.mark.parametrize(
    "bad", ["short", "has a space inside zzz1", "x" * 513, "ctrl\x07char-zzz1"]
)
def test_a_bad_key_is_400_and_the_message_holds_no_value(harness: Any, bad: str) -> None:
    with harness() as h:
        response = put_key(h, bad)
        assert response.status_code == 400
        assert "zzz1" not in response.text and bad not in response.text
        assert h.keychain.data == {}


def test_a_provider_without_a_key_field_is_404_on_the_key_route(harness: Any) -> None:
    with harness() as h:
        assert put_key(h, provider="ollama").status_code == 404
        assert put_key(h, provider="mystery").status_code == 404


def test_when_the_engine_refuses_a_key_save_everything_returns(harness: Any) -> None:
    with harness(engine_cls=RefusingEngine) as h:
        assert put_key(h).status_code == 409
        assert h.keychain.data == {}
        assert "openrouter_api_key" not in h.file_text()


# ── 7.4 No response holds the key ────────────────────────────────────────


def windows(text: str, key: str, size: int = 5) -> list[str]:
    return [key[i : i + size] for i in range(len(key) - size + 1) if key[i : i + size] in text]


def test_no_response_holds_five_consecutive_characters_of_the_key(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))
    real = httpx.AsyncClient
    monkeypatch.setattr(
        connection_probe.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw)
    )
    with harness() as h:
        texts = [put_key(h).text, h.client.get("/v1/connections").text]
        texts.append(h.client.post("/v1/connections/openrouter/test", headers=ORIGIN).text)
        texts.append(h.client.post("/v1/connections/openrouter/models", headers=ORIGIN).text)
        texts.append(h.client.get("/v1/settings/chat").text)
        texts.append(h.client.delete("/v1/connections/openrouter/key", headers=ORIGIN).text)
        texts.append(h.client.get("/v1/connections").text)
        for text in texts:
            assert windows(text, KEY64) == []
        put_key(h)
        assert h.field("openrouter", "api_key")["last4"] == KEY64[-4:]
        assert len(KEY64) == 64


def test_a_short_key_shows_no_characters(harness: Any) -> None:
    with harness() as h:
        assert put_key(h, "short-key-1").status_code == 200
        field = h.field("openrouter", "api_key")
        assert field["set"] is True and field["last4"] is None


# ── 7.6 POST .../test with typed values ──────────────────────────────────


@pytest.fixture
def mock_http(monkeypatch: pytest.MonkeyPatch):
    """Route every provider request through a handler; return the request log."""
    seen: list[httpx.Request] = []
    state: dict[str, Any] = {"handler": lambda request: httpx.Response(200, json={})}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return state["handler"](request)

    real = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        connection_probe.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw)
    )
    return SimpleNamespace(seen=seen, set=lambda fn: state.__setitem__("handler", fn))


def test_a_typed_address_is_tested_and_not_saved(harness: Any, mock_http: Any) -> None:
    with harness() as h:
        response = h.client.post(
            "/v1/connections/ollama/test", json={"fields": {"base_url": NEW_URL}}, headers=ORIGIN
        )
        assert response.json() == {"status": "ok", "reachable": True, "reason": None}
        assert [str(r.url) for r in mock_http.seen] == [NEW_URL + "/api/tags"]
        assert h.field("ollama", "base_url")["source"] == "default"
        assert h.file_text() == ""


def test_a_typed_key_is_sent_and_neither_saved_nor_logged(
    harness: Any, mock_http: Any, caplog: pytest.LogCaptureFixture
) -> None:
    with harness() as h, caplog.at_level(logging.DEBUG):
        response = h.client.post(
            "/v1/connections/openrouter/test",
            json={"fields": {"api_key": KEY64}},
            headers=ORIGIN,
        )
        assert response.json()["reachable"] is True
        request = mock_http.seen[0]
        assert request.url.path.endswith("/key")
        assert request.headers["authorization"] == f"Bearer {KEY64}"
        assert h.keychain.data == {} and h.field("openrouter", "api_key")["set"] is False
        assert KEY64 not in caplog.text and KEY64 not in response.text
        assert KEY64 in list(h.secrets)


@pytest.mark.parametrize(
    "bad", ["http://user:pass@localhost:8081/v1", "file:///etc/passwd", "http://h/?a=1"]
)
def test_a_typed_bad_address_is_400_and_sends_nothing(
    harness: Any, mock_http: Any, bad: str
) -> None:
    with harness() as h:
        response = h.client.post(
            "/v1/connections/llamacpp/test", json={"fields": {"chat_url": bad}}, headers=ORIGIN
        )
        assert response.status_code == 400
        assert bad not in response.text
        assert mock_http.seen == []


def test_a_bad_typed_key_is_400(harness: Any, mock_http: Any) -> None:
    with harness() as h:
        response = h.client.post(
            "/v1/connections/openrouter/test",
            json={"fields": {"api_key": "has space zzz1"}},
            headers=ORIGIN,
        )
        assert response.status_code == 400 and "zzz1" not in response.text
        assert mock_http.seen == []


def test_an_unknown_typed_field_is_404(harness: Any, mock_http: Any) -> None:
    with harness() as h:
        response = h.client.post(
            "/v1/connections/ollama/test", json={"fields": {"nope": "x"}}, headers=ORIGIN
        )
        assert response.status_code == 404


# ── 7.7 POST .../models ──────────────────────────────────────────────────


def models(h: Harness, provider: str, fields: dict[str, str] | None = None) -> Any:
    body = {"fields": fields} if fields is not None else None
    return h.client.post(f"/v1/connections/{provider}/models", json=body, headers=ORIGIN)


def test_ollama_lists_its_models(harness: Any, mock_http: Any) -> None:
    mock_http.set(
        lambda r: httpx.Response(
            200, json={"models": [{"name": "qwen3:4b"}, {"name": "llama3.2:latest"}]}
        )
    )
    with harness() as h:
        body = models(h, "ollama").json()
        assert body == {
            "status": "ok",
            "reachable": True,
            "reason": None,
            "models": ["llama3.2:latest", "qwen3:4b"],
            "truncated": False,
        }
        assert mock_http.seen[0].url.path == "/api/tags"


def test_llamacpp_and_openrouter_read_data_ids(harness: Any, mock_http: Any) -> None:
    mock_http.set(lambda r: httpx.Response(200, json={"data": [{"id": "b"}, {"id": "a"}]}))
    with harness() as h:
        assert models(h, "llamacpp").json()["models"] == ["a", "b"]
        assert mock_http.seen[0].url.path == "/v1/models"
        put_key(h)
        assert models(h, "openrouter").json()["models"] == ["a", "b"]
        assert mock_http.seen[-1].headers["authorization"] == f"Bearer {KEY64}"


def test_the_list_is_cut_at_1000_sorted_with_a_flag(harness: Any, mock_http: Any) -> None:
    names = [f"m{n:04d}" for n in range(1500)]
    mock_http.set(
        lambda r: httpx.Response(200, json={"models": [{"name": n} for n in reversed(names)]})
    )
    with harness() as h:
        body = models(h, "ollama").json()
        assert body["models"] == names[:1000] and body["truncated"] is True


def test_invalid_names_are_dropped(harness: Any, mock_http: Any) -> None:
    items = [{"name": n} for n in ["good", "", "x" * 201, "bad\nname", "bad\x00", 5, None]]
    items.append({"other": "field"})
    mock_http.set(lambda r: httpx.Response(200, json={"models": items}))
    with harness() as h:
        assert models(h, "ollama").json()["models"] == ["good"]


def test_a_body_over_8_mib_is_not_read_further(harness: Any, mock_http: Any) -> None:
    big = b'{"models": [' + b'{"name": "m"},' * (700_000) + b'{"name": "z"}]}'
    assert len(big) > connection_probe.MODELS_BODY_LIMIT
    mock_http.set(lambda r: httpx.Response(200, content=big))
    with harness() as h:
        body = models(h, "ollama").json()
        assert body["models"] == [] and body["truncated"] is True


def test_a_non_json_body_is_never_returned(harness: Any, mock_http: Any) -> None:
    mock_http.set(lambda r: httpx.Response(200, content=b"BODY-MARKER-do-not-return"))
    with harness() as h:
        response = models(h, "ollama")
        assert response.json()["models"] == []
        assert "BODY-MARKER" not in response.text


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused to key zzz")), "refused"),
        (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "timeout"),
        (lambda r: httpx.Response(401), "unauthorised"),
        (lambda r: httpx.Response(500), "http-500"),
    ],
)
def test_failures_use_the_test_reasons(
    harness: Any, mock_http: Any, handler: Any, reason: str
) -> None:
    mock_http.set(handler)
    with harness() as h:
        body = models(h, "ollama").json()
        assert (body["reachable"], body["reason"], body["models"]) == (False, reason, [])
        assert "zzz" not in json.dumps(body)


def test_openrouter_without_a_key_sends_nothing(harness: Any, mock_http: Any) -> None:
    with harness() as h:
        body = models(h, "openrouter").json()
        assert (body["reachable"], body["reason"]) == (False, "not-configured")
        assert mock_http.seen == []


def test_typed_values_list_models_and_save_nothing(harness: Any, mock_http: Any) -> None:
    mock_http.set(lambda r: httpx.Response(200, json={"models": [{"name": "x"}]}))
    with harness() as h:
        assert models(h, "ollama", {"base_url": NEW_URL}).json()["models"] == ["x"]
        assert str(mock_http.seen[0].url) == NEW_URL + "/api/tags"
        assert h.field("ollama", "base_url")["source"] == "default"
        assert models(h, "ollama", {"base_url": "ftp://x"}).status_code == 400


def test_the_models_route_is_session_only(harness: Any, mock_http: Any) -> None:
    with harness() as h:
        h.client.cookies.clear()
        header = bearer(h.policy, "read", "graph", "run")
        assert h.client.post("/v1/connections/ollama/models", headers=header).status_code == 403
        assert mock_http.seen == []
        assert models(h, "mystery").status_code in (401, 404)


_ROUTE_KEY = "sk-or-v1-" + "r0uTeK3y" * 7  # gitleaks:allow
_ROUTE_KEY_2 = "sk-or-v1-" + "s3c0nDkY" * 7  # gitleaks:allow


def test_a_key_saved_through_the_route_is_removed_from_the_log_buffer_and_logs_route(
    harness: Any,
) -> None:
    """Task 6.1: save through the key route, log the key, read it back redacted."""
    with harness() as h:
        buffer = h.app.state.log_buffer
        logger = logging.getLogger("omrg.test.key-route")
        logger.setLevel(logging.INFO)
        logger.addHandler(buffer)
        try:
            for key in (_ROUTE_KEY, _ROUTE_KEY_2):  # the second save replaces the first
                saved = h.client.put(
                    "/v1/connections/openrouter/key", json={"api_key": key}, headers=ORIGIN
                )
                assert saved.status_code == 200, saved.text
                logger.error("upstream echoed %s and a cut piece %s", key, key[:-6])
            logs = h.client.get("/v1/logs", headers=ORIGIN)
        finally:
            logger.removeHandler(buffer)
        assert logs.status_code == 200, logs.text
        for key in (_ROUTE_KEY, _ROUTE_KEY_2):
            assert key[9:30] not in logs.text
            assert key[9:30] not in json.dumps(buffer.records())
        assert "upstream echoed ***" in logs.text
