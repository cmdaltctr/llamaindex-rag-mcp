"""The public Engine — owns its composition and operates on it.

An Engine owns its vector store, embedder, reranker, profile resolver and
effective settings for its own lifetime. It constructs nothing — the
composition root (``compose.build_engine()``) constructs the dependencies
and returns an Engine owning them. Two engines with different
configurations coexist in one process without interfering.

Construction (direct or via ``from_environment()``) mutates no
process-global state. The legacy server startup path
(``compose.ensure_runtime_setup()``) builds an engine via the same
factory and then installs it as the process default.
"""

from __future__ import annotations

import collections
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from llama_index.core.embeddings import BaseEmbedding

    from .core.profiles.resolver import ProfileResolver
    from .core.retrieval.reranker import CrossEncoderReranker
    from .core.settings import EffectiveSettings
    from .core.vectordb.base import VectorStore

logger = logging.getLogger(__name__)

_QUERY_EMBED_CACHE_MAXSIZE = 128


class Engine:
    """Owns its providers, store and settings for its lifetime.

    Construct via ``Engine.from_environment()`` or directly with
    already-composed dependencies. The constructor accepts
    already-composed dependencies and constructs nothing itself.

    Public surface:
        - ``ingest(path, ...)`` — async, returns the ingestion result dict
        - ``search(query, ...)`` — sync, returns list[dict] hits
        - ``answer(question, ...)`` — async, returns the answer result dict
        - ``list_collections()`` — sync, returns list[str]
        - ``delete_collection(name)`` — sync
        - ``close()`` — sync
    """

    def __init__(
        self,
        effective_settings: EffectiveSettings,
        *,
        store: VectorStore,
        embed_model: BaseEmbedding,
        reranker: CrossEncoderReranker | None = None,
        profile_resolver: ProfileResolver | None = None,
        profile_resolver_factory: Callable[[], ProfileResolver] | None = None,
        answer_llm_factory: Callable[[], Any] | None = None,
        verify_llm_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        """Own already-composed dependencies; construct nothing.

        Args:
            effective_settings: The server-default :class:`EffectiveSettings`.
            store: The composed :class:`VectorStore`.
            embed_model: The composed LlamaIndex embedding model.
            reranker: Optional pre-constructed reranker.
            profile_resolver: Optional pre-constructed :class:`ProfileResolver`.
            profile_resolver_factory: Optional callable returning a
                :class:`ProfileResolver` (resolved lazily on first use
                so ``build_engine`` does not eagerly construct it).
            answer_llm_factory: Optional callable returning the answer LLM
                (resolved lazily on first ``answer()`` call; construction
                errors propagate to the caller).
            verify_llm_factory: Optional callable taking an answer block
                and returning the verify LLM (a construction failure
                degrades to ``verification_skipped``, never an error).
        """
        self._effective_settings = effective_settings
        self._store = store
        self._embed_model = embed_model
        self._reranker = reranker
        self._profile_resolver = profile_resolver
        self._profile_resolver_factory = profile_resolver_factory
        self._answer_llm_factory = answer_llm_factory
        self._verify_llm_factory = verify_llm_factory
        self._answer_llm: Any = None
        # Engine-owned query embedding cache: keyed by (query, model_name),
        # shared between filtered/unfiltered search within this engine,
        # never between engines, dropped on close().
        self._query_cache: collections.OrderedDict = collections.OrderedDict()
        self._closed = False

    # ── Construction ───────────────────────────────────────────────

    @classmethod
    def from_environment(cls) -> Engine:
        """Construct an Engine from environment settings.

        Delegates to ``compose.build_engine()`` (side-effect-free: no
        process-global state is installed).
        """
        from .compose import build_engine

        return build_engine()

    # ── Public operations ──────────────────────────────────────────

    async def ingest(
        self,
        path: str,
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        progress_callback: Any = None,
        collection_name: str = "documents",
    ) -> dict:
        """Index a file or directory into the engine's store."""
        self._check_open()
        from .core.ingestion.pipeline import ingest_path_async

        effective = self._resolve_settings(collection_name)
        return await ingest_path_async(
            path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            progress_callback=progress_callback,
            collection_name=collection_name,
            effective_settings=effective,
            store=self._store,
            embed_model=self._embed_model,
        )

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        rerank: bool | None = None,
        hybrid: bool | None = None,
        expand_window: int = 0,
        collection_name: str = "documents",
        metadata_filter: dict | None = None,
        include_diagnostics: bool = False,
        technical_fraction: float | None = None,
        fetch_k: int | None = None,
    ) -> list[dict]:
        """Run a semantic similarity search over indexed documents."""
        self._check_open()
        from .core.retrieval.pipeline import search

        effective = self._resolve_settings(collection_name)
        return search(
            query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            rerank=rerank,
            hybrid=hybrid,
            expand_window=expand_window,
            collection_name=collection_name,
            metadata_filter=metadata_filter,
            include_diagnostics=include_diagnostics,
            technical_fraction=technical_fraction,
            fetch_k=fetch_k,
            reranker=self._reranker,
            store=self._store,
            effective_settings=effective,
            embed_model=self._embed_model,
            query_cache=self._query_cache,
        )

    async def answer(
        self,
        question: str,
        *,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        rerank: bool | None = None,
        hybrid: bool | None = None,
        expand_window: int = 0,
        collection_name: str = "documents",
        metadata_filter: dict | None = None,
        include_diagnostics: bool = False,
    ) -> dict:
        """Answer a question from retrieved evidence with verifiable citations."""
        self._check_open()
        from .core.answer.pipeline import answer as core_answer

        effective = self._resolve_settings(collection_name)

        # Lazily build the answer LLM on first use.
        complete = None
        if self._answer_llm is None and self._answer_llm_factory is not None:
            self._answer_llm = self._answer_llm_factory()
        if self._answer_llm is not None:
            complete = self._server_seam(self._answer_llm)

        # Build the verify LLM if claim verification is enabled. A
        # construction failure degrades to verification_skipped with the
        # redacted provider diagnostic retained (ADR-059); a None result
        # keeps the plain no-judge reason.
        verify_complete = None
        verify_unavailable_reason = None
        if getattr(effective.answer, "verify_claims", False):
            if self._verify_llm_factory is not None:
                try:
                    verify_llm = self._verify_llm_factory(effective.answer)
                except Exception as exc:
                    verify_unavailable_reason = (
                        "verification provider unavailable: "
                        f"{type(exc).__name__}: {self._redact_error(exc, effective)}"
                    )
                else:
                    if verify_llm is not None:
                        verify_complete = self._server_seam(verify_llm)
                    else:
                        verify_unavailable_reason = (
                            "verification provider unavailable (no judge configured)"
                        )

        return await core_answer(
            question,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            rerank=rerank,
            hybrid=hybrid,
            expand_window=expand_window,
            collection_name=collection_name,
            metadata_filter=metadata_filter,
            include_diagnostics=include_diagnostics,
            complete=complete,
            verify_complete=verify_complete,
            verify_unavailable_reason=verify_unavailable_reason,
            completion_source="server",
            reranker=self._reranker,
            store=self._store,
            effective_settings=effective,
            embed_model=self._embed_model,
            query_cache=self._query_cache,
        )

    def list_collections(self) -> list[str]:
        """Return every collection name in the engine's store."""
        self._check_open()
        from .core.retrieval.pipeline import list_collections as core_list

        collections = core_list(store=self._store)
        return [c["name"] for c in collections]

    def delete_collection(self, name: str) -> None:
        """Permanently delete a collection and all of its rows."""
        self._check_open()
        self._store.delete_collection(name)

    def close(self) -> None:
        """Release this engine's resources; reject further use.

        Closes the owned store (a store ``close()`` failure is logged
        and does not stop the release), drops the query-embedding
        cache, evicts only the BM25 cache entries in this store's
        identity namespace, and releases the owned embedder, reranker,
        answer model and factory references (ADR-061). Never touches
        process-wide ingestion coordination state. Other engines and
        shared process-wide model caches remain functional. Idempotent.
        """
        if self._closed:
            return
        self._closed = True
        # Drop the engine-owned query embedding cache.
        self._query_cache.clear()
        # Evict BM25 cache entries for this store's identity only.
        from .core.retrieval.sparse import evict_bm25_cache

        evict_bm25_cache(self._store.cache_identity)
        # Close the owned store; a failure is logged, not raised, so the
        # reference release below always completes.
        try:
            self._store.close()
        except Exception as exc:
            logger.warning(
                "store close() failed during engine close: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
        # Release owned references (ADR-061: the embedder reference must
        # go so a closed engine never pins model resources). Shared
        # process-wide caches (reranker model cache) are untouched.
        self._store = None  # type: ignore[assignment]
        self._embed_model = None  # type: ignore[assignment]
        self._reranker = None
        self._profile_resolver = None
        self._profile_resolver_factory = None
        self._answer_llm = None
        self._answer_llm_factory = None
        self._verify_llm_factory = None

    # ── Internal helpers ───────────────────────────────────────────

    def _check_open(self) -> None:
        """Reject operations on a closed engine.

        Raises:
            RuntimeError: When the engine has been closed.
        """
        if self._closed:
            raise RuntimeError("Engine is closed; construct a new Engine for further operations.")

    @staticmethod
    def _redact_error(exc: BaseException, effective: Any) -> str:
        """Format *exc* without leaking credential material."""
        from .core.vectordb.identity import redact_cloud_secrets, redact_secret

        detail = str(exc)
        detail = redact_cloud_secrets(
            detail,
            getattr(effective, "chroma_cloud_api_key", "") or "",
            getattr(effective, "chroma_cloud_tenant", "") or "",
            getattr(effective, "chroma_cloud_database", "") or "",
        )
        return redact_secret(detail, getattr(effective, "openrouter_api_key", "") or "")

    def _resolve_settings(self, collection_name: str) -> EffectiveSettings:
        """Resolve effective settings for a collection via the profile resolver.

        The profile resolver is constructed lazily from its factory on
        first use so ``build_engine`` does not eagerly construct it.
        Resolution errors propagate: an invalid collection profile tag
        is a configuration error, not an absent optional capability.
        """
        if self._profile_resolver is None and self._profile_resolver_factory is not None:
            self._profile_resolver = self._profile_resolver_factory()
        if self._profile_resolver is not None:
            return self._profile_resolver.resolve(collection_name)
        return self._effective_settings

    def _install_as_process_default(self) -> None:
        """Install this engine's components as process defaults (legacy transports).

        Called only by ``compose.ensure_runtime_setup()``. The builder
        itself never installs; this method is the installer over the
        built engine.
        """
        from llama_index.core import Settings as LlamaIndexSettings

        from .core.settings import set_default_effective_settings
        from .core.vectordb import set_default_store

        LlamaIndexSettings.embed_model = self._embed_model
        set_default_store(self._store)
        set_default_effective_settings(self._effective_settings)

    @staticmethod
    def _server_seam(llm: Any) -> Any:
        """Adapt the composition-root LLM to the core async completion seam."""

        async def seam(prompt: str) -> str:
            completion = await llm.acomplete(prompt)
            return completion.text

        return seam
