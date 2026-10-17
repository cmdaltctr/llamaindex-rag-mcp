"""Readiness of a user profile's pipelines (unify-profiles-and-pipelines, D9).

A profile is ready only when each of its three pipelines matches its purpose.
:func:`contract_reasons` checks the ports and the write steps of one graph.
:func:`issue_reasons` turns draft-check issues into plain lines. Every line
names the pipeline, and the step when one step causes it, and says what to
fix. An issue code never stands alone.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from ..pipelines import EffectClass
from .catalogue import SLOT_CONTRACTS, SlotContract

if TYPE_CHECKING:
    from ..pipelines import GraphDocument, OperationCatalogue, PipelineIssue

#: The one issue the list check ignores: it depends on a target collection.
COLLECTION_ISSUE_CODE = "embedding_identity_mismatch"

_BY_SLOT: dict[str, SlotContract] = {c.slot: c for c in SLOT_CONTRACTS}


def slot_title(slot: str) -> str:
    """Return the user-facing title of a slot pipeline."""
    return _BY_SLOT[slot].title


def no_graph_reason(slot: str) -> str:
    """Explain that a slot pipeline has no saved graph."""
    return f"The {slot_title(slot)} pipeline has no saved graph. Open it in Studio and build one."


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def issue_reasons(
    slot: str, issues: Iterable[PipelineIssue], *, keep_collection_issues: bool = False
) -> list[str]:
    """Return one plain line for each draft-check issue.

    Args:
        slot: The pipeline the issues belong to.
        issues: Issues from the draft check.
        keep_collection_issues: Keep ``embedding_identity_mismatch``. The
            readiness list leaves it out, because no collection is involved.
    """
    title = slot_title(slot)
    lines = []
    for issue in issues:
        if issue.code == COLLECTION_ISSUE_CODE and not keep_collection_issues:
            continue
        where = f" in step '{issue.node_id}'" if issue.node_id else ""
        lines.append(_sentence(f"The {title} pipeline has a problem{where}: {issue.message}"))
    return lines


def _output_kind(graph: GraphDocument, catalogue: OperationCatalogue, name: str) -> str | None:
    """Return the value kind that the graph output ``name`` carries, if known."""
    output = next((o for o in graph.outputs if o.name == name), None)
    node = graph.node(output.source.node) if output else None
    entry = catalogue.get(node.operation, node.version) if node else None
    if output is None or entry is None:
        return None
    port = next((p for p in entry.descriptor.outputs if p.name == output.source.port), None)
    return None if port is None else str(port.type.kind.value)


def _write_steps(graph: GraphDocument, catalogue: OperationCatalogue) -> list[str]:
    """Return the ids of enabled steps that write to a collection."""
    steps = []
    for node in graph.nodes:
        entry = catalogue.get(node.operation, node.version)
        if node.enabled and entry and entry.descriptor.effect is EffectClass.SOURCE_COMMIT:
            steps.append(node.id)
    return steps


def contract_reasons(slot: str, graph: GraphDocument, catalogue: OperationCatalogue) -> list[str]:
    """Return the reasons a graph does not fit the purpose of ``slot``.

    Args:
        slot: ``ingest``, ``search`` or ``answer``.
        graph: The parsed graph document.
        catalogue: The operations that the graph uses.

    Returns:
        Plain lines. The list is empty when the graph fits.
    """
    contract = _BY_SLOT[slot]
    title, reasons = contract.title, []
    graph_input = next((i for i in graph.inputs if i.name == contract.input_name), None)
    if graph_input is None:
        reasons.append(
            f"The {title} pipeline needs an input named `{contract.input_name}` "
            f"of kind `{contract.input_kind}`."
        )
    elif graph_input.kind.value != contract.input_kind:
        reasons.append(
            f"The input `{contract.input_name}` of the {title} pipeline must be of kind "
            f"`{contract.input_kind}`, not `{graph_input.kind.value}`. Change its kind."
        )
    if not any(o.name == contract.output_name for o in graph.outputs):
        reasons.append(f"The {title} pipeline needs an output named `{contract.output_name}`.")
    else:
        kind = _output_kind(graph, catalogue, contract.output_name)
        if kind is not None and kind != contract.output_kind:
            reasons.append(
                f"The output `{contract.output_name}` of the {title} pipeline must carry "
                f"`{contract.output_kind}` values, not `{kind}`. Connect it to a step that "
                f"makes them."
            )
    writers = _write_steps(graph, catalogue)
    if contract.write_steps == "none":
        reasons += [
            f"The {title} pipeline must not write to a collection, but step '{step}' does. "
            f"Remove that step."
            for step in writers
        ]
    elif len(writers) != 1:
        listed = f" ({', '.join(writers)})" if writers else ""
        reasons.append(
            f"The {title} pipeline needs exactly one write step; it has {len(writers)}{listed}."
        )
    return reasons
