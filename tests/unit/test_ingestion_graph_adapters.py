"""Ingestion graph adapters reproduce ``ingest_path_async`` (task 3.4).

The canonical ingestion graph is admitted for real and its adapters are
chained by hand over ``tests/fixtures/pipeline_parity/ingestion/``. Stored
chunk ids, texts, metadata and per-source outcomes must equal the standard
path. Other tests pin the catalogue contract, reader declarations, the
bounded one-source-at-a-time input, explicit resources, and that only the
commit node mutates the store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.ingestion.snapshot import (
    collect_rows,
    copy_sources,
    load_expected,
    pin_detection,
    portable_rows,
)
from tests.unit.test_ingestion_graph_adapters_support import (
    CANONICAL_NODES,
    admit,
    build_catalogue,
    canonical_graph,
    invoke,
    offline_settings,
    resources,
    run_by_hand,
)

from omrg.core.ingestion import graph_adapters, pipeline
from omrg.core.ingestion.graph_adapters import SourceWork, source_unit_id
from omrg.core.ingestion.sources import SourceUnit
from omrg.core.pipelines import EffectClass, PortKind, preflight

_OPERATIONS = {
    "source.discover",
    "source.identify",
    "read.document",
    "prepare.normalise",
    "prepare.enrich",
    "prepare.chunk",
    "embed.chunks",
    "commit.source",
}


# ── Catalogue contract ──────────────────────────────────────────────────


def test_register_publishes_every_ingestion_operation() -> None:
    """One registration call adds the four ingestion families."""
    catalogue = build_catalogue()
    assert {d.operation_id for d in catalogue.descriptors()} == _OPERATIONS
    assert {d.family for d in catalogue.descriptors()} == {
        "sources",
        "read",
        "prepare",
        "embed",
        "commit",
    }


def test_only_the_commit_operation_mutates_the_store() -> None:
    """``commit.source`` is the single protected source-commit operation."""
    commits = [d for d in build_catalogue().descriptors() if d.effect is EffectClass.SOURCE_COMMIT]
    assert [d.operation_id for d in commits] == ["commit.source"]
    assert commits[0].collection_param == "collection"
    commit_input = commits[0].input_port("chunks")
    assert commit_input is not None
    assert commit_input.type.kind is PortKind.EMBEDDED_CHUNKS
    assert commit_input.type.embedding_identity


def test_read_keeps_reader_declarations_on_its_port() -> None:
    """The read output promises ``text_format`` and ``structured``."""
    read = build_catalogue().get("read.document")
    assert read is not None
    documents = read.descriptor.output_port("documents")
    assert documents is not None
    assert documents.type.reader_declarations == {"text_format", "structured"}


def test_canonical_graph_passes_preflight() -> None:
    """The canonical template validates against the published catalogue."""
    from omrg.core.pipelines import parse_definition

    definition = parse_definition(canonical_graph("documents"))
    report = preflight(definition, build_catalogue(), inputs={"path": "/tmp/x"})
    assert report.issues == ()
    assert report.order == CANONICAL_NODES


def test_embedding_cannot_be_bypassed_into_the_commit() -> None:
    """Chunks without vectors cannot reach the vector-only commit port."""
    from omrg.core.pipelines import parse_definition

    data = canonical_graph("documents")
    data["graph"]["edges"] = [
        e for e in data["graph"]["edges"] if e["target"]["node"] not in {"embed", "commit"}
    ] + [
        {
            "source": {"node": "chunk", "port": "chunks"},
            "target": {"node": "commit", "port": "chunks"},
        }
    ]
    data["graph"]["nodes"] = [n for n in data["graph"]["nodes"] if n["id"] != "embed"]
    report = preflight(parse_definition(data), build_catalogue(), inputs={"path": "/tmp/x"})
    assert "incompatible_ports" in {issue.code for issue in report.issues}


# ── Parity with ingest_path_async ───────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_chain_matches_ingest_path_async(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """Chunk ids, texts, metadata and per-source outcomes agree."""
    from omrg.core.vectordb import get_default_store

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = offline_settings(effective_settings)
    store = get_default_store()
    catalogue = build_catalogue()

    standard = await pipeline.ingest_path_async(
        str(root), collection_name="graph_standard", effective_settings=settings, store=store
    )
    snapshot = admit(canonical_graph("graph_parity"), settings, root, catalogue)
    outputs = await run_by_hand(snapshot, catalogue, resources(snapshot, catalogue, store))

    assert standard["status"] == "ok", standard
    graph_rows = collect_rows(store, "graph_parity", root)
    assert graph_rows == collect_rows(store, "graph_standard", root)
    assert portable_rows(graph_rows) == load_expected()
    summaries = [o.values["summary"] for o in outputs]
    keys = ("file", "status", "chunks", "source_version")
    expected = sorted((tuple(d.get(k) for k in keys) for d in standard["file_details"]), key=str)
    assert sorted((tuple(s.get(k) for k in keys) for s in summaries), key=str) == expected
    assert sum(s["chunks"] for s in summaries) == standard["chunks_created"]
    assert all(o.effects == (f"committed:{o.values['summary']['source_id']}",) for o in outputs)


@pytest.mark.asyncio
async def test_unchanged_sources_skip_expensive_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """After a standard ingest, the canonical graph reuses every source."""
    from omrg.core.vectordb import get_default_store

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = offline_settings(effective_settings)
    store = get_default_store()
    catalogue = build_catalogue()
    await pipeline.ingest_path_async(
        str(root), collection_name="graph_reuse", effective_settings=settings, store=store
    )

    async def _no_read(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("an unchanged source was read")

    monkeypatch.setattr(graph_adapters, "read_document", _no_read)
    snapshot = admit(canonical_graph("graph_reuse"), settings, root, catalogue)
    outputs = await run_by_hand(snapshot, catalogue, resources(snapshot, catalogue, store))

    assert [o.values["summary"]["status"] for o in outputs] == ["skipped_unchanged"] * 3
    assert all(o.effects == () for o in outputs)


# ── Stage behaviour ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reader_markdown_declaration_reaches_the_splitter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """A ``.txt`` source whose reader declares Markdown splits as Markdown."""
    from omrg.core.ingestion.backends.orchestrator import BackendRead
    from omrg.core.vectordb import get_default_store

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = offline_settings(effective_settings)
    store = get_default_store()
    catalogue = build_catalogue()
    real_read = graph_adapters.read_document

    async def _markdown_read(file_path: Path, **kwargs: Any) -> BackendRead:
        read = await real_read(file_path, **kwargs)
        return BackendRead(read.documents, read.structured, "markdown")

    seen: list[bool] = []
    real_split = graph_adapters.split_documents

    async def _spy_split(documents: list, file_path: Path, **kwargs: Any) -> list:
        seen.append(kwargs["is_markdown"])
        return await real_split(documents, file_path, **kwargs)

    monkeypatch.setattr(graph_adapters, "read_document", _markdown_read)
    monkeypatch.setattr(graph_adapters, "split_documents", _spy_split)
    snapshot = admit(canonical_graph("graph_markdown"), settings, root, catalogue)
    await run_by_hand(snapshot, catalogue, resources(snapshot, catalogue, store))

    assert seen == [True, True, True]


@pytest.mark.asyncio
async def test_identify_refuses_more_than_one_source(
    tmp_path: Path, effective_settings: Any
) -> None:
    """A whole directory list cannot enter one per-source chain."""
    from omrg.core.vectordb import get_default_store

    settings = offline_settings(effective_settings)
    catalogue = build_catalogue()
    snapshot = admit(canonical_graph("graph_bounded"), settings, tmp_path, catalogue)
    units = (
        SourceUnit(0, tmp_path / "a.md", "a.md", None),
        SourceUnit(1, tmp_path / "b.md", "b.md", None),
    )
    run_resources = resources(snapshot, catalogue, get_default_store())
    with pytest.raises(ValueError, match="one source unit"):
        await invoke(snapshot, catalogue, run_resources, "identify", {"sources": units})


def test_source_unit_id_is_the_relative_path(tmp_path: Path) -> None:
    """Unit events name the source by its path relative to the root."""
    assert source_unit_id(SourceUnit(3, tmp_path / "n" / "a.md", "n/a.md", None)) == "n/a.md"


@pytest.mark.asyncio
async def test_binary_source_cleanup_happens_only_in_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """A binary unit passes through; the commit removes its stale rows."""
    from omrg.core.vectordb import get_default_store

    settings = offline_settings(effective_settings)
    store = get_default_store()
    catalogue = build_catalogue()
    snapshot = admit(canonical_graph("graph_binary"), settings, tmp_path, catalogue)
    run_resources = resources(snapshot, catalogue, _ReadOnlyStore(store))
    unit = SourceUnit(0, tmp_path / "blob.md", "blob.md", "binary/unknown")

    value: Any = (unit,)
    for node_id, in_port, out_port in (
        ("identify", "sources", "sources"),
        ("read", "sources", "documents"),
        ("normalise", "documents", "documents"),
        ("enrich", "documents", "documents"),
        ("chunk", "documents", "chunks"),
        ("embed", "chunks", "chunks"),
    ):
        output = await invoke(snapshot, catalogue, run_resources, node_id, {in_port: value})
        value = output.values[out_port]
    assert isinstance(value, SourceWork) and value.status == "binary"

    summary = await invoke(
        snapshot, catalogue, resources(snapshot, catalogue, store), "commit", {"chunks": value}
    )
    assert summary.values["summary"]["status"] == "skipped"


# ── Explicit resources and settings ─────────────────────────────────────


class _ReadOnlyStore:
    """Store proxy that fails on every mutation."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def __getattr__(self, name: str) -> Any:
        if name in {"write_nodes", "delete_ids", "delete_where", "delete_collection"}:
            raise AssertionError(f"a non-commit node called store.{name}")
        return getattr(self._store, name)


@pytest.mark.asyncio
async def test_non_commit_nodes_never_mutate_the_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """Every node before the commit reads only; the commit writes."""
    from omrg.core.vectordb import get_default_store

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = offline_settings(effective_settings)
    store = get_default_store()
    catalogue = build_catalogue()
    data = canonical_graph("graph_readonly")
    data["graph"]["nodes"] = [n for n in data["graph"]["nodes"] if n["id"] != "commit"]
    data["graph"]["edges"] = [e for e in data["graph"]["edges"] if e["target"]["node"] != "commit"]
    data["graph"]["outputs"] = [{"name": "chunks", "source": {"node": "embed", "port": "chunks"}}]
    snapshot = admit(data, settings, root, catalogue)

    outputs = await run_by_hand(
        snapshot, catalogue, resources(snapshot, catalogue, _ReadOnlyStore(store))
    )

    assert sum(o.values["chunks"].prepared.chunk_count for o in outputs) == len(load_expected())
    assert not store.collection_exists("graph_readonly")


@pytest.mark.asyncio
async def test_adapters_never_read_process_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """With no process defaults installed, the explicit chain still ingests."""
    from omrg.core.settings import reset_default_effective_settings
    from omrg.core.vectordb import get_default_store, reset_default_store

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = offline_settings(effective_settings)
    store = get_default_store()
    catalogue = build_catalogue()
    snapshot = admit(canonical_graph("graph_no_defaults"), settings, root, catalogue)
    run_resources = resources(snapshot, catalogue, store)
    reset_default_effective_settings()
    reset_default_store()

    await run_by_hand(snapshot, catalogue, run_resources)

    assert portable_rows(collect_rows(store, "graph_no_defaults", root)) == load_expected()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["store", "embedder", "ingestion_shape"])
async def test_missing_resource_fails_before_any_work(
    tmp_path: Path, effective_settings: Any, missing: str
) -> None:
    """The identify node never substitutes a default for a missing resource."""
    from omrg.core.vectordb import get_default_store

    (tmp_path / "a.md").write_text("# A\n\ntext\n", encoding="utf-8")
    settings = offline_settings(effective_settings)
    catalogue = build_catalogue()
    snapshot = admit(canonical_graph("graph_missing"), settings, tmp_path, catalogue)
    run_resources = resources(snapshot, catalogue, get_default_store())
    del run_resources[missing]
    unit = SourceUnit(0, tmp_path / "a.md", "a.md", None)
    with pytest.raises(LookupError, match=missing):
        await invoke(snapshot, catalogue, run_resources, "identify", {"sources": (unit,)})


# ── Through the runner ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_runner_unit_split_matches_ingest_path_async(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """``run_pipeline`` with the ingestion unit split writes the same rows."""
    from omrg.core.ingestion.graph_adapters import ingestion_unit_split
    from omrg.core.pipelines import RunStatus, run_pipeline
    from omrg.core.vectordb import get_default_store

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = offline_settings(effective_settings)
    store = get_default_store()
    catalogue = build_catalogue()
    await pipeline.ingest_path_async(
        str(root), collection_name="runner_standard", effective_settings=settings, store=store
    )
    snapshot = admit(canonical_graph("runner_graph"), settings, root, catalogue)

    result = await run_pipeline(
        snapshot,
        catalogue,
        resources(snapshot, catalogue, store),
        units=ingestion_unit_split(),
    )

    assert result.status is RunStatus.SUCCEEDED, result.error
    assert [u.unit_id for u in result.units] == ["guide.md", "nested/appendix.md", "notes.txt"]
    assert len(result.completed_effects) == 3
    assert collect_rows(store, "runner_graph", root) == collect_rows(store, "runner_standard", root)
