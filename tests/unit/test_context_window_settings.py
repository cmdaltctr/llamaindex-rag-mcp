"""Context window settings: sources, locks and live apply (Parts A.1 to A.4).

``ollama_context_window`` and ``llamacpp_context_window`` follow the provider
precedence of ADR-087: environment and ``.env`` lock, ``omrs.jsonc`` applies
and does not lock, then the default of 16,384 tokens. No test calls a
provider or reads the real user config folder.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tests.unit import test_web_connections_edit as edit

from omrs import compose
from omrs.compose_providers import ProviderValues, apply_provider_values, locked_fields
from omrs.config import Settings
from omrs.core.providers.llm import registry
from omrs.core.providers.llm.connection import (
    ConnectionDescriptor,
    ConnectionField,
    ConnectionTarget,
)

harness = edit.harness  # the web test fixture, reused as is

FIELDS = {
    "ollama_context_window": "OLLAMA_CONTEXT_WINDOW",
    "llamacpp_context_window": "LLAMACPP_CONTEXT_WINDOW",
}


TEXT_FIELDS = {
    "llamacpp_server_binary": "LLAMACPP_SERVER_BINARY",
    "llamacpp_server_model": "LLAMACPP_SERVER_MODEL",
}


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for variable in (*FIELDS.values(), *TEXT_FIELDS.values(), "LLAMACPP_IDLE_SLEEP_SECONDS"):
        monkeypatch.delenv(variable, raising=False)
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def build(tmp_path: Path, dotenv: str = "") -> Settings:
    env_file = tmp_path / "test.env"
    env_file.write_text(dotenv, encoding="utf-8")
    return Settings(_env_file=env_file)


@pytest.mark.parametrize("field", list(FIELDS))
def test_default_is_16384(tmp_path: Path, field: str) -> None:
    settings = build(tmp_path)
    assert getattr(settings, field) == 16384
    assert field not in settings.provider_explicit


@pytest.mark.parametrize(("field", "variable"), list(FIELDS.items()))
def test_environment_sets_and_locks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str, variable: str
) -> None:
    monkeypatch.setenv(variable, "8192")
    settings = build(tmp_path)
    assert getattr(settings, field) == 8192
    assert field in settings.provider_explicit
    assert locked_fields(settings, settings.provider_explicit)[field] == "environment"


@pytest.mark.parametrize(("field", "variable"), list(FIELDS.items()))
def test_dotenv_sets_and_locks(tmp_path: Path, field: str, variable: str) -> None:
    settings = build(tmp_path, f"{variable}=4096\n")
    assert getattr(settings, field) == 4096
    assert field in settings.provider_explicit


@pytest.mark.parametrize("value", ["1000", "300000", "abc"])
def test_bad_environment_value_fails_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    monkeypatch.setenv("OLLAMA_CONTEXT_WINDOW", value)
    with pytest.raises(ValidationError):
        build(tmp_path)


@pytest.mark.parametrize("raw", ["8192", '"8192"'])
@pytest.mark.parametrize("field", list(FIELDS))
def test_config_file_sets_and_does_not_lock(
    folder: Path, tmp_path: Path, field: str, raw: str
) -> None:
    (folder / "omrs.jsonc").write_text(f'{{"{field}": {raw}}}', encoding="utf-8")
    settings = build(tmp_path)
    assert getattr(settings, field) == 8192
    assert isinstance(getattr(settings, field), int)
    assert field in settings.config_file_fields
    assert settings.setting_sources[field] == "config-file"
    assert field not in locked_fields(settings, settings.provider_explicit)


@pytest.mark.parametrize("raw", ["987654321", "100", '"abc"', "16384.5", "true"])
def test_invalid_config_file_value_is_ignored_with_one_warning(
    folder: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture, raw: str
) -> None:
    (folder / "omrs.jsonc").write_text(f'{{"ollama_context_window": {raw}}}', encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        settings = build(tmp_path)
    assert settings.ollama_context_window == 16384
    assert "ollama_context_window" not in settings.config_file_fields
    text = " ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert "ollama_context_window" in text
    assert raw.strip('"') not in text.replace(str(folder), "")


def test_environment_beats_config_file(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (folder / "omrs.jsonc").write_text('{"ollama_context_window": 4096}', encoding="utf-8")
    monkeypatch.setenv("OLLAMA_CONTEXT_WINDOW", "8192")
    settings = build(tmp_path)
    assert settings.ollama_context_window == 8192
    assert "ollama_context_window" not in settings.config_file_fields


def test_saved_value_applies_as_an_integer(tmp_path: Path) -> None:
    settings = build(tmp_path)
    saved = ProviderValues(values={"ollama_context_window": "32768"})
    result = apply_provider_values(settings, saved)
    assert result.ollama_context_window == 32768
    assert isinstance(result.ollama_context_window, int)


def test_a_damaged_saved_value_is_ignored(tmp_path: Path) -> None:
    settings = build(tmp_path)
    for bad in ("abc", "100", "999999999", "16384.5"):
        saved = ProviderValues(values={"ollama_context_window": bad})
        assert apply_provider_values(settings, saved).ollama_context_window == 16384


def test_locked_value_beats_the_saved_value(tmp_path: Path) -> None:
    settings = build(tmp_path, "OLLAMA_CONTEXT_WINDOW=8192\n")
    saved = ProviderValues(values={"ollama_context_window": "32768"})
    assert apply_provider_values(settings, saved).ollama_context_window == 8192


def test_effective_settings_carry_the_ollama_window(tmp_path: Path) -> None:
    settings = build(tmp_path, "OLLAMA_CONTEXT_WINDOW=8192\n")
    assert compose.settings_to_effective(settings).ollama_context_window == 8192


# ── Descriptor kind ``int`` ──────────────────────────────────────────────


def _entry(summary: dict[str, Any], provider: str) -> dict[str, Any]:
    return next(c for c in summary["connections"] if c["provider"] == provider)


def window_field(summary: dict[str, Any]) -> dict[str, Any]:
    fields = _entry(summary, "ollama")["fields"]
    return next(f for f in fields if f["id"] == "context_window")


def test_summary_carries_an_int_field_for_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = edit.make_settings()
    monkeypatch.setattr(compose, "get_settings", lambda: settings)
    field = window_field(compose.connection_summary())
    assert field["kind"] == "int"
    assert field["label"] == "Context window (tokens)"
    assert (field["min"], field["max"], field["value"]) == (2048, 262144, 16384)
    assert (field["source"], field["locked"]) == ("default", False)


def test_url_fields_have_no_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = edit.make_settings()
    monkeypatch.setattr(compose, "get_settings", lambda: settings)
    for entry in compose.connection_summary()["connections"]:
        for field in entry["fields"]:
            if field["kind"] != "int":
                assert (field["min"], field["max"]) == (None, None)


def test_descriptor_bounds_match_the_settings_bounds() -> None:
    from omrs.config.user_config import INT_KEY_BOUNDS

    spec = next(f for f in registry.describe_all()["ollama"].fields if f.kind == "int")
    assert (spec.minimum, spec.maximum) == INT_KEY_BOUNDS[spec.settings_field]


def test_locked_int_field_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = edit.make_settings(
        ollama_context_window=8192, explicit=frozenset({"ollama_context_window"})
    )
    monkeypatch.setattr(compose, "get_settings", lambda: settings)
    field = window_field(compose.connection_summary())
    assert (field["value"], field["source"], field["locked"]) == (8192, "env", True)
    assert "OLLAMA_CONTEXT_WINDOW" in field["lock_reason"]


# ── Routes ───────────────────────────────────────────────────────────────


def window(h: Any, provider: str = "ollama") -> dict[str, Any]:
    return h.field(provider, "context_window")


def test_save_applies_live_and_reset_returns_to_default(harness: Any) -> None:
    with harness() as h:
        assert h.put("ollama", {"context_window": 32768}).status_code == 200
        assert (window(h)["value"], window(h)["source"]) == (32768, "config-file")
        assert '"ollama_context_window": 32768' in h.file_text()
        assert h.engines[0]._effective_settings.ollama_context_window == 32768
        assert h.put("ollama", {"context_window": None}).status_code == 200
        assert (window(h)["value"], window(h)["source"]) == (16384, "default")
        assert "ollama_context_window" not in h.file_text()
        assert h.engines[0]._effective_settings.ollama_context_window == 16384


def test_a_numeric_string_is_accepted(harness: Any) -> None:
    with harness() as h:
        assert h.put("ollama", {"context_window": "8192"}).status_code == 200
        assert window(h)["value"] == 8192


@pytest.mark.parametrize("value", [2048, 262144])
def test_range_edges_are_accepted(harness: Any, value: int) -> None:
    with harness() as h:
        assert h.put("ollama", {"context_window": value}).status_code == 200


@pytest.mark.parametrize("value", [1024, 2047, 262145, 300000, "abc", 16384.5, "16384.5", "", True])
def test_bad_values_are_400_and_save_nothing(harness: Any, value: Any) -> None:
    with harness() as h:
        response = h.put("ollama", {"context_window": value})
        assert response.status_code == 400, response.text
        message = response.json()["message"]
        assert "2048" in message and "262144" in message
        assert str(value) not in message or str(value) in ("", "True")
        assert (window(h)["value"], window(h)["source"]) == (16384, "default")


def test_environment_value_is_409_and_names_the_variable(harness: Any) -> None:
    with harness(ollama_context_window=8192, explicit=frozenset({"ollama_context_window"})) as h:
        response = h.put("ollama", {"context_window": 32768})
        assert response.status_code == 409
        assert "OLLAMA_CONTEXT_WINDOW" in response.json()["message"]
        assert window(h)["value"] == 8192


def test_bearer_cannot_save_a_window(harness: Any) -> None:
    with harness() as h:
        h.client.cookies.clear()
        header = edit.bearer(h.policy, "read", "graph", "run")
        response = h.client.put(
            "/v1/connections/ollama", json={"fields": {"context_window": 4096}}, headers=header
        )
        assert response.status_code == 403


def test_the_engine_still_refuses_embedding_changes(
    effective_settings: Any,
) -> None:
    from tests.unit.test_engine_pipelines_support import build_engine

    engine = build_engine(effective_settings())
    engine.use_provider_settings(effective_settings(ollama_context_window=32768))
    assert engine._effective_settings.ollama_context_window == 32768
    with pytest.raises(ValueError, match="embed_model"):
        engine.use_provider_settings(
            effective_settings(ollama_context_window=4096, embed_model="other-model")
        )


# ── A fake provider with an integer field needs no change outside the descriptor ──


def _fake_descriptor() -> ConnectionDescriptor:
    return ConnectionDescriptor(
        display_name="Fake",
        locality="local",
        requires_module="json",
        extra=None,
        fields=(
            ConnectionField(
                "context_window",
                "Window",
                "int",
                "llamacpp_context_window",
                "LLAMACPP_CONTEXT_WINDOW",
                minimum=2048,
                maximum=262144,
            ),
        ),
        read_only=lambda s: [],
        test_targets=lambda s: ConnectionTarget(()),
        models_target=lambda s: ConnectionTarget(()),
        parse_models=lambda payload: [],
    )


def test_fake_provider_with_an_int_field_gets_a_card_and_a_save_route(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = registry.describe_all
    monkeypatch.setattr(registry, "describe_all", lambda: {**real(), "fakeint": _fake_descriptor()})
    with harness() as h:
        field = h.field("fakeint", "context_window")
        assert (field["kind"], field["min"], field["max"], field["value"]) == (
            "int",
            2048,
            262144,
            16384,
        )
        assert h.put("fakeint", {"context_window": 4096}).status_code == 200
        assert h.field("fakeint", "context_window")["value"] == 4096
        assert h.put("fakeint", {"context_window": 5}).status_code == 400


# ── Program and model of the managed llama.cpp server ────────────────────


@pytest.mark.parametrize("field", list(TEXT_FIELDS))
def test_server_text_fields_default_to_empty(tmp_path: Path, field: str) -> None:
    settings = build(tmp_path)
    assert getattr(settings, field) == ""
    assert field not in settings.provider_explicit


@pytest.mark.parametrize(("field", "variable"), list(TEXT_FIELDS.items()))
def test_server_text_fields_take_the_environment_and_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str, variable: str
) -> None:
    monkeypatch.setenv(variable, "/from/env")
    settings = build(tmp_path)
    assert getattr(settings, field) == "/from/env"
    assert locked_fields(settings, settings.provider_explicit)[field] == "environment"


@pytest.mark.parametrize(("field", "variable"), list(TEXT_FIELDS.items()))
def test_server_text_fields_take_dotenv_and_lock(tmp_path: Path, field: str, variable: str) -> None:
    settings = build(tmp_path, f"{variable}=/from/dotenv\n")
    assert getattr(settings, field) == "/from/dotenv"
    assert field in settings.provider_explicit


@pytest.mark.parametrize("field", list(TEXT_FIELDS))
def test_server_text_fields_take_the_config_file_and_do_not_lock(
    folder: Path, tmp_path: Path, field: str
) -> None:
    (folder / "omrs.jsonc").write_text(f'{{"{field}": "/from/file"}}', encoding="utf-8")
    settings = build(tmp_path)
    assert getattr(settings, field) == "/from/file"
    assert field in settings.config_file_fields
    assert field not in locked_fields(settings, settings.provider_explicit)


def test_a_saved_server_value_applies_unless_locked(tmp_path: Path) -> None:
    saved = ProviderValues(values={"llamacpp_server_model": "org/name:Q8_0"})
    assert apply_provider_values(build(tmp_path), saved).llamacpp_server_model == "org/name:Q8_0"
    locked = build(tmp_path, "LLAMACPP_SERVER_MODEL=/env/m.gguf\n")
    assert apply_provider_values(locked, saved).llamacpp_server_model == "/env/m.gguf"


def test_server_values_never_reach_effective_settings(tmp_path: Path) -> None:
    effective = compose.settings_to_effective(build(tmp_path, "LLAMACPP_CONTEXT_WINDOW=4096\n"))
    assert not hasattr(effective, "llamacpp_server_binary")
    assert not hasattr(effective, "llamacpp_context_window")


# ── llama.cpp idle sleep (task 17.9) ─────────────────────────────────────

IDLE = "llamacpp_idle_sleep_seconds"


def test_idle_sleep_defaults_to_300(tmp_path: Path) -> None:
    settings = build(tmp_path)
    assert getattr(settings, IDLE) == 300
    assert IDLE not in settings.provider_explicit


def test_idle_sleep_from_the_environment_locks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LLAMACPP_IDLE_SLEEP_SECONDS", "0")
    settings = build(tmp_path)
    assert getattr(settings, IDLE) == 0
    assert locked_fields(settings, settings.provider_explicit)[IDLE] == "environment"


def test_idle_sleep_from_the_config_file_applies_and_does_not_lock(
    folder: Path, tmp_path: Path
) -> None:
    (folder / "omrs.jsonc").write_text('{"llamacpp_idle_sleep_seconds": 900}', encoding="utf-8")
    settings = build(tmp_path)
    assert getattr(settings, IDLE) == 900
    assert IDLE in settings.config_file_fields
    assert IDLE not in locked_fields(settings, settings.provider_explicit)


@pytest.mark.parametrize("value", ["-1", "86401", "soon"])
def test_a_bad_idle_sleep_in_the_environment_fails_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    monkeypatch.setenv("LLAMACPP_IDLE_SLEEP_SECONDS", value)
    with pytest.raises(ValidationError):
        build(tmp_path)
