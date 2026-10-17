"""Structured graph validation errors.

Validation collects every problem it finds as a :class:`PipelineIssue` and
raises one :class:`PipelineValidationError` before any node, model call or
store mutation runs. Each issue names the node, port, edge or lever that a
client must change, so browser and notebook clients can show the problem in
place.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict


class IssueCode:
    """Stable machine-readable issue codes.

    Clients match on these strings. Add codes; do not rename them.
    """

    INVALID_DOCUMENT = "invalid_document"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    DUPLICATE_NODE = "duplicate_node"
    UNKNOWN_OPERATION = "unknown_operation"
    UNKNOWN_OPERATION_VERSION = "unknown_operation_version"
    UNKNOWN_NODE = "unknown_node"
    UNKNOWN_PORT = "unknown_port"
    INVALID_PARAMETER = "invalid_parameter"
    EXECUTABLE_TEXT = "executable_text"
    MISSING_INPUT = "missing_input"
    AMBIGUOUS_INPUT = "ambiguous_input"
    INCOMPATIBLE_PORTS = "incompatible_ports"
    CYCLE = "cycle"
    INVALID_BYPASS = "invalid_bypass"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    EMBEDDING_IDENTITY_MISMATCH = "embedding_identity_mismatch"
    CONFLICTING_COMMIT = "conflicting_commit"
    MULTIPLE_COMMIT_DESTINATIONS = "multiple_commit_destinations"
    UNSUPPORTED_PROFILE = "unsupported_profile"
    INVALID_OVERRIDE = "invalid_override"
    HOST_OWNED_SETTING = "host_owned_setting"
    UNKNOWN_GRAPH_INPUT = "unknown_graph_input"
    MISSING_GRAPH_INPUT = "missing_graph_input"
    PROFILE_RESOLUTION_FAILED = "profile_resolution_failed"


class PipelineIssue(BaseModel):
    """One actionable validation problem.

    Attributes:
        code: Stable issue code from :class:`IssueCode`.
        message: Plain-English explanation with the change to make.
        node_id: Node that holds the problem, when one applies.
        port: Port name on ``node_id``, when one applies.
        edge: Edge label ``"src.port->dst.port"``, when one applies.
        lever: Setting lever path such as ``retrieval.top_k``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    node_id: str | None = None
    port: str | None = None
    edge: str | None = None
    lever: str | None = None


class PipelineValidationError(ValueError):
    """A graph failed validation before any side effect.

    Attributes:
        issues: Every problem found, in discovery order.
        nodes: On a draft check, the effective controls of each node whose
            parameters passed validation, as ``{"node_id", "controls"}``
            entries. ``None`` when the check was not a draft check.
    """

    def __init__(
        self, issues: Iterable[PipelineIssue], *, nodes: Iterable[Mapping[str, Any]] | None = None
    ) -> None:
        """Create the error from one or more issues.

        Args:
            issues: The validation problems. Must not be empty.
            nodes: Draft controls for the nodes that are valid so far.

        Raises:
            ValueError: If ``issues`` is empty.
        """
        self.issues: tuple[PipelineIssue, ...] = tuple(issues)
        self.nodes: tuple[Mapping[str, Any], ...] | None = None if nodes is None else tuple(nodes)
        if not self.issues:
            raise ValueError("PipelineValidationError needs at least one issue")
        super().__init__(self._summary())

    def _summary(self) -> str:
        first = self.issues[0]
        where = first.node_id or first.edge or first.lever
        prefix = f"[{first.code}] {where}: " if where else f"[{first.code}] "
        more = len(self.issues) - 1
        suffix = f" (+{more} more issue{'s' if more > 1 else ''})" if more else ""
        return f"Pipeline validation failed: {prefix}{first.message}{suffix}"

    @property
    def codes(self) -> tuple[str, ...]:
        """Return the issue codes in discovery order."""
        return tuple(issue.code for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe description for transports."""
        return {
            "status": "invalid",
            "message": str(self),
            "issues": [issue.model_dump(exclude_none=True) for issue in self.issues],
        }
