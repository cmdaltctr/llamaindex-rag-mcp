"""Static routing tables derived from an admitted graph document.

The tables say which values feed each input port, in declared order, how
many consumers each value has, and which nodes depend on which.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .models import GraphDocument

# A value source: ``(node_id, port)`` for a node output, ``("", name)`` for
# a graph input. Node identifiers are never empty.
SourceKey = tuple[str, str]


@dataclass(frozen=True)
class Wiring:
    """Static routing tables derived from the admitted graph."""

    feeds: Mapping[tuple[str, str], tuple[SourceKey, ...]]
    consumers: Mapping[SourceKey, int]
    upstream: Mapping[str, frozenset[str]]
    downstream: Mapping[str, frozenset[str]]

    @classmethod
    def build(cls, graph: GraphDocument) -> Wiring:
        """Return the routing tables for ``graph``."""
        feeds: dict[tuple[str, str], list[SourceKey]] = {}
        consumers: dict[SourceKey, int] = {}
        upstream: dict[str, set[str]] = {n.id: set() for n in graph.nodes}
        downstream: dict[str, set[str]] = {n.id: set() for n in graph.nodes}
        for edge in graph.edges:
            key = (edge.source.node, edge.source.port)
            feeds.setdefault((edge.target.node, edge.target.port), []).append(key)
            consumers[key] = consumers.get(key, 0) + 1
            upstream[edge.target.node].add(edge.source.node)
            downstream[edge.source.node].add(edge.target.node)
        for graph_input in graph.inputs:
            key = ("", graph_input.name)
            for target in graph_input.targets:
                feeds.setdefault((target.node, target.port), []).append(key)
                consumers[key] = consumers.get(key, 0) + 1
        for graph_output in graph.outputs:
            key = (graph_output.source.node, graph_output.source.port)
            consumers[key] = consumers.get(key, 0) + 1
        return cls(
            feeds={k: tuple(v) for k, v in feeds.items()},
            consumers=consumers,
            upstream={k: frozenset(v) for k, v in upstream.items()},
            downstream={k: frozenset(v) for k, v in downstream.items()},
        )

    def descendants(self, node_id: str) -> frozenset[str]:
        """Return every node reachable from ``node_id``."""
        found: set[str] = set()
        stack = list(self.downstream.get(node_id, ()))
        while stack:
            node = stack.pop()
            if node not in found:
                found.add(node)
                stack.extend(self.downstream.get(node, ()))
        return frozenset(found)
