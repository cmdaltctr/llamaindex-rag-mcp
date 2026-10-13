"""Shared helpers for the Engine graph tests (task 4.3).

The helpers build Engines from explicit settings and in-memory fakes, and
describe small retrieval and answer graphs with the registered operation
ids. This module holds no tests.
"""

from __future__ import annotations

import threading
from typing import Any

from tests.fixtures.pipeline_parity.retrieval import harness

from omrg.core.vectordb.identity import IDENTITY_MODEL_KEY, IDENTITY_PROVIDER_KEY
from omrg.engine import Engine

#: Methods that write to a store. Validation must call none of them.
WRITE_METHODS = (
    "create_collection",
    "delete_collection",
    "write_nodes",
    "upsert_precomputed",
    "delete_where",
    "delete_ids",
    "update_collection_metadata",
    "bump_generation",
)


def chunks(prefix: str = "doc", count: int = 3) -> list[dict[str, Any]]:
    """Return chunk rows with lineage and falling dense scores."""
    rows = []
    for index in range(count):
        source = f"{prefix}-s{index}"
        rows.append(
            {
                "id": f"{prefix}-row{index}",
                "text": f"{prefix} text number {index}",
                "dense_score": 0.9 - index * 0.1,
                "metadata": {
                    "file_name": f"{source}.md",
                    "source_id": source,
                    "source_version": "v1",
                    "chunk_id": f"{source}-c0",
                    "source_chunk_index": 0,
                    "source_chunk_count": 1,
                },
            }
        )
    return rows


class FakeStore(harness.ParityStore):
    """In-memory store that records reads, writes and close.

    Args:
        rows: Chunk rows every collection serves.
        metadata: Collection name to collection metadata.
        identity: Embedding identity the store writes with, if any.
    """

    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        metadata: dict[str, dict] | None = None,
        identity: Any = None,
    ) -> None:
        """Keep the rows and empty call logs."""
        super().__init__(rows)
        self._metadata = metadata or {}
        self._identity = identity
        self.writes: list[str] = []
        self.counted: list[str] = []
        self.closed = False
        self.gate: threading.Event | None = None
        self.entered = threading.Event()
        self.barrier: threading.Barrier | None = None

    @property
    def cache_identity(self) -> object:
        """Return a per-store cache identity."""
        return ("fake-store", id(self))

    def count(self, name: str) -> int:
        """Count rows; optionally wait on a gate or barrier first."""
        self.counted.append(name)
        self.entered.set()
        if self.barrier is not None:
            self.barrier.wait()
        if self.gate is not None:
            assert self.gate.wait(timeout=10), "test gate was never opened"
        return super().count(name)

    def query_dense(self, collection_name, query_embedding, n_results, where=None):
        """Return the rows by recorded dense score."""
        ordered = sorted(self._chunks, key=lambda c: c["dense_score"], reverse=True)
        return [
            {
                "id": c["id"],
                "score": c["dense_score"],
                "score_kind": "dense_cosine_v1",
                "metadata": dict(c["metadata"]),
                "document": c["text"],
            }
            for c in ordered[:n_results]
        ]

    def collection_exists(self, name: str) -> bool:
        """Return whether metadata exists for ``name``."""
        return name in self._metadata

    def get_collection_metadata(self, name: str) -> dict | None:
        """Return a copy of the collection metadata."""
        meta = self._metadata.get(name)
        return None if meta is None else dict(meta)

    def close(self) -> None:
        """Record the close."""
        self.closed = True

    def __getattr__(self, name: str) -> Any:
        """Record any write method call."""
        if name in WRITE_METHODS:

            def record(*args: Any, **kwargs: Any) -> None:
                self.writes.append(name)

            return record
        raise AttributeError(name)


def identity_metadata(provider: str, model: str) -> dict[str, str]:
    """Return collection metadata that stamps an embedding identity."""
    return {IDENTITY_PROVIDER_KEY: provider, IDENTITY_MODEL_KEY: model}


class FakeEmbedder:
    """Embedder returning a fixed unit vector."""

    def __init__(self, model_name: str = "fake-embed") -> None:
        """Keep the model name."""
        self.model_name = model_name

    def get_query_embedding(self, query: str) -> list[float]:
        """Return a unit vector so the norm guard stays quiet."""
        return [1.0, 0.0]


class FakeResolver:
    """Profile resolver that maps collection names to settings."""

    def __init__(self, by_collection: dict[str, Any], profiles: dict[str, Any] | None = None):
        """Keep the mappings."""
        self.by_collection = by_collection
        self.profiles = profiles or {}
        self._env_overrides: dict[str, str] = {}

    def resolve(self, collection: str) -> Any:
        """Return the collection's settings."""
        return self.by_collection[collection]

    def _load_effective(self, profile: str) -> Any:
        if profile not in self.profiles:
            raise ValueError(f"unknown profile {profile!r}")
        return self.profiles[profile]


class Factory:
    """Counting factory for the answer or judge model."""

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        """Keep the result to return or the error to raise."""
        self.result = result
        self.error = error
        self.calls = 0

    def __call__(self, *args: Any) -> Any:
        """Count the call, then return or raise."""
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class FakeLLM:
    """Answer model that cites the first evidence item."""

    def __init__(self) -> None:
        """Start with no prompts."""
        self.prompts: list[str] = []

    async def acomplete(self, prompt: str) -> Any:
        """Return a cited answer."""
        self.prompts.append(prompt)
        return type("Completion", (), {"text": "The text is number zero [1]."})()


def build_engine(settings: Any, store: Any = None, **kwargs: Any) -> Engine:
    """Return an Engine over in-memory fakes."""
    return Engine(
        settings,
        store=store if store is not None else FakeStore(chunks()),
        embed_model=kwargs.pop("embed_model", FakeEmbedder()),
        **kwargs,
    )


def _edges(pairs: list[tuple[str, str, str, str]]) -> list[dict[str, Any]]:
    return [
        {"source": {"node": a, "port": b}, "target": {"node": c, "port": d}} for a, b, c, d in pairs
    ]


_RETRIEVAL_EDGES = [
    ("prepare", "query", "dense", "query"),
    ("dense", "evidence", "select", "evidence"),
    ("select", "evidence", "context", "evidence"),
]


def retrieval_graph(**prepare_params: Any) -> dict[str, Any]:
    """Return prepare_query -> dense -> threshold -> context.assemble."""
    return {
        "schema_version": 1,
        "nodes": [
            {"id": "prepare", "operation": "retrieve.prepare_query", "params": prepare_params},
            {"id": "dense", "operation": "retrieve.dense"},
            {"id": "select", "operation": "select.threshold"},
            {"id": "context", "operation": "context.assemble"},
        ],
        "edges": _edges(_RETRIEVAL_EDGES),
        "inputs": [
            {
                "name": "query",
                "kind": "query",
                "required": True,
                "targets": [{"node": "prepare", "port": "query"}],
            }
        ],
        "outputs": [{"name": "context", "source": {"node": "context", "port": "context"}}],
    }


def answer_graph(**prepare_params: Any) -> dict[str, Any]:
    """Return the retrieval graph followed by evidence, synthesis and citation."""
    graph = retrieval_graph(**prepare_params)
    graph["nodes"] += [
        {"id": "evidence", "operation": "answer.prepare_evidence"},
        {"id": "synth", "operation": "answer.synthesise"},
        {"id": "cite", "operation": "answer.cite"},
    ]
    graph["edges"] += _edges(
        [
            ("context", "context", "evidence", "context"),
            ("evidence", "context", "synth", "context"),
            ("synth", "answer", "cite", "answer"),
        ]
    )
    graph["inputs"][0]["targets"].append({"node": "synth", "port": "query"})
    graph["outputs"] = [{"name": "answer", "source": {"node": "cite", "port": "answer"}}]
    return graph
