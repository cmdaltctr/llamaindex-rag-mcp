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

from .core.profiles.catalogue import uses_ollama_embeddings
from .core.settings import (
    PROVIDER_ADDRESS_FIELDS,
    PROVIDER_INT_FIELDS,
    PROVIDER_SECRET_FIELDS,
    provider_secret_values,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from .core.profiles.resolver import ProfileResolver
    from .core.settings import EffectiveSettings

#: Server-default settings a provider update may change.
_EDITABLE_TOP = (*PROVIDER_ADDRESS_FIELDS, *PROVIDER_SECRET_FIELDS, *PROVIDER_INT_FIELDS)
_EDITABLE_ANSWER = ("provider", "model", "verify_provider", "verify_model")


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
        snapshot_source: Returns the provider settings a new generation
            freezes, or ``None`` when factories take no snapshot.
        raw_factories: The factories as given, before binding to a snapshot.
    """

    effective: EffectiveSettings
    resolver: ProfileResolver | None = None
    resolver_factory: Callable[[], ProfileResolver] | None = None
    answer_llm: Any = None
    answer_llm_factory: Callable[[], Any] | None = None
    verify_llm_factory: Callable[[Any], Any] | None = None
    snapshot_source: Callable[[], Any] | None = None
    raw_factories: tuple[Any, Any, Any] = (None, None, None)

    @classmethod
    def start(
        cls,
        effective: EffectiveSettings,
        *,
        snapshot_source: Callable[[], Any] | None = None,
        resolver: ProfileResolver | None = None,
        raw_factories: tuple[Any, Any, Any] = (None, None, None),
    ) -> Generation:
        """Create a generation; with a *snapshot_source*, freeze one snapshot now.

        Each factory then receives the snapshot as its last argument, so a
        generation that builds late (after a newer one took over) still uses
        the values it was created with.
        """
        resolver_factory, answer_factory, verify_factory = raw_factories
        if snapshot_source is not None:
            snapshot = snapshot_source()
            resolver_factory = _bind(resolver_factory, snapshot)
            answer_factory = _bind(answer_factory, snapshot)
            verify_factory = _bind(verify_factory, snapshot)
        return cls(
            effective,
            resolver=resolver,
            resolver_factory=resolver_factory,
            answer_llm_factory=answer_factory,
            verify_llm_factory=verify_factory,
            snapshot_source=snapshot_source,
            raw_factories=raw_factories,
        )

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


def _bind(factory: Callable[..., Any] | None, snapshot: Any) -> Callable[..., Any] | None:
    """Return *factory* with *snapshot* appended to its arguments, or ``None``."""
    if factory is None:
        return None
    return lambda *args: factory(*args, snapshot)


def _delegate(name: str) -> property:
    """Return a property that reads and writes *name* on the current generation."""
    return property(
        lambda self: getattr(self._gen, name),
        lambda self, value: setattr(self._gen, name, value),
    )


def changed_settings(
    old: EffectiveSettings, new: EffectiveSettings, *, profiles_ollama: bool = False
) -> list[str]:
    """Return the names of settings that differ beyond the editable provider values.

    The Ollama address counts as different while embeddings use Ollama,
    because the running embedder keeps the address it was built with. The
    same holds when any profile selects Ollama embeddings (*profiles_ollama*).
    Names only; no value leaves this function.
    """
    from .config import _resolve_effective_embed_provider

    old_values, new_values = old.model_dump(), new.model_dump()
    for key in _EDITABLE_TOP:
        old_values.pop(key), new_values.pop(key)
    for key in _EDITABLE_ANSWER:
        old_values["answer"].pop(key), new_values["answer"].pop(key)
    names = [key for key in old_values if old_values[key] != new_values[key]]
    uses_ollama = profiles_ollama or "ollama" in (
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

    def _init_providers(
        self,
        effective: EffectiveSettings,
        *,
        resolver: Any = None,
        resolver_factory: Any = None,
        answer_llm_factory: Any = None,
        verify_llm_factory: Any = None,
        snapshot_source: Callable[[], Any] | None = None,
    ) -> None:
        """Start the first generation from the constructor arguments."""
        self._gen = Generation.start(
            effective,
            snapshot_source=snapshot_source,
            resolver=resolver,
            raw_factories=(resolver_factory, answer_llm_factory, verify_llm_factory),
        )

    def profile_catalogue(self) -> Any:
        """Return the user-profile catalogue, or ``None`` when there is none."""
        return getattr(self._resolver(), "catalogue", None)

    def _get_answer_llm(self) -> Any:
        """Build the answer LLM on first use and keep it."""
        return self._gen.get_answer_llm()

    def _resolver(self) -> Any:
        """Return the profile resolver, built from its factory on first use."""
        return self._gen.get_resolver()

    def use_provider_settings(self, effective: EffectiveSettings) -> None:
        """Take new server-default settings that differ only in LLM provider values.

        Allowed differences are the provider addresses and API keys (see
        ``PROVIDER_ADDRESS_FIELDS`` and ``PROVIDER_SECRET_FIELDS``), the
        answer provider and model, and the judge provider and model. The next answer, judge,
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
        names = changed_settings(
            self._gen.effective,
            effective,
            profiles_ollama=uses_ollama_embeddings(self.profile_catalogue()),
        )
        if names:
            raise ValueError(
                "Only LLM provider addresses, keys, the answer provider and model and the "
                "claim check judge provider and model can change while the server runs "
                "(embedding settings need a restart). "
                f"These differ: {', '.join(names)}."
            )
        old = self._gen
        self._gen = Generation.start(
            effective,
            snapshot_source=old.snapshot_source,
            resolver=None if old.resolver_factory else old.resolver,
            raw_factories=old.raw_factories,
        )
        held = self._redaction  # type: ignore[attr-defined]
        retired = held.retired_provider_keys
        for key in held.provider_keys:
            if key and key not in retired:
                retired = (*retired, key)
        self._redaction = replace(  # type: ignore[attr-defined]
            held, provider_keys=provider_secret_values(effective), retired_provider_keys=retired
        )
        self._pipelines.reset_judges()  # type: ignore[attr-defined]
