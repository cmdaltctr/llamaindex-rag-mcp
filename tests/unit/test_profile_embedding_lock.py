"""The embedding lock and binding rules (ADR-081, design D7).

Real LanceDB and ChromaDB stores hold the collections. The stamp is written
through collection metadata, rows through ``upsert_precomputed``.
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any

import pytest

from omrg.core.profiles.embedding_lock import (
    binding_refusal,
    blocking_collections,
    collection_embedding_state,
)
from omrg.core.vectordb.identity import (
    IDENTITY_MODEL_KEY,
    IDENTITY_PROVIDER_KEY,
    EmbeddingIdentity,
)
from omrg.core.vectordb.lancedb.store import LanceVectorStore

A = EmbeddingIdentity("ollama", "model-a")
B = EmbeddingIdentity("llamacpp", "model-b")
HOST = EmbeddingIdentity("llamacpp", "host-model")


@pytest.fixture(params=["lancedb", "chroma"])
def store(request: pytest.FixtureRequest, tmp_path: Any) -> Any:
    if request.param == "chroma":
        if find_spec("chromadb") is None:
            pytest.skip("chromadb extra not installed")
        from omrg.core.vectordb.chroma.store import ChromaVectorStore

        return ChromaVectorStore()
    return LanceVectorStore(uri=str(tmp_path / "lancedb"))


def _rows(store: Any, name: str, count: int) -> None:
    store.upsert_precomputed(
        name,
        ids=[f"{name}-{i}" for i in range(count)],
        documents=["text"] * count,
        metadatas=[{"row": i} for i in range(count)],
        embeddings=[[1.0, 0.0]] * count,
        embedding_identity=EmbeddingIdentity("test", "test"),
    )


def _stamp(store: Any, name: str, identity: EmbeddingIdentity) -> None:
    store.update_collection_metadata(
        name, {IDENTITY_PROVIDER_KEY: identity.provider, IDENTITY_MODEL_KEY: identity.model}
    )


def _state(store: Any, name: str, *, stamp: EmbeddingIdentity | None, rows: int) -> Any:
    if rows:
        _rows(store, name, rows)
    if stamp is not None:
        _stamp(store, name, stamp)
    return collection_embedding_state(store, name)


# ── collection_embedding_state ───────────────────────────────────────────


def test_state_reads_the_stamp_and_the_row_count(store: Any) -> None:
    state = _state(store, "papers", stamp=A, rows=3)
    assert (state.collection, state.provider, state.model, state.chunk_count) == (
        "papers",
        "ollama",
        "model-a",
        3,
    )


def test_state_of_rows_without_a_stamp_has_no_model(store: Any) -> None:
    state = _state(store, "legacy", stamp=None, rows=2)
    assert (state.provider, state.model, state.chunk_count) == (None, None, 2)


def test_state_of_an_unknown_collection_is_empty(store: Any) -> None:
    state = collection_embedding_state(store, "nothing")
    assert (state.provider, state.model, state.chunk_count) == (None, None, 0)


# ── blocking_collections ─────────────────────────────────────────────────


def test_an_empty_unstamped_collection_does_not_block(store: Any) -> None:
    state = collection_embedding_state(store, "drafts")
    assert blocking_collections([state], B) == []


def test_a_stamped_collection_with_rows_blocks_another_model(store: Any) -> None:
    state = _state(store, "papers", stamp=A, rows=2)
    assert blocking_collections([state], B) == [state]


def test_a_stamped_collection_with_no_rows_still_blocks(store: Any) -> None:
    state = _state(store, "emptied", stamp=A, rows=0)
    assert state.chunk_count == 0
    assert blocking_collections([state], B) == [state]


def test_rows_without_a_stamp_always_block(store: Any) -> None:
    state = _state(store, "legacy", stamp=None, rows=2)
    assert blocking_collections([state], A) == [state]
    assert blocking_collections([state], B) == [state]


def test_a_request_equal_to_the_stamp_does_not_block(store: Any) -> None:
    state = _state(store, "papers", stamp=A, rows=2)
    assert blocking_collections([state], A) == []


def test_blocking_keeps_the_given_order() -> None:
    from omrg.core.profiles.embedding_lock import CollectionEmbeddingState as S

    first, second = S("one", "ollama", "model-a", 4), S("two", None, None, 9)
    assert blocking_collections([first, second], B) == [first, second]


# ── binding_refusal ──────────────────────────────────────────────────────


def test_binding_to_an_empty_unstamped_collection_is_allowed(store: Any) -> None:
    state = collection_embedding_state(store, "drafts")
    assert binding_refusal(state, B, HOST) is None


def test_binding_refuses_a_different_stamp_and_names_both_models(store: Any) -> None:
    state = _state(store, "papers", stamp=A, rows=2)
    message = binding_refusal(state, B, HOST)
    assert message is not None
    for text in ("papers", "ollama", "model-a", "llamacpp", "model-b"):
        assert text in message


def test_binding_accepts_a_matching_stamp(store: Any) -> None:
    state = _state(store, "papers", stamp=B, rows=2)
    assert binding_refusal(state, B, HOST) is None


def test_a_profile_without_a_choice_uses_the_host_model(store: Any) -> None:
    state = _state(store, "papers", stamp=A, rows=2)
    message = binding_refusal(state, None, HOST)
    assert message is not None and "host-model" in message and "model-a" in message
    host_state = _state(store, "hosted", stamp=HOST, rows=2)
    assert binding_refusal(host_state, None, HOST) is None


def test_rows_without_a_stamp_bind_only_to_the_server_default(store: Any) -> None:
    state = _state(store, "legacy", stamp=None, rows=2)
    assert binding_refusal(state, None, HOST) is None
    assert binding_refusal(state, HOST, HOST) is None
    message = binding_refusal(state, B, HOST)
    assert message is not None
    assert "legacy" in message and "not recorded" in message and "model-b" in message


def test_a_stamped_collection_with_no_rows_refuses_another_model(store: Any) -> None:
    state = _state(store, "emptied", stamp=A, rows=0)
    assert binding_refusal(state, B, HOST) is not None


def test_web_profile_service_uses_the_engine_host_model(tmp_path: Any) -> None:
    """The server default comes from the Engine, not from the process settings."""
    from types import SimpleNamespace

    from omrg.compose_profile_setup import build_profile_service

    engine = SimpleNamespace(
        _embedders=SimpleNamespace(host_identity=HOST),
        store=None,
        list_collections=list,
    )
    service = build_profile_service(engine, tmp_path)

    embedding = service.embedding.fields(None, [])["embedding"]

    assert (embedding["provider"], embedding["model"]) == (HOST.provider, HOST.model)
