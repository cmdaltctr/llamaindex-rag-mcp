"""Tests for the LRU query-embedding cache and the search() refactor.

Covers Section 4 of the rag-retrieval-quality-improvements OpenSpec change:
- Same query on the unfiltered path embeds the query only once.
- Same query on the metadata-filtered path embeds the query only once.
- Unfiltered then filtered with the same query shares the cache.
- Distinct queries do not collide.
- LRU eviction caps the cache at maxsize=128.
"""

from __future__ import annotations

import pytest
from llama_index.core import Settings
from llama_index.core.embeddings import MockEmbedding

from rag_mcp.core.ingestion import ingest_path_async
from rag_mcp.core.retrieval import dense as _dense
from rag_mcp.core.retrieval import search as _retrieval_search

# ── Helpers ────────────────────────────────────────────────────────────────


class _CountingMockEmbedding(MockEmbedding):
    """A ``MockEmbedding`` subclass that counts calls to the query path.

    Used in lieu of a wrapper because pydantic's ``BaseEmbedding``
    rejects attribute assignment for unknown fields, so monkey-patching
    methods on a plain ``MockEmbedding`` instance is not viable.

    Counts are tracked on a class-level mutable list so tests can
    instantiate the embedding and read the counter through the
    instance returned by the fixture.
    """

    @classmethod
    def make(cls, model_name: str = "counting-mock") -> _CountingMockEmbedding:
        instance = cls(embed_dim=384, model_name=model_name)
        # Stash a list as a per-instance counter via object.__setattr__
        # to bypass pydantic's field validation.  Tuple ensures
        # references stay stable across method calls.
        object.__setattr__(instance, "_call_counter", [0])
        return instance

    @property
    def calls(self) -> int:
        return self._call_counter[0]

    def _get_vector(self) -> list[float]:
        # Unit-normalised so the embedding norm guard
        # (guard-embedding-normalisation) accepts ingest through this
        # mock: the stock constant [0.5] * dim vector has norm ~9.8.
        # Normalising preserves the constant-vector property, so scores
        # and rankings are unchanged.
        import math

        vector = super()._get_vector()
        norm = math.sqrt(math.fsum(x * x for x in vector))
        return [x / norm for x in vector] if norm else list(vector)

    def _get_query_embedding(self, query: str) -> list[float]:
        self._call_counter[0] += 1
        return super()._get_query_embedding(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        self._call_counter[0] += 1
        return await super()._aget_query_embedding(query)


@pytest.fixture
def counting_embed():
    """Install a counting subclass of MockEmbedding as ``Settings.embed_model``.

    Also clears the LRU cache before and after each test so call
    counts are isolated. Each test gets a unique ``model_name`` so the
    cache key cannot leak across tests.
    """
    _dense._cached_query_embedding.cache_clear()
    previous = Settings.embed_model

    counter = _CountingMockEmbedding.make(model_name="counting-mock-1")
    Settings.embed_model = counter

    yield counter

    Settings.embed_model = previous
    _dense._cached_query_embedding.cache_clear()


# ── 4.4: unfiltered repeat hits cache ─────────────────────────────────────


@pytest.mark.asyncio
async def test_unfiltered_repeat_query_embeds_once(
    sample_md,
    counting_embed,
) -> None:
    """Two identical unfiltered searches SHALL embed the query only once."""
    await ingest_path_async(str(sample_md), collection_name="cache_unfiltered")

    # Reset the counter so ingestion-time embed calls don't leak in.
    counting_embed._call_counter[0] = 0

    _retrieval_search(
        "capital of France",
        collection_name="cache_unfiltered",
    )
    _retrieval_search(
        "capital of France",
        collection_name="cache_unfiltered",
    )

    assert counting_embed.calls == 1, (
        f"Expected 1 embed call across two identical queries, got {counting_embed.calls}"
    )


# ── 4.5: filtered repeat hits cache ───────────────────────────────────────


@pytest.mark.asyncio
async def test_filtered_repeat_query_embeds_once(
    sample_md,
    counting_embed,
) -> None:
    """Two identical filtered searches SHALL embed the query only once."""
    await ingest_path_async(str(sample_md), collection_name="cache_filtered")
    counting_embed._call_counter[0] = 0

    _retrieval_search(
        "capital of France",
        collection_name="cache_filtered",
        metadata_filter={"category": "AI"},
    )
    _retrieval_search(
        "capital of France",
        collection_name="cache_filtered",
        metadata_filter={"category": "AI"},
    )

    assert counting_embed.calls == 1


# ── 4.6: filtered + unfiltered share the cache ────────────────────────────


@pytest.mark.asyncio
async def test_filtered_and_unfiltered_share_cache(
    sample_md,
    counting_embed,
) -> None:
    """An unfiltered call and a filtered call with the same query embed once."""
    await ingest_path_async(str(sample_md), collection_name="cache_shared")
    counting_embed._call_counter[0] = 0

    _retrieval_search("capital of France", collection_name="cache_shared")
    _retrieval_search(
        "capital of France",
        collection_name="cache_shared",
        metadata_filter={"category": "AI"},
    )

    assert counting_embed.calls == 1


# ── 4.7: distinct queries do not collide ──────────────────────────────────


@pytest.mark.asyncio
async def test_distinct_queries_do_not_collide(
    sample_md,
    counting_embed,
) -> None:
    """Two different queries SHALL each get their own embedding."""
    await ingest_path_async(str(sample_md), collection_name="cache_distinct")
    counting_embed._call_counter[0] = 0

    _retrieval_search("capital of France", collection_name="cache_distinct")
    _retrieval_search("capital of Germany", collection_name="cache_distinct")

    assert counting_embed.calls == 2


# ── 4.8: LRU eviction at configured maxsize ───────────────────────────────


def test_lru_eviction_caps_cache_at_maxsize() -> None:
    """The cache SHALL evict least-recently-used entries past maxsize=128."""
    cache = _dense._cached_query_embedding
    cache.cache_clear()

    previous = Settings.embed_model
    counter = _CountingMockEmbedding.make(model_name="lru-test-model")
    Settings.embed_model = counter

    try:
        for i in range(200):
            _dense._embed_query(f"query-{i}")

        info = cache.cache_info()
        assert info.maxsize == _dense._QUERY_EMBED_CACHE_MAXSIZE == 128
        assert info.currsize <= 128, f"Cache currsize {info.currsize} exceeded maxsize 128"
    finally:
        Settings.embed_model = previous
        cache.cache_clear()
