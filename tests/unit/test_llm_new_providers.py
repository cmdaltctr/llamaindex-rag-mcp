"""The ``openai_compatible`` and ``anthropic`` Chat providers (design D5).

Each provider is one module with ``build()`` and a ``CONNECTION`` descriptor,
registered with one line. The plumbing around them (value sources, live
apply, redaction, readiness) reads the descriptors, so a further provider
needs no change there. Keys in these tests are fake.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest
from tests.unit.test_connection_summary import make_settings

from omrg import compose
from omrg.compose_providers import ProviderValues, apply_provider_values, locked_fields
from omrg.config import Settings
from omrg.config.provider_sources import PROVIDER_FIELDS
from omrg.core.providers.llm import registry
from omrg.core.providers.llm.connection import (
    ConnectionDescriptor,
    ConnectionField,
    ConnectionTarget,
)
from omrg.core.settings import PROVIDER_SECRET_FIELDS, provider_secret_values
from omrg.core.vectordb.identity import RedactionSecrets

ANT_KEY = "sk-ant-api03-AAAA1111BBBB2222CCCC3333"  # gitleaks:allow
ANT_KEY_2 = "sk-ant-api03-ZZZZ9999YYYY8888XXXX7777"  # gitleaks:allow
OAI_KEY = "sk-oai-0123456789abcdefABCDEF"  # gitleaks:allow
OAI_URL = "http://localhost:1234/v1"


def descriptor(name: str) -> ConnectionDescriptor:
    return registry.describe_all()[name]


# ── Descriptor shape and registry order ───────────────────────────────────


def test_registry_order_and_display_names() -> None:
    described = registry.describe_all()
    assert list(described) == ["ollama", "llamacpp", "openrouter", "openai_compatible", "anthropic"]
    assert described["openai_compatible"].display_name == "OpenAI-compatible"
    assert described["anthropic"].display_name == "Anthropic"
    assert described["openai_compatible"].locality == "cloud"
    assert described["anthropic"].locality == "cloud"


def test_extras_and_modules() -> None:
    oai, ant = descriptor("openai_compatible"), descriptor("anthropic")
    assert (oai.requires_module, oai.extra) == ("llama_index.llms.openai_like", None)
    assert (ant.requires_module, ant.extra) == ("llama_index.llms.anthropic", "anthropic")
    assert registry._PROVIDER_EXTRAS["anthropic"] == "anthropic"
    assert "openai_compatible" not in registry._PROVIDER_EXTRAS


def test_install_hint_names_the_anthropic_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(name: str) -> Any:
        raise ImportError("no module")

    monkeypatch.setattr(registry.importlib, "import_module", fail)
    registry._cache.pop("anthropic", None)
    with pytest.raises(ImportError, match=r"uv sync --extra anthropic"):
        registry.get("anthropic")


def test_fields() -> None:
    oai = {f.id: f for f in descriptor("openai_compatible").fields}
    assert oai["base_url"] == ConnectionField(
        "base_url",
        "Address",
        "url",
        "openai_compatible_base_url",
        "OPENAI_COMPATIBLE_BASE_URL",
    )
    key = oai["api_key"]
    assert (key.kind, key.settings_field, key.env_var) == (
        "secret",
        "openai_compatible_api_key",
        "OPENAI_COMPATIBLE_API_KEY",
    )
    assert key.required is False
    (ant_key,) = descriptor("anthropic").fields
    assert (ant_key.id, ant_key.kind, ant_key.settings_field, ant_key.env_var) == (
        "api_key",
        "secret",
        "anthropic_api_key",
        "ANTHROPIC_API_KEY",
    )
    assert ant_key.required is True


def test_a_field_is_required_unless_marked_optional() -> None:
    assert ConnectionField("k", "Key", "secret", "anthropic_api_key", "X").required is True


def test_read_only_rows() -> None:
    settings = make_settings()
    assert [(r.label, r.value) for r in descriptor("anthropic").read_only(settings)] == [
        ("Address", "https://api.anthropic.com")
    ]


def test_openai_compatible_default_address() -> None:
    assert Settings(_env_file=None).openai_compatible_base_url == "https://api.openai.com/v1"
    assert Settings(_env_file=None).openai_compatible_api_key == ""
    assert Settings(_env_file=None).anthropic_api_key == ""


# ── Test and model-list targets ───────────────────────────────────────────


def test_openai_compatible_target_sends_a_bearer_only_with_a_key() -> None:
    keyed = descriptor("openai_compatible").test_targets(
        make_settings(
            openai_compatible_base_url="http://h:1/v1/", openai_compatible_api_key=OAI_KEY
        )
    )
    assert keyed.urls == ("http://h:1/v1/models",)
    assert keyed.headers == {"Authorization": f"Bearer {OAI_KEY}"}
    assert OAI_KEY not in repr(keyed)
    bare = descriptor("openai_compatible").test_targets(
        make_settings(openai_compatible_base_url=OAI_URL, openai_compatible_api_key="  ")
    )
    assert bare == ConnectionTarget((f"{OAI_URL}/models",))
    assert bare.headers == {}


def test_openai_compatible_models_target_matches_the_test_target() -> None:
    settings = make_settings(openai_compatible_base_url=OAI_URL, openai_compatible_api_key=OAI_KEY)
    d = descriptor("openai_compatible")
    assert d.models_target(settings) == d.test_targets(settings)


def test_openai_compatible_blank_address_has_no_target() -> None:
    target = descriptor("openai_compatible").test_targets(
        make_settings(openai_compatible_base_url="  ")
    )
    assert target.urls == ()


def test_the_openai_compatible_key_goes_only_to_its_own_address() -> None:
    settings = make_settings(
        openai_compatible_base_url=OAI_URL,
        openai_compatible_api_key=OAI_KEY,
        openrouter_api_key="sk-or-v1-OTHERKEY0123456789",  # gitleaks:allow
        ollama_base_url="http://ollama.test:11434",
    )
    for name, d in registry.describe_all().items():
        target = d.test_targets(settings)
        sent_key = any(OAI_KEY in v for v in target.headers.values())
        assert sent_key is (name == "openai_compatible")
        if name == "openai_compatible":
            assert all(url.startswith(OAI_URL) for url in target.urls)


def test_anthropic_target_uses_the_fixed_address_and_two_headers() -> None:
    target = descriptor("anthropic").test_targets(make_settings(anthropic_api_key=ANT_KEY))
    assert target.urls == ("https://api.anthropic.com/v1/models",)
    assert target.headers == {"x-api-key": ANT_KEY, "anthropic-version": "2023-06-01"}
    assert ANT_KEY not in repr(target)
    assert descriptor("anthropic").models_target(make_settings(anthropic_api_key=ANT_KEY)) == target


def test_anthropic_without_a_key_has_no_target() -> None:
    d = descriptor("anthropic")
    assert d.test_targets(make_settings(anthropic_api_key="")) == ConnectionTarget(())
    assert d.models_target(make_settings(anthropic_api_key="  ")) == ConnectionTarget(())


@pytest.mark.parametrize("provider", ["openai_compatible", "anthropic"])
def test_models_come_from_data_id(provider: str) -> None:
    parse = descriptor(provider).parse_models
    assert parse({"data": [{"id": "m1"}, {"id": "m2"}, {"x": 1}]}) == ["m1", "m2"]
    for bad in (None, [], "t", {}, {"data": 3}, {"data": [{"id": 5}]}):
        assert parse(bad) == []


# ── build() ───────────────────────────────────────────────────────────────


def test_openai_compatible_build_uses_the_saved_address_key_and_model() -> None:
    settings = make_settings(openai_compatible_base_url=OAI_URL, openai_compatible_api_key=OAI_KEY)
    llm = registry.get("openai_compatible")(settings, timeout=7.0, answer_model="m-x")
    assert (llm.model, llm.api_base, llm.api_key) == ("m-x", OAI_URL, OAI_KEY)
    assert llm.is_chat_model is True
    assert llm.timeout == 7.0


def test_openai_compatible_build_works_without_a_key() -> None:
    llm = registry.get("openai_compatible")(make_settings(), answer_model="m-x")
    assert llm.api_key  # a placeholder, the client refuses an empty key
    assert llm.timeout == make_settings().metadata.classify_timeout


def test_openai_compatible_build_needs_a_model() -> None:
    with pytest.raises(ValueError, match="model"):
        registry.get("openai_compatible")(make_settings())


def test_anthropic_build_passes_model_key_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stub class stands in for the optional package, so the test needs no extra."""
    seen: dict[str, Any] = {}

    class StubAnthropic:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    stub = types.ModuleType("llama_index.llms.anthropic")
    stub.Anthropic = StubAnthropic  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_index.llms.anthropic", stub)
    registry.get("anthropic")(
        make_settings(anthropic_api_key=ANT_KEY), timeout=9.0, answer_model="claude-x"
    )
    assert seen == {"model": "claude-x", "api_key": ANT_KEY, "timeout": 9.0}


def test_anthropic_build_needs_a_model() -> None:
    with pytest.raises(ValueError, match="model"):
        registry.get("anthropic")(make_settings(anthropic_api_key=ANT_KEY))


# ── Value sources and locking ─────────────────────────────────────────────

NEW_FIELDS = {
    "openai_compatible_base_url": "OPENAI_COMPATIBLE_BASE_URL",
    "openai_compatible_api_key": "OPENAI_COMPATIBLE_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
}


def test_provider_fields_match_the_descriptors() -> None:
    """The static field list the config layer uses equals what the descriptors declare."""
    declared = {f.settings_field for d in registry.describe_all().values() for f in d.fields}
    assert set(PROVIDER_FIELDS) == declared | {"answer.provider", "answer.model"}
    secrets = {
        f.settings_field
        for d in registry.describe_all().values()
        for f in d.fields
        if f.kind == "secret"
    }
    assert set(PROVIDER_SECRET_FIELDS) == secrets


@pytest.mark.parametrize(("field", "variable"), list(NEW_FIELDS.items()))
def test_environment_locks_each_new_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, field: str, variable: str
) -> None:
    for name in (*NEW_FIELDS.values(), "OPENROUTER_API_KEY", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)  # the shell may hold real values
    monkeypatch.setenv(variable, "value-from-env")
    settings = Settings(_env_file=tmp_path / "absent.env")
    assert settings.provider_explicit == frozenset({field})
    assert locked_fields(settings, settings.provider_explicit)[field] == "environment"


def test_saved_values_apply_unless_locked() -> None:
    settings = make_settings()
    values = ProviderValues(
        values={
            "openai_compatible_base_url": OAI_URL,
            "openai_compatible_api_key": OAI_KEY,
            "anthropic_api_key": ANT_KEY,
            "answer.provider": "anthropic",
            "answer.model": "claude-x",
        }
    )
    applied = apply_provider_values(settings, values, frozenset())
    assert applied.openai_compatible_base_url == OAI_URL
    assert applied.openai_compatible_api_key == OAI_KEY
    assert applied.anthropic_api_key == ANT_KEY
    assert (applied.answer.provider, applied.answer.model) == ("anthropic", "claude-x")
    locked = apply_provider_values(settings, values, frozenset({"anthropic_api_key"}))
    assert locked.anthropic_api_key == ""
    assert locked.openai_compatible_api_key == OAI_KEY


def test_effective_settings_carry_the_new_values() -> None:
    effective = compose.settings_to_effective(
        make_settings(
            openai_compatible_base_url=OAI_URL,
            openai_compatible_api_key=OAI_KEY,
            anthropic_api_key=ANT_KEY,
        )
    )
    assert provider_secret_values(effective) == ("", OAI_KEY, ANT_KEY)
    assert effective.openai_compatible_base_url == OAI_URL


@pytest.mark.parametrize("name", ["openai_compatible", "anthropic"])
def test_the_new_providers_are_not_embedding_or_metadata_providers(name: str) -> None:
    with pytest.raises(ValueError, match="not recognised"):
        Settings(_env_file=None, embed_provider=name)
    with pytest.raises(ValueError, match="not recognised"):
        make_settings(extraction_mode=name)


# ── Summary shape ─────────────────────────────────────────────────────────


def entries(settings: Settings, values: ProviderValues | None = None) -> dict[str, Any]:
    from pathlib import Path

    from omrg.compose_connections import build_connection_summary

    result = build_connection_summary(settings, Path("."), values)
    return {e["provider"]: e for e in result["connections"]}


def test_summary_entries() -> None:
    result = entries(make_settings(answer_provider="openai_compatible"))
    oai, ant = result["openai_compatible"], result["anthropic"]
    assert oai["roles"] == ["answers"]
    assert ant["roles"] == []
    assert [(f["id"], f["kind"], f["required"]) for f in oai["fields"]] == [
        ("base_url", "url", True),
        ("api_key", "secret", False),
    ]
    assert [(f["id"], f["kind"], f["required"]) for f in ant["fields"]] == [
        ("api_key", "secret", True)
    ]
    assert ant["read_only"] == [{"label": "Address", "value": "https://api.anthropic.com"}]
    assert oai["fields"][0]["value"] == "https://api.openai.com/v1"
    assert oai["fields"][0]["source"] == "default"
    assert result["openai_compatible"]["locality"] == "cloud"


def test_summary_roles_follow_the_answer_provider() -> None:
    assert entries(make_settings(answer_provider="anthropic"))["anthropic"]["roles"] == ["answers"]


def test_summary_never_holds_a_key_and_shows_last4_only_for_long_keys() -> None:
    import json

    settings = make_settings(anthropic_api_key=ANT_KEY, openai_compatible_api_key="short-key-1")
    result = entries(settings)
    text = json.dumps(result)
    assert ANT_KEY not in text and "short-key-1" not in text
    ant_field = result["anthropic"]["fields"][0]
    assert (ant_field["set"], ant_field["last4"]) == (True, ANT_KEY[-4:])
    oai_field = result["openai_compatible"]["fields"][1]
    assert (oai_field["set"], oai_field["last4"]) == (True, None)


def test_summary_locks_an_env_key_and_a_missing_keychain() -> None:
    result = entries(
        make_settings(anthropic_api_key=ANT_KEY, explicit=frozenset({"anthropic_api_key"}))
    )
    field = result["anthropic"]["fields"][0]
    assert (field["source"], field["locked"]) == ("env", True)
    assert "ANTHROPIC_API_KEY" in field["lock_reason"]


# ── Redaction ─────────────────────────────────────────────────────────────


def test_redaction_covers_every_provider_key_and_retired_key() -> None:
    held = RedactionSecrets(provider_keys=(OAI_KEY, ANT_KEY), retired_provider_keys=(ANT_KEY_2,))
    text = held.redact(f"a {OAI_KEY} b {ANT_KEY} c {ANT_KEY_2}")
    for key in (OAI_KEY, ANT_KEY, ANT_KEY_2):
        assert key not in text
        assert key[8:] not in text  # the part after the shared prefix


def test_a_shared_prefix_does_not_leave_the_tail_of_another_key() -> None:
    """Both keys start with ``sk-ant-api03-``; removing one prefix must not expose the other."""
    held = RedactionSecrets(provider_keys=(ANT_KEY, ANT_KEY_2))
    text = held.redact(f"x {ANT_KEY_2} y")
    assert ANT_KEY_2[14:] not in text
    assert "ZZZZ9999" not in text


def test_redaction_has_no_openrouter_only_holder() -> None:
    assert not hasattr(RedactionSecrets(), "retired_openrouter_keys")


def test_redaction_values_list_every_secret_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compose, "get_settings", lambda: make_settings(anthropic_api_key=ANT_KEY))
    values = compose.redaction_values()
    assert set(PROVIDER_SECRET_FIELDS) <= set(values)
    assert values["anthropic_api_key"] == ANT_KEY


def test_startup_error_text_redacts_every_provider_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from omrg.transports import mcp

    monkeypatch.setattr(
        compose,
        "get_settings",
        lambda: make_settings(anthropic_api_key=ANT_KEY, openai_compatible_api_key=OAI_KEY),
    )
    text = mcp._error_detail(RuntimeError(f"failed {ANT_KEY} {OAI_KEY}"))
    assert ANT_KEY not in text and OAI_KEY not in text


def test_composed_engine_redacts_all_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from omrg.compose_engine import build_redaction

    held = build_redaction(
        make_settings(anthropic_api_key=ANT_KEY, openai_compatible_api_key=OAI_KEY)
    )
    out = held.redact(f"{ANT_KEY} {OAI_KEY}")
    assert ANT_KEY not in out and OAI_KEY not in out


def test_error_detail_redacts_the_new_keys() -> None:
    from omrg.core.answer.stages import safe_error_detail

    effective = compose.settings_to_effective(
        make_settings(anthropic_api_key=ANT_KEY, openai_compatible_api_key=OAI_KEY)
    )
    detail = safe_error_detail(RuntimeError(f"bad {ANT_KEY} and {OAI_KEY}"), effective)
    assert ANT_KEY not in detail and OAI_KEY not in detail


# ── Engine: live apply and redaction follow the new keys ──────────────────


def test_engine_takes_the_new_fields_without_the_embedding_guard(effective_settings: Any) -> None:
    from tests.unit.test_engine_pipelines_support import build_engine

    engine = build_engine(effective_settings())
    engine.use_provider_settings(
        effective_settings(
            openai_compatible_base_url=OAI_URL,
            openai_compatible_api_key=OAI_KEY,
            anthropic_api_key=ANT_KEY,
        )
    )
    current = engine._gen.effective
    assert (current.openai_compatible_base_url, current.anthropic_api_key) == (OAI_URL, ANT_KEY)


def test_engine_redaction_follows_and_keeps_every_retired_key(effective_settings: Any) -> None:
    from tests.unit.test_engine_pipelines_support import build_engine

    engine = build_engine(
        effective_settings(anthropic_api_key=ANT_KEY),
        redaction=RedactionSecrets(provider_keys=(ANT_KEY,)),
    )
    engine.use_provider_settings(effective_settings(anthropic_api_key=ANT_KEY_2))
    assert ANT_KEY not in engine.redact(f"late failure {ANT_KEY}")
    assert ANT_KEY_2 not in engine.redact(f"fail {ANT_KEY_2}")
    engine.use_provider_settings(effective_settings(openai_compatible_api_key=OAI_KEY))
    for key in (ANT_KEY, ANT_KEY_2, OAI_KEY):
        assert key not in engine.redact(f"fail {key}")


def test_engine_still_refuses_an_embedding_change(effective_settings: Any) -> None:
    from tests.unit.test_engine_pipelines_support import build_engine

    engine = build_engine(effective_settings())
    with pytest.raises(ValueError, match="embed"):
        engine.use_provider_settings(effective_settings(embed_model="other"))


# ── A further provider needs no other change ─────────────────────────────


@pytest.fixture
def fake_third() -> Iterator[None]:
    """A provider with an optional and a required key, using existing settings fields."""
    module = types.ModuleType("fake_third_llm")
    module.build = lambda settings, **_: None  # type: ignore[attr-defined]
    module.CONNECTION = ConnectionDescriptor(  # type: ignore[attr-defined]
        display_name="Third",
        locality="cloud",
        requires_module="json",
        extra=None,
        fields=(
            ConnectionField("api_key", "API key", "secret", "anthropic_api_key", "X_KEY", False),
            ConnectionField("base_url", "Address", "url", "openai_compatible_base_url", "X_URL"),
        ),
        read_only=lambda settings: [],
        test_targets=lambda s: ConnectionTarget((s.openai_compatible_base_url + "/ping",)),
        models_target=lambda s: ConnectionTarget(()),
        parse_models=lambda payload: [],
    )
    sys.modules["fake_third_llm"] = module
    before = dict(registry._registry)
    registry.register("third", "fake_third_llm:build")
    try:
        yield
    finally:
        registry._registry.clear()
        registry._registry.update(before)
        sys.modules.pop("fake_third_llm", None)


@pytest.mark.usefixtures("fake_third")
def test_a_third_provider_appears_in_the_summary_with_its_flags() -> None:
    card = entries(make_settings(anthropic_api_key=""))["third"]
    assert [(f["id"], f["required"]) for f in card["fields"]] == [
        ("api_key", False),
        ("base_url", True),
    ]


_OLD_ANT = "sk-ant-api03-" + "A" * 30 + "oldoldold"  # gitleaks:allow
_NEW_ANT = "sk-ant-api03-" + "B" * 30 + "newnewnew"  # gitleaks:allow


@pytest.mark.parametrize("cut", [4, 9, 20])
def test_shared_prefix_keys_leave_no_fragment_of_the_second_key(cut: int) -> None:
    from omrg.core.vectordb.identity import redact_secrets

    fragment = _NEW_ANT[:-cut]
    assert "B" not in redact_secrets(f"error {fragment}", [_OLD_ANT, _NEW_ANT])
    assert "B" not in redact_secrets(f"error {fragment}", [_NEW_ANT, _OLD_ANT])


_ENV_KEY = "env-openai-key-must-not-be-used"  # gitleaks:allow


def test_openai_compatible_never_falls_back_to_the_environment_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty saved key must not send OPENAI_API_KEY to a typed address."""
    pytest.importorskip("llama_index.llms.openai_like")
    from omrg.core.providers.llm import openai_compatible

    monkeypatch.setenv("OPENAI_API_KEY", _ENV_KEY)
    settings = make_settings(
        openai_compatible_api_key="", openai_compatible_base_url="http://x.test/v1"
    )
    llm = openai_compatible.build(settings, answer_model="m")
    assert llm.api_key == "no-key"
    assert _ENV_KEY not in repr(llm.api_key)
