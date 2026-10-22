"""Embedding lock and binding rules for profiles (ADR-081, design D7).

One collection holds vectors from one embedding model only. These pure
functions decide two questions without a store write:

* May a profile change its embedding model? Not while a bound collection holds
  vectors made with another model (:func:`blocking_collections`).
* May a profile bind to a collection? Not when the collection holds vectors
  made with a model other than the profile's effective model
  (:func:`binding_refusal`).

A collection holds vectors when it has a stamp or at least one row. Rows
without a stamp always block, because the store stamps an unstamped collection
on its next write and would mix vectors. The functions read the stamp from the
collection metadata and do not use ``StoreCollectionView``, which reports no
stamp when the store has no composed identity.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..vectordb.identity import (
    IDENTITY_MODEL_KEY,
    IDENTITY_PROVIDER_KEY,
    EmbeddingIdentity,
)

NOT_RECORDED = "not recorded"


@dataclass(frozen=True)
class CollectionEmbeddingState:
    """What one collection records about its embedding model.

    Attributes:
        collection: The collection name.
        provider: The stamped provider, or ``None`` when no stamp exists.
        model: The stamped model, or ``None`` when no stamp exists.
        chunk_count: The number of rows in the collection.
    """

    collection: str
    provider: str | None
    model: str | None
    chunk_count: int

    @property
    def holds_vectors(self) -> bool:
        """Whether the collection has a stamp or at least one row."""
        return self.stamped or self.chunk_count > 0

    @property
    def stamped(self) -> bool:
        """Whether the collection records the model that made its vectors."""
        return self.provider is not None and self.model is not None

    def matches(self, identity: EmbeddingIdentity) -> bool:
        """Return whether the stamp names ``identity``."""
        return self.provider == identity.provider and self.model == identity.model

    def describe(self) -> str:
        """Return the stamp as text: ``provider/model``, or ``not recorded``."""
        return f"{self.provider}/{self.model}" if self.stamped else NOT_RECORDED


def collection_embedding_state(store: Any, name: str) -> CollectionEmbeddingState:
    """Read the stamp and the row count of a collection.

    Args:
        store: A vector store.
        name: The collection name. An unknown collection has no stamp, no rows.
    """
    metadata = store.get_collection_metadata(name) or {}
    provider, model = metadata.get(IDENTITY_PROVIDER_KEY), metadata.get(IDENTITY_MODEL_KEY)
    stamped = isinstance(provider, str) and isinstance(model, str) and provider and model
    return CollectionEmbeddingState(
        collection=name,
        provider=provider if stamped else None,
        model=model if stamped else None,
        chunk_count=int(store.count(name)),
    )


def blocking_collections(
    states: Sequence[CollectionEmbeddingState], requested: EmbeddingIdentity
) -> list[CollectionEmbeddingState]:
    """Return the collections that block a change to ``requested``.

    A collection blocks when it holds vectors and its stamp does not name the
    requested model. Rows without a stamp always block. The order of ``states``
    stays.
    """
    return [s for s in states if s.holds_vectors and not (s.stamped and s.matches(requested))]


def binding_refusal(
    state: CollectionEmbeddingState,
    profile_identity: EmbeddingIdentity | None,
    host_identity: EmbeddingIdentity,
) -> str | None:
    """Return why a profile cannot bind to a collection, or ``None`` when it can.

    Args:
        state: The collection's state.
        profile_identity: The profile's chosen model, or ``None`` for the
            server default.
        host_identity: The server default model.

    Returns:
        A plain-English message that names the collection and both models, or
        ``None`` when the binding is allowed.
    """
    effective = profile_identity or host_identity
    wanted = f"{effective.provider}/{effective.model}"
    if state.stamped:
        if state.matches(effective):
            return None
        return (
            f"Collection {state.collection!r} holds vectors made with {state.describe()}, "
            f"but this profile uses {wanted}. Create a new collection to use this profile, "
            f"or choose a profile that uses {state.describe()}."
        )
    if state.chunk_count == 0:
        return None
    if (effective.provider, effective.model) == (host_identity.provider, host_identity.model):
        return None
    return (
        f"Collection {state.collection!r} holds {state.chunk_count} chunks, but the model "
        f"that made them is {NOT_RECORDED}. This profile uses {wanted}. Create a new "
        f"collection to use this profile."
    )
