"""Task 2.1: versioned graph, result, event and validation-error models."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from tests.unit.test_pipeline_support import search_graph

from omrg.core.pipelines import (
    SCHEMA_VERSION,
    EventKind,
    GraphDocument,
    GraphLayout,
    IssueCode,
    NodeOutcome,
    NodeStatus,
    PipelineDefinition,
    PipelineEvent,
    PipelineIssue,
    PipelineResult,
    PipelineValidationError,
    RunStatus,
    parse_definition,
)


def _definition() -> PipelineDefinition:
    return PipelineDefinition(
        graph=GraphDocument.model_validate(search_graph()),
        layout=GraphLayout(
            title="Hybrid search",
            positions={"dense": {"x": 10.0, "y": 20.0}},
            viewport={"x": 0.0, "y": 0.0, "zoom": 1.0},
            selection=("dense",),
        ),
    )


def test_definition_json_round_trip_is_lossless() -> None:
    """A definition survives JSON serialisation unchanged."""
    original = _definition()
    restored = PipelineDefinition.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.graph.execution_identity() == original.graph.execution_identity()


def test_parse_definition_accepts_plain_data() -> None:
    """``parse_definition`` builds a definition from JSON-like data."""
    data = json.loads(_definition().model_dump_json())
    assert parse_definition(data) == _definition()


def test_parse_definition_accepts_bare_graph_document() -> None:
    """A bare graph document gets an empty layout."""
    parsed = parse_definition(search_graph())
    assert parsed.layout == GraphLayout()
    assert len(parsed.graph.nodes) == 6


def test_layout_change_keeps_execution_identity() -> None:
    """Moving nodes or the viewport is presentation only."""
    first = _definition()
    moved = first.model_copy(
        update={
            "layout": GraphLayout(
                title="Renamed",
                positions={"dense": {"x": 999.0, "y": -5.0}},
                viewport={"x": 50.0, "y": 50.0, "zoom": 2.0},
            )
        }
    )
    assert moved.graph.execution_identity() == first.graph.execution_identity()


def test_connection_change_changes_execution_identity() -> None:
    """Rewiring a graph changes its execution identity."""
    data = search_graph()
    rewired = search_graph()
    rewired["edges"][3]["source"] = {"node": "fuse", "port": "evidence"}
    first = GraphDocument.model_validate(data)
    second = GraphDocument.model_validate(rewired)
    assert first.execution_identity() != second.execution_identity()


def test_execution_identity_ignores_dict_key_order() -> None:
    """Identity is canonical, so parameter key order does not matter."""
    a = search_graph()
    a["nodes"][0]["params"] = {"top_k": 5, "collection": "docs"}
    b = search_graph()
    b["nodes"][0]["params"] = {"collection": "docs", "top_k": 5}
    assert (
        GraphDocument.model_validate(a).execution_identity()
        == GraphDocument.model_validate(b).execution_identity()
    )


@pytest.mark.parametrize("version", [0, 2, 99])
def test_unsupported_schema_version_is_rejected(version: int) -> None:
    """Unsupported versions fail with an actionable compatibility issue."""
    data = search_graph()
    data["schema_version"] = version
    with pytest.raises(PipelineValidationError) as excinfo:
        parse_definition(data)
    issue = excinfo.value.issues[0]
    assert issue.code == IssueCode.UNSUPPORTED_SCHEMA_VERSION
    assert str(SCHEMA_VERSION) in issue.message
    assert str(version) in issue.message


def test_missing_schema_version_is_rejected() -> None:
    """A graph without a schema version is not guessed."""
    data = search_graph()
    del data["schema_version"]
    with pytest.raises(PipelineValidationError) as excinfo:
        parse_definition(data)
    assert excinfo.value.codes == (IssueCode.UNSUPPORTED_SCHEMA_VERSION,)


def test_malformed_document_becomes_structured_error() -> None:
    """Pydantic errors become ``invalid_document`` issues."""
    data = search_graph()
    data["nodes"][0]["surprise"] = True
    with pytest.raises(PipelineValidationError) as excinfo:
        parse_definition(data)
    assert IssueCode.INVALID_DOCUMENT in excinfo.value.codes


def test_node_id_must_be_identifier() -> None:
    """Node identifiers cannot carry expressions."""
    data = search_graph()
    data["nodes"][0]["id"] = "__import__('os')"
    with pytest.raises(PipelineValidationError):
        parse_definition(data)


def test_graph_document_is_frozen() -> None:
    """Admitted documents cannot be mutated in place."""
    graph = GraphDocument.model_validate(search_graph())
    with pytest.raises(ValidationError):
        graph.profile = "codebase"  # type: ignore[misc]


def test_parameters_must_be_json_values() -> None:
    """Parameters hold JSON data only, never Python objects."""
    data = search_graph()
    data["nodes"][0]["params"] = {"top_k": object()}
    with pytest.raises(ValidationError):
        GraphDocument.model_validate(data)


def test_event_round_trip() -> None:
    """Events serialise and restore with their sequence and kind."""
    event = PipelineEvent(
        run_id="run-1",
        sequence=3,
        kind=EventKind.NODE_COMPLETED,
        node_id="dense",
        unit_id="source-1",
        message="10 rows",
        data={"rows": 10},
        timestamp=datetime(2026, 10, 13, tzinfo=UTC),
    )
    assert PipelineEvent.model_validate_json(event.model_dump_json()) == event


def test_result_round_trip_reports_failure_and_effects() -> None:
    """Results name the failing node, skipped dependants and effects."""
    result = PipelineResult(
        run_id="run-1",
        status=RunStatus.FAILED,
        graph_identity="abc",
        outputs={},
        nodes=(
            NodeOutcome(node_id="read", status=NodeStatus.SUCCEEDED),
            NodeOutcome(node_id="chunk", status=NodeStatus.FAILED, error="boom"),
            NodeOutcome(node_id="commit", status=NodeStatus.SKIPPED),
        ),
        failed_node="chunk",
        completed_effects=("committed source a.md",),
        wall_time_s=0.5,
        error="boom",
    )
    restored = PipelineResult.model_validate_json(result.model_dump_json())
    assert restored == result
    assert restored.skipped_nodes == ("commit",)


def test_validation_error_carries_structured_issues() -> None:
    """The error message and dict form name the first problem."""
    error = PipelineValidationError(
        [
            PipelineIssue(code=IssueCode.CYCLE, message="Remove one edge.", node_id="a"),
            PipelineIssue(code=IssueCode.MISSING_INPUT, message="Connect it.", node_id="b"),
        ]
    )
    assert isinstance(error, ValueError)
    assert "cycle" in str(error) and "+1 more issue" in str(error)
    payload = error.to_dict()
    assert payload["issues"][1] == {
        "code": "missing_input",
        "message": "Connect it.",
        "node_id": "b",
    }


def test_validation_error_requires_issues() -> None:
    """An error without issues is a programming mistake."""
    with pytest.raises(ValueError, match="at least one issue"):
        PipelineValidationError([])


# ── Lazy public exports ──────────────────────────────────────────────


def test_top_level_exports_graph_types() -> None:
    """The four graph types are public, lazy and declared in ``__all__``."""
    import omrg

    assert omrg.PipelineDefinition is PipelineDefinition
    assert omrg.PipelineResult is PipelineResult
    assert omrg.PipelineEvent is PipelineEvent
    assert omrg.PipelineValidationError is PipelineValidationError
    for name in (
        "PipelineDefinition",
        "PipelineResult",
        "PipelineEvent",
        "PipelineValidationError",
    ):
        assert name in omrg.__all__
        assert name in dir(omrg)


def test_importing_omrg_does_not_load_pipelines_or_settings() -> None:
    """Import is side-effect free; graph types load only on access."""
    code = (
        "import sys, omrg\n"
        "assert 'omrg.core.pipelines' not in sys.modules\n"
        "assert 'omrg.config' not in sys.modules\n"
        "omrg.PipelineDefinition\n"
        "assert 'omrg.core.pipelines' in sys.modules\n"
        "assert 'omrg.config' not in sys.modules, 'graph types must not resolve settings'\n"
        "assert 'networkx' not in sys.modules, 'networkx loads only for validation'\n"
    )
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr


def test_layout_direction_defaults_to_horizontal_and_accepts_vertical() -> None:
    assert GraphLayout().direction == "horizontal"
    assert GraphLayout.model_validate({"direction": "vertical"}).direction == "vertical"
    assert GraphLayout.model_validate({"positions": {}}).direction == "horizontal"


def test_layout_direction_refuses_other_values() -> None:
    with pytest.raises(ValidationError):
        GraphLayout.model_validate({"direction": "diagonal"})
