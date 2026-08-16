"""Embedding-identity metadata for Chroma collections.

A collection's vector space belongs to exactly one embedding
configuration.  Vector dimensions alone cannot prove compatibility —
two distinct 1024-dim models embed incompatible spaces — so the
provider, model, and immutable index identity are stamped into
collection metadata on first write and verified before every
subsequent write/query.

The guard is a mixin: :class:`ChromaVectorStore` supplies the
``_identity`` attribute (``None`` disables enforcement entirely, the
pre-cloud behaviour) and collection handles; this module owns the
read-merge-write stamping and the mismatch rejection. It also provides
pure helpers that redact configured Chroma Cloud connection values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Collection metadata keys recording the embedding configuration that
# produced a collection.
IDENTITY_PROVIDER_KEY = "rag_embed_provider"
IDENTITY_MODEL_KEY = "rag_embed_model"
IDENTITY_INDEX_KEY = "rag_index_identity"
_MIN_REDACTED_PREFIX_LEN = 6


@dataclass(frozen=True)
class EmbeddingIdentity:
    """The embedding configuration that owns a collection's vector space.

    Attributes:
        provider: Effective embedding backend (``llamacpp``,
            ``openrouter``...).
        model: Embedding model identifier.
        index_identity: Optional immutable index identity (corpus/config
            hash or the derived collection name).
    """

    provider: str
    model: str
    index_identity: str | None = None


def redact_secret(message: str, secret: str | None) -> str:
    """Redact a full secret and each prefix of six or more characters.

    Cloud errors can echo submitted credentials or truncated fragments.
    The full value is always removed. Longer prefixes are removed first
    so no useful credential fragment remains in logs or client responses.

    Args:
        message: Raw message text.
        secret: Secret to redact; empty/None returns the message unchanged.

    Returns:
        The redacted message.
    """
    if not secret:
        return message
    message = message.replace(secret, "***")
    for length in range(len(secret) - 1, _MIN_REDACTED_PREFIX_LEN - 1, -1):
        message = message.replace(secret[:length], "***")
    return message


def redact_cloud_secrets(
    message: str,
    api_key: str | None,
    tenant: str | None,
    database: str | None,
) -> str:
    """Redact configured Chroma Cloud connection values from a message."""
    for value in (api_key, tenant, database):
        message = redact_secret(message, value)
    return message


def read_stored_identity(collection: Any) -> tuple[str | None, str | None, str | None]:
    """Return the ``(provider, model, index_identity)`` stored on a collection.

    A collection without identity metadata (pre-cloud local indexes)
    yields ``(None, None, None)`` and is treated as legacy.
    """
    metadata = collection.metadata or {}
    return (
        metadata.get(IDENTITY_PROVIDER_KEY),
        metadata.get(IDENTITY_MODEL_KEY),
        metadata.get(IDENTITY_INDEX_KEY),
    )


def stamp_collection_identity(collection: Any, identity: EmbeddingIdentity) -> None:
    """Stamp ``identity`` into collection metadata (read-merge-write).

    Chroma's ``modify(metadata=...)`` replaces the complete map, so
    existing keys such as profile tags are read and merged first —
    a bare write would silently drop them.
    """
    stamp: dict[str, str] = {
        IDENTITY_PROVIDER_KEY: identity.provider,
        IDENTITY_MODEL_KEY: identity.model,
    }
    if identity.index_identity is not None:
        stamp[IDENTITY_INDEX_KEY] = identity.index_identity
    merged = dict(collection.metadata or {})
    if all(merged.get(key) == value for key, value in stamp.items()):
        return
    merged.update(stamp)
    collection.modify(metadata=merged)


def identities_match(
    stored: tuple[str | None, str | None, str | None],
    active: EmbeddingIdentity,
) -> bool:
    """Return whether a stored identity triple matches the active identity.

    Provider and model must match exactly.  The index identity is
    compatible when either side omits it (the active side extends the
    index) and incompatible only when both supply differing values —
    the same model over a different corpus is a different index.
    """
    stored_provider, stored_model, stored_index = stored
    index_differs = (
        stored_index is not None
        and active.index_identity is not None
        and stored_index != active.index_identity
    )
    return stored_provider == active.provider and stored_model == active.model and not index_differs


def build_identity_mismatch_error(
    collection_name: str,
    stored: tuple[str | None, str | None, str | None],
    active: EmbeddingIdentity,
) -> ValueError:
    """Build the rejection error for an identity mismatch.

    Callers must gate with :func:`identities_match` first.  A dimension
    match proves nothing: two distinct models with the same output
    width embed incompatible spaces.
    """
    stored_provider, stored_model, stored_index = stored
    return ValueError(
        f"Collection {collection_name!r} was indexed with embedding "
        f"provider={stored_provider!r}, model={stored_model!r}"
        + (f", index_identity={stored_index!r}" if stored_index else "")
        + f", but the active configuration is provider={active.provider!r}, "
        f"model={active.model!r}"
        + (f", index_identity={active.index_identity!r}" if active.index_identity else "")
        + ". Matching vector dimensions do not prove embedding-space "
        "compatibility; create a fresh collection (re-ingest) for this "
        "configuration."
    )


class IdentityGuardMixin:
    """Write/query-path embedding-identity enforcement.

    The concrete store supplies ``self._identity``
    (:class:`EmbeddingIdentity` or ``None``).  ``None`` disables all
    stamping and checks, preserving the pre-cloud direct-call behaviour.
    """

    # Supplied by the concrete store.
    _identity: EmbeddingIdentity | None

    def _check_or_stamp_identity(self, collection: Any) -> None:
        """Write-path rule: stamp legacy collections, reject mismatches."""
        if self._identity is None:
            return
        stored = read_stored_identity(collection)
        if stored[0] is None:
            stamp_collection_identity(collection, self._identity)
            return
        self._reject_identity_mismatch(collection.name, stored)

    def _guard_query_identity(self, collection_name: str, collection: Any) -> None:
        """Query-path rule: reject mismatches before the query is issued.

        Legacy collections without identity metadata query normally;
        stamping never happens on the read path so read-only
        evaluation workers never mutate a shared collection.
        """
        if self._identity is None:
            return
        stored = read_stored_identity(collection)
        if stored[0] is not None:
            self._reject_identity_mismatch(collection_name, stored)

    def _reject_identity_mismatch(
        self,
        collection_name: str,
        stored: tuple[str | None, str | None, str | None],
    ) -> None:
        """Raise unless the stored identity matches the active one."""
        identity = self._identity
        if identity is None or identities_match(stored, identity):
            return
        raise build_identity_mismatch_error(collection_name, stored, identity)
