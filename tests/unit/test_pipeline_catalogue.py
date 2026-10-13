"""Task 2.2: operation catalogue, port contracts and registration."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from tests.unit.test_pipeline_support import (
    ANY_EVIDENCE,
    CHUNKS,
    DENSE_EVIDENCE,
    EMBEDDED,
    FUSED_EVIDENCE,
    NoParams,
    RerankParams,
    fixture_catalogue,
    fixture_descriptors,
    noop_adapter,
)

from omrg.core.pipelines import (
    SCORE_KIND_DENSE,
    SCORE_KIND_NATIVE_SPARSE,
    SCORE_KIND_RERANK,
    SCORE_KIND_RRF,
    BypassSpec,
    Cardinality,
    EffectClass,
    OperationCatalogue,
    OperationDescriptor,
    PortKind,
    PortSpec,
    PortType,
    Provenance,
    check_port_compatibility,
)

PIPELINES_DIR = Path(__file__).resolve().parents[2] / "src" / "omrg" / "core" / "pipelines"


def _descriptor(**overrides: object) -> OperationDescriptor:
    base: dict[str, object] = {
        "operation_id": "select.example",
        "version": 1,
        "title": "Example",
        "family": "select",
        "parameters": NoParams,
        "inputs": (PortSpec(name="evidence", type=ANY_EVIDENCE),),
        "outputs": (PortSpec(name="evidence", type=ANY_EVIDENCE),),
        "effect": EffectClass.PURE,
    }
    base.update(overrides)
    return OperationDescriptor(**base)  # type: ignore[arg-type]


# ── Port contracts ───────────────────────────────────────────────────


def test_score_kind_constants_match_domain_constants() -> None:
    """Graph score kinds are the same strings the domains emit."""
    from omrg.core.retrieval.fusion import RRF_SCORE_KIND
    from omrg.core.retrieval.pipeline import RERANK_SCORE_KIND
    from omrg.core.vectordb.score import DENSE_SCORE_KIND, NATIVE_SPARSE_SCORE_KIND

    assert SCORE_KIND_DENSE == DENSE_SCORE_KIND
    assert SCORE_KIND_NATIVE_SPARSE == NATIVE_SPARSE_SCORE_KIND
    assert SCORE_KIND_RRF == RRF_SCORE_KIND
    assert SCORE_KIND_RERANK == RERANK_SCORE_KIND


def test_matching_ports_are_compatible() -> None:
    """A dense producer satisfies an any-score evidence consumer."""
    assert check_port_compatibility(DENSE_EVIDENCE, ANY_EVIDENCE) == []


def test_kind_mismatch_is_incompatible() -> None:
    """Raw chunks cannot feed a vector-only port."""
    reasons = check_port_compatibility(CHUNKS, EMBEDDED)
    assert any("chunks" in reason and "embedded_chunks" in reason for reason in reasons)


def test_fusion_score_cannot_feed_dense_threshold() -> None:
    """A dense-only consumer rejects RRF scores."""
    reasons = check_port_compatibility(FUSED_EVIDENCE, DENSE_EVIDENCE)
    assert any(SCORE_KIND_RRF in reason for reason in reasons)


def test_missing_provenance_is_incompatible() -> None:
    """Evidence without chunk lineage cannot satisfy a lineage consumer."""
    bare = PortType(kind=PortKind.RANKED_EVIDENCE)
    reasons = check_port_compatibility(bare, ANY_EVIDENCE)
    assert any(Provenance.CHUNK_LINEAGE.value in reason for reason in reasons)


def test_unspecified_score_kind_fails_restricted_consumer() -> None:
    """A producer that does not declare its score kind cannot feed a dense-only port."""
    reasons = check_port_compatibility(ANY_EVIDENCE, DENSE_EVIDENCE)
    assert reasons


def test_embedding_identity_requirement() -> None:
    """A consumer that needs embedding identity rejects producers without it."""
    no_identity = PortType(kind=PortKind.EMBEDDED_CHUNKS, provenance=EMBEDDED.provenance)
    reasons = check_port_compatibility(no_identity, EMBEDDED)
    assert any("embedding identity" in reason for reason in reasons)


def test_port_type_schema_is_json_safe() -> None:
    """Port types describe themselves as sorted JSON data."""
    schema = DENSE_EVIDENCE.to_schema()
    assert schema == {
        "kind": "ranked_evidence",
        "provenance": ["chunk_lineage", "collection"],
        "score_kinds": [SCORE_KIND_DENSE],
        "embedding_identity": True,
        "reader_declarations": [],
    }


# ── Descriptor contract ──────────────────────────────────────────────


def test_descriptor_schema_lists_ports_params_and_effects() -> None:
    """The descriptor schema gives clients enough to build node controls."""
    descriptor = next(d for d in fixture_descriptors() if d.operation_id == "select.rerank")
    schema = descriptor.to_schema()
    assert schema["operation_id"] == "select.rerank"
    assert schema["version"] == 1
    assert schema["effect"] == "model_call"
    assert schema["bypass"] == {"input_port": "evidence", "output_port": "evidence"}
    assert schema["parameters"]["properties"]["enabled"]
    assert schema["inputs"][0]["cardinality"] == "one"
    assert schema["capabilities"] == ["reranker"]
    assert schema["lever_params"] == {"enabled": "retrieval.rerank_enabled"}


def test_parameters_must_forbid_extra_keys() -> None:
    """Parameter models must reject unknown keys."""

    class Loose(BaseModel):
        value: int = 1

    with pytest.raises(ValidationError, match="extra"):
        _descriptor(parameters=Loose)


def test_bypass_ports_must_exist() -> None:
    """A bypass must name declared ports."""
    with pytest.raises(ValidationError, match="bypass"):
        _descriptor(bypass=BypassSpec(input_port="evidence", output_port="missing"))


def test_bypass_cannot_change_port_kind() -> None:
    """An embedding step cannot declare a pass-through of raw chunks."""
    with pytest.raises(ValidationError, match="bypass"):
        _descriptor(
            inputs=(PortSpec(name="chunks", type=CHUNKS),),
            outputs=(PortSpec(name="chunks", type=EMBEDDED),),
            bypass=BypassSpec(input_port="chunks", output_port="chunks"),
        )


def test_lever_params_must_name_parameters_and_allowed_levers() -> None:
    """Lever parameters must exist and map to allowed graph levers."""
    with pytest.raises(ValidationError, match="lever"):
        _descriptor(lever_params={"missing": "retrieval.top_k"})
    with pytest.raises(ValidationError, match="lever"):
        _descriptor(parameters=RerankParams, lever_params={"enabled": "embed_model"})


def test_collection_param_must_exist() -> None:
    """The collection parameter must be part of the parameter model."""
    with pytest.raises(ValidationError, match="collection"):
        _descriptor(collection_param="collection")


def test_source_commit_must_name_collection() -> None:
    """A source-commit operation must say which collection it writes."""
    with pytest.raises(ValidationError, match="source_commit"):
        _descriptor(effect=EffectClass.SOURCE_COMMIT)


def test_duplicate_port_names_rejected() -> None:
    """Port names are unique per direction."""
    with pytest.raises(ValidationError, match="duplicate"):
        _descriptor(
            inputs=(
                PortSpec(name="evidence", type=ANY_EVIDENCE),
                PortSpec(name="evidence", type=ANY_EVIDENCE, cardinality=Cardinality.OPTIONAL),
            )
        )


def test_operation_id_rejects_expressions() -> None:
    """Operation identifiers are dotted names only."""
    with pytest.raises(ValidationError):
        _descriptor(operation_id="os.system('rm')")


# ── Registration ─────────────────────────────────────────────────────


def test_register_and_lookup_latest_version() -> None:
    """Lookup without a version returns the highest registered version."""
    catalogue = OperationCatalogue()
    catalogue.register(_descriptor(), noop_adapter)
    catalogue.register(_descriptor(version=2), noop_adapter)
    assert catalogue.get("select.example").descriptor.version == 2
    assert catalogue.get("select.example", 1).descriptor.version == 1
    assert catalogue.get("select.example", 3) is None
    assert catalogue.get("missing") is None


def test_duplicate_registration_rejected() -> None:
    """The same operation version cannot be registered twice."""
    catalogue = OperationCatalogue()
    catalogue.register(_descriptor(), noop_adapter)
    with pytest.raises(ValueError, match="already registered"):
        catalogue.register(_descriptor(), noop_adapter)


def test_registration_requires_async_adapter() -> None:
    """Adapters are coroutine functions or objects with an async ``__call__``."""

    def sync_adapter(context: object, inputs: object, params: object) -> None:
        return None

    with pytest.raises(TypeError, match="async"):
        OperationCatalogue().register(_descriptor(), sync_adapter)  # type: ignore[arg-type]


def test_adapter_reference_is_recorded() -> None:
    """The registry records where each adapter lives."""
    entry = fixture_catalogue().get("select.rerank")
    assert entry.adapter_ref == "tests.unit.test_pipeline_support:noop_adapter"


def test_catalogue_reports_unavailable_operations_with_reasons() -> None:
    """Unavailable optional capabilities produce an actionable reason."""
    listing = fixture_catalogue().describe(
        {
            "embedder": None,
            "store": None,
            "reranker": "Reranker model is not installed; run `omrg models pull`.",
        }
    )
    by_id = {entry["operation_id"]: entry for entry in listing}
    assert by_id["retrieve.dense"]["available"] is True
    assert by_id["retrieve.dense"]["unavailable_reasons"] == []
    assert by_id["select.rerank"]["available"] is False
    assert "not installed" in by_id["select.rerank"]["unavailable_reasons"][0]
    sparse = by_id["retrieve.sparse"]
    assert sparse["available"] is False
    assert "sparse_backend" in sparse["unavailable_reasons"][0]
    assert by_id["select.rerank"]["adapter_ref"].endswith(":noop_adapter")


def test_dispatch_modules_have_no_name_branches() -> None:
    """Registry dispatch never branches on operation names (invariant 11)."""
    for path in sorted(PIPELINES_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                for comparator in node.comparators:
                    value = getattr(comparator, "value", None)
                    assert not (isinstance(value, str) and "." in value and value.islower()), (
                        f"{path.name}:{node.lineno} compares against operation-like {value!r}"
                    )


FORBIDDEN_PREFIXES = (
    "omrg.core.ingestion",
    "omrg.core.retrieval",
    "omrg.core.answer",
    "omrg.core.providers",
    "omrg.transports",
    "subprocess",
)


def test_pipelines_package_avoids_domain_and_process_imports() -> None:
    """``core/pipelines`` stays independent of domains, transports and subprocess."""
    for path in sorted(PIPELINES_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    # Resolve relative imports against omrg.core.pipelines.
                    parts = ["omrg", "core", "pipelines"][: 3 - (node.level - 1)]
                    module = ".".join([*parts, module] if module else parts)
                names = [module]
            for name in names:
                assert not name.startswith(FORBIDDEN_PREFIXES), f"{path.name} imports {name}"
