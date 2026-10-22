"""Graph contracts, operation catalogue, preflight and admission.

This package defines what a user-connected pipeline graph is and checks it
before any side effect. It does not import the ingestion, retrieval,
answering or provider domains, transports, or process launch. The
composition root builds an :class:`OperationCatalogue`, domain packages
register adapters on it, and the Engine injects resources and settings.

Module map:

* ``models`` - versioned graph document, separate layout, parsing.
* ``ports`` - typed port contracts with provenance and score kinds.
* ``levers`` - overridable settings and host-owned settings.
* ``catalogue`` - operation descriptors and the registry.
* ``adapters`` - the async adapter protocol and node context.
* ``validation`` / ``topology`` - validation before admission.
* ``admission`` / ``snapshot`` - profile resolution and frozen run state.
* ``results`` / ``errors`` - public result, event and error types.
* ``runner`` - :func:`run_pipeline`, the async execution entry point.
* ``execution`` / ``scheduler`` / ``wiring`` / ``run_state`` - one pass over a unit; ready-node
  scheduling with a concurrency bound and resource leases.
* ``events`` - ordered event delivery to an injected async sink.
* ``cancellation`` - run-scoped cooperative cancellation.
"""

from __future__ import annotations

from .adapters import CancellationFlag, CancellationToken, NodeContext, NodeOutput, OperationAdapter
from .admission import ProfileSource, ResolverProfileSource, admit_pipeline
from .cancellation import PipelineCancelledError, RunCancellation
from .catalogue import (
    BypassSpec,
    EffectClass,
    HostOptionSet,
    OperationCatalogue,
    OperationDescriptor,
    RegisteredOperation,
)
from .errors import IssueCode, PipelineIssue, PipelineValidationError
from .execution import FatalNodeError
from .levers import ALLOWED_LEVERS, LeverSpec, apply_levers, is_host_owned
from .models import (
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    EdgeSpec,
    GraphDocument,
    GraphInput,
    GraphLayout,
    GraphOutput,
    NodePosition,
    NodeSpec,
    PipelineDefinition,
    PortRef,
    Viewport,
    parse_definition,
)
from .ports import (
    READER_STRUCTURED,
    READER_TEXT_FORMAT,
    SCORE_KIND_DENSE,
    SCORE_KIND_NATIVE_SPARSE,
    SCORE_KIND_RERANK,
    SCORE_KIND_RRF,
    SCORE_KIND_SPARSE_RANK,
    Cardinality,
    EmbeddingRef,
    PayloadProvenance,
    PortKind,
    PortSpec,
    PortType,
    Provenance,
    check_port_compatibility,
)
from .results import (
    EventKind,
    NodeOutcome,
    NodeStatus,
    PipelineEvent,
    PipelineResult,
    RunStatus,
    UnitOutcome,
)
from .runner import RunLimits, UnitSplit, run_pipeline
from .snapshot import (
    AdmissionSnapshot,
    CollectionSnapshot,
    ControlSource,
    EffectiveControl,
    NodeSnapshot,
)
from .validation import CollectionView, HostContext, PreflightReport, preflight, validate_pipeline

__all__ = [
    "ALLOWED_LEVERS",
    "READER_STRUCTURED",
    "READER_TEXT_FORMAT",
    "SCHEMA_VERSION",
    "SCORE_KIND_DENSE",
    "SCORE_KIND_NATIVE_SPARSE",
    "SCORE_KIND_RERANK",
    "SCORE_KIND_RRF",
    "SCORE_KIND_SPARSE_RANK",
    "SUPPORTED_SCHEMA_VERSIONS",
    "AdmissionSnapshot",
    "BypassSpec",
    "CancellationFlag",
    "CancellationToken",
    "Cardinality",
    "CollectionSnapshot",
    "CollectionView",
    "ControlSource",
    "EdgeSpec",
    "EffectClass",
    "EffectiveControl",
    "EmbeddingRef",
    "EventKind",
    "FatalNodeError",
    "GraphDocument",
    "GraphInput",
    "GraphLayout",
    "GraphOutput",
    "HostContext",
    "HostOptionSet",
    "IssueCode",
    "LeverSpec",
    "NodeContext",
    "NodeOutcome",
    "NodeOutput",
    "NodePosition",
    "NodeSnapshot",
    "NodeSpec",
    "NodeStatus",
    "OperationAdapter",
    "OperationCatalogue",
    "OperationDescriptor",
    "PayloadProvenance",
    "PipelineCancelledError",
    "PipelineDefinition",
    "PipelineEvent",
    "PipelineIssue",
    "PipelineResult",
    "PipelineValidationError",
    "PortKind",
    "PortRef",
    "PortSpec",
    "PortType",
    "PreflightReport",
    "ProfileSource",
    "Provenance",
    "RegisteredOperation",
    "ResolverProfileSource",
    "RunCancellation",
    "RunLimits",
    "RunStatus",
    "UnitOutcome",
    "UnitSplit",
    "Viewport",
    "admit_pipeline",
    "apply_levers",
    "check_port_compatibility",
    "is_host_owned",
    "parse_definition",
    "preflight",
    "run_pipeline",
    "validate_pipeline",
]
