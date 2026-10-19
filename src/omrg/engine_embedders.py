"""The Engine's embedder set, keyed by (provider, model) (ADR-081, D5, D6).

A collection can follow a profile that names its own embedding model. The
Engine keeps one embedder for each (provider, model) pair that its profiles
name. The host embedder, composed from ``.env``, is the first entry. Other
entries are built on first use through a factory that ``compose`` supplies, so
this module constructs no provider itself (import-linter contract
``providers-constructed-only-in-compose``).

Two Engines never share an embedder (``engine-scoped-composition``). Closing an
Engine releases its set.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core.vectordb.identity import EmbeddingIdentity
    from .engine import Engine


class EngineEmbedders:
    """Embedders of one Engine by (provider, model).

    ``get`` can run from ingestion worker threads, so a lock guards the build.
    """

    def __init__(
        self,
        host_model: Any,
        host_identity: EmbeddingIdentity | None = None,
        factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        """Hold the host embedder and the factory for the others.

        Args:
            host_model: The embedder composed from the server settings.
            host_identity: The concrete (provider, model) of *host_model*, or
                ``None`` when unknown. A request for that pair returns the host.
            factory: Builds an embedder for a (provider, model) pair. ``None``
                means this set holds only the host embedder.
        """
        self._lock = threading.Lock()
        self._host = host_model
        self.host_identity = host_identity
        self._host_key = (host_identity.provider, host_identity.model) if host_identity else None
        self._factory = factory
        self._models: dict[tuple[str, str], Any] = {}
        self._released = False

    def get(self, identity: EmbeddingIdentity | None) -> Any:
        """Return the embedder for *identity*, building it on first use.

        Args:
            identity: The pair a profile names. ``None`` and the host pair
                return the host embedder.

        Raises:
            ValueError: If the pair is new and the set has no factory.
            RuntimeError: If the set was released.
        """
        if identity is None:
            return self._host
        key = (identity.provider, identity.model)
        if key == self._host_key:
            return self._host
        with self._lock:
            if self._released:
                raise RuntimeError("The Engine embedders were released with Engine.close().")
            model = self._models.get(key)
            if model is None:
                if self._factory is None:
                    raise ValueError(
                        f"No embedder factory is available for provider={identity.provider!r}, "
                        f"model={identity.model!r}."
                    )
                model = self._factory(*key)
                self._models[key] = model
            return model

    def release(self) -> None:
        """Drop every embedder so a closed Engine pins no model resources."""
        with self._lock:
            self._released = True
            self._models.clear()
            self._host = None
            self._factory = None


def definition_collection(definition: Any) -> str | None:
    """Return the default collection a graph definition names, or ``None``.

    Accepts a graph mapping (bare or wrapped in ``{"graph": ...}``), a parsed
    definition and an admission snapshot.
    """
    if isinstance(definition, Mapping):
        graph = definition.get("graph", definition)
        return graph.get("collection") if isinstance(graph, Mapping) else None
    graph = getattr(definition, "graph", None)
    if graph is not None:
        return getattr(graph, "collection", None)
    try:
        return json.loads(definition.graph_json).get("collection")
    except (AttributeError, TypeError, ValueError):
        return None


def embedding_for(
    engine: Engine, collection: str | None, binding: Any = None
) -> tuple[Any, EmbeddingIdentity | None]:
    """Return the embedder and identity that operations on *collection* use.

    The profile that the collection follows decides (D6). A built-in profile,
    an untagged collection and an empty choice return the host embedder and
    ``None``, so stores keep their composed identity.

    Args:
        engine: The Engine.
        collection: The collection of the operation.
        binding: The binding the caller already read for this operation, to
            avoid a second tag read. ``None`` asks the resolver.
    """
    if collection is None:
        choice = None
    elif binding is not None:
        choice = getattr(binding, "embedding", None)
    else:
        read = getattr(engine._resolver(), "embedding_choice", None)
        choice = read(collection) if read is not None else None
    return engine._embedders.get(choice), choice
