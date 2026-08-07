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

from rag_mcp.core.metadata import registry as _metadata_registry
from rag_mcp.core.providers.llm import registry as _llm_registry

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
        dispatch_prefix = "rag_mcp.core.metadata.extractor"
        offenders = [
            name for name, path in _metadata_registry._registry.items()
            if path.startswith(dispatch_prefix)
        ]
        assert not offenders, (
            f"Metadata backends still resolved to the dispatch module: "
            f"{sorted(offenders)}"
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
            f"Configurable sub-providers missing from the LLM provider "
            f"registry: {sorted(missing)}"
        )
