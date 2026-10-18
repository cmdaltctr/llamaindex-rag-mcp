"""Provider and chat keys in the workspace settings table (design D1, D6; tasks 4.1, 4.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository
from omrg.integrations.workspace_sqlite.settings import (
    CHAT_MODEL,
    CHAT_PROVIDER,
    UnknownSettingError,
    WorkspaceSettings,
    provider_key,
)


@pytest.fixture
def settings(tmp_path: Path) -> WorkspaceSettings:
    path = tmp_path / "ws" / "workspace.db"
    SqliteWorkspaceRepository(path)
    return WorkspaceSettings(path)


def test_chat_choice_round_trips(settings: WorkspaceSettings) -> None:
    assert (CHAT_PROVIDER, CHAT_MODEL) == ("chat.provider", "chat.model")
    assert settings.get_chat_provider() is None and settings.get_chat_model() is None
    settings.set_chat_choice("openrouter", "anthropic/claude-sonnet-4")
    assert settings.get_chat_provider() == "openrouter"
    assert settings.get_chat_model() == "anthropic/claude-sonnet-4"
    settings.set_chat_choice(None, None)
    assert settings.get_chat_provider() is None and settings.get_chat_model() is None


def test_provider_fields_round_trip(settings: WorkspaceSettings) -> None:
    key = provider_key("ollama", "base_url")
    assert key == "provider.ollama.base_url"
    settings.set(key, "http://localhost:11434")
    assert settings.get(key) == "http://localhost:11434"
    assert settings.get_valid(key) == "http://localhost:11434"


def test_key_saved_at_reads_back_as_a_timestamp(settings: WorkspaceSettings) -> None:
    key = provider_key("openrouter", "key_saved_at")
    assert settings.get_key_saved_at("openrouter") is None
    settings.set_key_saved_at("openrouter", "2026-10-18T10:00:00+00:00")
    assert settings.get(key) == "2026-10-18T10:00:00+00:00"
    assert settings.get_key_saved_at("openrouter") == "2026-10-18T10:00:00+00:00"
    settings.set_key_saved_at("openrouter", None)
    assert settings.get_key_saved_at("openrouter") is None


@pytest.mark.parametrize(
    "key",
    [
        "chat.other",
        "chat",
        "provider.openrouter",
        "provider..key_saved_at",
        "provider.Open Router.key_saved_at",
        "provider.openrouter.Key",
        "provider.openrouter.a.b",
        "provider.openrouter.api_key ",
        "Provider.openrouter.key_saved_at",
        "other.openrouter.base_url",
    ],
)
def test_unknown_keys_raise(settings: WorkspaceSettings, key: str) -> None:
    with pytest.raises(UnknownSettingError):
        settings.get(key)
    with pytest.raises(UnknownSettingError):
        settings.set(key, "x")


@pytest.mark.parametrize("bad", ["", "   ", "line\nbreak", "x" * 5000, "\x00"])
def test_a_damaged_chat_value_reads_unset(settings: WorkspaceSettings, bad: str) -> None:
    settings.set(CHAT_PROVIDER, bad)
    settings.set(CHAT_MODEL, bad)
    assert settings.get_chat_provider() is None
    assert settings.get_chat_model() is None


@pytest.mark.parametrize("bad", ["not a date", "", "2026-13-45", "x" * 500])
def test_a_damaged_timestamp_reads_unset(settings: WorkspaceSettings, bad: str) -> None:
    settings.set("provider.openrouter.key_saved_at", bad)
    assert settings.get_key_saved_at("openrouter") is None


def test_a_damaged_provider_field_reads_unset(settings: WorkspaceSettings) -> None:
    key = "provider.ollama.base_url"
    settings.set(key, "bad\nvalue")
    assert settings.get_valid(key) is None


def test_set_chat_choice_refuses_a_damaged_value(settings: WorkspaceSettings) -> None:
    with pytest.raises(ValueError):
        settings.set_chat_choice("open router", "m")


@pytest.mark.parametrize(
    ("provider", "field"),
    [
        ("OpenRouter", "key_saved_at"),
        ("open router", "key_saved_at"),
        ("openrouter", "Key"),
        ("openrouter", ""),
        ("../x", "key_saved_at"),
    ],
)
def test_provider_key_refuses_bad_names(provider: str, field: str) -> None:
    from omrg.integrations.workspace_sqlite.settings import provider_key

    with pytest.raises(UnknownSettingError):
        provider_key(provider, field)


def test_provider_key_builds_the_allowed_key() -> None:
    from omrg.integrations.workspace_sqlite.settings import provider_key

    assert provider_key("openrouter", "key_saved_at") == "provider.openrouter.key_saved_at"


@pytest.mark.parametrize(
    "field", ["api_key", "token", "password", "secret", "authorization", "key"]
)
def test_a_secret_looking_field_is_never_a_known_key(
    settings: WorkspaceSettings, field: str
) -> None:
    from omrg.integrations.workspace_sqlite.settings import is_known_key

    assert is_known_key(f"provider.openrouter.{field}") is False
    with pytest.raises(UnknownSettingError):
        provider_key("openrouter", field)
    with pytest.raises(UnknownSettingError):
        settings.set(f"provider.openrouter.{field}", "sk-or-v1-FAKE")


def test_stored_field_ids_match_the_provider_descriptors() -> None:
    """Every url field a descriptor declares is storable; no secret field is."""
    from omrg.core.providers.llm.registry import describe_all
    from omrg.integrations.workspace_sqlite.settings import (
        KEY_SAVED_AT,
        PROVIDER_FIELD_IDS,
    )

    descriptors = describe_all()
    assert descriptors
    url_ids = {f.id for d in descriptors.values() for f in d.fields if f.kind == "url"}
    secret_ids = {f.id for d in descriptors.values() for f in d.fields if f.kind == "secret"}
    assert PROVIDER_FIELD_IDS == url_ids | {KEY_SAVED_AT}
    assert not secret_ids & PROVIDER_FIELD_IDS
