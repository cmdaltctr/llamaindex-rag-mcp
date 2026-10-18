"""Chat settings over HTTP: ``GET``/``PUT /v1/settings/chat`` and the model test (8.1, 8.3).

Settings are built in memory (no ``.env``) and patched into the composition
root. The Engine's ``use_provider_settings`` is recorded. No real provider
is contacted: the model test uses fake LLMs from a patched registry. The
test result holds a reason from a fixed set; it never holds reply or
exception text.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_connection_summary import SECRET, make_settings  # noqa: E402
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

from omrg import compose  # noqa: E402
from omrg.core.providers.llm import registry as llm_registry  # noqa: E402
from omrg.integrations.workspace_sqlite.settings import WorkspaceSettings  # noqa: E402
from omrg.transports.api.routes import chat_settings  # noqa: E402

REPLY = "REPLY-MARKER-do-not-return"
FAILURE = "EXCEPTION-MARKER-do-not-return"


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch) -> Any:
    def apply(**overrides: Any) -> Any:
        settings = make_settings(**overrides)
        monkeypatch.setattr(compose, "get_settings", lambda: settings)
        return settings

    return apply


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any, configure: Any, monkeypatch: pytest.MonkeyPatch):
    configure()
    monkeypatch.setattr(chat_settings, "module_installed", lambda name: True)
    engine = make_engine(lance_store(tmp_path), effective_settings())
    applied: list[Any] = []
    engine.use_provider_settings = applied.append  # type: ignore[method-assign]
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        client.applied = applied  # type: ignore[attr-defined]
        client.db = WorkspaceSettings(app.state.mcp_http.records)  # type: ignore[attr-defined]
        client.policy = policy  # type: ignore[attr-defined]
        yield client


def put(client: TestClient, body: Any) -> Any:
    # ``json=None`` sends no body, so send the JSON text ``null`` explicitly.
    headers = {**ORIGIN, "Content-Type": "application/json"}
    return client.put("/v1/settings/chat", content=json.dumps(body), headers=headers)


# ── GET /v1/settings/chat ────────────────────────────────────────────────


def test_get_default_choice(setup: Any) -> None:
    body = setup.get("/v1/settings/chat").json()
    assert body == {
        "status": "ok",
        "provider": "ollama",
        "model": "answer-model",
        "source": "default",
        "locked": False,
        "lock_reason": None,
        "enabled": True,
        "ready": True,
        "reason": None,
    }


def test_get_needs_read_scope(setup: Any) -> None:
    setup.cookies.clear()
    assert setup.get("/v1/settings/chat").status_code == 401
    assert setup.get("/v1/settings/chat", headers=bearer(setup.policy, "graph")).status_code == 403
    assert setup.get("/v1/settings/chat", headers=bearer(setup.policy, "read")).status_code == 200


def test_get_reason_disabled(setup: Any, configure: Any) -> None:
    configure(answer_enabled=False)
    body = setup.get("/v1/settings/chat").json()
    assert (body["enabled"], body["ready"], body["reason"]) == (False, False, "disabled")


def test_get_reason_unknown_provider(setup: Any, configure: Any) -> None:
    configure(answer_provider="gemini")
    body = setup.get("/v1/settings/chat").json()
    assert (body["ready"], body["reason"]) == (False, "unknown-provider")


def test_get_reason_not_installed(setup: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_settings, "module_installed", lambda name: False)
    body = setup.get("/v1/settings/chat").json()
    assert (body["ready"], body["reason"]) == (False, "not-installed")


def test_get_reason_not_configured_without_key(setup: Any, configure: Any) -> None:
    configure(answer_provider="openrouter")
    body = setup.get("/v1/settings/chat").json()
    assert (body["ready"], body["reason"]) == (False, "not-configured")


def test_get_ready_with_key_and_never_returns_it(setup: Any, configure: Any) -> None:
    configure(answer_provider="openrouter", openrouter_api_key=SECRET)
    response = setup.get("/v1/settings/chat")
    assert response.json()["ready"] is True
    assert SECRET not in response.text


def test_get_sends_no_provider_request(setup: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a provider request was sent by GET")

    monkeypatch.setattr(llm_registry, "get", forbidden)
    assert setup.get("/v1/settings/chat").status_code == 200


def test_get_env_source_locks(setup: Any, configure: Any) -> None:
    configure(explicit=frozenset({"answer.model"}))
    body = setup.get("/v1/settings/chat").json()
    assert body["source"] == "env"
    assert body["locked"] is True
    assert "ANSWER__MODEL" in body["lock_reason"]


# ── PUT /v1/settings/chat ────────────────────────────────────────────────


def test_put_saves_and_applies(setup: Any) -> None:
    response = put(setup, {"provider": "llamacpp", "model": "my-model"})
    assert response.status_code == 200, response.text
    assert (setup.db.get_chat_provider(), setup.db.get_chat_model()) == ("llamacpp", "my-model")
    assert len(setup.applied) == 1
    assert setup.applied[0].answer.provider == "llamacpp"
    assert setup.applied[0].answer.model == "my-model"
    body = setup.get("/v1/settings/chat").json()
    assert (body["provider"], body["model"], body["source"]) == ("llamacpp", "my-model", "saved")
    assert body["locked"] is False


def test_put_requires_session_and_origin(setup: Any) -> None:
    payload = {"provider": "ollama", "model": "m"}
    assert setup.put("/v1/settings/chat", json=payload).status_code == 403
    headers = {**ORIGIN, **bearer(setup.policy, "read")}
    assert setup.put("/v1/settings/chat", json=payload, headers=headers).status_code == 403
    setup.cookies.clear()
    assert setup.put("/v1/settings/chat", json=payload, headers=ORIGIN).status_code == 401
    assert setup.db.get_chat_provider() is None


def test_put_null_clears(setup: Any) -> None:
    put(setup, {"provider": "llamacpp", "model": "m"})
    response = put(setup, None)
    assert response.status_code == 200, response.text
    assert (setup.db.get_chat_provider(), setup.db.get_chat_model()) == (None, None)
    assert setup.get("/v1/settings/chat").json()["source"] == "default"
    assert setup.applied[-1].answer.provider == "ollama"


@pytest.mark.parametrize(
    "body",
    [
        {"provider": "gemini", "model": "m"},
        {"provider": "ollama", "model": ""},
        {"provider": "ollama", "model": "x" * 201},
        {"provider": "ollama", "model": "bad\nname"},
        {"provider": "ollama", "model": "bad\x00name"},
        {"provider": "ollama"},
        {"provider": "ollama", "model": "m", "extra": 1},
    ],
)
def test_put_bad_body_is_400_and_saves_nothing(setup: Any, body: Any) -> None:
    response = put(setup, body)
    assert response.status_code in (400, 422), response.text
    assert setup.db.get_chat_provider() is None
    assert setup.db.get_chat_model() is None
    assert setup.applied == []


def test_put_unknown_provider_is_400(setup: Any) -> None:
    assert put(setup, {"provider": "gemini", "model": "m"}).status_code == 400


def test_put_locked_is_409_naming_variable(setup: Any, configure: Any) -> None:
    configure(explicit=frozenset({"answer.model"}))
    response = put(setup, {"provider": "ollama", "model": "m"})
    assert response.status_code == 409
    assert "ANSWER__MODEL" in response.text
    assert setup.db.get_chat_model() is None
    assert setup.applied == []
    assert put(setup, None).status_code == 409


def test_put_engine_refusal_restores_state(setup: Any) -> None:
    put(setup, {"provider": "llamacpp", "model": "old"})

    def refuse(effective: Any) -> None:
        raise ValueError("refused")

    # Replace the recorder installed by the fixture on the app engine.
    setup.app.state.runtime.engine.use_provider_settings = refuse
    response = put(setup, {"provider": "ollama", "model": "new"})
    assert response.status_code == 409
    assert (setup.db.get_chat_provider(), setup.db.get_chat_model()) == ("llamacpp", "old")
    body = setup.get("/v1/settings/chat").json()
    assert (body["provider"], body["model"]) == ("llamacpp", "old")


# ── POST /v1/settings/chat/test ──────────────────────────────────────────


class Reply:
    def __init__(self, text: str) -> None:
        self.text = text

    def __str__(self) -> str:
        return self.text


class StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(FAILURE)
        self.status_code = status_code


class FakeLLM:
    def __init__(self, behaviour: Any) -> None:
        self.behaviour = behaviour
        self.prompts: list[str] = []

    async def acomplete(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        result = self.behaviour
        if isinstance(result, BaseException):
            raise result
        if callable(result):
            return await result()
        return Reply(result)


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> Any:
    built: list[tuple[str, str | None]] = []
    holder: dict[str, Any] = {}

    def install(behaviour: Any) -> list[tuple[str, str | None]]:
        llm = FakeLLM(behaviour)
        holder["llm"] = llm

        def get(name: str) -> Any:
            def build(settings: Any, *, timeout: Any = None, answer_model: Any = None) -> Any:
                built.append((name, answer_model))
                return llm

            return build

        monkeypatch.setattr(llm_registry, "get", get)
        return built

    install.holder = holder  # type: ignore[attr-defined]
    return install


def run_test(client: TestClient, body: Any = None) -> Any:
    kwargs: dict[str, Any] = {"headers": ORIGIN}
    if body is not None:
        kwargs["json"] = body
    return client.post("/v1/settings/chat/test", **kwargs)


def test_model_replies(setup: Any, fake_llm: Any) -> None:
    built = fake_llm(REPLY)
    response = run_test(setup, {"provider": "llamacpp", "model": "cand"})
    body = response.json()
    assert response.status_code == 200, response.text
    assert body["ok"] is True
    assert body["reason"] is None
    assert isinstance(body["elapsed_ms"], int)
    assert set(body) == {"status", "ok", "reason", "elapsed_ms"}
    assert built == [("llamacpp", "cand")]
    assert REPLY not in response.text
    assert setup.db.get_chat_provider() is None  # a test never saves
    assert setup.applied == []


def test_no_body_tests_the_choice_in_use(setup: Any, fake_llm: Any) -> None:
    built = fake_llm(REPLY)
    assert run_test(setup).json()["ok"] is True
    assert built == [("ollama", "answer-model")]


@pytest.mark.parametrize(
    ("behaviour", "reason"),
    [
        (ConnectionRefusedError(FAILURE), "refused"),
        (TimeoutError(FAILURE), "timeout"),
        (StatusError(401), "unauthorised"),
        (StatusError(403), "unauthorised"),
        (StatusError(404), "http-404"),
        (StatusError(500), "http-500"),
        (ModuleNotFoundError(FAILURE), "not-installed"),
        (RuntimeError(FAILURE), "failed"),
        ("", "empty-reply"),
        ("   ", "empty-reply"),
    ],
)
def test_fixed_reasons_and_no_text(setup: Any, fake_llm: Any, behaviour: Any, reason: str) -> None:
    fake_llm(behaviour)
    response = run_test(setup)
    body = response.json()
    assert (body["ok"], body["reason"]) == (False, reason)
    assert FAILURE not in response.text
    assert setup.db.get_chat_provider() is None


def test_slow_model_times_out(setup: Any, fake_llm: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow() -> Any:
        await asyncio.sleep(5)

    monkeypatch.setattr(chat_settings, "TEST_TIMEOUT_SECONDS", 0.05)
    fake_llm(slow)
    body = run_test(setup).json()
    assert (body["ok"], body["reason"]) == (False, "timeout")


def test_not_configured_sends_no_request(setup: Any, configure: Any, fake_llm: Any) -> None:
    configure(answer_provider="openrouter")
    built = fake_llm(REPLY)
    body = run_test(setup).json()
    assert (body["ok"], body["reason"]) == (False, "not-configured")
    assert built == []


def test_unknown_provider_is_400(setup: Any, fake_llm: Any) -> None:
    fake_llm(REPLY)
    assert run_test(setup, {"provider": "gemini", "model": "m"}).status_code == 400


def test_test_needs_session(setup: Any, fake_llm: Any) -> None:
    fake_llm(REPLY)
    assert setup.post("/v1/settings/chat/test").status_code == 403
    headers = {**ORIGIN, **bearer(setup.policy, "read")}
    assert setup.post("/v1/settings/chat/test", headers=headers).status_code == 403
    setup.cookies.clear()
    assert setup.post("/v1/settings/chat/test", headers=ORIGIN).status_code == 401


def test_chat_settings_responses_conform(setup: Any, configure: Any) -> None:
    configure(openrouter_api_key=SECRET)
    check = ContractChecker()
    check.check(setup.get("/v1/settings/chat"), 200)
    check.check(put(setup, {"provider": "ollama", "model": "qwen3:4b"}), 200)
    check.check(put(setup, {"provider": "gemini", "model": "m"}), 400)
    check.check(put(setup, None), 200)
    check.check(
        setup.post(
            "/v1/settings/chat/test", json={"provider": "gemini", "model": "m"}, headers=ORIGIN
        ),
        400,
    )
    check.check(
        setup.post(
            "/v1/settings/chat/test", json={"provider": "ollama", "model": "m"}, headers=ORIGIN
        ),
        200,
    )
    assert check.operations >= FAMILIES["chat_settings"]
