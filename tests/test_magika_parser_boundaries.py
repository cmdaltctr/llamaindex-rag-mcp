"""Fail-first regressions for the pinned Magika parser and ingestion boundary.

Each test maps to tasks 1.3 through 1.5 of the ``pin-magika-detection``
OpenSpec change. The CLI is always faked. No test needs a live detector,
reader, embedder, store, or network service.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import TextNode

from omrg.core.codebase import codebase_map
from omrg.core.codebase.codebase_map import FileEntry, detect_file_types
from omrg.core.ingestion import chunker, pipeline
from omrg.integrations import magika


def _magika_row(path: Path, *, group: str, label: str, is_text: bool) -> str:
    """Build one verified Magika 1.0.3 JSONL row."""
    return json.dumps(
        {
            "path": str(path),
            "result": {
                "status": "ok",
                "value": {
                    "dl": {"label": "ignored-model-output"},
                    "output": {
                        "group": group,
                        "label": label,
                        "is_text": is_text,
                    },
                    "score": 0.96,
                },
            },
        }
    )


def _scan_jsonl(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    stdout: str,
    settings: object,
) -> list[FileEntry]:
    """Run the Magika parser against deterministic CLI JSONL."""
    monkeypatch.setattr(magika, "_is_magika_available", lambda settings: True)
    monkeypatch.setattr(
        magika.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=stdout, stderr=""),
    )
    return magika.scan_with_magika(str(root), settings=settings)


def test_scan_reads_nested_output_instead_of_model_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    effective_settings,
) -> None:
    """Task 1.3: only ``result.value.output`` supplies the public label."""
    source = tmp_path / "probe.txt"
    source.write_text("def answer() -> int:\n    return 42\n", encoding="utf-8")

    entries = _scan_jsonl(
        monkeypatch,
        tmp_path,
        _magika_row(source, group="code", label="python", is_text=True),
        effective_settings(),
    )

    assert [(entry.path, entry.group, entry.label, entry.is_text) for entry in entries] == [
        ("probe.txt", "code", "python", True)
    ]


@pytest.mark.parametrize(
    ("case", "row"),
    [
        (
            "non-ok status",
            {
                "path": "/ignored/probe.txt",
                "result": {"status": "error", "value": {"output": {}}},
            },
        ),
        ("non-json row", "this is not JSONL"),
        (
            "missing output",
            {"path": "/ignored/probe.txt", "result": {"status": "ok", "value": {}}},
        ),
        (
            "empty group",
            {
                "path": "/ignored/probe.txt",
                "result": {
                    "status": "ok",
                    "value": {"output": {"group": "", "label": "txt", "is_text": True}},
                },
            },
        ),
        (
            "empty label",
            {
                "path": "/ignored/probe.txt",
                "result": {
                    "status": "ok",
                    "value": {"output": {"group": "text", "label": "", "is_text": True}},
                },
            },
        ),
        (
            "non-boolean is_text",
            {
                "path": "/ignored/probe.txt",
                "result": {
                    "status": "ok",
                    "value": {"output": {"group": "text", "label": "txt", "is_text": 1}},
                },
            },
        ),
    ],
)
def test_scan_rejects_invalid_cli_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    effective_settings,
    case: str,
    row: dict[str, object] | str,
) -> None:
    """Task 1.3: one invalid record invalidates the whole detector scan."""
    stdout = row if isinstance(row, str) else json.dumps(row)

    with pytest.raises(ValueError, match="Magika"):
        _scan_jsonl(monkeypatch, tmp_path, stdout, effective_settings())


def test_scan_ignores_blank_lines_without_omitting_valid_records(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    effective_settings,
) -> None:
    """Task 1.3: blank JSONL lines are inert, not detector failures."""
    source = tmp_path / "note.md"
    source.write_text("# Note\n", encoding="utf-8")
    stdout = f"\n   \n{_magika_row(source, group='text', label='markdown', is_text=True)}\n\n"

    entries = _scan_jsonl(monkeypatch, tmp_path, stdout, effective_settings())

    assert [(entry.path, entry.group, entry.label) for entry in entries] == [
        ("note.md", "document", "markdown")
    ]


def test_scan_applies_only_the_specified_boundary_and_alias_rules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    effective_settings,
) -> None:
    """Task 1.4: preserve readable groups and change only two text aliases."""
    rows = [
        _magika_row(tmp_path / "archive.pdf", group="unknown", label="unknown", is_text=False),
        _magika_row(tmp_path / "paper.pdf", group="document", label="pdf", is_text=False),
        _magika_row(tmp_path / "binary.py", group="code", label="python", is_text=False),
        _magika_row(tmp_path / "opaque.txt", group="text", label="txt", is_text=False),
        _magika_row(tmp_path / "note.md", group="text", label="markdown", is_text=True),
        _magika_row(tmp_path / "plain.txt", group="text", label="txt", is_text=True),
        _magika_row(tmp_path / "data.csv", group="text", label="csv", is_text=True),
    ]

    entries = _scan_jsonl(monkeypatch, tmp_path, "\n".join(rows), effective_settings())
    observed = {entry.path: (entry.group, entry.label, entry.is_text) for entry in entries}

    assert observed == {
        "archive.pdf": ("binary", "unknown", False),
        "paper.pdf": ("document", "pdf", False),
        "binary.py": ("code", "python", False),
        "opaque.txt": ("text", "txt", False),
        "note.md": ("document", "markdown", True),
        "plain.txt": ("document", "text", True),
        "data.csv": ("text", "csv", True),
    }


def test_detect_file_types_warns_and_uses_whole_scan_suffix_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    effective_settings,
) -> None:
    """Task 1.3: ValueError means fallback, never unknown rows or partial data."""
    suffix_entries = [FileEntry("probe.txt", "document", "text", True, ".txt")]
    monkeypatch.setattr(codebase_map, "_is_magika_available", lambda settings: True)
    monkeypatch.setattr(
        codebase_map,
        "scan_with_magika",
        lambda path, settings: (_ for _ in ()).throw(ValueError("Magika invalid record")),
    )
    monkeypatch.setattr(codebase_map, "scan_with_suffix", lambda path, settings: suffix_entries)

    with caplog.at_level(logging.WARNING, logger="omrg.core.codebase.codebase_map"):
        inventory = detect_file_types(str(tmp_path), settings=effective_settings())

    assert inventory.entries == suffix_entries
    assert inventory.type_counts == {"document/text": 1}
    assert any(
        "falling back to suffix detection" in record.getMessage() for record in caplog.records
    )


def _configure_pipeline_fakes(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace store writes and lineage lookups with no-I/O test seams."""
    fake_store = SimpleNamespace(collection_exists=lambda name: False)
    timings = SimpleNamespace(
        as_dict=lambda: {
            "embedding_seconds": 0.0,
            "store_write_seconds": 0.0,
            "lock_wait_seconds": 0.0,
            "cleanup_seconds": 0.0,
        }
    )

    async def fake_replace(nodes, **kwargs):
        return SimpleNamespace(
            chunks_written=len(nodes),
            chunks_removed=0,
            norm_band=None,
            timings=timings,
        )

    monkeypatch.setattr(pipeline, "is_complete_current_version", lambda *args, **kwargs: (False, 0))
    monkeypatch.setattr(pipeline, "replace_source_nodes_async", fake_replace)
    monkeypatch.setattr(pipeline, "resolve_declared_text_format", lambda *args, **kwargs: "plain")
    return fake_store


def _enable_cli_jsonl(monkeypatch: pytest.MonkeyPatch, stdout: str) -> None:
    """Configure the production parser's subprocess boundary only."""
    monkeypatch.setattr(magika, "_is_magika_available", lambda settings: True)
    monkeypatch.setattr(
        magika.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=stdout, stderr=""),
    )


@pytest.mark.asyncio
async def test_binary_content_renamed_pdf_skips_before_reader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    effective_settings,
) -> None:
    """Task 1.4: unreadable non-document content bypasses every reader."""
    source = tmp_path / "archive.pdf"
    source.write_bytes(b"PK\x03\x04" + b"zip payload")
    _enable_cli_jsonl(
        monkeypatch,
        _magika_row(source, group="unknown", label="unknown", is_text=False),
    )
    fake_store = _configure_pipeline_fakes(monkeypatch)
    reader = AsyncMock(side_effect=AssertionError("binary content reached a reader"))
    monkeypatch.setattr(pipeline, "read_and_chunk_file_async", reader)

    result = await pipeline.ingest_path_async(
        str(source),
        collection_name="magika_binary_boundary",
        effective_settings=effective_settings(),
        store=fake_store,
    )

    assert result["status"] == "ok", result
    assert result["files_indexed"] == 0
    reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_pdf_detection_preserves_document_type_for_stub_reader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    effective_settings,
) -> None:
    """Task 1.4: a detected PDF remains readable with ``is_text=False``."""
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.4\nminimal test fixture\n")
    _enable_cli_jsonl(
        monkeypatch, _magika_row(source, group="document", label="pdf", is_text=False)
    )
    fake_store = _configure_pipeline_fakes(monkeypatch)
    reader = AsyncMock(return_value=[TextNode(text="stub reader output")])
    monkeypatch.setattr(pipeline, "read_and_chunk_file_async", reader)

    result = await pipeline.ingest_path_async(
        str(source),
        collection_name="magika_pdf_boundary",
        effective_settings=effective_settings(pdf_reader="pypdf"),
        store=fake_store,
    )

    assert result["status"] == "ok", result
    assert reader.await_args is not None
    assert reader.await_args.kwargs["content_type"] == "document/pdf"


@pytest.mark.asyncio
async def test_substantial_misnamed_python_uses_ast_splitter_with_injected_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    effective_settings,
) -> None:
    """Task 1.5: direct-file ``.`` keys retain injected code routing."""
    source = tmp_path / "module.txt"
    source.write_text(
        "\n".join(
            [
                '"""Substantial source fixture."""',
                "",
                "def add(left: int, right: int) -> int:",
                '    """Return a stable sum."""',
                "    return left + right",
                "",
                "class Counter:",
                "    def __init__(self, value: int = 0) -> None:",
                "        self.value = value",
                "",
                "    def increment(self) -> int:",
                "        self.value += 1",
                "        return self.value",
            ]
        ),
        encoding="utf-8",
    )
    _enable_cli_jsonl(monkeypatch, _magika_row(source, group="code", label="python", is_text=True))
    fake_store = _configure_pipeline_fakes(monkeypatch)
    observed: dict[str, object] = {}

    async def fake_code_splitter(*args, **kwargs):
        observed["language"] = args[1]
        observed["content_type"] = args[4]
        return [TextNode(text="AST-split source", metadata={})]

    async def fail_document_reader(*args, **kwargs):
        raise AssertionError("misnamed Python used the document reader")

    monkeypatch.setattr(
        chunker,
        "_chunking_get",
        lambda name: fake_code_splitter if name == "code" else pytest.fail(name),
    )
    monkeypatch.setattr(chunker, "read_document", fail_document_reader)
    monkeypatch.setattr(
        magika,
        "get_default_effective_settings",
        lambda: (_ for _ in ()).throw(AssertionError("global settings read attempted")),
    )

    result = await pipeline.ingest_path_async(
        str(source),
        collection_name="magika_ast_splitter",
        effective_settings=effective_settings(),
        store=fake_store,
        embed_model=MockEmbedding(embed_dim=8),
    )

    assert result["status"] == "ok", result
    assert observed == {"language": "python", "content_type": "code/python"}
