"""``compose_providers``: saved provider values over resolved settings (tasks 3.3, 3.4)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from omrg import compose
from omrg.compose_providers import (
    ProviderValues,
    apply_provider_values,
    locked_fields,
)
from omrg.config import Settings

SECRET = "sk-or-v1-SECRETVALUE0123456789"  # noqa: S105 - fake key


def make_settings(**extra: Any) -> Settings:
    return Settings(_env_file=None, **extra)


def test_compose_re_exports_the_names() -> None:
    assert compose.ProviderValues is ProviderValues
    assert compose.apply_provider_values is apply_provider_values


def test_saved_values_replace_defaults() -> None:
    base = make_settings(embed_provider="openrouter", answer={"provider": "ollama"})
    values = ProviderValues(
        {
            "ollama_base_url": "http://gpu-box.local:11434",
            "llamacpp_chat_url": "http://gpu-box.local:8081/v1",
            "openrouter_api_key": SECRET,
            "answer.provider": "openrouter",
            "answer.model": "openai/gpt-4o-mini",
        }
    )
    result = apply_provider_values(base, values, frozenset())
    assert result.ollama_base_url == "http://gpu-box.local:11434"
    assert result.llamacpp_chat_url == "http://gpu-box.local:8081/v1"
    assert result.openrouter_api_key == SECRET
    assert (result.answer.provider, result.answer.model) == ("openrouter", "openai/gpt-4o-mini")


def test_the_input_settings_are_not_changed() -> None:
    base = make_settings(embed_provider="openrouter")
    before = base.model_copy(deep=True)
    apply_provider_values(base, ProviderValues({"ollama_base_url": "http://x:1"}), frozenset())
    assert base == before


def test_environment_value_wins_and_locks() -> None:
    base = make_settings(embed_provider="openrouter", llamacpp_chat_url="http://env:8081/v1")
    values = ProviderValues({"llamacpp_chat_url": "http://saved:8081/v1"})
    result = apply_provider_values(base, values, frozenset({"llamacpp_chat_url"}))
    assert result.llamacpp_chat_url == "http://env:8081/v1"
    assert locked_fields(base, frozenset({"llamacpp_chat_url"})) == {
        "llamacpp_chat_url": "environment"
    }


def test_explicit_defaults_to_the_settings_record() -> None:
    base = make_settings(embed_provider="openrouter")
    object.__setattr__(base, "provider_explicit", frozenset({"answer.model"}))
    values = ProviderValues({"answer.model": "saved", "answer.provider": "openrouter"})
    result = apply_provider_values(base, values)
    assert result.answer.model == base.answer.model
    assert result.answer.provider == base.answer.provider


def test_blank_saved_value_is_ignored() -> None:
    base = make_settings(embed_provider="openrouter", openrouter_api_key="from-env")
    result = apply_provider_values(base, ProviderValues({"openrouter_api_key": "  "}), frozenset())
    assert result.openrouter_api_key == "from-env"


def test_unknown_key_is_ignored() -> None:
    base = make_settings(embed_provider="openrouter")
    result = apply_provider_values(base, ProviderValues({"embed_model": "other"}), frozenset())
    assert result.embed_model == base.embed_model


def test_ollama_address_is_locked_while_embeddings_use_ollama() -> None:
    base = make_settings(embed_provider="local", local_backend="ollama", embed_model="nomic")
    values = ProviderValues({"ollama_base_url": "http://other:11434"})
    result = apply_provider_values(base, values, frozenset())
    assert result.ollama_base_url == base.ollama_base_url
    assert locked_fields(base, frozenset()) == {"ollama_base_url": "embeddings"}


def test_ollama_address_applies_when_embeddings_use_another_provider() -> None:
    base = make_settings(embed_provider="openrouter")
    assert locked_fields(base, frozenset()) == {}
    values = ProviderValues({"ollama_base_url": "http://other:11434"})
    assert apply_provider_values(base, values, frozenset()).ollama_base_url == "http://other:11434"


def test_environment_lock_wins_over_the_embeddings_reason() -> None:
    base = make_settings(embed_provider="local", local_backend="ollama", embed_model="nomic")
    assert locked_fields(base, frozenset({"ollama_base_url"})) == {"ollama_base_url": "environment"}


def test_repr_hides_every_value() -> None:
    values = ProviderValues({"openrouter_api_key": SECRET, "ollama_base_url": "http://h:1"})
    assert SECRET not in repr(values)
    assert "http://h:1" not in repr(values)
    assert "openrouter_api_key" in repr(values)


def test_provider_effective_settings_applies_the_source_to_the_resolved_settings(
    monkeypatch,
) -> None:
    base = make_settings(embed_provider="openrouter")
    monkeypatch.setattr(compose, "get_settings", lambda: base)
    effective = compose.provider_effective_settings(
        lambda: ProviderValues({"answer.model": "saved-model"})
    )
    assert effective.answer.model == "saved-model"
    assert effective.ollama_base_url == base.ollama_base_url


def test_chat_choice_locks_as_one_unit_when_only_the_model_is_explicit() -> None:
    base = make_settings(embed_provider="openrouter")
    explicit = frozenset({"answer.model"})
    assert locked_fields(base, explicit) == {
        "answer.model": "environment",
        "answer.provider": "environment",
    }
    values = ProviderValues({"answer.provider": "openrouter", "answer.model": "saved"})
    result = apply_provider_values(base, values, explicit)
    assert (result.answer.provider, result.answer.model) == (
        base.answer.provider,
        base.answer.model,
    )


def test_chat_choice_locks_as_one_unit_when_only_the_provider_is_explicit() -> None:
    base = make_settings(embed_provider="openrouter")
    explicit = frozenset({"answer.provider"})
    assert set(locked_fields(base, explicit)) == {"answer.provider", "answer.model"}


class _Catalogue:
    def __init__(self, *records: dict[str, Any]) -> None:
        self.records = list(records)

    def list_profiles(self) -> list[dict[str, Any]]:
        return self.records


def test_profiles_use_ollama_reads_the_catalogue() -> None:
    from omrg.core.profiles.catalogue import uses_ollama_embeddings as profiles_use_ollama

    assert profiles_use_ollama(None) is False
    assert profiles_use_ollama(_Catalogue({"profile_id": "a"})) is False
    other = {"embed_provider": "openrouter", "embed_model": "m"}
    assert profiles_use_ollama(_Catalogue(other)) is False
    mine = {"embed_provider": "ollama", "embed_model": "nomic"}
    assert profiles_use_ollama(_Catalogue(other, mine)) is True


def test_ollama_address_locks_when_a_profile_uses_ollama_embeddings() -> None:
    base = make_settings(embed_provider="openrouter")
    assert locked_fields(base, frozenset(), profiles_ollama=True) == {
        "ollama_base_url": "embeddings"
    }
    values = ProviderValues({"ollama_base_url": "http://other:11434"})
    result = apply_provider_values(base, values, frozenset(), profiles_ollama=True)
    assert result.ollama_base_url == base.ollama_base_url


# ── Locks (move-settings-to-config-file, task 2.5) ────────────────────────


def test_a_config_file_value_does_not_lock() -> None:
    base = make_settings(embed_provider="openrouter")
    object.__setattr__(base, "config_file_fields", frozenset({"llamacpp_chat_url"}))
    object.__setattr__(base, "setting_sources", {"llamacpp_chat_url": "config-file"})
    assert "llamacpp_chat_url" not in locked_fields(base, frozenset())
    saved = ProviderValues({"llamacpp_chat_url": "http://saved:8081/v1"})
    assert apply_provider_values(base, saved).llamacpp_chat_url == "http://saved:8081/v1"


def test_the_chat_choice_locks_as_a_unit_when_the_environment_sets_one() -> None:
    base = make_settings(embed_provider="openrouter")
    assert locked_fields(base, frozenset({"answer.model"})) == {
        "answer.provider": "environment",
        "answer.model": "environment",
    }


# ── Keychain references (task 3.3) ────────────────────────────────────────


class FakeSecret:
    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value


class FakeKeychain:
    def __init__(self, entries: dict[str, str] | None = None, *, available: bool = True) -> None:
        self.entries = entries or {}
        self.available = available
        self.reads: list[str] = []

    def read(self, provider: str) -> FakeSecret | None:
        self.reads.append(provider)
        return FakeSecret(self.entries[provider]) if provider in self.entries else None


def settings_with_reference(provider: str = "openrouter") -> Settings:
    base = make_settings(embed_provider="openrouter")
    object.__setattr__(base, "keychain_refs", {"openrouter_api_key": provider})
    return base


def test_a_keychain_reference_resolves_to_the_saved_key() -> None:
    from omrg.compose_providers import resolve_keychain_references

    store = FakeKeychain({"openrouter": SECRET})
    resolved, problems = resolve_keychain_references(settings_with_reference(), store=store)
    assert resolved.openrouter_api_key == SECRET
    assert resolved.setting_sources["openrouter_api_key"] == "keychain"
    assert problems == {}
    assert store.reads == ["openrouter"]


def test_a_missing_keychain_entry_says_so_and_leaves_no_key() -> None:
    from omrg.compose_providers import resolve_keychain_references

    resolved, problems = resolve_keychain_references(
        settings_with_reference(), store=FakeKeychain({})
    )
    assert resolved.openrouter_api_key == ""
    assert problems == {"openrouter": "keychain-missing"}


def test_no_usable_keychain_is_unreadable_and_reads_nothing() -> None:
    from omrg.compose_providers import resolve_keychain_references

    store = FakeKeychain({"openrouter": SECRET}, available=False)
    resolved, problems = resolve_keychain_references(settings_with_reference(), store=store)
    assert resolved.openrouter_api_key == ""
    assert problems == {"openrouter": "keychain-unreadable"}
    assert store.reads == []


def test_a_failing_keychain_call_is_unreadable() -> None:
    from omrg.compose_providers import resolve_keychain_references
    from omrg.integrations.keychain import KeychainUnavailableError

    class Failing(FakeKeychain):
        def read(self, provider: str) -> FakeSecret | None:
            raise KeychainUnavailableError("The system keychain did not answer in time.")

    _, problems = resolve_keychain_references(settings_with_reference(), store=Failing())
    assert problems == {"openrouter": "keychain-unreadable"}


def test_the_input_settings_are_not_changed_by_resolving() -> None:
    from omrg.compose_providers import resolve_keychain_references

    base = settings_with_reference()
    resolve_keychain_references(base, store=FakeKeychain({"openrouter": SECRET}))
    assert base.openrouter_api_key == ""


def test_no_reference_means_no_keychain_and_no_keyring_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A CLI run without ``keychain://`` must not load keyring or build a store."""
    from omrg.compose_providers import resolve_keychain_references
    from omrg.integrations import keychain

    monkeypatch.setitem(sys.modules, "keyring", None)  # an import now raises ImportError

    def boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("a keychain store was built without a reference")

    monkeypatch.setattr(keychain, "KeychainStore", boom)
    base = make_settings(embed_provider="openrouter")
    resolved, problems = resolve_keychain_references(base)
    assert resolved is base
    assert problems == {}


def test_the_default_store_reports_unreadable_when_keyring_cannot_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omrg.compose_providers import resolve_keychain_references

    monkeypatch.setitem(sys.modules, "keyring", None)
    resolved, problems = resolve_keychain_references(settings_with_reference())
    assert resolved.openrouter_api_key == ""
    assert problems == {"openrouter": "keychain-unreadable"}


def test_a_reference_from_the_file_resolves_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI path: omrg.jsonc holds the reference, the resolver reads the keychain."""
    from omrg.compose_providers import resolve_keychain_references

    folder = tmp_path / "omrg-config"
    folder.mkdir()
    (folder / "omrg.jsonc").write_text(
        '{"openrouter_api_key": "keychain://openrouter"}', encoding="utf-8"
    )
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(folder))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    resolved, problems = resolve_keychain_references(
        settings, store=FakeKeychain({"openrouter": SECRET})
    )
    assert (resolved.openrouter_api_key, problems) == (SECRET, {})


# ── compose.get_settings resolves references for the CLI and stdio (task 5.3) ─


def _reference_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    folder = tmp_path / "omrg-config"
    folder.mkdir()
    (folder / "omrg.jsonc").write_text(text, encoding="utf-8")
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(folder))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("omrg.config._settings", None)


def test_compose_get_settings_resolves_a_keychain_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrg import compose
    from omrg.integrations import keychain

    _reference_folder(tmp_path, monkeypatch, '{"openrouter_api_key": "keychain://openrouter"}')
    store = FakeKeychain({"openrouter": SECRET})
    monkeypatch.setattr(keychain, "KeychainStore", lambda: store)
    first = compose.get_settings()
    assert first.openrouter_api_key == SECRET
    assert first.setting_sources["openrouter_api_key"] == "keychain"
    assert compose.get_settings() is first  # resolved once for one launch
    assert store.reads == ["openrouter"]
    monkeypatch.setattr("omrg.config._settings", None)


def test_compose_get_settings_without_a_reference_never_loads_the_keychain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrg import compose

    _reference_folder(tmp_path, monkeypatch, '{"llamacpp_chat_url": "http://gpu:8081/v1"}')
    monkeypatch.delitem(sys.modules, "omrg.integrations.keychain", raising=False)
    monkeypatch.setitem(sys.modules, "keyring", None)  # an import now raises ImportError
    settings = compose.get_settings()
    assert settings.llamacpp_chat_url == "http://gpu:8081/v1"
    assert "omrg.integrations.keychain" not in sys.modules
    monkeypatch.setattr("omrg.config._settings", None)


def test_compose_get_settings_logs_a_missing_entry_by_provider_name_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from omrg import compose
    from omrg.integrations import keychain

    _reference_folder(tmp_path, monkeypatch, '{"openrouter_api_key": "keychain://openrouter"}')
    monkeypatch.setattr(keychain, "KeychainStore", lambda: FakeKeychain({}))
    with caplog.at_level("WARNING"):
        settings = compose.get_settings()
    assert settings.openrouter_api_key == ""
    assert "openrouter" in caplog.text and "keychain-missing" in caplog.text
    monkeypatch.setattr("omrg.config._settings", None)


# ── provider_values_from_file: the file over the launch settings (D7) ─────


def _file(tmp_path: Path, text: str) -> Any:
    from omrg.config.settings_file import read_settings_file

    folder = tmp_path / "cfg"
    folder.mkdir(exist_ok=True)
    (folder / "omrg.jsonc").write_text(text, encoding="utf-8")
    return read_settings_file(folder)


def test_values_from_the_file_override_the_launch_settings(tmp_path: Path) -> None:
    from omrg.compose_providers import provider_values_from_file

    text = '{"llamacpp_chat_url": "http://gpu:1/v1", "answer": {"model": "m"}}'
    values = provider_values_from_file(make_settings(), _file(tmp_path, text), None)
    assert values.values["llamacpp_chat_url"] == "http://gpu:1/v1"
    assert values.values["answer.model"] == "m"
    assert values.sources == {"llamacpp_chat_url": "config-file", "answer.model": "config-file"}


def test_a_field_the_file_dropped_goes_back_to_the_code_default(tmp_path: Path) -> None:
    from omrg.compose_providers import provider_values_from_file

    base = make_settings(llamacpp_chat_url="http://old:1/v1")
    object.__setattr__(base, "setting_sources", {"llamacpp_chat_url": "config-file"})
    values = provider_values_from_file(base, _file(tmp_path, "{}"), None)
    default = Settings.model_fields["llamacpp_chat_url"].default
    assert values.values["llamacpp_chat_url"] == default
    assert apply_provider_values(base, values).llamacpp_chat_url == default


def test_a_key_the_file_dropped_is_unset(tmp_path: Path) -> None:
    from omrg.compose_providers import provider_values_from_file

    base = make_settings(openrouter_api_key=SECRET)
    object.__setattr__(base, "setting_sources", {"openrouter_api_key": "keychain"})
    values = provider_values_from_file(base, _file(tmp_path, "{}"), None)
    assert "openrouter_api_key" in values.unset
    applied = apply_provider_values(base, values)
    assert applied.openrouter_api_key == ""
    assert "openrouter_api_key" not in applied.setting_sources


def test_an_environment_field_is_left_to_the_environment(tmp_path: Path) -> None:
    from omrg.compose_providers import provider_values_from_file

    base = make_settings()
    object.__setattr__(base, "provider_explicit", frozenset({"llamacpp_chat_url"}))
    text = '{"llamacpp_chat_url": "http://x:1/v1"}'
    values = provider_values_from_file(base, _file(tmp_path, text), None)
    assert "llamacpp_chat_url" not in values.values
    assert apply_provider_values(base, values).llamacpp_chat_url == base.llamacpp_chat_url


def test_a_keychain_reference_resolves_through_the_given_store(tmp_path: Path) -> None:
    from omrg.compose_providers import provider_values_from_file

    store = FakeKeychain({"openrouter": SECRET})
    values = provider_values_from_file(
        make_settings(), _file(tmp_path, '{"openrouter_api_key": "keychain://openrouter"}'), store
    )
    assert values.values["openrouter_api_key"] == SECRET
    assert values.sources["openrouter_api_key"] == "keychain"
    assert values.keychain_available is True and values.key_problems == {}
    assert SECRET not in repr(values)


def test_a_reference_with_no_keychain_is_unreadable_and_unset(tmp_path: Path) -> None:
    from omrg.compose_providers import provider_values_from_file

    values = provider_values_from_file(
        make_settings(), _file(tmp_path, '{"openrouter_api_key": "keychain://openrouter"}'), None
    )
    assert values.key_problems == {"openrouter": "keychain-unreadable"}
    assert "openrouter_api_key" in values.unset and values.keychain_available is False


def test_the_chat_pair_locks_together(tmp_path: Path) -> None:
    from omrg.compose_providers import provider_values_from_file

    base = make_settings()
    object.__setattr__(base, "provider_explicit", frozenset({"answer.model"}))
    text = '{"answer": {"provider": "llamacpp"}}'
    values = provider_values_from_file(base, _file(tmp_path, text), None)
    assert "answer.provider" not in values.values
