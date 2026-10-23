"""Immutable admission snapshot recorded before a run starts.

The snapshot holds the admitted graph, the run inputs and the effective
settings of every node, with the source of each graph-supported control.
Later edits to the draft graph, the inputs or a collection profile cannot
reach an admitted run. Mutable values are stored as canonical JSON text and
returned as fresh copies.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from ..settings import EffectiveSettings
from .models import GraphDocument

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ControlSource(StrEnum):
    """Where an effective control value came from.

    Precedence, highest first: ``node``, ``graph``, then the resolved
    profile. Within profile resolution, ``environment`` values keep their
    existing priority over profile bundle values.
    """

    NODE = "node"
    GRAPH = "graph"
    ENVIRONMENT = "environment"
    PROFILE = "profile"


class EffectiveControl(BaseModel):
    """One effective control value and its source."""

    model_config = _FROZEN

    lever: str
    value: JsonValue
    source: ControlSource
    detail: str


class CollectionSnapshot(BaseModel):
    """Settings resolved once for one referenced collection.

    Attributes:
        name: Collection name.
        profile_name: Operational profile applied.
        profile_origin: ``collection`` when inherited from the collection,
            ``graph`` when the graph named the profile explicitly.
        settings: Resolved settings before graph and node overrides.
    """

    model_config = _FROZEN

    name: str
    profile_name: str
    profile_origin: Literal["collection", "graph"]
    settings: EffectiveSettings


class NodeSnapshot(BaseModel):
    """Admitted state of one node."""

    model_config = _FROZEN

    node_id: str
    operation: str
    version: int
    enabled: bool
    effect: str
    collection: str | None
    params_json: str
    controls: tuple[EffectiveControl, ...]
    settings: EffectiveSettings

    @property
    def params(self) -> dict[str, Any]:
        """Return a fresh copy of the validated parameters that were set."""
        return json.loads(self.params_json)

    def control(self, lever: str) -> EffectiveControl | None:
        """Return the effective control for ``lever``, if recorded."""
        return next((c for c in self.controls if c.lever == lever), None)


class AdmissionSnapshot(BaseModel):
    """Everything an admitted run needs, frozen at admission.

    Attributes:
        graph_json: Canonical JSON of the admitted graph document.
        graph_identity: Execution identity of that document.
        schema_version: Graph schema version.
        profile_mode: ``inherited`` or ``explicit``.
        explicit_profile: Graph profile, when explicit.
        order: Deterministic topological node order.
        collections: One entry per referenced collection.
        nodes: One entry per node, in ``order``.
        inputs_json: Canonical JSON of the run inputs.
        admitted_at: UTC admission time.
    """

    model_config = _FROZEN

    graph_json: str
    graph_identity: str
    schema_version: int
    profile_mode: Literal["inherited", "explicit"]
    explicit_profile: str | None
    order: tuple[str, ...]
    collections: tuple[CollectionSnapshot, ...]
    nodes: tuple[NodeSnapshot, ...]
    inputs_json: str
    admitted_at: datetime

    @property
    def graph(self) -> GraphDocument:
        """Return a fresh copy of the admitted graph document."""
        return GraphDocument.model_validate_json(self.graph_json)

    @property
    def inputs(self) -> dict[str, Any]:
        """Return a fresh copy of the run inputs."""
        return json.loads(self.inputs_json)

    def node(self, node_id: str) -> NodeSnapshot:
        """Return the snapshot of ``node_id``.

        Raises:
            KeyError: If the node is not part of the run.
        """
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(node_id)

    def collection(self, name: str) -> CollectionSnapshot:
        """Return the snapshot of collection ``name``.

        Raises:
            KeyError: If the collection is not referenced.
        """
        for collection in self.collections:
            if collection.name == name:
                return collection
        raise KeyError(name)
