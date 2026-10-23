"""Host probe of PDF readers and the catalogue (task 4.1 of add-pdf-reader-step-setting).

The Engine probes each registered reader once, on first use. The Read
document step stays available when a reader is missing. The catalogue lists
the missing reader with a reason, and validation refuses a step that
selects it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_engine_pipelines_support import build_engine
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrs.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrs.core.pipelines import IssueCode, PipelineValidationError
from omrs.integrations.pdf import registry


@pytest.fixture
def probes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make ``pypdfium2`` fail its probe and record every probed reader."""
    seen: list[str] = []

    def _probe(name: str) -> None:
        seen.append(name)
        if name == "pypdfium2":
            raise ImportError("PDF reader 'pypdfium2' dependency 'pypdfium2' is not importable")

    monkeypatch.setattr(registry, "probe", _probe)
    return seen


def _read_entry(engine: Any) -> dict[str, Any]:
    return next(e for e in engine.describe_operations() if e["operation_id"] == "read.document")


def _graph(reader: str) -> Any:
    definition = canonical_ingestion_definition("documents")
    data = definition.model_dump(mode="json")
    for node in data["graph"]["nodes"]:
        if node["id"] == "read":
            node["params"] = {**node["params"], "pdf_reader": reader}
    return data


def test_missing_reader_is_listed_and_the_step_stays_available(
    effective_settings: Any, probes: list[str]
) -> None:
    """``pypdfium2`` is reported with its package; the inherited reader is the host one."""
    engine = build_engine(offline_settings(effective_settings))
    entry = _read_entry(engine)
    assert entry["available"] is True
    reasons = entry["unavailable_options"]["pdf_reader"]
    assert list(reasons) == ["pypdfium2"]
    assert "pypdfium2" in reasons["pypdfium2"]
    assert entry["inherited_values"] == {"pdf_reader": "pypdf"}


def test_other_operations_report_empty_option_maps(
    effective_settings: Any, probes: list[str]
) -> None:
    """Operations without option parameters report two empty maps."""
    engine = build_engine(offline_settings(effective_settings))
    other = next(e for e in engine.describe_operations() if e["operation_id"] == "retrieve.dense")
    assert other["unavailable_options"] == {}
    assert other["inherited_values"] == {}


def test_each_reader_is_probed_once_per_engine(
    effective_settings: Any, probes: list[str], tmp_path: Path
) -> None:
    """Two catalogue calls and a validation probe every registered reader once."""
    engine = build_engine(offline_settings(effective_settings))
    engine.describe_operations()
    engine.describe_operations()
    engine.validate_pipeline(_graph("pypdf"), inputs={"path": str(tmp_path)})
    assert sorted(probes) == registry.available()


def test_selecting_a_missing_reader_fails_validation(
    effective_settings: Any, probes: list[str], tmp_path: Path
) -> None:
    """Admission refuses the node with ``option_unavailable`` and names the package."""
    engine = build_engine(offline_settings(effective_settings))
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(_graph("pypdfium2"), inputs={"path": str(tmp_path)})
    issue = next(i for i in caught.value.issues if i.code == IssueCode.OPTION_UNAVAILABLE)
    assert issue.node_id == "read"
    assert "pypdfium2" in issue.message


def test_selecting_an_installed_reader_validates(
    effective_settings: Any, probes: list[str], tmp_path: Path
) -> None:
    """An installed non-default reader passes validation."""
    engine = build_engine(offline_settings(effective_settings))
    engine.validate_pipeline(_graph("pdf_inspector"), inputs={"path": str(tmp_path)})


def test_pdf_reader_options_names_the_missing_package(probes: list[str]) -> None:
    """Installed readers map to ``None``; a missing one gives a reason with the package."""
    from omrs.capabilities import pdf_reader_options

    options = pdf_reader_options()
    assert set(options) == set(registry.available())
    assert options["pypdf"] is None
    assert "pypdfium2" in (options["pypdfium2"] or "")
