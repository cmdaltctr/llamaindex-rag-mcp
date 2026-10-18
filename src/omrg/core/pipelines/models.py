"""Versioned graph documents and their separate presentation layout.

A :class:`GraphDocument` holds only execution semantics: nodes, named
ports, edges, graph inputs and outputs, an optional operational profile and
allowed overrides. A :class:`GraphLayout` holds the title, node positions,
viewport and selection. Layout changes never change
:meth:`GraphDocument.execution_identity`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator

from .errors import IssueCode, PipelineIssue, PipelineValidationError
from .ports import PortKind

SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({SCHEMA_VERSION})

NodeId = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")]
PortName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
OperationName = Annotated[str, Field(min_length=1, max_length=128)]

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class PortRef(BaseModel):
    """A port on a node."""

    model_config = _FROZEN

    node: NodeId
    port: PortName

    def label(self) -> str:
        """Return ``node.port``."""
        return f"{self.node}.{self.port}"


class EdgeSpec(BaseModel):
    """A typed connection from an output port to an input port."""

    model_config = _FROZEN

    source: PortRef
    target: PortRef

    def label(self) -> str:
        """Return ``src.port->dst.port``."""
        return f"{self.source.label()}->{self.target.label()}"


class NodeSpec(BaseModel):
    """One operation instance.

    Attributes:
        id: Stable node identifier, unique in the graph.
        operation: Registered operation identifier, for example
            ``retrieve.dense``.
        version: Pinned operation version. ``None`` selects the latest
            registered version; admission records the resolved version.
        params: JSON parameters validated by the operation's schema.
        enabled: ``False`` bypasses the node. Valid only when the
            operation declares a compatible bypass.
    """

    model_config = _FROZEN

    id: NodeId
    operation: OperationName
    version: int | None = Field(default=None, ge=1)
    params: dict[str, JsonValue] = Field(default_factory=dict)
    enabled: bool = True


class GraphInput(BaseModel):
    """A named value supplied when a run starts."""

    model_config = _FROZEN

    name: PortName
    kind: PortKind
    targets: tuple[PortRef, ...] = Field(min_length=1)
    required: bool = True


class GraphOutput(BaseModel):
    """A named node output returned in the run result."""

    model_config = _FROZEN

    name: PortName
    source: PortRef


class GraphDocument(BaseModel):
    """The executable part of a pipeline definition.

    Attributes:
        schema_version: Graph document schema version.
        nodes: Operation instances.
        edges: Typed connections.
        inputs: Values supplied at run start.
        outputs: Values returned in the result.
        profile: Operational profile (``documents`` or ``codebase``).
            ``None`` inherits each collection's resolved profile.
        collection: Default collection for collection-bound nodes that do
            not name one.
        overrides: Graph-wide lever overrides, ``block.field`` to value.
    """

    model_config = _FROZEN

    schema_version: int
    nodes: tuple[NodeSpec, ...] = Field(min_length=1)
    edges: tuple[EdgeSpec, ...] = ()
    inputs: tuple[GraphInput, ...] = ()
    outputs: tuple[GraphOutput, ...] = ()
    profile: str | None = None
    collection: str | None = Field(default=None, min_length=1, max_length=128)
    overrides: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def _supported_version(cls, value: int) -> int:
        if value not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(_version_issue(value).message)
        return value

    def canonical_json(self) -> str:
        """Return deterministic JSON with sorted keys."""
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def execution_identity(self) -> str:
        """Return the SHA-256 of the canonical execution document."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def node(self, node_id: str) -> NodeSpec | None:
        """Return the node with ``node_id``, if any."""
        return next((n for n in self.nodes if n.id == node_id), None)


class NodePosition(BaseModel):
    """Canvas position of one node."""

    model_config = _FROZEN

    x: float
    y: float


class Viewport(BaseModel):
    """Canvas viewport."""

    model_config = _FROZEN

    x: float = 0.0
    y: float = 0.0
    zoom: float = Field(default=1.0, gt=0)


class GraphLayout(BaseModel):
    """Presentation state kept apart from execution."""

    model_config = _FROZEN

    title: str = Field(default="", max_length=200)
    positions: dict[str, NodePosition] = Field(default_factory=dict)
    viewport: Viewport = Field(default_factory=Viewport)
    selection: tuple[str, ...] = ()
    # Which way the Studio arrange action lays the graph out. Absent means horizontal.
    direction: Literal["horizontal", "vertical"] = "horizontal"


class PipelineDefinition(BaseModel):
    """A graph document plus its presentation layout."""

    model_config = _FROZEN

    graph: GraphDocument
    layout: GraphLayout = Field(default_factory=GraphLayout)


def _version_issue(found: Any) -> PipelineIssue:
    supported = ", ".join(str(v) for v in sorted(SUPPORTED_SCHEMA_VERSIONS))
    return PipelineIssue(
        code=IssueCode.UNSUPPORTED_SCHEMA_VERSION,
        message=(
            f"Graph schema version {found!r} is not supported; this OMRG reads "
            f"version {supported}. Re-save the graph with this version of OMRG, "
            "or upgrade OMRG to read newer graphs."
        ),
    )


def _document_issues(exc: ValidationError) -> list[PipelineIssue]:
    issues = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        issues.append(
            PipelineIssue(code=IssueCode.INVALID_DOCUMENT, message=f"{loc}: {error.get('msg')}")
        )
    return issues


def parse_definition(data: Mapping[str, Any] | PipelineDefinition) -> PipelineDefinition:
    """Build a :class:`PipelineDefinition` from JSON-like data.

    Accepts either ``{"graph": ..., "layout": ...}`` or a bare graph
    document. The schema version is checked first so an old or new
    document gets a compatibility message, not a field error.

    Args:
        data: Parsed JSON data or an existing definition.

    Returns:
        The validated definition.

    Raises:
        PipelineValidationError: For unsupported versions or malformed data.
    """
    if isinstance(data, PipelineDefinition):
        return data
    if not isinstance(data, Mapping):
        raise PipelineValidationError(
            [PipelineIssue(code=IssueCode.INVALID_DOCUMENT, message="Expected a JSON object.")]
        )
    wrapped = "graph" in data and isinstance(data.get("graph"), Mapping)
    graph = data["graph"] if wrapped else data
    version = graph.get("schema_version")
    if isinstance(version, bool) or version not in SUPPORTED_SCHEMA_VERSIONS:
        raise PipelineValidationError([_version_issue(version)])
    payload = dict(data) if wrapped else {"graph": dict(data)}
    try:
        return PipelineDefinition.model_validate(payload)
    except ValidationError as exc:
        raise PipelineValidationError(_document_issues(exc)) from exc
