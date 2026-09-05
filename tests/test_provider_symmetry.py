"""Symmetry test: every LLM-backed metadata backend is registered in both registries.

Asserts the structural invariant that ADR-027 described in prose but never
enforced: every metadata extraction backend that delegates to an LLM
sub-provider SHALL be registered in both the metadata extraction registry
and the LLM provider registry, under the same name, and implemented outside
the dispatch module.

See ``openspec/changes/tripwire-retirement-and-provider-symmetry/`` and
``design.md`` D5: "the reason this gap survived three releases is that
nothing failed when it appeared."
"""

from __future__ import annotations

from omrg.core.metadata import registry as _metadata_registry
from omrg.core.providers.llm import registry as _llm_registry

# LLM-backed metadata backends — the ones that delegate to a specific LLM
# sub-provider (ollama, llamacpp, openrouter).  Excludes keyword (regex,
# no LLM), llamaindex (uses whichever LLM is configured via provider
# selection, not a standalone sub-provider), and disabled (sentinel).
_LLM_BACKED_BACKENDS = frozenset({"ollama", "llamacpp", "openrouter"})

# Sub-provider names accepted by config validation (config/__init__.py).
# These are the names an operator can select; each MUST be registered so a
# selectable-but-missing provider fails loudly rather than silently.
# Derived from the Literal tuples at:
#   local_backend  ∈ ("llamacpp", "ollama")
#   cloud_backend  ∈ ("openrouter",)
_CONFIGURABLE_SUB_PROVIDERS = frozenset({"ollama", "llamacpp", "openrouter"})


class TestProviderSymmetry:
    """Backend symmetry across the metadata and LLM provider registries."""

    def test_llm_backed_backends_are_in_both_registries(self) -> None:
        """ollama, llamacpp, and openrouter appear in each registry.

        A backend registered in one registry but not the other is the gap
        this change closes; this test makes its reappearance fail loudly.
        """
        metadata_names = set(_metadata_registry.available())
        llm_names = set(_llm_registry.available())

        missing_from_llm = _LLM_BACKED_BACKENDS - llm_names
        assert not missing_from_llm, (
            f"LLM-backed backends missing from the LLM provider registry: "
            f"{sorted(missing_from_llm)}"
        )

        missing_from_metadata = _LLM_BACKED_BACKENDS - metadata_names
        assert not missing_from_metadata, (
            f"LLM-backed backends missing from the metadata extraction "
            f"registry: {sorted(missing_from_metadata)}"
        )

    def test_no_metadata_backend_resolves_to_dispatch_module(self) -> None:
        """No registered metadata backend lives in the dispatch module.

        The dispatch module (``core.metadata.extractor``) must contain no
        backend implementation — only dispatch logic.  Every backend
        resolves to its own module.
        """
        dispatch_prefix = "omrg.core.metadata.extractor"
        offenders = [
            name
            for name, path in _metadata_registry._registry.items()
            if path.startswith(dispatch_prefix)
        ]
        assert not offenders, (
            f"Metadata backends still resolved to the dispatch module: {sorted(offenders)}"
        )

    def test_every_configurable_sub_provider_is_registered(self) -> None:
        """Every sub-provider name accepted by config validation is registered.

        A name that config validation accepts but the registry does not
        know is a defect: the operator can select it, but the system
        cannot serve it.
        """
        llm_names = set(_llm_registry.available())
        missing = _CONFIGURABLE_SUB_PROVIDERS - llm_names
        assert not missing, (
            f"Configurable sub-providers missing from the LLM provider registry: {sorted(missing)}"
        )


class TestNoInlineLLMConstruction:
    """Backends resolve LLMs through the registry, never by hand.

    The registry exists so that adding a provider is one file plus one
    ``register()`` line (invariant 10).  An inline construction bypasses it
    silently: the provider stays registered, the symmetry test still passes,
    and the code path that matters never uses it.  That is exactly how the
    OpenRouter gap survived from ADR-027 to now, so it is pinned here.
    """

    def test_llamaindex_backend_constructs_no_llm_inline(self) -> None:
        import inspect

        from omrg.core.metadata import llamaindex

        source = inspect.getsource(llamaindex)
        for forbidden in ("OpenAILike(", "Ollama("):
            assert forbidden not in source, (
                f"{forbidden} is constructed inline in llamaindex.py — "
                "resolve it through core.providers.llm.registry instead"
            )

    def test_llamaindex_backend_uses_the_registry(self) -> None:
        import inspect

        from omrg.core.metadata import llamaindex

        assert "providers.llm.registry" in inspect.getsource(llamaindex)


class TestPipelineTimeoutIsSeparate:
    """The pipeline budget must not collapse into the classification one."""

    def test_defaults_differ(self) -> None:
        from omrg.core.settings import MetadataBlock

        block = MetadataBlock()
        assert block.classify_timeout == 30.0
        assert block.pipeline_timeout == 180.0

    def test_both_models_carry_the_field(self) -> None:
        from omrg.core.metadata.settings import MetadataSettings
        from omrg.core.settings import MetadataBlock

        for model in (MetadataSettings, MetadataBlock):
            assert "pipeline_timeout" in model.model_fields

    def test_providers_honour_an_explicit_timeout(self) -> None:
        """Each provider must apply the caller's timeout, not its own default."""
        import sys
        import types

        recorded: dict[str, object] = {}

        class _Recorder:
            def __init__(self, **kwargs: object) -> None:
                recorded.update(kwargs)

        from omrg.config import Settings

        settings = Settings(_env_file=None)

        stub_like = types.ModuleType("llama_index.llms.openai_like")
        stub_like.OpenAILike = _Recorder  # type: ignore[attr-defined]
        stub_ollama = types.ModuleType("llama_index.llms.ollama")
        stub_ollama.Ollama = _Recorder  # type: ignore[attr-defined]

        original = dict(sys.modules)
        try:
            sys.modules["llama_index.llms.openai_like"] = stub_like
            sys.modules["llama_index.llms.ollama"] = stub_ollama

            from omrg.core.providers.llm import llamacpp, ollama, openrouter

            for module, key in (
                (llamacpp, "timeout"),
                (openrouter, "timeout"),
                (ollama, "request_timeout"),
            ):
                recorded.clear()
                module.build(settings, timeout=99.0)
                assert recorded[key] == 99.0, f"{module.__name__} ignored the caller's timeout"
        finally:
            sys.modules.clear()
            sys.modules.update(original)


class TestMetadataSettingsParity:
    """``MetadataSettings`` and ``MetadataBlock`` must declare identical fields.

    ``MetadataSettings`` (core/metadata/settings.py) is consumed by the
    config-layer resolver; ``MetadataBlock`` (core/settings.py) is the
    mirrored block on the frozen ``EffectiveSettings`` used at runtime.
    A field added to one and forgotten on the other is a live hole — the
    setting parses on one side and silently vanishes on the other. See
    design.md D1 and openspec/changes/fix-silent-metadata-degradation/.
    """

    def test_field_names_match(self) -> None:
        from omrg.core.metadata.settings import MetadataSettings
        from omrg.core.settings import MetadataBlock

        assert set(MetadataSettings.model_fields) == set(MetadataBlock.model_fields)

    def test_field_defaults_match(self) -> None:
        from omrg.core.metadata.settings import MetadataSettings
        from omrg.core.settings import MetadataBlock

        for name, field in MetadataSettings.model_fields.items():
            other = MetadataBlock.model_fields[name]
            assert field.default == other.default, (
                f"MetadataSettings.{name} default {field.default!r} != "
                f"MetadataBlock.{name} default {other.default!r}"
            )

    def test_six_timeout_overrides_present_and_optional(self) -> None:
        """All six per-provider overrides exist on both models and default to None."""
        from omrg.core.metadata.settings import MetadataSettings
        from omrg.core.settings import MetadataBlock

        expected = {
            "llamacpp_classify_timeout_override",
            "ollama_classify_timeout_override",
            "openrouter_classify_timeout_override",
            "llamacpp_pipeline_timeout_override",
            "ollama_pipeline_timeout_override",
            "openrouter_pipeline_timeout_override",
        }
        for model in (MetadataSettings, MetadataBlock):
            missing = expected - set(model.model_fields)
            assert not missing, f"{model.__name__} missing: {sorted(missing)}"
            for name in expected:
                assert model.model_fields[name].default is None, (
                    f"{model.__name__}.{name} default must be None, "
                    f"got {model.model_fields[name].default!r}"
                )
