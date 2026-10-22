"""Content-type dispatch through ``read.document`` in a graph (verification gap B).

The parity fixtures hold only Markdown and text sources. This test feeds a
code source and a configuration source through the canonical ingestion
graph. Both files end in ``.txt``, so only the detected content type can
route them to the registered ``code`` and ``config`` strategies.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from llama_index.core import Settings as LlamaIndexSettings
from tests.fixtures.pipeline_parity.ingestion.snapshot import collect_rows
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrs.core.chunking import registry as chunking_registry
from omrs.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrs.core.pipelines import EventKind, RunStatus
from omrs.core.vectordb.lancedb.store import LanceVectorStore
from omrs.engine import Engine

_CONTENT_TYPES = {
    "script.txt": ("code", "python"),
    "service.txt": ("config", "yaml"),
}
_PYTHON = '''"""Small module."""


def add(a: int, b: int) -> int:
    """Return the sum."""
    return a + b


class Counter:
    """Count calls."""

    def __init__(self) -> None:
        self.calls = 0

    def tick(self) -> int:
        self.calls += 1
        return self.calls
'''
_YAML = "service:\n  name: demo\n  port: 8080\n  replicas: 2\n"


def _pin_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report the scripted Magika types for the two sources."""
    from omrs.core.codebase import codebase_map

    def _detect(path: str, *, settings: Any) -> SimpleNamespace:
        entries = [
            SimpleNamespace(path=name, group=group, label=label)
            for name, (group, label) in _CONTENT_TYPES.items()
        ]
        return SimpleNamespace(entries=entries)

    monkeypatch.setattr(codebase_map, "detect_file_types", _detect)


def _spy_strategy(monkeypatch: pytest.MonkeyPatch, name: str, calls: list[str]) -> None:
    """Wrap the registered strategy ``name`` so each call is recorded."""
    real = chunking_registry.get(name)

    def _spy(file_path: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(Path(file_path).name)
        return real(file_path, *args, **kwargs)

    monkeypatch.setitem(chunking_registry._cache, name, _spy)


async def test_code_and_config_sources_route_through_read_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """The detected type selects the strategy and stays on every stored chunk."""
    root = tmp_path / "sources"
    root.mkdir()
    (root / "script.txt").write_text(_PYTHON, encoding="utf-8")
    (root / "service.txt").write_text(_YAML, encoding="utf-8")
    _pin_types(monkeypatch)
    code_calls: list[str] = []
    config_calls: list[str] = []
    _spy_strategy(monkeypatch, "code", code_calls)
    _spy_strategy(monkeypatch, "config", config_calls)
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    engine = Engine(
        offline_settings(effective_settings),
        store=store,
        embed_model=LlamaIndexSettings.embed_model,
    )
    reads: dict[str, dict[str, Any]] = {}

    async def sink(event: Any) -> None:
        if event.kind == EventKind.NODE_COMPLETED and event.node_id == "read":
            reads[str(event.unit_id)] = dict(event.data)

    result = await engine.run_pipeline(
        canonical_ingestion_definition("typed"), inputs={"path": str(root)}, on_event=sink
    )

    assert result.status is RunStatus.SUCCEEDED, result.error
    assert code_calls == ["script.txt"]
    assert config_calls == ["service.txt"]
    assert {unit: data.get("specialised") for unit, data in reads.items()} == {
        "script.txt": True,
        "service.txt": True,
    }
    rows = collect_rows(store, "typed", root)
    by_file: dict[str, set[str]] = {}
    for row in rows:
        by_file.setdefault(row["rel_path"], set()).add(row["metadata"]["content_type"])
    assert by_file == {"script.txt": {"code/python"}, "service.txt": {"config/yaml"}}
    engine.close()
