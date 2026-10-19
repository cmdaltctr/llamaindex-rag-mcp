"""Behaviour of the Answer / verify graph adapters (task 3.6).

Covers the published descriptors, the no-evidence short circuit, lazy
answer and judge resources, per-stage failure attribution, citation
resolution, degraded verification and poisoned process defaults. Every
model is a fake; no test reaches a network.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict
from tests.fixtures.pipeline_parity.answer.harness import (
    EXPECTED,
    ScriptedSeam,
    case_by_name,
    case_rows,
    case_settings,
    observation,
)
from tests.test_no_global_settings_reads import _scan_default_accessors
from tests.unit.test_answer_graph_adapters_support import (
    CATALOGUE,
    CITE,
    PREPARE,
    SYNTHESISE,
    VERIFY,
    CountingFactory,
    FakeLLM,
    build_catalogue,
    case_resources,
    run_answer_chain,
    run_answer_chain_outputs,
    run_node,
)

from omrg.core.answer.graph_adapters import ANSWER_LLM_RESOURCE, VERIFY_LLM_RESOURCE
from omrg.core.pipelines import (
    EffectClass,
    OperationCatalogue,
    OperationDescriptor,
    PortKind,
    PortSpec,
    PortType,
    Provenance,
    check_port_compatibility,
    parse_definition,
    preflight,
)

_SRC = Path(__file__).resolve().parents[2] / "src" / "omrg"


def _rows(name: str) -> list[dict]:
    return case_rows(case_by_name(name))


def _resources(complete: ScriptedSeam | None, judge: ScriptedSeam | None = None) -> dict:
    return {
        ANSWER_LLM_RESOURCE: CountingFactory(FakeLLM(complete) if complete else None),
        VERIFY_LLM_RESOURCE: CountingFactory(FakeLLM(judge) if judge else None),
    }


def _verifying(effective_settings: Any, **answer: Any) -> Any:
    block = {"verify_claims": True, **answer}
    return case_settings(effective_settings(), {"answer_block": block})


# ── Descriptors ──────────────────────────────────────────────────────


def test_register_publishes_the_answer_family_with_effect_classes() -> None:
    """Preparation and citations are pure; synthesis and verification call models."""
    effects = {d.operation_id: d.effect for d in CATALOGUE.descriptors()}
    assert effects == {
        PREPARE: EffectClass.PURE,
        SYNTHESISE: EffectClass.MODEL_CALL,
        CITE: EffectClass.PURE,
        VERIFY: EffectClass.MODEL_CALL,
    }


def test_registering_twice_is_rejected() -> None:
    """One ``register_answer_operations`` call per catalogue."""
    from omrg.core.answer.graph_adapters import register_answer_operations

    catalogue = OperationCatalogue()
    register_answer_operations(catalogue)
    with pytest.raises(ValueError, match="already registered"):
        register_answer_operations(catalogue)


def test_descriptors_publish_safe_schemas_and_the_verify_lever() -> None:
    """Schemas are JSON-safe; verification maps to the ``answer.verify_claims`` lever."""
    listing = json.loads(json.dumps(CATALOGUE.describe({})))
    assert all(entry["available"] for entry in listing)
    verify = CATALOGUE.get(VERIFY).descriptor
    assert verify.lever_params == {"verify_claims": "answer.verify_claims"}
    assert verify.bypass is not None
    for entry in CATALOGUE.descriptors():
        assert entry.free_text_params == frozenset()
        string_params = [
            name for name, field in entry.parameters.model_fields.items() if field.annotation is str
        ]
        assert string_params == [], "a prompt-like string parameter must be free text"


def test_port_contracts_keep_citations_before_verification() -> None:
    """Verification needs resolved citations; prepared context feeds synthesis."""
    prepare = CATALOGUE.get(PREPARE).descriptor
    synth = CATALOGUE.get(SYNTHESISE).descriptor
    cite = CATALOGUE.get(CITE).descriptor
    verify = CATALOGUE.get(VERIFY).descriptor
    to_synth = check_port_compatibility(
        prepare.output_port("context").type, synth.input_port("context").type
    )
    assert to_synth == []
    assert (
        check_port_compatibility(cite.output_port("answer").type, verify.input_port("answer").type)
        == []
    )
    skipped = check_port_compatibility(
        synth.output_port("answer").type, verify.input_port("answer").type
    )
    assert skipped and "chunk_lineage" in skipped[0]
    assert Provenance.CHUNK_LINEAGE in synth.input_port("context").type.provenance


def _answer_graph(*, skip_citations: bool = False) -> dict[str, Any]:
    nodes = ["retrieve", "prepare", "synth", "cite", "verify"]
    ops = {"retrieve": _FAKE_CONTEXT.operation_id, "prepare": PREPARE, "synth": SYNTHESISE}
    ops.update(cite=CITE, verify=VERIFY)
    links = [("retrieve", "context", "prepare", "context")]
    links.append(("prepare", "context", "synth", "context"))
    if skip_citations:
        nodes.remove("cite")
        links.append(("synth", "answer", "verify", "answer"))
    else:
        links.append(("synth", "answer", "cite", "answer"))
        links.append(("cite", "answer", "verify", "answer"))
    return {
        "schema_version": 1,
        "nodes": [{"id": n, "operation": ops[n]} for n in nodes],
        "edges": [
            {"source": {"node": a, "port": ap}, "target": {"node": b, "port": bp}}
            for a, ap, b, bp in links
        ],
        "inputs": [
            {
                "name": "query",
                "kind": "query",
                "targets": [
                    {"node": "retrieve", "port": "query"},
                    {"node": "synth", "port": "query"},
                ],
            },
        ],
        "outputs": [{"name": "answer", "source": {"node": "verify", "port": "answer"}}],
    }


async def _no_op(context: Any, inputs: Any, params: Any) -> Any:
    raise AssertionError("preflight must not run adapters")


class _NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


#: Stand-in for the context producer that task 3.2 publishes.
_FAKE_CONTEXT = OperationDescriptor(
    operation_id="context.fixture",
    version=1,
    title="Fixture context",
    family="context",
    parameters=_NoParams,
    inputs=(PortSpec("query", PortType(PortKind.QUERY)),),
    outputs=(
        PortSpec(
            "context",
            PortType(
                PortKind.CONTEXT,
                provenance=frozenset({Provenance.COLLECTION, Provenance.CHUNK_LINEAGE}),
            ),
        ),
    ),
    effect=EffectClass.READ_ONLY,
)


def test_canonical_answer_graph_passes_preflight() -> None:
    """The four operations wire into a valid graph; skipping citations is rejected."""
    catalogue = build_catalogue()
    catalogue.register(_FAKE_CONTEXT, _no_op)
    report = preflight(parse_definition(_answer_graph()), catalogue)
    assert report.issues == ()
    assert report.order == ("retrieve", "prepare", "synth", "cite", "verify")
    bad = preflight(parse_definition(_answer_graph(skip_citations=True)), catalogue)
    assert [issue.code for issue in bad.issues] == ["incompatible_ports"]


# ── No evidence and lazy resources ───────────────────────────────────


async def test_empty_evidence_returns_no_evidence_without_resolving_models(
    effective_settings: Any,
) -> None:
    """Design D3: empty input gives ``no_evidence``; no model is resolved or called."""
    seam = ScriptedSeam({"replies": ["unused [1]."]})
    judge = ScriptedSeam({"raise": "judge must not be called"})
    resources = _resources(seam, judge)
    settings = _verifying(effective_settings)
    result = await run_answer_chain(settings, [], resources)
    assert result["status"] == "no_evidence"
    assert seam.prompts == [] and judge.prompts == []
    assert resources[ANSWER_LLM_RESOURCE].calls == []
    assert resources[VERIFY_LLM_RESOURCE].calls == []


async def test_no_evidence_never_looks_up_the_answer_resource(effective_settings: Any) -> None:
    """With no resources at all, empty evidence is still ``no_evidence``."""
    result = await run_answer_chain(effective_settings(), [], {})
    assert result["status"] == "no_evidence"


async def test_missing_answer_resource_is_the_no_provider_outcome(effective_settings: Any) -> None:
    """No ``answer_llm`` resource keeps evidence and names the configuration."""
    result = await run_answer_chain(effective_settings(), _rows("ok_single_citation"), {})
    assert result["status"] == "error"
    assert "ANSWER__PROVIDER" in result["error"]
    assert result["evidence"] and result["failure_stage"] is None


async def test_answer_model_resolves_once_and_judge_stays_lazy(effective_settings: Any) -> None:
    """The answer factory runs once; the judge factory never runs when verification is off."""
    seam = ScriptedSeam({"replies": ["The tower is 100 metres tall [1]."]})
    resources = _resources(seam, ScriptedSeam({"raise": "judge must not be called"}))
    result = await run_answer_chain(effective_settings(), _rows("ok_single_citation"), resources)
    assert result["status"] == "ok"
    assert resources[ANSWER_LLM_RESOURCE].calls == [()]
    assert resources[VERIFY_LLM_RESOURCE].calls == []


async def test_judge_stays_lazy_for_an_uncited_answer(effective_settings: Any) -> None:
    """An ungrounded answer skips verification before any judge is built."""
    resources = _resources(ScriptedSeam({"replies": ["The tower is tall."]}))
    result = await run_answer_chain(
        _verifying(effective_settings), _rows("uncited_answer_is_unverified"), resources
    )
    assert result["status"] == "generation_unverified"
    assert resources[VERIFY_LLM_RESOURCE].calls == []


async def test_synthesis_accepts_unprepared_context(effective_settings: Any) -> None:
    """Synthesis numbers raw context rows itself, so wiring cannot skip numbering."""
    expected = EXPECTED["ok_merged_constituents"]["result"]
    resources, complete, judge = case_resources(case_by_name("ok_merged_constituents"))
    result = await run_answer_chain(
        effective_settings(), _rows("ok_merged_constituents"), resources, with_prepare=False
    )
    assert observation(result, complete, judge)["result"] == expected


# ── Citations and failure attribution ────────────────────────────────


async def test_synthesis_output_is_unresolved_until_citations_run(
    effective_settings: Any,
) -> None:
    """Synthesis alone reports an unverified answer; the citation node grounds it."""
    resources, _, _ = case_resources(case_by_name("ok_single_citation"))
    outputs = await run_answer_chain_outputs(
        effective_settings(), _rows("ok_single_citation"), resources
    )
    draft = outputs[SYNTHESISE].values["answer"]
    cited = outputs[CITE].values["answer"]
    assert draft["status"] == "generation_unverified" and draft["citations"] == []
    assert cited["status"] == "ok"
    assert [c["chunk_id"] for c in cited["citations"]] == ["c-tower"]
    assert outputs[PREPARE].values["context"][0]["ordinal"] == 1


async def test_generation_failure_is_attributed_and_passes_through(
    effective_settings: Any,
) -> None:
    """A model failure is a generation outcome; later nodes keep it unchanged."""
    resources, _, _ = case_resources(case_by_name("generation_failure_attributed"))
    outputs = await run_answer_chain_outputs(
        _verifying(effective_settings), _rows("generation_failure_attributed"), resources
    )
    failed = outputs[SYNTHESISE].values["answer"]
    assert failed["failure_stage"] == "generation" and failed["evidence"]
    assert outputs[SYNTHESISE].summary["failure_stage"] == "generation"
    assert outputs[CITE].values["answer"] == failed
    assert outputs[VERIFY].values["answer"] == failed
    assert resources[VERIFY_LLM_RESOURCE].calls == []


async def test_citation_failure_is_attributed_to_generation(effective_settings: Any) -> None:
    """Absurd citation output fails at the citation node as a generation failure."""
    name = "citation_assembly_failure_attributed_to_generation"
    resources, _, _ = case_resources(case_by_name(name))
    outputs = await run_answer_chain_outputs(effective_settings(), _rows(name), resources)
    assert outputs[SYNTHESISE].values["answer"]["failure_stage"] is None
    cited = outputs[CITE].values["answer"]
    assert cited["failure_stage"] == "generation"
    assert outputs[CITE].summary["failure_stage"] == "generation"


async def test_answer_factory_failure_fails_the_synthesis_node(effective_settings: Any) -> None:
    """A host that cannot build the answer model fails the node, as ``Engine.answer`` raises."""
    resources = {ANSWER_LLM_RESOURCE: CountingFactory(None, error=RuntimeError("no model"))}
    with pytest.raises(RuntimeError, match="no model"):
        await run_answer_chain(effective_settings(), _rows("ok_single_citation"), resources)


# ── Verification ─────────────────────────────────────────────────────


async def test_judge_factory_failure_degrades_with_redacted_reason(
    effective_settings: Any,
) -> None:
    """An unbuildable judge is an explicit skip with its reason; secrets are removed."""
    secret = "sk-or-v1-SECRETSECRET"  # noqa: S105 - fake key for the redaction check
    settings = _verifying(effective_settings).model_copy(update={"openrouter_api_key": secret})
    resources = _resources(ScriptedSeam({"replies": ["The tower is 100 metres tall [1]."]}))
    resources[VERIFY_LLM_RESOURCE] = CountingFactory(None, error=RuntimeError(f"bad key {secret}"))
    outputs = await run_answer_chain_outputs(settings, _rows("ok_single_citation"), resources)
    result = outputs[VERIFY].values["answer"]
    reason = result["verification_skipped"]
    assert reason.startswith("verification provider unavailable: RuntimeError: bad key")
    assert "SECRET" not in reason and "verified" not in result
    assert outputs[VERIFY].fallback == reason
    assert resources[VERIFY_LLM_RESOURCE].calls == [(settings.answer,)]


async def test_judge_factory_returning_none_is_the_no_judge_reason(
    effective_settings: Any,
) -> None:
    """A host with no judge model reports the standard no-judge reason."""
    resources = _resources(ScriptedSeam({"replies": ["The tower is 100 metres tall [1]."]}))
    result = await run_answer_chain(
        _verifying(effective_settings), _rows("ok_single_citation"), resources
    )
    expected = EXPECTED["verification_no_judge_default_reason"]["result"]
    assert result["verification_skipped"] == expected["verification_skipped"]


async def test_judge_failure_is_an_outcome_not_an_exception(effective_settings: Any) -> None:
    """A judge that raises gives ``verification_skipped`` and a fallback reason."""
    complete = ScriptedSeam({"replies": ["The tower is 100 metres tall [1]."]})
    judge = ScriptedSeam({"raise": "judge network down"})
    outputs = await run_answer_chain_outputs(
        _verifying(effective_settings), _rows("ok_single_citation"), _resources(complete, judge)
    )
    result = outputs[VERIFY].values["answer"]
    assert result["status"] == "ok"
    assert result["verification_skipped"].startswith("verification failed: ConnectionError")
    assert outputs[VERIFY].fallback == result["verification_skipped"]
    assert outputs[VERIFY].summary["verification"] == "skipped"


async def test_verified_answer_is_not_verified_twice(effective_settings: Any) -> None:
    """A second verification node passes a verified answer through."""
    complete = ScriptedSeam({"replies": ["The tower is 100 metres tall [1]."]})
    judge = ScriptedSeam({"replies": ["supported"]})
    settings = _verifying(effective_settings)
    resources = _resources(complete, judge)
    result = await run_answer_chain(settings, _rows("ok_single_citation"), resources)
    assert result["verified"] is True
    again = await run_node(VERIFY, settings, resources, {"answer": result})
    assert again.values["answer"] == result
    assert len(judge.prompts) == 1


# ── Injected settings only ───────────────────────────────────────────


async def test_adapters_never_read_process_defaults(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Poisoned process defaults are never read by the adapter chain."""
    import omrg.core.settings as core_settings
    import omrg.core.vectordb as vectordb

    def _poisoned(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("an answer graph adapter read a process default")

    base = effective_settings()
    monkeypatch.setattr(core_settings, "get_default_effective_settings", _poisoned)
    monkeypatch.setattr(core_settings, "resolve_effective_settings", _poisoned)
    monkeypatch.setattr(vectordb, "get_default_store", _poisoned)
    case = case_by_name("verification_unsupported_claim")
    resources, complete, judge = case_resources(case)
    result = await run_answer_chain(case_settings(base, case), case_rows(case), resources)
    assert observation(result, complete, judge) == EXPECTED["verification_unsupported_claim"]


def test_adapter_module_has_no_default_accessor_reads() -> None:
    """The adapter module passes the default-accessor scan (prepares task 3.8)."""
    source = (_SRC / "core" / "answer" / "graph_adapters.py").read_text(encoding="utf-8")
    assert _scan_default_accessors(source) == []


def test_adapter_module_import_stays_inside_the_answer_domain() -> None:
    """Importing the adapters loads no ingestion, retrieval, transport or provider code."""
    code = (
        "import json, sys\n"
        "import omrg.core.answer.graph_adapters\n"
        "bad = sorted(m for m in sys.modules if m.startswith(("
        "'omrg.core.ingestion', 'omrg.core.retrieval', 'omrg.core.providers', "
        "'omrg.compose', 'omrg.transports', 'omrg.integrations')))\n"
        "print(json.dumps(bad))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []
