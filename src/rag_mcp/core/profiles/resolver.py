"""Profile resolver — maps collection → effective Tier 2 levers.

The :class:`ProfileResolver` is the runtime component that resolves which
profile applies to a given collection at operation time.  It reads the
collection's metadata tag through the Phase 3 :class:`VectorStore`
interface, loads the named profile bundle (cached), and returns an
:class:`EffectiveSettings` bundle of Tier 2 levers.

Resolution rules (spec: profiles-dual-use-case):

1.  A collection with ``metadata={"profile": "codebase"}`` resolves to
    the codebase profile.
2.  A collection with no profile tag inherits the server-wide default
    (``RAG_PROFILE``).
3.  When ``RAG_PROFILE=hybrid``, an untagged collection resolves to
    ``hybrid.yaml``'s ``default_profile`` (never to ``hybrid`` itself).
4.  A collection tagged ``hybrid`` is rejected — hybrid is a mode
    selector, not an operational profile.
5.  A collection tagged with a non-existent profile name is rejected
    listing available profiles.

Tier classification (design D1):

* **Tier 1** (constructed once at startup in ``compose.py``): embedder,
  chunking/reader registries, vector store handle, reranker model.
* **Tier 2** (resolved per operation by this resolver): reranker toggle,
  ``top_k``, hybrid/RRF, chunking fallback, taxonomy mode.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ...config import _load_profile_bundle
from ..ingestion.settings import parse_extension_set
from ..settings import EffectiveSettings
from ..vectordb import get_default_store
from ..vectordb.base import VectorStore

logger = logging.getLogger(__name__)

# Operational profiles that carry concrete retrieval settings.
OPERATIONAL_PROFILES: frozenset[str] = frozenset({"documents", "codebase"})


def _parse_profile_bool(value: Any) -> bool:
    """Parse a profile bundle boolean using legacy ``.lower() == "true"``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _bundle_to_effective(
    profile_name: str,
    bundle: dict[str, Any],
    base: EffectiveSettings | None = None,
) -> EffectiveSettings:
    """Overlay a raw profile bundle's Tier 2 levers onto *base*.

    Environment variables override the profile bundle values for Tier 2
    levers, preserving the "env still wins" precedence established by
    the startup Settings resolver.

    Validates each lever value and raises a clear error naming the
    offending key if validation fails.

    Args:
        profile_name: The operational profile name (``documents`` or
            ``codebase``).
        bundle: Raw key-value dict from the YAML bundle.
        base: Server-default :class:`EffectiveSettings` to overlay onto,
            supplied by ``compose.py``.  Only the profile-owned levers are
            replaced; every other field is inherited.  When ``None``, class
            defaults are used — correct only for tests that assert on
            levers alone.

    Returns:
        Frozen :class:`EffectiveSettings` instance.
    """
    # Tier 2 lever env overrides (env still wins over the profile bundle).
    # The bundle is nested (v2.0.0), and env vars use the nested delimiter.
    retrieval = bundle.get("retrieval", {}) or {}
    chunking = bundle.get("chunking", {}) or {}
    metadata = bundle.get("metadata", {}) or {}
    ingestion = bundle.get("ingestion", {}) or {}
    answer = bundle.get("answer", {}) or {}

    raw_top_k = os.environ.get("RETRIEVAL__TOP_K", retrieval.get("top_k", 10))
    try:
        top_k = int(raw_top_k)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Profile {profile_name!r} has invalid retrieval.top_k={raw_top_k!r}: "
            f"must be an integer ({exc})"
        ) from exc

    reranker_enabled = _parse_profile_bool(
        os.environ.get("RETRIEVAL__RERANK_ENABLED", retrieval.get("rerank_enabled", False))
    )
    hybrid_enabled = _parse_profile_bool(
        os.environ.get("RETRIEVAL__HYBRID_ENABLED", retrieval.get("hybrid_enabled", False))
    )
    chunk_strategy_fallback = str(
        os.environ.get(
            "CHUNKING__STRATEGY_FALLBACK",
            chunking.get("strategy_fallback", "markdown"),
        )
    )
    metadata_taxonomy_mode = str(
        os.environ.get("METADATA__TAXONOMY_MODE", metadata.get("taxonomy_mode", "category"))
    )

    # Validate taxonomy mode against known values.
    if metadata_taxonomy_mode not in ("category", "file_type"):
        raise ValueError(
            f"Profile {profile_name!r} has invalid metadata.taxonomy_mode="
            f"{metadata_taxonomy_mode!r}: must be 'category' or 'file_type'"
        )

    # Overlay ONLY the profile-owned levers onto the server-default base
    # (task 4.4).  Every field the profile does not own — chroma_persist_dir,
    # embed_model, chunk sizes, concurrency, backends — MUST be inherited
    # from *base*, not reset to class defaults.  Constructing a fresh
    # EffectiveSettings here would silently discard the operator's .env.
    if base is None:
        base = EffectiveSettings()

    # The ingestible extension set is profile-scoped (design D4): the
    # bundle value (a YAML list), the env override (comma-separated or a
    # JSON array string), or the server-default base set — in that order.
    resolved_extensions = parse_extension_set(
        os.environ.get(
            "INGESTION__INGEST_EXTENSIONS",
            ingestion.get("ingest_extensions", base.ingestion.ingest_extensions),
        )
    )

    # Claim verification (ADR-059): the three verify fields are the one
    # answer-block carve-out that IS profile-overlaid.  Precedence matches
    # every other Tier 2 lever: env wins over the bundle, the bundle wins
    # over the server-default base.  Everything else on the answer block
    # stays server-level configuration.
    verify_claims = _parse_profile_bool(
        os.environ.get(
            "ANSWER__VERIFY_CLAIMS", answer.get("verify_claims", base.answer.verify_claims)
        )
    )
    verify_model = str(
        os.environ.get("ANSWER__VERIFY_MODEL", answer.get("verify_model", base.answer.verify_model))
    )
    verify_provider = str(
        os.environ.get(
            "ANSWER__VERIFY_PROVIDER",
            answer.get("verify_provider", base.answer.verify_provider),
        )
    )

    return base.model_copy(
        update={
            "profile_name": profile_name,
            "chunking": base.chunking.model_copy(
                update={"strategy_fallback": chunk_strategy_fallback}
            ),
            "ingestion": base.ingestion.model_copy(
                update={"ingest_extensions": resolved_extensions}
            ),
            "retrieval": base.retrieval.model_copy(
                update={
                    "top_k": top_k,
                    "rerank_enabled": reranker_enabled,
                    "hybrid_enabled": hybrid_enabled,
                }
            ),
            "metadata": base.metadata.model_copy(update={"taxonomy_mode": metadata_taxonomy_mode}),
            "answer": base.answer.model_copy(
                update={
                    "verify_claims": verify_claims,
                    "verify_model": verify_model,
                    "verify_provider": verify_provider,
                }
            ),
        }
    )


class ProfileResolver:
    """Maps ``collection_name → EffectiveSettings`` at operation time.

    Reads collection metadata tags through the :class:`VectorStore`
    interface and resolves the applicable profile bundle.  Bundle loading
    is cached per profile name so repeated operations against the same
    collection do not re-read YAML.

    Construction is cheap — the resolver holds no Tier 1 state.  The
    expensive objects (reranker model, embedder) are constructed once in
    ``compose.py`` and injected into operations separately.
    """

    def __init__(
        self,
        store: VectorStore | None = None,
        server_profile: str | None = None,
        base: EffectiveSettings | None = None,
    ) -> None:
        """Initialise the resolver.

        Args:
            store: Optional :class:`VectorStore` for reading collection
                metadata.  Defaults to the process-wide store.
            server_profile: The server-wide default profile name
                (``RAG_PROFILE``).  Supplied by ``compose.py`` via
                injection (task 4.5); when ``None``, falls back to the
                composition root's default ``EffectiveSettings``.
            base: Server-default :class:`EffectiveSettings` that resolved
                profiles overlay their Tier 2 levers onto (task 4.4).
                Supplied by ``compose.build_profile_resolver()``.  When
                ``None``, class defaults are used — every non-lever field
                would then ignore the operator's configuration, so
                production callers MUST supply it.
        """
        self._store = store
        self._server_profile = server_profile
        self._base = base
        self._cache: dict[str, EffectiveSettings] = {}

    # ── Public API ──────────────────────────────────────────────────

    def resolve(self, collection_name: str) -> EffectiveSettings:
        """Resolve the effective settings for a collection.

        Args:
            collection_name: The target ChromaDB collection name.

        Returns:
            Frozen :class:`EffectiveSettings` for this collection.

        Raises:
            ValueError: If the collection's profile tag is ``hybrid``
                (mode selector, not operational) or names a non-existent
                profile.
        """
        store = self._get_store()
        server_profile = self._get_server_profile()

        # Read the collection's profile tag from metadata.
        tag = self._read_collection_tag(store, collection_name)

        if tag is None:
            # No tag → inherit server default.
            profile = server_profile
            if profile == "hybrid":
                profile = self._resolve_hybrid_default()
        else:
            profile = tag

        # Validate the resolved profile name.
        self._validate_profile(profile, tag, collection_name)

        return self._load_effective(profile)

    def resolve_profile_name(self, collection_name: str) -> str:
        """Resolve just the operational profile name for a collection.

        Convenience method for the safety-contract generator and
        diagnostics that need the name without loading the full bundle.

        Returns:
            The operational profile name (``documents`` or ``codebase``).

        Raises:
            ValueError: If the tag is invalid.
        """
        store = self._get_store()
        server_profile = self._get_server_profile()
        tag = self._read_collection_tag(store, collection_name)

        if tag is None:
            profile = server_profile
            if profile == "hybrid":
                profile = self._resolve_hybrid_default()
        else:
            profile = tag

        self._validate_profile(profile, tag, collection_name)
        return profile

    # ── Internal helpers ────────────────────────────────────────────

    def _get_store(self) -> VectorStore:
        """Return the injected store or the process-wide default."""
        return self._store if self._store is not None else get_default_store()

    def _get_server_profile(self) -> str:
        """Return the server-wide default profile name.

        Uses the injected ``server_profile`` constructor argument (task 4.5).
        Falls back to the resolved settings singleton only when no profile
        was injected — this fallback is removed in group 5 when the global
        is deleted.
        """
        if self._server_profile is not None:
            return self._server_profile
        # No injected profile: fall back to the composition root's default
        # EffectiveSettings rather than the config singleton (task 5.7).
        # Production always injects — see compose.build_profile_resolver().
        from ..settings import get_default_effective_settings

        return get_default_effective_settings().rag_profile

    def _read_collection_tag(self, store: VectorStore, collection_name: str) -> str | None:
        """Read the ``profile`` key from collection metadata.

        Returns ``None`` when the collection has no metadata or no
        ``profile`` key (the backward-compatible inheritance path).
        """
        try:
            meta = store.get_collection_metadata(collection_name)
        except Exception as exc:
            logger.debug(
                "Could not read metadata for collection %r: %s — "
                "treating as untagged (inherits server default)",
                collection_name,
                exc,
            )
            return None

        if not isinstance(meta, dict):
            return None
        tag = meta.get("profile")
        if isinstance(tag, str) and tag:
            return tag
        return None

    def _resolve_hybrid_default(self) -> str:
        """Resolve hybrid.yaml's ``default_profile`` to an operational name."""
        # _load_profile_bundle resolves hybrid → default_profile's bundle,
        # so read the raw hybrid.yaml for the default_profile key.
        try:
            from importlib.resources import files

            import yaml

            yaml_path = files("rag_mcp.config") / "profiles" / "hybrid.yaml"
            with yaml_path.open("r") as fh:
                raw = yaml.safe_load(fh)
            if isinstance(raw, dict):
                default = raw.get("default_profile", "documents")
                if default in OPERATIONAL_PROFILES:
                    return default
        except Exception:  # noqa: S110
            pass
        return "documents"

    def _validate_profile(self, profile: str, tag: str | None, collection_name: str) -> None:
        """Validate the resolved profile name.

        Args:
            profile: The resolved operational profile name.
            tag: The original collection metadata tag (for error messages).
            collection_name: Collection name (for error context).

        Raises:
            ValueError: If the profile is ``hybrid`` (rejected as an
                operational profile) or not in ``OPERATIONAL_PROFILES``.
        """
        if profile == "hybrid":
            raise ValueError(
                f"Collection {collection_name!r} is tagged "
                f"profile={tag!r}, but 'hybrid' is a mode selector, not "
                f"an operational profile. Tag the collection with "
                f"'documents' or 'codebase' instead."
            )

        if profile not in OPERATIONAL_PROFILES:
            available = ", ".join(sorted(OPERATIONAL_PROFILES))
            raise ValueError(
                f"Collection {collection_name!r} has an invalid profile "
                f"tag {tag!r}. Available profiles: {available}"
            )

    def _load_effective(self, profile_name: str) -> EffectiveSettings:
        """Load and cache the :class:`EffectiveSettings` for a profile.

        Bundle loading is cached per profile name so repeated operations
        against the same collection do not re-read YAML.
        """
        if profile_name in self._cache:
            return self._cache[profile_name]

        bundle = _load_profile_bundle(profile_name)
        if not bundle:
            # Graceful degradation: if the bundle is missing, fall back
            # to field defaults via an empty bundle.
            logger.warning(
                "Profile bundle %r could not be loaded — using field "
                "defaults. Check that config/profiles/%s.yaml exists.",
                profile_name,
                profile_name,
            )
            bundle = {}

        effective = _bundle_to_effective(profile_name, bundle, self._base)
        self._cache[profile_name] = effective
        return effective
