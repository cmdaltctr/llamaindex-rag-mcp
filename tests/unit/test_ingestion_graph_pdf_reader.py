"""The Read document step selects its PDF reader (task 2.1 of add-pdf-reader-step-setting).

``pdf_reader`` is a node parameter. ``None`` inherits the host reader; a set
value is one of the registered concrete readers and never ``auto``. The read
adapter reads with a copy of its settings that carries the step reader, so
the host default stays untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tests.unit.test_ingestion_graph_adapters_support import build_catalogue

from omrg.core.ingestion import graph_adapters
from omrg.core.ingestion.backends.orchestrator import BackendRead
from omrg.core.ingestion.graph_adapters import SourceWork
from omrg.core.ingestion.graph_adapters_catalogue import ReadParams
from omrg.core.ingestion.sources import SourceUnit
from omrg.core.pipelines import CancellationFlag, NodeContext
from omrg.integrations.pdf import registry


def _read_descriptor() -> Any:
    entry = build_catalogue().get("read.document")
    assert entry is not None
    return entry.descriptor


def _enum_of(schema: dict[str, Any]) -> list[str]:
    options = schema["properties"]["pdf_reader"]["anyOf"]
    return next(option["enum"] for option in options if "enum" in option)


# ── Parameter contract ───────────────────────────────────────────────────


def test_pdf_reader_choices_equal_the_registry() -> None:
    """The schema enum lists the registered concrete readers and nothing else."""
    assert _enum_of(ReadParams.model_json_schema()) == registry.available()
    assert "auto" not in _enum_of(ReadParams.model_json_schema())


def test_pdf_reader_defaults_to_inherit() -> None:
    """``None`` means the step inherits the host reader."""
    assert ReadParams().pdf_reader is None
    assert ReadParams(pdf_reader=None).pdf_reader is None


@pytest.mark.parametrize("name", registry.available())
def test_every_registered_reader_is_accepted(name: str) -> None:
    """A registered concrete reader validates."""
    assert ReadParams(pdf_reader=name).pdf_reader == name


@pytest.mark.parametrize("value", ["auto", "fastparser", ""])
def test_auto_and_unknown_readers_fail_validation(value: str) -> None:
    """``auto`` is a host policy, so a step cannot choose it."""
    with pytest.raises(ValidationError, match="pdf_reader"):
        ReadParams(pdf_reader=value)


def test_auto_message_tells_the_user_what_to_do() -> None:
    """The rejection of ``auto`` names the two valid choices."""
    with pytest.raises(ValidationError, match="concrete reader or inherit"):
        ReadParams(pdf_reader="auto")


def test_read_document_declares_the_reader_as_an_option_parameter() -> None:
    """The host reports reader availability for this parameter."""
    assert _read_descriptor().option_params == {"pdf_reader": "pdf_reader"}


# ── Adapter behaviour ────────────────────────────────────────────────────


async def _read_with(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any, step_reader: str | None
) -> str:
    """Run ``read_adapter`` and return the reader that ``read_document`` saw."""
    seen: list[str] = []

    async def _spy(_file_path: Path, **kwargs: Any) -> BackendRead:
        seen.append(kwargs["settings"].pdf_reader)
        return BackendRead([], False, "plain")

    async def _no_specialised(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(graph_adapters, "read_document", _spy)
    monkeypatch.setattr(graph_adapters, "chunk_specialised_source", _no_specialised)
    host = effective_settings(pdf_reader="pypdf")
    context = NodeContext(
        run_id="r",
        node_id="read",
        settings=host,
        resources={},
        cancellation=CancellationFlag(),
        collection="documents",
        unit_id="u",
    )
    unit = SourceUnit(0, Path("smoke_text.pdf"), "smoke_text.pdf", "application/pdf")
    work = SourceWork(unit, "documents")
    await graph_adapters.read_adapter(
        context, {"sources": work}, ReadParams(pdf_reader=step_reader)
    )
    assert host.pdf_reader == "pypdf"
    return seen[0]


@pytest.mark.asyncio
async def test_read_adapter_reads_with_the_step_reader(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    """A set reader reaches ``read_document`` and leaves the host settings alone."""
    assert await _read_with(monkeypatch, effective_settings, "pdf_inspector") == "pdf_inspector"


@pytest.mark.asyncio
async def test_read_adapter_inherits_the_host_reader(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    """``None`` passes the host reader through."""
    assert await _read_with(monkeypatch, effective_settings, None) == "pypdf"
