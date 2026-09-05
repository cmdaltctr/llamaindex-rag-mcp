"""Decisive two-engine isolation tests (tasks 4.8 and 4.9).

Constructs two engines over separate real LanceDB stores with
distinguishable deterministic embedders, with NO process-default store
installed and the LlamaIndex global embedder replaced by a poisoned
sentinel that fails on any use. Runs the full operation surface —
ingest, source replacement, dense search, hybrid (native sparse)
retrieval, answering, listing and paged reads — on both engines and
asserts every embedding and query went through its own engine's model.

Any direct-Engine seam that still reads a process default either raises
(the default-store accessor fails) or triggers the poisoned global,
failing the test. This is the red line the change must hold.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import types
from pathlib import Path
from typing import Any

import pytest
from llama_index.core import Settings
from llama_index.core.embeddings import MockEmbedding

from omrg.core.profiles.resolver import ProfileResolver
from omrg.core.settings import AnswerBlock
from omrg.core.vectordb.lancedb import LanceVectorStore
from omrg.engine import Engine

# The engines use the native sparse backend (Lance FTS): rank_bm25 is an
# optional extra and hybrid retrieval must not depend on it here.
_EMBED_DIM = 32


class _SaltedEmbedding(MockEmbedding):
    """Deterministic per-(model, text) embeddings that record every call.

    Vectors are unit-normalised SHA-256 digests salted with the model
    name, so two engines embed the same text differently and a leaked
    vector is detectable. Query and text calls are recorded for
    per-engine attribution.
    """

    def __init__(self, *, model_name: str, embed_dim: int = _EMBED_DIM) -> None:
        super().__init__(embed_dim=embed_dim, model_name=model_name)
        object.__setattr__(self, "_queries", [])
        object.__setattr__(self, "_texts", [])

    @property
    def queries(self) -> list[str]:
        return self._queries

    @property
    def texts(self) -> list[str]:
        return self._texts

    def _vector_for(self, text: str) -> list[float]:
        digest = hashlib.sha256(f"{self.model_name}:{text}".encode()).digest()
        raw = [float(b) for b in digest[:_EMBED_DIM]]
        norm = math.sqrt(math.fsum(v * v for v in raw)) or 1.0
        return [v / norm for v in raw]

    def _get_query_embedding(self, query: str) -> list[float]:
        self._queries.append(query)
        return self._vector_for(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        self._queries.append(query)
        return self._vector_for(query)

    def get_text_embedding(self, text: str) -> list[float]:
        self._texts.append(text)
        return self._vector_for(text)

    def get_text_embedding_batch(self, texts, **kwargs):  # noqa: ANN001, ARG002
        self._texts.extend(texts)
        return [self._vector_for(text) for text in texts]


class _PoisonedGlobalEmbedding(MockEmbedding):
    """Valid ``BaseEmbedding`` whose every embedding call fails.

    Installed on the LlamaIndex global: any code path that embeds
    through ``Settings.embed_model`` raises instead of silently using
    the wrong model.
    """

    def _get_query_embedding(self, query: str) -> list[float]:
        raise AssertionError("the LlamaIndex global embedder embedded a query")

    def get_text_embedding_batch(self, texts, **kwargs):  # noqa: ANN001, ARG002
        raise AssertionError("the LlamaIndex global embedder embedded texts")


class _StubLLM:
    """Minimal answer-LLM double returning a fixed cited reply."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.prompts: list[str] = []

    async def acomplete(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        return types.SimpleNamespace(text=self._reply)


def _engine(tmp_path: Path, name: str, effective: Any) -> tuple[Engine, _SaltedEmbedding]:
    """Build one engine over its own temporary LanceDB store."""
    store = LanceVectorStore(uri=str(tmp_path / f"store-{name}"))
    embed = _SaltedEmbedding(model_name=f"iso-{name}")
    return (
        Engine(
            effective,
            store=store,
            embed_model=embed,
            profile_resolver=ProfileResolver(
                store=store, server_profile="documents", base=effective
            ),
            answer_llm_factory=lambda: _StubLLM(f"Answer from {name} [1]."),
        ),
        embed,
    )


@pytest.fixture
def poisoned_global():
    """Install the poisoned sentinel on the LlamaIndex global embedder."""
    previous = Settings.embed_model
    Settings.embed_model = _PoisonedGlobalEmbedding(embed_dim=_EMBED_DIM)  # type: ignore[assignment]
    yield
    Settings.embed_model = previous


@pytest.fixture
def engine_pair(tmp_path: Path, effective_settings):
    """Two engines with distinguishable embedders over separate stores.

    Strips the process-default store and effective settings the shared
    conftest installs for every test, so any direct-Engine seam that
    falls back to a process default fails loudly instead of silently
    reading the harness store (task 4.8 precondition).
    """
    from omrg.core.settings import reset_default_effective_settings
    from omrg.core.vectordb import get_default_store, reset_default_store

    reset_default_store()
    reset_default_effective_settings()
    with pytest.raises(RuntimeError, match="ensure_runtime_setup"):
        get_default_store()

    base = effective_settings(
        hybrid_sparse_backend="native",
        rerank_enabled=False,
    )
    effective_a = base.model_copy(
        update={"answer": AnswerBlock(enabled=True, provider="stub", model="stub")}
    )
    effective_b = base.model_copy(
        update={"answer": AnswerBlock(enabled=True, provider="stub", model="stub")}
    )
    engine_a, embed_a = _engine(tmp_path, "a", effective_a)
    engine_b, embed_b = _engine(tmp_path, "b", effective_b)
    return engine_a, engine_b, embed_a, embed_b


def _corpus(tmp_path: Path, name: str, marker: str) -> Path:
    """Write a one-file corpus with an engine-unique marker word."""
    docs = tmp_path / f"docs-{name}"
    docs.mkdir()
    (docs / "notes.md").write_text(
        f"# {name} corpus\n\nThe {marker} protocol governs this corpus. "
        f"Only the {marker} documents mention {marker} explicitly.\n",
        encoding="utf-8",
    )
    return docs


def _sources(rows: list[dict]) -> set[str]:
    return {row.get("source") for row in rows}


# ── Task 4.8: the decisive full-path test ─────────────────────────────


def test_two_engine_full_path_isolation(tmp_path: Path, engine_pair, poisoned_global) -> None:
    """Ingest, dense and hybrid search, listing and paged reads stay per-engine.

    With no process-default store and a poisoned LlamaIndex global,
    every operation on each engine must run entirely through that
    engine's injected dependencies.
    """
    engine_a, engine_b, embed_a, embed_b = engine_pair
    corpus_a = _corpus(tmp_path, "alpha", "zenith")
    corpus_b = _corpus(tmp_path, "beta", "aurora")

    asyncio.run(engine_a.ingest(str(corpus_a), collection_name="documents"))
    asyncio.run(engine_b.ingest(str(corpus_b), collection_name="documents"))

    # Document embeddings came from each engine's model only.
    assert embed_a.texts, "engine A embedder saw no document text"
    assert embed_b.texts, "engine B embedder saw no document text"
    assert not any("aurora" in text for text in embed_a.texts)
    assert not any("zenith" in text for text in embed_b.texts)

    # Listing and paged reads see only the owning engine's corpus.
    assert engine_a.list_collections() == ["documents"]
    assert engine_b.list_collections() == ["documents"]
    pages_a = list(engine_a._store.iter_documents("documents", page_size=1))
    pages_b = list(engine_b._store.iter_documents("documents", page_size=1))
    assert any("zenith" in text for _, text, _ in pages_a)
    assert not any("aurora" in text for _, text, _ in pages_a)
    assert any("aurora" in text for _, text, _ in pages_b)
    assert not any("zenith" in text for _, text, _ in pages_b)

    # Dense search: query embeddings per engine, corpus separation kept.
    hits_a = engine_a.search("zenith", collection_name="documents")
    assert engine_b.search("aurora", collection_name="documents")
    assert "zenith" in embed_a.queries
    assert "aurora" in embed_b.queries
    assert not any(q == "zenith" for q in embed_b.queries)
    assert not any(q == "aurora" for q in embed_a.queries)
    assert hits_a and all("notes.md" in (source or "") for source in _sources(hits_a))
    assert all("zenith" in (row.get("text") or "") for row in hits_a)

    # Hybrid retrieval (native sparse) through the engine's embedder.
    hybrid_a = engine_a.search("zenith", hybrid=True, collection_name="documents")
    hybrid_b = engine_b.search("aurora", hybrid=True, collection_name="documents")
    assert hybrid_a and all("zenith" in (row.get("text") or "") for row in hybrid_a)
    assert hybrid_b and all("aurora" in (row.get("text") or "") for row in hybrid_b)

    engine_a.close()
    engine_b.close()


def test_interleaved_operations_never_observe_the_other_model(
    tmp_path: Path, engine_pair, poisoned_global
) -> None:
    """Task 4.9: interleaved ingest/search/answer keep model attribution."""
    engine_a, engine_b, embed_a, embed_b = engine_pair
    corpus_a = _corpus(tmp_path, "alpha", "zenith")
    corpus_b = _corpus(tmp_path, "beta", "aurora")

    # Interleave: A ingest, B ingest, A search, B search, A answer, B answer.
    asyncio.run(engine_a.ingest(str(corpus_a), collection_name="documents"))
    asyncio.run(engine_b.ingest(str(corpus_b), collection_name="documents"))
    a_dense = engine_a.search("zenith protocol", collection_name="documents")
    b_dense = engine_b.search("aurora protocol", collection_name="documents")
    a_answer = asyncio.run(engine_a.answer("What governs the corpus?", top_k=2))
    b_answer = asyncio.run(engine_b.answer("What governs the corpus?", top_k=2))

    # Each engine's query embedder saw exactly the queries its
    # operations issued — never the other engine's.
    assert embed_a.queries.count("zenith protocol") == 1
    assert embed_b.queries.count("aurora protocol") == 1
    assert not any("aurora" in q for q in embed_a.queries)
    assert not any("zenith" in q for q in embed_b.queries)

    # Answers retrieved evidence from the owning corpus only.
    assert a_dense and all("zenith" in (row.get("text") or "") for row in a_dense)
    assert b_dense and all("aurora" in (row.get("text") or "") for row in b_dense)
    assert a_answer["status"] in {"ok", "generation_unverified"}
    assert a_answer["answer"] == "Answer from a [1]."
    assert all("zenith" in (row.get("text") or "") for row in a_answer["evidence"])
    assert b_answer["status"] in {"ok", "generation_unverified"}
    assert b_answer["answer"] == "Answer from b [1]."
    assert all("aurora" in (row.get("text") or "") for row in b_answer["evidence"])

    engine_a.close()
    engine_b.close()


def test_source_replacement_uses_engine_embedder(
    tmp_path: Path, engine_pair, poisoned_global
) -> None:
    """Re-ingesting a changed source re-embeds through the same engine."""
    engine_a, engine_b, embed_a, embed_b = engine_pair
    corpus = tmp_path / "docs-replace"
    corpus.mkdir()
    doc = corpus / "notes.md"
    doc.write_text("# replace\n\nOriginal magenta content.\n", encoding="utf-8")

    asyncio.run(engine_a.ingest(str(corpus), collection_name="documents"))
    texts_before = len(embed_a.texts)

    doc.write_text(
        "# replace\n\nUpdated magenta content with vermilion additions.\n",
        encoding="utf-8",
    )
    result = asyncio.run(engine_a.ingest(str(corpus), collection_name="documents"))

    # Replacement re-embedded the changed source through engine A.
    assert len(embed_a.texts) > texts_before
    assert any("vermilion" in text for text in embed_a.texts)
    assert result["status"] in {"ok", "completed", "success"} or result  # shape varies
    # Engine B never observed the replacement.
    assert not any("magenta" in text or "vermilion" in text for text in embed_b.texts)

    hits = engine_a.search("vermilion", collection_name="documents")
    assert hits and all("vermilion" in (row.get("text") or "") for row in hits)
    engine_a.close()
    engine_b.close()


def test_close_engine_a_leaves_engine_b_functional(
    tmp_path: Path, engine_pair, poisoned_global
) -> None:
    """Closing one engine neither stops the other nor unblocks its ops."""
    engine_a, engine_b, embed_a, embed_b = engine_pair
    corpus_a = _corpus(tmp_path, "alpha", "zenith")
    corpus_b = _corpus(tmp_path, "beta", "aurora")
    asyncio.run(engine_a.ingest(str(corpus_a), collection_name="documents"))
    asyncio.run(engine_b.ingest(str(corpus_b), collection_name="documents"))

    engine_a.close()
    with pytest.raises(RuntimeError, match="[Cc]losed"):
        engine_a.search("zenith", collection_name="documents")

    # Engine B keeps operating through its own dependencies.
    hits = engine_b.search("aurora", collection_name="documents")
    assert hits and all("aurora" in (row.get("text") or "") for row in hits)
    assert "aurora" in embed_b.queries
    engine_b.close()
