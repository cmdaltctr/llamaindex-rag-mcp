"""``BaseRetriever`` adapter over :func:`omrg.core.retrieval.search`.

Wraps the existing ``search()`` path (profile-resolved levers, hybrid
fusion, reranking, context assembly) as a LlamaIndex ``BaseRetriever``
so the response synthesiser composes with the project's own retrieval —
answering has no retrieval code of its own (design D3).  Lineage fields
(``chunk_id``, ``source_id``, ``source_version``, ``source``,
``source_chunk_index``, ``score``, ``score_kind``) ride through node
metadata so citations stay verifiable downstream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from llama_index.core import QueryBundle
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode

if TYPE_CHECKING:
    from collections.abc import Callable

#: Search-row lineage fields copied verbatim into node metadata.
_LINEAGE_FIELDS = (
    "chunk_id",
    "chunk_ids",
    "source_id",
    "source_version",
    "source",
    "source_chunk_index",
    "score",
    "score_kind",
)


class SearchRetriever(BaseRetriever):
    """Adapter that presents ``search()`` results as scored nodes.

    Constructed with the retrieval arguments ``answer()`` accepts and
    queried with ``retrieve(query)``.  The raw search rows are kept on
    :attr:`rows` so the pipeline can build its evidence list from the
    authoritative row dicts rather than re-parsing node metadata.
    """

    def __init__(
        self,
        *,
        search_fn: Callable[..., list[dict]] | None = None,
        collection_name: str = "documents",
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        rerank: bool | None = None,
        hybrid: bool | None = None,
        expand_window: int = 0,
        metadata_filter: dict | None = None,
        reranker: Any = None,
        store: Any = None,
        effective_settings: Any = None,
    ) -> None:
        """Store the retrieval arguments; nothing runs until ``retrieve``.

        Args:
            search_fn: Retrieval entry point (dependency injection for
                tests; defaults to ``core.retrieval.search``).
            collection_name: Collection to search.
            top_k: Maximum chunks to return (profile default when None).
            similarity_threshold: Minimum score to include.
            rerank: Tri-state rerank control.
            hybrid: Tri-state hybrid fusion control.
            expand_window: Neighbours merged into each chunk by context
                assembly.
            metadata_filter: Store ``where`` clause.
            reranker: Optional pre-constructed reranker.
            store: Optional injected vector store.
            effective_settings: Optional resolved profile settings.
        """
        self._search_fn = search_fn
        self._collection_name = collection_name
        self._top_k = top_k
        self._similarity_threshold = similarity_threshold
        self._rerank = rerank
        self._hybrid = hybrid
        self._expand_window = expand_window
        self._metadata_filter = metadata_filter
        self._reranker = reranker
        self._store = store
        self._effective_settings = effective_settings
        # Raw search rows from the last retrieve() call.
        self.rows: list[dict] = []
        super().__init__(callback_manager=None)

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        """Run ``search()`` and convert rows to scored nodes with lineage."""
        if self._search_fn is None:
            from ..retrieval.pipeline import search as _search
        else:
            _search = self._search_fn

        self.rows = _search(
            query_bundle.query_str,
            top_k=self._top_k,
            similarity_threshold=self._similarity_threshold,
            rerank=self._rerank,
            hybrid=self._hybrid,
            expand_window=self._expand_window,
            collection_name=self._collection_name,
            metadata_filter=self._metadata_filter,
            reranker=self._reranker,
            store=self._store,
            effective_settings=self._effective_settings,
        )
        return [_row_to_node(row) for row in self.rows]


def _row_to_node(row: dict) -> NodeWithScore:
    """Convert one search result row to a ``NodeWithScore``.

    The node text is the chunk text; lineage fields are copied into
    node metadata.  The score is coerced to float when present so the
    synthesiser's ranking sees a numeric value.
    """
    metadata: dict[str, Any] = {}
    for field in _LINEAGE_FIELDS:
        if row.get(field) is not None:
            metadata[field] = row[field]
    node = TextNode(text=row.get("text") or "", metadata=metadata)
    score = row.get("score")
    return NodeWithScore(node=node, score=float(score) if score is not None else None)
