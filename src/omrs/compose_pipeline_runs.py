"""Per-run planning and result provenance for graph runs on one Engine.

:func:`plan_run` derives the run-scoped resources of an admitted snapshot:
the ingestion shape, the per-source unit split and the OCR client. Every
resource is borrowed from the Engine; a run builds and closes nothing.
:func:`with_provenance` adds node summaries and admitted node controls to
the result, so a finished run explains each node without its events.

Heavy imports happen inside functions, so building an Engine imports
nothing new.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .compose_pipelines import GraphHost
    from .core.pipelines import AdmissionSnapshot, PipelineResult, UnitSplit


@dataclass
class RunPlan:
    """Run-scoped additions an admitted snapshot needs.

    Attributes:
        resources: Resources derived from this run (ingestion shape, OCR).
            Every value is borrowed: the run closes nothing.
        units: Per-source unit split for an ingestion graph.
    """

    resources: dict[str, Any] = field(default_factory=dict)
    units: UnitSplit | None = None


def plan_run(snapshot: AdmissionSnapshot, catalogue: Any, graph_host: GraphHost) -> RunPlan:
    """Plan an admitted run from its snapshot.

    An ingestion graph (one with registered ingestion operations) gets:

    * its ingestion shape as resource ``ingestion_shape``, computed once;
    * the per-source unit split on its ``source.discover`` node;
    * resource ``ocr``: the Engine's composed client, else the Engine's
      lazily built client when a node's settings enable the OCR fallback.
      The run borrows it; only ``Engine.close()`` closes it.
    """
    from .core.ingestion.graph_adapters import (
        DISCOVER,
        INGESTION_DESCRIPTORS,
        ingestion_unit_split,
    )
    from .core.ingestion.graph_fingerprint import INGESTION_SHAPE_RESOURCE, ingestion_shape

    ingestion_ops = {descriptor.operation_id for descriptor in INGESTION_DESCRIPTORS}
    nodes = [node for node in snapshot.nodes if node.operation in ingestion_ops]
    plan = RunPlan()
    if not nodes:
        return plan
    plan.resources[INGESTION_SHAPE_RESOURCE] = ingestion_shape(snapshot, catalogue)
    discover = [node.node_id for node in nodes if node.operation == DISCOVER.operation_id]
    if len(discover) == 1:
        plan.units = dataclasses.replace(ingestion_unit_split(), node=discover[0])
    wants_ocr = next((n.settings for n in nodes if n.settings.ocr_fallback_enabled), None)
    if "ocr" not in graph_host.resources and wants_ocr is not None and graph_host.ocr_factory:
        plan.resources["ocr"] = graph_host.ocr_factory(wants_ocr)
    return plan


#: Event kinds whose data is the node summary kept in the node outcome.
SUMMARY_EVENTS = frozenset({"node_completed", "node_bypassed"})


def with_provenance(result: PipelineResult, snapshot: AdmissionSnapshot, summaries: Any) -> Any:
    """Return *result* with each node summary and the admitted node controls."""
    nodes = tuple(
        n.model_copy(update={"summary": summaries.get((n.node_id, n.unit_id), {})})
        for n in result.nodes
    )
    controls = {node.node_id: node.controls for node in snapshot.nodes}
    return result.model_copy(update={"nodes": nodes, "controls": controls})
