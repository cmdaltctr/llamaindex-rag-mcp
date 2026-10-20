"""Judge settings over HTTP: ``GET``/``PUT /v1/settings/judge`` (add-judge-model-setting 2.2).

Each test follows a scenario of the ``llm-provider-settings`` delta. Settings
are built in memory (no ``.env``) and patched into the composition root. The
Engine's ``use_provider_settings`` is recorded. No provider is contacted.
"""

from __future__ import annotations

import json
from pathlib import Path
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
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

from omrg import compose  # noqa: E402
from omrg.core.providers.llm import registry as llm_registry  # noqa: E402
from omrg.transports.api.routes import chat_settings  # noqa: E402

URL = "/v1/settings/judge"
KEYS = ("answer.verify_provider", "answer.verify_model")


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch) -> Any:
    def apply(*, sources: dict[str, str] | None = None, **overrides: Any) -> Any:
        settings = make_settings(**overrides)
        if sources is not None:
            object.__setattr__(settings, "setting_sources", sources)
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
        client.store = app.state.mcp_http.store  # type: ignore[attr-defined]
        client.judge = lambda: tuple(  # type: ignore[attr-defined]
            app.state.mcp_http.store.read().values.get(key) for key in KEYS
        )
        client.policy = policy  # type: ignore[attr-defined]
        yield client


def put(client: TestClient, body: Any) -> Any:
    # ``json=None`` sends no body, so send the JSON text ``null`` explicitly.
    headers = {**ORIGIN, "Content-Type": "application/json"}
    return client.put(URL, content=json.dumps(body), headers=headers)


def file_bytes(client: Any) -> bytes | None:
    path = client.store.path
    return path.read_bytes() if path.exists() else None


# ── GET /v1/settings/judge ───────────────────────────────────────────────


def test_default_judge_has_no_model(setup: Any) -> None:
    assert setup.get(URL).json() == {
        "status": "ok",
        "revision": "absent",
        "provider": "cloud",
        "resolved_provider": "openrouter",
        "model": "",
        "source": "default",
        "locked": False,
        "lock_reason": None,
        "enabled": True,
        "ready": False,
        "reason": "no-model",
    }


def test_get_needs_read_scope(setup: Any) -> None:
    setup.cookies.clear()
    assert setup.get(URL).status_code == 401
    assert setup.get(URL, headers=bearer(setup.policy, "graph")).status_code == 403
    assert setup.get(URL, headers=bearer(setup.policy, "read")).status_code == 200


def test_ready_judge_from_the_file(setup: Any, configure: Any) -> None:
    configure(openrouter_api_key=SECRET)
    assert put(setup, {"provider": "openrouter", "model": "openai/gpt-5-mini"}).status_code == 200
    response = setup.get(URL)
    body = response.json()
    assert (body["provider"], body["resolved_provider"], body["model"]) == (
        "openrouter",
        "openrouter",
        "openai/gpt-5-mini",
    )
    assert (body["source"], body["ready"], body["reason"]) == ("config-file", True, None)
    assert SECRET not in response.text


def test_the_local_alias_resolves_to_the_local_backend(setup: Any, configure: Any) -> None:
    configure(verify_provider="local", verify_model="judge-gguf")
    body = setup.get(URL).json()
    assert (body["provider"], body["resolved_provider"]) == ("local", "ollama")
    assert (body["ready"], body["reason"]) == (True, None)


def test_reason_disabled(setup: Any, configure: Any) -> None:
    configure(answer_enabled=False, verify_model="m")
    body = setup.get(URL).json()
    assert (body["enabled"], body["ready"], body["reason"]) == (False, False, "disabled")


def test_reason_unknown_provider(setup: Any, configure: Any) -> None:
    configure(verify_provider="gemini", verify_model="m")
    assert setup.get(URL).json()["reason"] == "unknown-provider"


def test_reason_not_installed(setup: Any, configure: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    configure(verify_model="m")
    monkeypatch.setattr(chat_settings, "module_installed", lambda name: False)
    assert setup.get(URL).json()["reason"] == "not-installed"


def test_reason_not_configured_without_a_key(setup: Any, configure: Any) -> None:
    configure(verify_model="openai/gpt-5-mini")
    assert setup.get(URL).json()["reason"] == "not-configured"


def test_get_sends_no_provider_request(setup: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a provider request was sent by GET")

    async def forbidden_async(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a provider request was sent by GET")

    monkeypatch.setattr(llm_registry, "get", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden_async)
    assert setup.get(URL).status_code == 200


def test_get_reports_no_claim_check_switch(setup: Any) -> None:
    assert "verify_claims" not in setup.get(URL).json()


# ── PUT /v1/settings/judge ───────────────────────────────────────────────


def test_save_a_judge(setup: Any) -> None:
    response = put(setup, {"provider": "openrouter", "model": "openai/gpt-5-mini"})
    assert response.status_code == 200, response.text
    assert setup.judge() == ("openrouter", "openai/gpt-5-mini")
    assert response.json()["revision"] == setup.store.read().revision
    assert response.json()["source"] == "config-file"
    assert setup.store.read().values.get("answer.provider") is None  # the Chat choice stays
    assert len(setup.applied) == 1
    block = setup.applied[0].answer
    assert (block.verify_provider, block.verify_model) == ("openrouter", "openai/gpt-5-mini")


def test_put_requires_session_and_origin(setup: Any) -> None:
    payload = {"provider": "ollama", "model": "m"}
    assert setup.put(URL, json=payload).status_code == 403
    headers = {**ORIGIN, **bearer(setup.policy, "read")}
    assert setup.put(URL, json=payload, headers=headers).status_code == 403
    setup.cookies.clear()
    assert setup.put(URL, json=payload, headers=ORIGIN).status_code == 401
    assert setup.judge() == (None, None)


@pytest.mark.parametrize(
    "body",
    [
        {"provider": "openrouter", "model": ""},
        {"provider": "openrouter", "model": "  "},
        {"provider": "gemini", "model": "m"},
        {"provider": "cloud", "model": "m"},  # a save never writes an alias
        {"provider": "local", "model": "m"},
        {"provider": "ollama"},
        {"model": "m"},
        {"provider": "ollama", "model": "x" * 201},
        {"provider": "ollama", "model": "bad\nname"},
        {"provider": "ollama", "model": "m", "extra": 1},
    ],
)
def test_bad_body_is_400_and_saves_nothing(setup: Any, body: Any) -> None:
    before = file_bytes(setup)
    response = put(setup, body)
    assert response.status_code == 400, response.text
    assert file_bytes(setup) == before
    assert setup.applied == []


def test_clear_the_judge(setup: Any) -> None:
    put(setup, {"provider": "llamacpp", "model": "judge-gguf"})
    response = put(setup, None)
    assert response.status_code == 200, response.text
    assert setup.judge() == (None, None)
    assert "verify" not in setup.store.path.read_text(encoding="utf-8")
    body = setup.get(URL).json()
    assert (body["source"], body["provider"], body["model"]) == ("default", "cloud", "")
    assert setup.applied[-1].answer.verify_model == ""


def test_a_revision_only_body_clears(setup: Any) -> None:
    put(setup, {"provider": "llamacpp", "model": "judge-gguf"})
    response = put(setup, {"revision": setup.store.read().revision})
    assert response.status_code == 200, response.text
    assert setup.judge() == (None, None)


def test_locked_by_dotenv_is_409_naming_the_variable(setup: Any, configure: Any) -> None:
    configure(
        verify_model="from-dotenv",
        explicit=frozenset({"answer.verify_model"}),
        sources={"answer.verify_model": "dotenv"},
    )
    body = setup.get(URL).json()
    assert (body["source"], body["locked"]) == ("dotenv", True)
    assert "ANSWER__VERIFY_MODEL" in body["lock_reason"]
    before = file_bytes(setup)
    response = put(setup, {"provider": "ollama", "model": "other"})
    assert response.status_code == 409
    assert "ANSWER__VERIFY_MODEL" in response.text
    assert put(setup, None).status_code == 409
    assert file_bytes(setup) == before
    assert setup.applied == []
    assert setup.get(URL).json()["model"] == "from-dotenv"


def test_the_environment_provider_locks_the_model_too(setup: Any, configure: Any) -> None:
    configure(explicit=frozenset({"answer.verify_provider"}))
    body = setup.get(URL).json()
    assert (body["source"], body["locked"]) == ("env", True)
    assert put(setup, {"provider": "ollama", "model": "m"}).status_code == 409


def test_a_stale_revision_is_409_and_saves_nothing(setup: Any) -> None:
    put(setup, {"provider": "llamacpp", "model": "old"})
    before = file_bytes(setup)
    response = put(setup, {"provider": "ollama", "model": "new", "revision": "stale"})
    assert response.status_code == 409, response.text
    assert file_bytes(setup) == before


def test_an_engine_refusal_is_409_and_leaves_the_file(setup: Any) -> None:
    put(setup, {"provider": "llamacpp", "model": "old"})
    before = file_bytes(setup)

    def refuse(effective: Any) -> None:
        raise ValueError("refused")

    setup.app.state.runtime.engine.use_provider_settings = refuse
    response = put(setup, {"provider": "ollama", "model": "new"})
    assert response.status_code == 409
    assert file_bytes(setup) == before
    body = setup.get(URL).json()
    assert (body["provider"], body["model"]) == ("llamacpp", "old")


def test_judge_settings_responses_conform(setup: Any) -> None:
    check = ContractChecker()
    check.check(setup.get(URL), 200)
    check.check(put(setup, {"provider": "ollama", "model": "qwen3:4b"}), 200)
    check.check(put(setup, {"provider": "openrouter", "model": ""}), 400)
    check.check(put(setup, {"provider": "ollama", "model": "m", "revision": "stale"}), 409)
    check.check(put(setup, None), 200)
    setup.app.state.runtime.providers = None  # provider settings not loaded
    check.check(put(setup, {"provider": "ollama", "model": "m"}), 404)
    assert check.operations >= FAMILIES["judge_settings"]
