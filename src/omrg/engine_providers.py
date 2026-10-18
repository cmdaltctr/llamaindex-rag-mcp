"""Live LLM provider values for a running Engine (design D3).

The Engine keeps its server-default settings, answer-model slot, judge
factory and profile resolver in one *generation*. ``use_provider_settings``
replaces the whole generation, never a field of it. A call that already
started holds the generation it captured and finishes with it; later calls
see the new one. The embedder, store and reranker belong to the Engine and
never change.

``EngineProviders`` is a mixin for :class:`omrg.engine.Engine` (which sits
near the 500-line ceiling). It keeps the private attribute names that the
Engine, its lifecycle helpers and its tests already use.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from .core.profiles.resolver import ProfileResolver
    from .core.settings import EffectiveSettings

#: Server-default settings a provider update may change.
_EDITABLE_TOP = ("ollama_base_url", "llamacpp_chat_url", "openrouter_api_key")
_EDITABLE_ANSWER = ("provider", "model")


@dataclass
class Generation:
    """Settings and lazily built LLM resources that one provider update owns.

    Attributes:
        effective: The server-default settings of this generation.
        resolver: The profile resolver, built on first use from its factory.
        resolver_factory: Builds the profile resolver, or ``None``.
        answer_llm: The answer model, built on first use and then kept.
        answer_llm_factory: Builds the answer model, or ``None``.
        verify_llm_factory: Builds the claim-verification judge, or ``None``.
    """

    effective: EffectiveSettings
    resolver: ProfileResolver | None = None
    resolver_factory: Callable[[], ProfileResolver] | None = None
    answer_llm: Any = None
    answer_llm_factory: Callable[[], Any] | None = None
    verify_llm_factory: Callable[[Any], Any] | None = None

    def get_answer_llm(self) -> Any:
        """Build the answer LLM on first use and keep it."""
        if self.answer_llm is None and self.answer_llm_factory is not None:
            self.answer_llm = self.answer_llm_factory()
        return self.answer_llm

    def get_resolver(self) -> Any:
        """Return the profile resolver, built from its factory on first use."""
        if self.resolver is None and self.resolver_factory is not None:
            self.resolver = self.resolver_factory()
        return self.resolver


def _delegate(name: str) -> property:
    """Return a property that reads and writes *name* on the current generation."""
    return property(
        lambda self: getattr(self._gen, name),
        lambda self, value: setattr(self._gen, name, value),
    )


def changed_settings(old: EffectiveSettings, new: EffectiveSettings) -> list[str]:
    """Return the names of settings that differ beyond the editable provider values.

    The Ollama address counts as different while embeddings use Ollama,
    because the running embedder keeps the address it was built with.
    Names only; no value leaves this function.
    """
    from .config import _resolve_effective_embed_provider

    old_values, new_values = old.model_dump(), new.model_dump()
    for key in _EDITABLE_TOP:
        old_values.pop(key), new_values.pop(key)
    for key in _EDITABLE_ANSWER:
        old_values["answer"].pop(key), new_values["answer"].pop(key)
    names = [key for key in old_values if old_values[key] != new_values[key]]
    uses_ollama = "ollama" in (
        _resolve_effective_embed_provider(old),
        _resolve_effective_embed_provider(new),
    )
    if uses_ollama and old.ollama_base_url != new.ollama_base_url:
        names.append("ollama_base_url (embeddings use it)")
    return names


class EngineProviders:
    """Mixin that gives the Engine swappable LLM provider values."""

    _gen: Generation
    _effective_settings = _delegate("effective")
    _profile_resolver = _delegate("resolver")
    _profile_resolver_factory = _delegate("resolver_factory")
    _answer_llm = _delegate("answer_llm")
    _answer_llm_factory = _delegate("answer_llm_factory")
    _verify_llm_factory = _delegate("verify_llm_factory")

    def _init_providers(self, effective: EffectiveSettings, **resources: Any) -> None:
        """Start the first generation from the constructor arguments."""
        self._gen = Generation(effective, **resources)

    def _get_answer_llm(self) -> Any:
        """Build the answer LLM on first use and keep it."""
        return self._gen.get_answer_llm()

    def _resolver(self) -> Any:
        """Return the profile resolver, built from its factory on first use."""
        return self._gen.get_resolver()

    def use_provider_settings(self, effective: EffectiveSettings) -> None:
        """Take new server-default settings that differ only in LLM provider values.

        Allowed differences are the Ollama, llama.cpp chat and OpenRouter
        values and the answer provider and model. The next answer, judge,
        ingest and graph run build their resources from the new values
        through the factories the composition root gave. A call that already
        started finishes with the old values. The embedder, store and
        reranker stay as they are.

        Args:
            effective: The new server-default settings.

        Raises:
            ValueError: Other settings differ, including embedding settings.
                The Engine keeps its current settings. The message names
                the settings and holds no value.
            RuntimeError: The Engine is closed.
        """
        self._check_open()  # type: ignore[attr-defined]
        names = changed_settings(self._gen.effective, effective)
        if names:
            raise ValueError(
                "Only LLM provider addresses, keys and the answer provider and model can "
                "change while the server runs (embedding settings need a restart). "
                f"These differ: {', '.join(names)}."
            )
        old = self._gen
        self._gen = Generation(
            effective,
            resolver=None if old.resolver_factory else old.resolver,
            resolver_factory=old.resolver_factory,
            answer_llm_factory=old.answer_llm_factory,
            verify_llm_factory=old.verify_llm_factory,
        )
        self._redaction = replace(  # type: ignore[attr-defined]
            self._redaction,  # type: ignore[attr-defined]
            openrouter_api_key=effective.openrouter_api_key,
        )
        self._pipelines.reset_judges()  # type: ignore[attr-defined]
