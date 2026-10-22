"""Wiring, cardinality, cycle and port-type checks for one graph.

NetworkX finds cycles and gives a deterministic topological order. It is
imported inside :func:`analyse_topology` so importing the public graph
types stays cheap.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Union

from .catalogue import RegisteredOperation
from .errors import IssueCode, PipelineIssue
from .models import EdgeSpec, GraphDocument, GraphInput
from .ports import Cardinality, PortType, check_port_compatibility

Feed = Union[EdgeSpec, GraphInput]  # noqa: UP007 - runtime alias


@dataclass(frozen=True)
class TopologyResult:
    """Issues plus the deterministic execution order (empty on a cycle)."""

    issues: tuple[PipelineIssue, ...]
    order: tuple[str, ...]


class _Topology:
    def __init__(self, graph: GraphDocument, ops: Mapping[str, RegisteredOperation]) -> None:
        self.graph = graph
        self.ops = ops
        self.node_ids = [n.id for n in graph.nodes]
        self.issues: list[PipelineIssue] = []
        self.edges: list[EdgeSpec] = []
        self.feeds: dict[tuple[str, str], list[Feed]] = {}

    def add(self, code: str, message: str, **where: str | None) -> None:
        self.issues.append(PipelineIssue(code=code, message=message, **where))

    def _port_exists(self, node_id: str, port: str, *, output: bool, edge: str | None) -> bool:
        if node_id not in self.node_ids:
            self.add(
                IssueCode.UNKNOWN_NODE,
                f"Node {node_id!r} does not exist.",
                edge=edge,
                node_id=node_id,
            )
            return False
        entry = self.ops.get(node_id)
        if entry is None:
            return False  # Unknown operation is reported once, on the node.
        descriptor = entry.descriptor
        spec = descriptor.output_port(port) if output else descriptor.input_port(port)
        if spec is None:
            direction = "output" if output else "input"
            names = [p.name for p in (descriptor.outputs if output else descriptor.inputs)]
            self.add(
                IssueCode.UNKNOWN_PORT,
                f"'{descriptor.operation_id}' has no {direction} port {port!r}. "
                f"{direction.capitalize()} ports: {', '.join(names) or 'none'}.",
                node_id=node_id,
                port=port,
                edge=edge,
            )
            return False
        return True

    def collect_wiring(self) -> None:
        for edge in self.graph.edges:
            label = edge.label()
            src_ok = self._port_exists(edge.source.node, edge.source.port, output=True, edge=label)
            dst_ok = self._port_exists(edge.target.node, edge.target.port, output=False, edge=label)
            if edge.target.node in self.node_ids and edge.source.node in self.node_ids:
                self.edges.append(edge)
            if src_ok and dst_ok:
                self.feeds.setdefault((edge.target.node, edge.target.port), []).append(edge)
        for graph_input in self.graph.inputs:
            for target in graph_input.targets:
                if self._port_exists(target.node, target.port, output=False, edge=None):
                    self.feeds.setdefault((target.node, target.port), []).append(graph_input)
        for graph_output in self.graph.outputs:
            ref = graph_output.source
            self._port_exists(ref.node, ref.port, output=True, edge=None)

    def check_cardinality(self) -> None:
        for node in self.graph.nodes:
            entry = self.ops.get(node.id)
            if entry is None:
                continue
            bypass = entry.descriptor.bypass
            for port in entry.descriptor.inputs:
                if not node.enabled and bypass is not None and port.name != bypass.input_port:
                    continue
                count = len(self.feeds.get((node.id, port.name), []))
                if count == 0 and port.required:
                    self.add(
                        IssueCode.MISSING_INPUT,
                        f"Connect input port {port.name!r} ({port.type.kind.value}).",
                        node_id=node.id,
                        port=port.name,
                    )
                elif count > 1 and port.cardinality is not Cardinality.MANY:
                    self.add(
                        IssueCode.AMBIGUOUS_INPUT,
                        f"Input port {port.name!r} accepts one connection but has {count}. "
                        "Remove the extra connections or add a combine node.",
                        node_id=node.id,
                        port=port.name,
                    )

    def order(self) -> tuple[str, ...]:
        import networkx as nx

        dag = nx.DiGraph()
        dag.add_nodes_from(self.node_ids)
        dag.add_edges_from((e.source.node, e.target.node) for e in self.edges)
        if nx.is_directed_acyclic_graph(dag):
            position = {node_id: index for index, node_id in enumerate(self.node_ids)}
            return tuple(nx.lexicographical_topological_sort(dag, key=position.__getitem__))
        cycle = nx.find_cycle(dag)
        path = " -> ".join([*(u for u, _ in cycle), cycle[0][0]])
        self.add(
            IssueCode.CYCLE,
            f"The graph contains a cycle: {path}. Remove one connection; feedback loops are "
            "not supported.",
            node_id=cycle[0][0],
        )
        return ()

    def check_types(self, order: tuple[str, ...]) -> None:
        produced: dict[tuple[str, str], PortType] = {}
        for node_id in order:
            entry = self.ops.get(node_id)
            node = self.graph.node(node_id)
            if entry is None or node is None:
                continue
            upstream: dict[str, PortType] = {}
            for port in entry.descriptor.inputs:
                for feed in self.feeds.get((node_id, port.name), []):
                    actual = self._check_feed(feed, node_id, port.name, port.type, produced)
                    if actual is not None:
                        upstream[port.name] = actual
            descriptor = entry.descriptor
            if node.enabled:
                for out in descriptor.outputs:
                    produced[(node_id, out.name)] = out.type
            elif descriptor.bypass is not None:
                bypass = descriptor.bypass
                forwarded = upstream.get(bypass.input_port)
                if forwarded is None:
                    spec = descriptor.input_port(bypass.input_port)
                    forwarded = spec.type if spec else None
                if forwarded is not None:
                    produced[(node_id, bypass.output_port)] = forwarded

    def _check_feed(
        self,
        feed: Feed,
        node_id: str,
        port: str,
        required: PortType,
        produced: Mapping[tuple[str, str], PortType],
    ) -> PortType | None:
        if isinstance(feed, GraphInput):
            actual = PortType(kind=feed.kind)
            reasons = check_port_compatibility(actual, required)
            if reasons:
                self.add(
                    IssueCode.INCOMPATIBLE_PORTS,
                    f"Graph input {feed.name!r} cannot feed {node_id}.{port}: "
                    f"{'; '.join(reasons)}.",
                    node_id=node_id,
                    port=port,
                )
            return actual
        source = self.graph.node(feed.source.node)
        actual = produced.get((feed.source.node, feed.source.port))
        if actual is None:
            if source is not None and not source.enabled and feed.source.node in self.ops:
                self.add(
                    IssueCode.INVALID_BYPASS,
                    f"Disabled node {feed.source.node!r} produces no {feed.source.port!r} output; "
                    "its bypass forwards a different port.",
                    node_id=feed.source.node,
                    edge=feed.label(),
                )
            return None
        reasons = check_port_compatibility(actual, required)
        if reasons:
            bypassed = source is not None and not source.enabled
            code = IssueCode.INVALID_BYPASS if bypassed else IssueCode.INCOMPATIBLE_PORTS
            lead = (
                f"Bypassed node {feed.source.node!r} would forward an incompatible value"
                if bypassed
                else "Incompatible connection"
            )
            self.add(
                code,
                f"{lead} {feed.label()}: {'; '.join(reasons)}.",
                node_id=node_id,
                port=port,
                edge=feed.label(),
            )
        return actual


def analyse_topology(
    graph: GraphDocument, ops: Mapping[str, RegisteredOperation]
) -> TopologyResult:
    """Check wiring, cardinality, cycles and port types.

    Args:
        graph: The graph document.
        ops: Node id to resolved operation (unresolved nodes are absent).

    Returns:
        Issues found and the execution order (empty when cyclic).
    """
    topology = _Topology(graph, ops)
    topology.collect_wiring()
    topology.check_cardinality()
    order = topology.order()
    if order:
        topology.check_types(order)
    return TopologyResult(issues=tuple(topology.issues), order=order)
