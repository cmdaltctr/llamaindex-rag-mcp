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

from . import engine_profiles
from .compose_pipelines import EnginePipelines
from .core.vectordb.identity import RedactionSecrets
from .engine_answer import ClientCompletion, build_verifier, select_completion
from .engine_embedders import EngineEmbedders, definition_collection, embedding_for
from .engine_lifecycle import (
    graph_host,
    install_as_process_default,
    release_resources,
    resolve_bound,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from llama_index.core.embeddings import BaseEmbedding

    from .core.answer.pipeline import ResolvedRetrieval
    from .core.pipelines import (
        AdmissionSnapshot,
        CancellationToken,
        PipelineDefinition,
        PipelineResult,
        PreflightReport,
    )
    from .core.pipelines.events import EventSink
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
        - ``resolve_settings(collection)`` — sync, returns frozen settings
        - ``validate_pipeline(definition, ...)`` — sync, no side effects
        - ``run_pipeline(definition, ...)`` — async, returns PipelineResult
        - ``close()`` — sync; refused while a graph run is active
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
        ocr_client: Any = None,
        redaction: RedactionSecrets | None = None,
        embedders: EngineEmbedders | None = None,
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
            ocr_client: Optional managed OCR worker client (task 2.6a).
                The engine owns its lifecycle: OCR-required PDFs dispatched
                by this engine's ingests reuse its lazily-started
                subprocess, and :meth:`close` closes it.
            redaction: Credential values :meth:`redact` removes from error
                text. ``None`` means the Engine has nothing to remove.
            embedders: Embedders by (provider, model) for collections whose
                profile names a model (ADR-081). ``None`` keeps only
                *embed_model*.
        """
        self._effective_settings = effective_settings
        self._store = store
        self._embed_model = embed_model
        self._embedders = embedders or EngineEmbedders(embed_model)
        self._reranker = reranker
        self._profile_resolver = profile_resolver
        self._profile_resolver_factory = profile_resolver_factory
        self._answer_llm_factory = answer_llm_factory
        self._verify_llm_factory = verify_llm_factory
        self._ocr_client = ocr_client
        self._redaction = redaction or RedactionSecrets()
        self._answer_llm: Any = None
        # Engine-owned query embedding cache: keyed by (query, model_name),
        # shared between filtered/unfiltered search within this engine,
        # never between engines, dropped on close().
        self._query_cache: collections.OrderedDict = collections.OrderedDict()
        self._closed = False
        # Graph state: catalogue (built on first use), run lock, leases.
        self._pipelines = EnginePipelines()

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

        effective, binding = self._resolve_bound(collection_name)
        if binding is not None and binding.user:
            return await engine_profiles.ingest(
                self,
                binding,
                path,
                collection_name,
                progress_callback=progress_callback,
                values={"chunk_size": chunk_size, "chunk_overlap": chunk_overlap},
            )
        embed_model, identity = embedding_for(self, collection_name, binding)
        return await ingest_path_async(
            path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            progress_callback=progress_callback,
            collection_name=collection_name,
            effective_settings=effective,
            store=self._store,
            embed_model=embed_model,
            embedding_identity=identity,
            ocr_client=self._ocr_client,
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

        effective, binding = self._resolve_bound(collection_name)
        if binding is not None and binding.user:
            return engine_profiles.search(
                self,
                binding,
                query,
                collection_name,
                include_diagnostics=include_diagnostics,
                values={
                    "top_k": top_k,
                    "similarity_threshold": similarity_threshold,
                    "rerank": rerank,
                    "hybrid": hybrid,
                    "expand_window": expand_window or None,
                    "metadata_filter": metadata_filter,
                    "technical_fraction": technical_fraction,
                    "fetch_k": fetch_k,
                },
            )
        embed_model, identity = embedding_for(self, collection_name, binding)
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
            embed_model=embed_model,
            embedding_identity=identity,
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
        client_completion: ClientCompletion | None = None,
        rows: list[dict] | ResolvedRetrieval | None = None,
    ) -> dict:
        """Answer a question from retrieved evidence with verifiable citations.

        Args:
            question: Free-text question.
            top_k: Maximum chunks used as evidence.
            similarity_threshold: Minimum evidence score.
            rerank: Tri-state rerank control.
            hybrid: Tri-state hybrid retrieval control.
            expand_window: Neighbours merged into each chunk.
            collection_name: Collection to answer from.
            metadata_filter: Store-compatible metadata filter.
            include_diagnostics: Include retrieval and completion diagnostics.
            client_completion: A caller's completion that replaces the server
                answer model and caps the answer rounds. Verification stays
                server-side. ``None`` keeps the server model.
            rows: Pre-retrieved rows (or a :class:`ResolvedRetrieval`); the
                Engine skips retrieval and answers from them.
        """
        self._check_open()
        from .core.answer.pipeline import answer as core_answer

        effective, binding = self._resolve_bound(collection_name)
        if binding is not None and binding.user:
            engine_profiles.refuse_caller_inputs(binding, client_completion, rows)
            return await engine_profiles.answer(
                self,
                binding,
                question,
                collection_name,
                values={
                    "top_k": top_k,
                    "similarity_threshold": similarity_threshold,
                    "rerank": rerank,
                    "hybrid": hybrid,
                    "expand_window": expand_window or None,
                    "metadata_filter": metadata_filter,
                    "include_diagnostics": include_diagnostics or None,
                },
            )
        embed_model, identity = embedding_for(self, collection_name, binding)
        complete, effective, source = select_completion(
            effective, client_completion, self._get_answer_llm
        )
        verify_complete, verify_unavailable_reason = build_verifier(
            effective, self._verify_llm_factory, self.redact
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
            completion_source=source,
            rows=rows,
            reranker=self._reranker,
            store=self._store,
            effective_settings=effective,
            embed_model=embed_model,
            embedding_identity=identity,
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

    @property
    def store(self) -> Any:
        """The owned vector store (read-only; callers must not close it)."""
        self._check_open()
        return self._store

    @property
    def profile_resolver(self) -> Any:
        """This Engine's profile resolver, or ``None`` when it has none."""
        return self._resolver()

    def resolve_settings(self, collection: str | None = None) -> EffectiveSettings:
        """Return the frozen settings for ``collection`` (default: settings collection).

        Uses the Engine's own profile resolver, else the Engine settings.
        """
        self._check_open()
        return self._resolve_settings(collection or self._effective_settings.collection_name)

    def validate_pipeline(
        self,
        definition: PipelineDefinition | Mapping[str, Any],
        *,
        inputs: Mapping[str, Any] | None = None,
        collection: str | None = None,
    ) -> AdmissionSnapshot | PreflightReport:
        """Validate a graph against this Engine, with no side effects.

        With ``inputs`` the graph is admitted and the frozen
        ``AdmissionSnapshot`` is returned (:meth:`run_pipeline` accepts
        it); without, a draft check returns the ``PreflightReport``.
        ``collection`` is the default for nodes that name none.

        Raises:
            PipelineValidationError: With every node, port and input issue.
        """
        self._check_open()
        host = self._graph_host(collection or definition_collection(definition))
        return self._pipelines.validate(definition, host, inputs=inputs)

    async def run_pipeline(
        self,
        definition: PipelineDefinition | Mapping[str, Any] | AdmissionSnapshot,
        *,
        inputs: Mapping[str, Any] | None = None,
        on_event: EventSink | None = None,
        cancellation: CancellationToken | None = None,
        run_id: str | None = None,
    ) -> PipelineResult:
        """Validate, admit and run a graph on this Engine's borrowed resources.

        Accepts an ``AdmissionSnapshot`` too (omit ``inputs``). Runs on one
        Engine are serialised. Failures and cancellation give a result.
        ``run_id`` names the run in its events and result (a caller's job id).

        Raises:
            PipelineValidationError: Before any side effect.
            RuntimeError: When the Engine is closed.
        """
        self._check_open()
        host = self._graph_host(definition_collection(definition))
        return await self._pipelines.run(
            definition,
            host,
            inputs=inputs,
            on_event=on_event,
            cancellation=cancellation,
            run_id=run_id,
        )

    def describe_operations(self, collection: str | None = None) -> list[dict[str, Any]]:
        """Return the graph operation catalogue with availability reasons."""
        self._check_open()
        return self._pipelines.describe(self._graph_host(collection))

    def redact(self, text: str) -> str:
        """Remove configured credential values from *text*.

        Transports call this on every error text they return or log.
        """
        return self._redaction.redact(text)

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
        if self._pipelines.active_runs:
            raise RuntimeError(
                f"Engine has {self._pipelines.active_runs} active graph run(s); cancel them or "
                "wait for them to finish, then close the Engine again."
            )
        self._closed = True
        self._pipelines.release()
        release_resources(self)

    # ── Internal helpers ───────────────────────────────────────────

    def _check_open(self) -> None:
        """Reject operations on a closed engine.

        Raises:
            RuntimeError: When the engine has been closed.
        """
        if self._closed:
            raise RuntimeError("Engine is closed; construct a new Engine for further operations.")

    def _graph_host(self, collection: str | None) -> Any:
        """Describe this Engine's resources to graph validation and runs."""
        return graph_host(self, collection)

    def _get_answer_llm(self) -> Any:
        """Build the answer LLM on first use and keep it."""
        if self._answer_llm is None and self._answer_llm_factory is not None:
            self._answer_llm = self._answer_llm_factory()
        return self._answer_llm

    def _resolver(self) -> Any:
        """Return the profile resolver, built from its factory on first use."""
        if self._profile_resolver is None and self._profile_resolver_factory is not None:
            self._profile_resolver = self._profile_resolver_factory()
        return self._profile_resolver

    def _resolve_settings(self, collection_name: str) -> EffectiveSettings:
        """Resolve a collection's settings; an invalid profile tag raises."""
        return self._resolve_bound(collection_name)[0]

    def _resolve_bound(self, collection_name: str) -> tuple[EffectiveSettings, Any]:
        """Resolve the settings and the profile binding with one tag read."""
        return resolve_bound(self, collection_name)

    def _install_as_process_default(self) -> None:
        """Install this engine's components as process defaults (legacy transports).

        Called only by ``compose.ensure_runtime_setup()``. The builder
        itself never installs; this method is the installer over the
        built engine.
        """
        install_as_process_default(self)
