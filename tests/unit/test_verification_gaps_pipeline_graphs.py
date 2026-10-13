"""Pipeline-graph gaps from the verification report (section B).

Each test runs a real admitted graph through ``Engine.run_pipeline``:

* two revisions that differ only in their connections run differently;
* a reader that declares ``structured=True`` skips enrichment and
  reaches the splitter as structured;
* the canonical ingestion graph keeps ``metadata_degraded=true`` parity
  with ``Engine.ingest``;
* a registered replacement ``sentence`` splitter is the one a graph run
  calls;
* metadata enrichment in a graph run reads only the running Engine's
  own store.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from llama_index.core import Settings as LlamaIndexSettings
from llama_index.core.schema import TextNode
from tests.fixtures.pipeline_parity.ingestion.snapshot import (
    collect_rows,
    copy_sources,
    pin_detection,
)
from tests.fixtures.pipeline_parity.retrieval import harness
from tests.test_metadata_store_ownership import _Capture, _prompt_categories
from tests.unit.test_engine_pipelines_support import FakeStore, build_engine, chunks
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrg.core.chunking import registry as chunking_registry
from omrg.core.ingestion import graph_adapters
from omrg.core.ingestion.backends.orchestrator import BackendRead
from omrg.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrg.core.metadata import extractor
from omrg.core.pipelines import RunStatus
from omrg.core.vectordb.lancedb import LanceVectorStore
from omrg.engine import Engine

_SOURCES = ["guide.md", "nested/appendix.md", "notes.txt"]


def _lance_engine(tmp_path: Path, settings: Any, name: str = "lancedb") -> Engine:
    """Return an Engine over its own LanceDB directory and the mock embedder."""
    store = LanceVectorStore(uri=str(tmp_path / name))
    return Engine(settings, store=store, embed_model=LlamaIndexSettings.embed_model)


# ── Changing a connection changes execution ──────────────────────────────


def _wired(order: list[str]) -> dict[str, Any]:
    """Return one retrieval graph; ``order`` wires the middle nodes in sequence."""
    chain = ["prepare", "dense", *order, "context"]
    ports = {"prepare": "query"}
    edges = [
        {
            "source": {"node": a, "port": ports.get(a, "evidence")},
            "target": {"node": b, "port": "query" if a == "prepare" else "evidence"},
        }
        for a, b in zip(chain, chain[1:], strict=False)
    ]
    return {
        "schema_version": 1,
        "nodes": [
            {"id": "prepare", "operation": "retrieve.prepare_query", "params": {"top_k": 2}},
            {"id": "dense", "operation": "retrieve.dense"},
            {"id": "rerank", "operation": "select.rerank", "params": {"enabled": True}},
            {"id": "select", "operation": "select.threshold"},
            {"id": "context", "operation": "context.assemble"},
        ],
        "edges": edges,
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


def test_two_revisions_differing_only_in_wiring_run_differently(effective_settings: Any) -> None:
    """Same nodes, same store: moving one connection changes nodes run and output."""
    rows = chunks()
    # The reranker reverses the dense order: the last dense row scores highest.
    scores = {row["id"]: 0.90 + index * 0.03 for index, row in enumerate(rows)}
    # Reranking on: the dense stage fetches more rows than ``top_k``.
    settings = effective_settings(**{"retrieval.rerank_enabled": True})
    engine = build_engine(
        settings, FakeStore(rows), reranker=harness.ParityReranker(scores, fail=False)
    )
    rerank_first, select_first = _wired(["rerank", "select"]), _wired(["select", "rerank"])
    assert {n["id"] for n in rerank_first["nodes"]} == {n["id"] for n in select_first["nodes"]}

    results = {}
    for name, graph in (("rerank_first", rerank_first), ("select_first", select_first)):
        snapshot = engine.validate_pipeline(graph, inputs={"query": "text"})
        result = asyncio.run(engine.run_pipeline(snapshot))
        assert result.status is RunStatus.SUCCEEDED, result.error
        assert result.graph_identity == snapshot.graph_identity
        results[name] = result

    first, second = results["rerank_first"], results["select_first"]
    assert first.graph_identity != second.graph_identity
    assert [n.node_id for n in first.nodes] == ["prepare", "dense", "rerank", "select", "context"]
    assert [n.node_id for n in second.nodes] == ["prepare", "dense", "select", "rerank", "context"]
    ids_first = [r["source_id"] for r in first.outputs["context"].public_rows()]
    ids_second = [r["source_id"] for r in second.outputs["context"].public_rows()]
    assert ids_first == ["doc-s2", "doc-s1"]
    assert ids_second == ["doc-s1", "doc-s0"]


# ── Reader declares structured output ────────────────────────────────────


@pytest.mark.parametrize("structured", [True, False])
async def test_structured_reader_declaration_through_a_graph_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any, structured: bool
) -> None:
    """``structured=True`` skips enrichment and reaches the splitter as structured."""
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    real_read, real_split = graph_adapters.read_document, graph_adapters.split_documents
    real_enrich = graph_adapters.enrich_documents
    split_flags: list[bool] = []
    enriched: list[str] = []

    async def _read(file_path: Path, **kwargs: Any) -> BackendRead:
        read = await real_read(file_path, **kwargs)
        return BackendRead(read.documents, structured, read.text_format)

    async def _split(documents: list, file_path: Path, **kwargs: Any) -> list:
        split_flags.append(kwargs["structured"])
        return await real_split(documents, file_path, **kwargs)

    async def _enrich(documents: list, file_path: Path, **kwargs: Any) -> Any:
        enriched.append(Path(file_path).name)
        return await real_enrich(documents, file_path, **kwargs)

    monkeypatch.setattr(graph_adapters, "read_document", _read)
    monkeypatch.setattr(graph_adapters, "split_documents", _split)
    monkeypatch.setattr(graph_adapters, "enrich_documents", _enrich)
    engine = _lance_engine(tmp_path, offline_settings(effective_settings))
    events: list[Any] = []

    async def sink(event: Any) -> None:
        if event.kind == "node_completed" and event.node_id == "read":
            events.append(dict(event.data))

    result = await engine.run_pipeline(
        canonical_ingestion_definition("structured"), inputs={"path": str(root)}, on_event=sink
    )

    assert result.status is RunStatus.SUCCEEDED, result.error
    assert split_flags == [structured] * 3
    assert [e["structured"] for e in events] == [structured] * 3
    assert enriched == ([] if structured else ["guide.md", "appendix.md", "notes.txt"])
    engine.close()


# ── Canonical ingestion parity with degraded metadata ────────────────────


async def test_ingestion_parity_keeps_metadata_degraded_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """Graph and ``Engine.ingest`` both report degraded metadata and store equal rows."""
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)

    async def _degraded(text: str, file_name: str, settings: Any, *, store: Any = None) -> Any:
        return {"category": "fallback", "keywords": ["k1", "k2"]}, True

    monkeypatch.setattr(extractor, "extract_metadata_with_status_async", _degraded)
    engine = _lance_engine(tmp_path, offline_settings(effective_settings))
    standard = await engine.ingest(str(root), collection_name="standard")
    enrich_summaries: list[bool] = []

    async def sink(event: Any) -> None:
        if event.kind == "node_completed" and event.node_id == "enrich":
            enrich_summaries.append(event.data["metadata_degraded"])

    result = await engine.run_pipeline(
        canonical_ingestion_definition("graph"), inputs={"path": str(root)}, on_event=sink
    )

    assert result.status is RunStatus.SUCCEEDED, result.error
    by_file = {d["file"]: d["metadata_degraded"] for d in standard["file_details"]}
    assert set(by_file.values()) == {True}
    graph = {u.outputs["summary"]["file"]: u.outputs["summary"] for u in result.units}
    assert {f: s["metadata_degraded"] for f, s in graph.items()} == by_file
    assert enrich_summaries == [True, True, True]
    graph_rows = collect_rows(engine._store, "graph", root)
    assert graph_rows and graph_rows == collect_rows(engine._store, "standard", root)
    assert {row["metadata"]["category"] for row in graph_rows} == {"fallback"}
    engine.close()


# ── Registered replacement splitter through a graph run ──────────────────

_SENTINEL = "SENTINEL-GRAPH-SPLIT"
_sentinel_calls: list[dict[str, Any]] = []


async def _sentinel_sentence_strategy(
    documents: list,
    file_path: str,
    is_markdown: bool,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    settings: object | None = None,
    markdown_chunking: object | None = None,
) -> list:
    """Record the call and return one recognisable node."""
    _sentinel_calls.append({"file": Path(file_path).name, "is_markdown": is_markdown})
    return [TextNode(text=f"{_SENTINEL} {Path(file_path).name}", metadata={})]


async def test_registered_replacement_splitter_runs_in_a_graph(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """The ``sentence`` strategy from the registry splits every source of the run."""
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    _sentinel_calls.clear()
    monkeypatch.setitem(
        chunking_registry._registry, "sentence", f"{__name__}:_sentinel_sentence_strategy"
    )
    monkeypatch.delitem(chunking_registry._cache, "sentence", raising=False)
    engine = _lance_engine(tmp_path, offline_settings(effective_settings))
    try:
        result = await engine.run_pipeline(
            canonical_ingestion_definition("sentinel"), inputs={"path": str(root)}
        )
    finally:
        chunking_registry._cache.pop("sentence", None)

    assert result.status is RunStatus.SUCCEEDED, result.error
    assert sorted(c["file"] for c in _sentinel_calls) == ["appendix.md", "guide.md", "notes.txt"]
    assert {c["file"]: c["is_markdown"] for c in _sentinel_calls}["notes.txt"] is False
    assert {c["file"]: c["is_markdown"] for c in _sentinel_calls}["guide.md"] is True
    texts = sorted(row["text"] for row in collect_rows(engine._store, "sentinel", root))
    assert texts == sorted(f"{_SENTINEL} {Path(s).name}" for s in _SOURCES)
    engine.close()


# ── Metadata store ownership through Engine.run_pipeline ─────────────────


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> _Capture:
    """Replace ``httpx.AsyncClient`` and every retry sleep with fakes."""
    fake = _Capture()
    monkeypatch.setattr("httpx.AsyncClient", fake)

    async def _no_sleep(_seconds: float) -> None:
        return None

    for target in ("_common", "ollama", "llamacpp"):
        monkeypatch.setattr(f"omrg.core.metadata.{target}._retry_sleep", _no_sleep)
    return fake


@pytest.mark.parametrize("first", ["a", "b"])
def test_two_engines_graph_ingestion_prompts_hold_only_own_labels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capture: _Capture,
    effective_settings: Any,
    first: str,
) -> None:
    """Each graph run's classification prompt lists only its own store's labels."""
    pin_detection(monkeypatch)
    settings = effective_settings(
        extraction_mode="local", local_backend="ollama", hybrid_sparse_backend="native"
    )
    engines = {key: _lance_engine(tmp_path, settings, f"store-{key}") for key in ("a", "b")}
    markers = {"a": "zenith", "b": "aurora"}
    order = [first, "b" if first == "a" else "a"]

    for round_name in ("first", "second"):
        for key in order:
            docs = tmp_path / f"{key}-{round_name}"
            docs.mkdir()
            (docs / "notes.txt").write_text(f"{markers[key]} protocol notes.\n", "utf-8")
            result = asyncio.run(
                engines[key].run_pipeline(
                    canonical_ingestion_definition(round_name), inputs={"path": str(docs)}
                )
            )
            assert result.status is RunStatus.SUCCEEDED, result.error

    second_round = capture.prompts[2:]
    assert len(capture.prompts) == 4 and len(second_round) == 2
    for prompt in second_round:
        own = "zenith" if "Document:\nzenith" in prompt else "aurora"
        other = "aurora" if own == "zenith" else "zenith"
        categories = _prompt_categories(prompt)
        assert f"{own}_topic" in categories, prompt
        assert f"{other}_topic" not in categories, prompt
    for engine in engines.values():
        engine.close()
