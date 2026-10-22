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

from collections.abc import Iterable
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


def embedding_identity_from_settings(settings: Any) -> EmbeddingIdentity:
    """Derive the :class:`EmbeddingIdentity` stamped into collections.

    Shared by the settings-driven factories registered in the
    vector-store registry (``chroma`` and ``lancedb``).  The provider
    is the effective concrete backend (two-tier aliases resolved); the
    model is that backend's model field.  Production has no corpus
    identity, so ``index_identity`` stays ``None``.

    The config import is lazy and function-scoped, matching the
    ``core/providers/common.py`` precedent: the settings object
    arrives as a parameter, never as a singleton read.

    Args:
        settings: A resolved ``omrs.config.Settings`` instance.

    Returns:
        The identity to stamp into and enforce on collections written
        through the constructed store.
    """
    from ...config import _resolve_effective_embed_provider

    provider = _resolve_effective_embed_provider(settings)
    model_fields = {
        "llamacpp": settings.llamacpp_embed_model,
        "ollama": settings.embed_model,
        "openrouter": settings.openrouter_embed_model,
    }
    model = model_fields.get(provider, settings.embed_model)
    return EmbeddingIdentity(provider=provider, model=model, index_identity=None)


def write_identity(
    override: EmbeddingIdentity | None,
    composed: EmbeddingIdentity | None,
    embed_model: Any,
) -> EmbeddingIdentity:
    """Return the identity a write validates and stamps with.

    A per-call *override* wins over the store's *composed* identity. Direct
    calls with neither fall back to a diagnostic identity named after the
    embedder, which is used for error text only.
    """
    return (
        override
        or composed
        or EmbeddingIdentity(
            provider=type(embed_model).__name__,
            model=str(getattr(embed_model, "model_name", type(embed_model).__name__)),
        )
    )


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


def redact_secrets(message: str, secrets: Iterable[str | None]) -> str:
    """Redact every secret in *secrets* from *message*.

    Every full value and every prefix of six or more characters goes into one
    list, longest piece first. Two keys of one provider often share a prefix
    such as ``sk-ant-api03-``. Removing one key's short prefix first would
    leave the rest of a cut-off piece of the other key in the text.

    Args:
        message: Raw message text.
        secrets: Secret values. Blank and ``None`` entries are skipped.

    Returns:
        The redacted message.
    """
    pieces: set[str] = set()
    for secret in {s for s in secrets if s}:
        pieces.add(secret)
        pieces.update(secret[:length] for length in range(_MIN_REDACTED_PREFIX_LEN, len(secret)))
    for piece in sorted(pieces, key=len, reverse=True):
        message = message.replace(piece, "***")
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


@dataclass(frozen=True)
class RedactionSecrets:
    """Credential values to remove from error text.

    Held by the Engine (not by ``EffectiveSettings``, which stays pure data)
    so every transport redacts the same values.

    Attributes:
        chroma_cloud_api_key: Chroma Cloud API key.
        chroma_cloud_tenant: Chroma Cloud tenant identifier.
        chroma_cloud_database: Chroma Cloud database name.
        provider_keys: The LLM provider API keys in use (OpenRouter, the
            OpenAI-compatible server, Anthropic and any later provider).
        retired_provider_keys: Earlier provider keys. A call that began
            with an old key can still fail with it in the error text, so
            the Engine keeps every key it has held (append-only).
    """

    chroma_cloud_api_key: str = ""
    chroma_cloud_tenant: str = ""
    chroma_cloud_database: str = ""
    provider_keys: tuple[str, ...] = ()
    retired_provider_keys: tuple[str, ...] = ()

    def redact(self, text: str) -> str:
        """Remove each value and each prefix of six or more characters."""
        text = redact_cloud_secrets(
            text,
            self.chroma_cloud_api_key,
            self.chroma_cloud_tenant,
            self.chroma_cloud_database,
        )
        return redact_secrets(text, (*self.retired_provider_keys, *self.provider_keys))


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

    def _check_or_stamp_identity(
        self, collection: Any, identity: EmbeddingIdentity | None = None
    ) -> None:
        """Write-path rule: stamp legacy collections, reject mismatches.

        ``identity`` replaces the composed identity for this call (ADR-081).
        """
        active = identity or self._identity
        if active is None:
            return
        stored = read_stored_identity(collection)
        if stored[0] is None:
            stamp_collection_identity(collection, active)
            return
        self._reject_identity_mismatch(collection.name, stored, active)

    def _guard_query_identity(
        self,
        collection_name: str,
        collection: Any,
        identity: EmbeddingIdentity | None = None,
    ) -> None:
        """Query-path rule: reject mismatches before the query is issued.

        Legacy collections without identity metadata query normally;
        stamping never happens on the read path so read-only
        evaluation workers never mutate a shared collection.
        ``identity`` replaces the composed identity for this call.
        """
        active = identity or self._identity
        if active is None:
            return
        stored = read_stored_identity(collection)
        if stored[0] is not None:
            self._reject_identity_mismatch(collection_name, stored, active)

    def _reject_identity_mismatch(
        self,
        collection_name: str,
        stored: tuple[str | None, str | None, str | None],
        identity: EmbeddingIdentity | None = None,
    ) -> None:
        """Raise unless the stored identity matches the active one."""
        active = identity or self._identity
        if active is None or identities_match(stored, active):
            return
        raise build_identity_mismatch_error(collection_name, stored, active)
