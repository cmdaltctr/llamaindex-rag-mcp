"""Reasoning levels on ``GET``/``PUT /v1/settings/chat`` and ``/v1/settings/judge`` (task 4.1).

Spec ``answer-reasoning-and-usage``: a level is empty or 1 to 32 letters,
digits, ``-`` and ``_``. A bad level gives 400 and changes nothing. A level
that ``ANSWER__REASONING`` (Chat) or ``ANSWER__VERIFY_REASONING`` (judge)
sets is locked: a save that sends it gives 409 naming the variable. The level
is written in the same write as the provider and model.

Body rules this suite pins (add-chat-reasoning-and-usage D4):

- ``reasoning`` left out keeps the saved level.
- ``reasoning: ""`` removes the saved level (provider default).
- A body with the saved provider and model and a new level writes the level,
  and the running Engine takes it.
- A body with only ``reasoning`` (and ``revision``) sets the level and keeps
  the provider and model.
- A clear (no provider, model or reasoning) also removes the saved level.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_connection_summary import make_settings  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs import compose  # noqa: E402
from omrs.core.answer.settings import AnswerSettings  # noqa: E402
from omrs.transports.api.routes import chat_settings  # noqa: E402

CHAT = "/v1/settings/chat"
JUDGE = "/v1/settings/judge"


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch) -> Any:
    def apply(**overrides: Any) -> Any:
        answer = overrides.pop("answer", None)
        settings = make_settings(**overrides)
        if answer is not None:
            object.__setattr__(settings, "answer", answer)
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
        client.saved = lambda key: app.state.mcp_http.store.read().values.get(key)  # type: ignore[attr-defined]
        client.policy = policy  # type: ignore[attr-defined]
        yield client


def put(client: TestClient, url: str, body: Any) -> Any:
    headers = {**ORIGIN, "Content-Type": "application/json"}
    return client.put(url, content=json.dumps(body), headers=headers)


def file_bytes(client: Any) -> bytes | None:
    path = client.store.path
    return path.read_bytes() if path.exists() else None


# ── GET ──────────────────────────────────────────────────────────────────


def test_chat_get_reports_the_level_fields(setup: Any) -> None:
    body = setup.get(CHAT).json()
    assert body["reasoning"] == ""
    assert body["reasoning_locked"] is False
    assert body["reasoning_lock_reason"] is None
    assert body["reasoning_ignored"] is False  # Ollama maps a level to ``think``


def test_judge_get_reports_the_level_fields(setup: Any) -> None:
    body = setup.get(JUDGE).json()
    assert (body["reasoning"], body["reasoning_locked"], body["reasoning_ignored"]) == (
        "",
        False,
        False,  # the judge resolves to OpenRouter by default
    )
    assert body["reasoning_lock_reason"] is None


def test_chat_get_reports_a_provider_that_ignores_the_level(setup: Any, configure: Any) -> None:
    configure(answer_provider="llamacpp")
    assert setup.get(CHAT).json()["reasoning_ignored"] is True


def test_chat_get_lock_names_the_variable(setup: Any, configure: Any) -> None:
    configure(
        explicit=frozenset({"answer.reasoning"}),
        answer=AnswerSettings(provider="ollama", model="answer-model", reasoning="high"),
    )
    body = setup.get(CHAT).json()
    assert body["reasoning"] == "high"
    assert body["reasoning_locked"] is True
    assert "ANSWER__REASONING" in body["reasoning_lock_reason"]
    assert body["locked"] is False  # the level locks alone, not the Chat choice


def test_judge_get_lock_names_the_variable(setup: Any, configure: Any) -> None:
    configure(explicit=frozenset({"answer.verify_reasoning"}))
    body = setup.get(JUDGE).json()
    assert body["reasoning_locked"] is True
    assert "ANSWER__VERIFY_REASONING" in body["reasoning_lock_reason"]
    assert body["locked"] is False


# ── PUT: save ────────────────────────────────────────────────────────────


def test_chat_save_writes_the_level_with_the_choice(setup: Any) -> None:
    response = put(
        setup, CHAT, {"provider": "openrouter", "model": "z-ai/glm-5.3-flash", "reasoning": "low"}
    )
    assert response.status_code == 200, response.text
    assert setup.saved("answer.reasoning") == "low"
    assert setup.saved("answer.model") == "z-ai/glm-5.3-flash"
    assert response.json()["reasoning"] == "low"
    assert len(setup.applied) == 1  # one write, one apply
    assert setup.applied[0].answer.reasoning == "low"
    assert setup.applied[0].answer.model == "z-ai/glm-5.3-flash"


def test_judge_save_writes_its_own_level(setup: Any) -> None:
    response = put(setup, JUDGE, {"provider": "openrouter", "model": "j", "reasoning": "high"})
    assert response.status_code == 200, response.text
    assert setup.saved("answer.verify_reasoning") == "high"
    assert setup.saved("answer.reasoning") is None  # the Chat level stays
    assert response.json()["reasoning"] == "high"
    assert setup.applied[-1].answer.verify_reasoning == "high"


def test_chat_save_without_reasoning_keeps_the_saved_level(setup: Any) -> None:
    put(setup, CHAT, {"provider": "ollama", "model": "m", "reasoning": "low"})
    response = put(setup, CHAT, {"provider": "ollama", "model": "other"})
    assert response.status_code == 200, response.text
    assert setup.saved("answer.reasoning") == "low"
    assert response.json()["reasoning"] == "low"


def test_chat_empty_reasoning_removes_the_level(setup: Any) -> None:
    put(setup, CHAT, {"provider": "ollama", "model": "m", "reasoning": "low"})
    response = put(setup, CHAT, {"provider": "ollama", "model": "m", "reasoning": ""})
    assert response.status_code == 200, response.text
    assert setup.saved("answer.reasoning") is None
    assert response.json()["reasoning"] == ""
    assert '"reasoning"' not in setup.store.path.read_text(encoding="utf-8")


def test_chat_same_choice_with_a_new_level_applies_it(setup: Any) -> None:
    put(setup, CHAT, {"provider": "ollama", "model": "m", "reasoning": "low"})
    response = put(setup, CHAT, {"provider": "ollama", "model": "m", "reasoning": "high"})
    assert response.status_code == 200, response.text
    assert setup.saved("answer.reasoning") == "high"
    assert setup.applied[-1].answer.reasoning == "high"
    assert (setup.applied[-1].answer.provider, setup.applied[-1].answer.model) == ("ollama", "m")


def test_chat_level_only_body_keeps_the_choice(setup: Any) -> None:
    put(setup, CHAT, {"provider": "llamacpp", "model": "m"})
    response = put(setup, CHAT, {"reasoning": "low"})
    assert response.status_code == 200, response.text
    assert (setup.saved("answer.provider"), setup.saved("answer.model")) == ("llamacpp", "m")
    assert setup.saved("answer.reasoning") == "low"


def test_chat_clear_also_removes_the_level(setup: Any) -> None:
    put(setup, CHAT, {"provider": "ollama", "model": "m", "reasoning": "low"})
    response = put(setup, CHAT, None)
    assert response.status_code == 200, response.text
    assert setup.saved("answer.reasoning") is None
    assert setup.saved("answer.provider") is None


def test_judge_level_only_body_keeps_the_choice(setup: Any) -> None:
    put(setup, JUDGE, {"provider": "ollama", "model": "j"})
    response = put(setup, JUDGE, {"reasoning": "none"})
    assert response.status_code == 200, response.text
    assert setup.saved("answer.verify_model") == "j"
    assert setup.saved("answer.verify_reasoning") == "none"


# ── PUT: refuse (400) ────────────────────────────────────────────────────


@pytest.mark.parametrize("url", [CHAT, JUDGE])
@pytest.mark.parametrize("level", ["high; drop", "x" * 33, "lo w", "niveau\n", "ünï"])
def test_bad_level_is_400_and_changes_nothing(setup: Any, url: str, level: str) -> None:
    before = file_bytes(setup)
    response = put(setup, url, {"provider": "ollama", "model": "m", "reasoning": level})
    assert response.status_code == 400, response.text
    # The route refuses it before any write, naming the field and not the value.
    message = response.json()["message"]
    assert message.startswith("Invalid request.") and "reasoning" in message
    assert level not in response.text
    assert file_bytes(setup) == before
    assert setup.applied == []


# ── PUT: lock (409) ──────────────────────────────────────────────────────


def test_chat_locked_level_is_409_naming_the_variable(setup: Any, configure: Any) -> None:
    configure(explicit=frozenset({"answer.reasoning"}))
    before = file_bytes(setup)
    response = put(setup, CHAT, {"provider": "ollama", "model": "m", "reasoning": "low"})
    assert response.status_code == 409
    assert "ANSWER__REASONING" in response.text
    assert file_bytes(setup) == before
    assert setup.applied == []


def test_chat_locked_level_still_lets_the_choice_save(setup: Any, configure: Any) -> None:
    configure(explicit=frozenset({"answer.reasoning"}))
    response = put(setup, CHAT, {"provider": "ollama", "model": "m"})
    assert response.status_code == 200, response.text
    assert setup.saved("answer.model") == "m"
    assert put(setup, CHAT, None).status_code == 200  # a clear skips the locked level


def test_judge_locked_level_is_409_naming_the_variable(setup: Any, configure: Any) -> None:
    configure(explicit=frozenset({"answer.verify_reasoning"}))
    before = file_bytes(setup)
    response = put(setup, JUDGE, {"provider": "ollama", "model": "m", "reasoning": "low"})
    assert response.status_code == 409
    assert "ANSWER__VERIFY_REASONING" in response.text
    assert file_bytes(setup) == before


def test_chat_locked_choice_allows_a_level_only_body(setup: Any, configure: Any) -> None:
    """A level-only body writes no choice, so the choice lock does not block it."""
    configure(explicit=frozenset({"answer.model"}))
    response = put(setup, CHAT, {"reasoning": "low"})
    assert response.status_code == 200, response.text
    assert setup.saved("answer.reasoning") == "low"
    assert (
        put(setup, CHAT, {"provider": "ollama", "model": "m", "reasoning": "low"}).status_code
        == 409
    )


def test_reasoning_responses_conform(setup: Any, configure: Any) -> None:
    check = ContractChecker()
    check.check(setup.get(CHAT), 200)
    check.check(setup.get(JUDGE), 200)
    check.check(put(setup, CHAT, {"provider": "ollama", "model": "m", "reasoning": "low"}), 200)
    check.check(put(setup, CHAT, {"reasoning": "bad level"}), 400)
    check.check(put(setup, JUDGE, {"provider": "ollama", "model": "m", "reasoning": "max"}), 200)
    configure(explicit=frozenset({"answer.reasoning", "answer.verify_reasoning"}))
    check.check(put(setup, CHAT, {"reasoning": "low"}), 409)
    check.check(put(setup, JUDGE, {"reasoning": "low"}), 409)
    assert setup.get(CHAT, headers=bearer(setup.policy, "read")).status_code == 200
