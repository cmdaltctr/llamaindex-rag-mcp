"""The embedding model of a profile: items, save and binding check (ADR-081, D7, D9, D10).

:class:`~omrg.compose_profiles.ProfileService` owns one :class:`ProfileEmbedding`.
It joins the pure lock rules of ``core.profiles.embedding_lock`` with the
workspace repository and the model check of ``compose_embedding``.

* :meth:`~ProfileEmbedding.fields` adds ``embedding`` and ``embedding_lock`` to
  every profile item.
* :meth:`~ProfileEmbedding.save` checks the model first, without a lock, because
  the probe is a network call. It then holds the process-wide ingestion write
  lock while it runs the lock check and writes the row, so no new stamp can
  appear between the two.
* :meth:`~ProfileEmbedding.check_binding` refuses a binding to a collection that
  holds vectors made with another model.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from . import compose_embedding
from .core.ingestion import write_lock
from .core.profiles.catalogue import BUILTIN_PROFILES
from .core.profiles.embedding_lock import (
    CollectionEmbeddingState,
    binding_refusal,
    blocking_collections,
    collection_embedding_state,
)
from .core.vectordb.identity import EmbeddingIdentity

if TYPE_CHECKING:
    from .compose_profiles import ProfileService


class EmbeddingLockedError(ValueError):
    """A bound collection holds vectors made with another model.

    Attributes:
        collections: The blocking collections, first blocking collection first,
            as ``{collection, provider, model, chunk_count}``.
    """

    def __init__(self, collections: list[dict[str, Any]]) -> None:
        first = collections[0]
        made = f"made with {first['model']}" if first["model"] else "but the model is not recorded"
        super().__init__(
            f"The model cannot change: {first['collection']} already holds vectors {made}. "
            f"Create a new collection to use another model."
        )
        self.collections = collections


class EmbeddingCheckFailedError(ValueError):
    """The model check failed, so the model was not saved.

    Attributes:
        reason: The plain-English reason from the check.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class EmbeddingMismatchError(ValueError):
    """A profile cannot bind to a collection that holds vectors from another model."""


def _described(state: CollectionEmbeddingState) -> dict[str, Any]:
    return {
        "collection": state.collection,
        "provider": state.provider,
        "model": state.model,
        "chunk_count": state.chunk_count,
    }


class ProfileEmbedding:
    """Embedding-model behaviour of a :class:`~omrg.compose_profiles.ProfileService`.

    Args:
        service: The profile service.
        host_identity: Returns the server default model. ``None`` reads it from
            the settings.
    """

    def __init__(
        self,
        service: ProfileService,
        host_identity: Callable[[], EmbeddingIdentity] | None = None,
    ) -> None:
        self._service = service
        self._host = host_identity or compose_embedding.server_default_identity

    # ── Reading ─────────────────────────────────────────────────────

    def _store(self) -> Any | None:
        try:
            return self._service._engine.store
        except (RuntimeError, AttributeError):
            return None

    def _states(self, collections: list[str]) -> list[CollectionEmbeddingState]:
        store = self._store()
        if store is None:
            return []
        return [collection_embedding_state(store, name) for name in collections]

    def fields(self, record: Mapping[str, Any] | None, used_by: list[str]) -> dict[str, Any]:
        """Return ``embedding`` and ``embedding_lock`` for a profile item.

        Args:
            record: The user profile record, or ``None`` for a built-in profile.
            used_by: The collections that follow the profile.
        """
        provider = record and record.get("embed_provider")
        model = record and record.get("embed_model")
        if record and provider and model:
            embedding = {
                "provider": provider,
                "model": model,
                "source": "profile",
                "dimensions": record.get("embed_dimensions"),
            }
        else:
            host = self._host()
            embedding = {
                "provider": host.provider,
                "model": host.model,
                "source": "server_default",
                "dimensions": None,
            }
        holding = [] if record is None else [s for s in self._states(used_by) if s.holds_vectors]
        lock = {"locked": bool(holding), "collections": [_described(s) for s in holding]}
        return {"embedding": embedding, "embedding_lock": lock}

    # ── Saving ──────────────────────────────────────────────────────

    def save(self, profile_id: str, provider: str | None, model: str | None) -> None:
        """Check the model, then save it for a user profile if the lock allows.

        Args:
            profile_id: A user profile id.
            provider: The embedding provider, or ``None`` for the server default.
            model: The model name, or ``None`` for the server default.

        Raises:
            BuiltinProfileError: For a built-in profile.
            UnknownProfileError: If the profile does not exist or was deleted.
            ValueError: If only one of provider and model is set.
            compose_embedding.UnknownEmbeddingProviderError: For an unregistered provider.
            EmbeddingCheckFailedError: With the reason, if the check fails.
            EmbeddingLockedError: With the blocking collections, if the lock refuses.
        """
        from .compose_profiles import BuiltinProfileError

        service = self._service
        if profile_id in BUILTIN_PROFILES:
            raise BuiltinProfileError("Duplicate the profile to choose another model.")
        service._user_record(profile_id)
        if (provider is None) != (model is None):
            raise ValueError("Send the provider and the model together, or neither.")
        dimensions: int | None = None
        if provider is None or model is None:
            requested = self._host()
        else:
            model = model.strip()
            result = compose_embedding.check_embedding_model(
                provider, model, redact=service._engine.redact
            )
            if not result["ok"]:
                raise EmbeddingCheckFailedError(result["reason"])
            dimensions = result["dimensions"]
            requested = EmbeddingIdentity(provider, model)
        with service.lock, write_lock:
            record = service._user_record(profile_id)
            used_by = service._used_by(profile_id, dict(service._collection_tags()))
            blockers = blocking_collections(self._states(used_by), requested)
            if blockers:
                raise EmbeddingLockedError([_described(s) for s in blockers])
            service._profiles.set_profile_embedding(
                record["profile_id"], provider=provider, model=model, dimensions=dimensions
            )

    # ── Binding ─────────────────────────────────────────────────────

    def check_binding(self, profile_id: str, collection: str) -> None:
        """Refuse a profile whose model differs from the collection's stamp.

        Raises:
            EmbeddingMismatchError: With a message that names both models.
        """
        store = self._store()
        if store is None:
            return
        choice: EmbeddingIdentity | None = None
        if profile_id not in BUILTIN_PROFILES:
            try:
                record = self._service._user_record(profile_id)
            except KeyError:
                return
            if record.get("embed_provider") and record.get("embed_model"):
                choice = EmbeddingIdentity(record["embed_provider"], record["embed_model"])
        state = collection_embedding_state(store, collection)
        message = binding_refusal(state, choice, self._host())
        if message:
            raise EmbeddingMismatchError(message)
