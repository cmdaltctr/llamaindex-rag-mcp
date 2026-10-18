"""Engine internals that live outside ``engine.py`` to keep it under the file-size ceiling.

* :func:`release_resources` is the body of ``Engine.close()``.
* :func:`graph_host` describes the Engine's resources to graph runs.
* :func:`install_as_process_default` is the legacy process-default installer.

Nothing here is public: the Engine is the only caller.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .compose_pipelines import build_graph_host
from .engine_embedders import embedding_for

if TYPE_CHECKING:
    from .engine import Engine

logger = logging.getLogger(__name__)


def release_resources(engine: Engine) -> None:
    """Drop caches, close the owned store and OCR client, release references.

    A store or OCR ``close()`` failure is logged, not raised, so the reference
    release always completes (ADR-061). Shared process-wide caches (the
    reranker model cache) are untouched.

    Args:
        engine: The Engine that is being closed. Its graph state is already
            released.
    """
    # Drop the engine-owned query embedding cache.
    engine._query_cache.clear()
    # Evict BM25 cache entries for this store's identity only.
    from .core.retrieval.sparse import evict_bm25_cache

    evict_bm25_cache(engine._store.cache_identity)
    try:
        engine._store.close()
    except Exception as exc:
        logger.warning(
            "store close() failed during engine close: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
    # Close the owned OCR worker client (task 2.6a): stop accepting
    # requests, close stdin, bounded graceful wait, then terminate.
    if engine._ocr_client is not None:
        try:
            engine._ocr_client.close()
        except Exception as exc:
            logger.warning(
                "OCR worker client close() failed during engine close: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
    # The embedder reference must go so a closed engine never pins model resources.
    engine._store = None  # type: ignore[assignment]
    engine._embed_model = None  # type: ignore[assignment]
    engine._embedders.release()
    engine._reranker = None
    engine._profile_resolver = None
    engine._profile_resolver_factory = None
    engine._answer_llm = None
    engine._answer_llm_factory = None
    engine._verify_llm_factory = None
    engine._ocr_client = None


def resolve_bound(engine: Engine, collection: str) -> tuple[Any, Any]:
    """Resolve the settings and the profile binding of a collection with one tag read.

    The binding is ``None`` when the Engine has no resolver or the resolver
    does not report bindings. A caller that finds a user binding runs the
    profile's pipelines; every other caller keeps the direct path.
    """
    from .core.profiles.resolver import ProfileResolver

    resolver = engine._resolver()
    if resolver is None:
        return engine._effective_settings, None
    if not isinstance(resolver, ProfileResolver):
        return resolver.resolve(collection), None
    return resolver.resolve_bound(collection)


def graph_host(engine: Engine, collection: str | None) -> Any:
    """Describe the Engine's resources to graph validation and runs.

    The embedder is the one the collection's profile names (ADR-081), so
    preflight and the steps use the model that made the collection's vectors.

    Args:
        engine: The Engine.
        collection: Default collection for nodes that name none.
    """
    answer_llm = engine._get_answer_llm if engine._answer_llm_factory is not None else None
    embedder, choice = embedding_for(engine, collection)
    resources = {
        "store": engine._store,
        "embedder": embedder,
        "embedding_identity": choice or engine._embedders.host_identity,
        "reranker": engine._reranker,
        "ocr": engine._ocr_client,
        "answer_llm": answer_llm,
        "verify_llm": engine._pipelines.judge(engine._verify_llm_factory),
    }
    from dataclasses import replace

    from .core.pipelines import HostOptionSet

    readers = HostOptionSet(
        inherited=engine._effective_settings.pdf_reader,
        unavailable={n: r for n, r in engine._pipelines.reader_options().items() if r},
    )
    graph = build_graph_host(
        engine._effective_settings,
        resources=resources,
        resolver=engine._resolver(),
        collection=collection,
        ocr_factory=engine._pipelines.ocr_client,
    )
    return replace(graph, host=replace(graph.host, options={"pdf_reader": readers}))


def install_as_process_default(engine: Engine) -> None:
    """Install the Engine's components as process defaults (legacy transports)."""
    from llama_index.core import Settings as LlamaIndexSettings

    from .core.settings import set_default_effective_settings
    from .core.vectordb import set_default_store

    LlamaIndexSettings.embed_model = engine._embed_model
    set_default_store(engine._store)
    set_default_effective_settings(engine._effective_settings)
