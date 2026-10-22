"""Graph preflight: reject invalid work before any side effect.

Preflight checks the whole graph and returns every problem it finds. It
never calls an adapter, a model or the store's write path. Resource checks
(capabilities, embedding identity) run only when the caller supplies a
:class:`HostContext`; without one, preflight gives structural feedback for
drafts. Server admission always supplies a host.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from .catalogue import (
    EffectClass,
    HostOptionSet,
    OperationCatalogue,
    RegisteredOperation,
    capability_reasons,
)
from .errors import IssueCode, PipelineIssue, PipelineValidationError
from .executable import executable_reason, iter_strings
from .levers import lever_error
from .models import SUPPORTED_SCHEMA_VERSIONS, GraphDocument, PipelineDefinition
from .ports import EmbeddingRef
from .topology import TopologyResult, analyse_topology

OPERATIONAL_GRAPH_PROFILES = frozenset({"documents", "codebase"})


class CollectionView(Protocol):
    """Read-only view of collection identities supplied by the host."""

    def embedding_identity(self, collection: str) -> EmbeddingRef | None:
        """Return the stored identity, or ``None`` for a new or legacy collection."""
        ...


@dataclass(frozen=True)
class HostContext:
    """Host facts preflight checks resources against.

    Attributes:
        capabilities: Capability name to ``None`` (available) or reason.
        embedding: Embedding identity the host's embedder produces.
        collections: View of stored collection identities.
        default_collection: Collection for bound nodes that name none.
        options: Option-set name to the choices the host cannot run and the
            value a node inherits. Preflight refuses a node that selects an
            unavailable choice.
    """

    capabilities: Mapping[str, str | None] = field(default_factory=dict)
    embedding: EmbeddingRef | None = None
    collections: CollectionView | None = None
    default_collection: str = "documents"
    options: Mapping[str, HostOptionSet] = field(default_factory=dict)


@dataclass(frozen=True)
class PreflightReport:
    """Outcome of preflight.

    Attributes:
        issues: Every problem found. Empty when the graph is valid.
        order: Deterministic topological node order (empty on a cycle).
        resolved_versions: Node to resolved operation version.
        params: Node to validated parameter model.
        collections: Node to bound collection, for collection-bound nodes.
        nodes: On a draft check, the effective controls of each usable node as
            ``{"node_id", "controls"}`` entries. Empty otherwise.
    """

    issues: tuple[PipelineIssue, ...]
    order: tuple[str, ...] = ()
    resolved_versions: Mapping[str, int] = field(default_factory=dict)
    params: Mapping[str, BaseModel] = field(default_factory=dict)
    collections: Mapping[str, str] = field(default_factory=dict)
    nodes: tuple[Mapping[str, Any], ...] = ()

    @property
    def ok(self) -> bool:
        """Return whether no issue was found."""
        return not self.issues

    def raise_for_issues(self) -> None:
        """Raise :class:`PipelineValidationError` when issues exist."""
        if self.issues:
            raise PipelineValidationError(self.issues)


class _Checker:
    """Collects issues for one preflight call."""

    def __init__(
        self, graph: GraphDocument, catalogue: OperationCatalogue, host: HostContext | None
    ) -> None:
        self.graph = graph
        self.catalogue = catalogue
        self.host = host
        self.issues: list[PipelineIssue] = []
        self.ops: dict[str, RegisteredOperation] = {}
        self.params: dict[str, BaseModel] = {}
        self.collections: dict[str, str] = {}

    def add(self, code: str, message: str, **where: str | None) -> None:
        self.issues.append(PipelineIssue(code=code, message=message, **where))

    # ── Document-level checks ─────────────────────────────────────

    def check_document(self) -> None:
        if self.graph.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            self.add(IssueCode.UNSUPPORTED_SCHEMA_VERSION, "Unsupported graph schema version.")
        profile = self.graph.profile
        if profile is not None and profile not in OPERATIONAL_GRAPH_PROFILES:
            hint = (
                " 'hybrid' is a server selector, not an operational profile."
                if profile == "hybrid"
                else ""
            )
            self.add(
                IssueCode.UNSUPPORTED_PROFILE,
                f"Graph profile {profile!r} is not supported.{hint} Use 'documents' or "
                "'codebase', or omit the profile to inherit each collection's profile.",
            )
        for lever, value in self.graph.overrides.items():
            problem = lever_error(lever, value)
            if problem is not None:
                kind, message = problem
                code = (
                    IssueCode.HOST_OWNED_SETTING
                    if kind == "host_owned"
                    else IssueCode.INVALID_OVERRIDE
                )
                self.add(code, message, lever=lever)
            self._check_text(value, None, f"overrides.{lever}", lever=lever)

    def _check_text(self, value: Any, node_id: str | None, where: str, **extra: str) -> None:
        for path, text in iter_strings(value, where):
            reason = executable_reason(text)
            if reason:
                self.add(
                    IssueCode.EXECUTABLE_TEXT,
                    f"'{path}' looks like executable code ({reason}). Graphs carry data for "
                    "registered operations only.",
                    node_id=node_id,
                    **extra,
                )

    # ── Node checks ───────────────────────────────────────────────

    def check_nodes(self) -> None:
        seen: set[str] = set()
        default_collection = self.host.default_collection if self.host else "documents"
        for node in self.graph.nodes:
            if node.id in seen:
                self.add(
                    IssueCode.DUPLICATE_NODE, f"Node id {node.id!r} is used twice.", node_id=node.id
                )
                continue
            seen.add(node.id)
            entry = self._resolve(node.id, node.operation, node.version)
            if entry is None:
                continue
            self.ops[node.id] = entry
            descriptor = entry.descriptor
            try:
                params = descriptor.parameters.model_validate(node.params)
            except ValidationError as exc:
                for error in exc.errors():
                    loc = ".".join(str(p) for p in error.get("loc", ())) or "params"
                    self.add(
                        IssueCode.INVALID_PARAMETER,
                        f"Parameter '{loc}': {error.get('msg')}.",
                        node_id=node.id,
                    )
                params = None
            for key, value in node.params.items():
                if key not in descriptor.free_text_params:
                    self._check_text(value, node.id, f"params.{key}")
            if params is not None:
                self.params[node.id] = params
            if descriptor.collection_param is not None:
                chosen = getattr(params, descriptor.collection_param, None) if params else None
                self.collections[node.id] = chosen or self.graph.collection or default_collection
            if not node.enabled and descriptor.bypass is None:
                self.add(
                    IssueCode.INVALID_BYPASS,
                    f"Operation '{descriptor.operation_id}' declares no bypass, so it cannot be "
                    "disabled. Enable the node or remove it.",
                    node_id=node.id,
                )

    def _resolve(
        self, node_id: str, operation: str, version: int | None
    ) -> RegisteredOperation | None:
        reason = executable_reason(operation)
        if reason:
            self.add(
                IssueCode.EXECUTABLE_TEXT,
                f"Operation {operation!r} looks like executable code ({reason}). Use a registered "
                "operation identifier.",
                node_id=node_id,
            )
            return None
        if self.catalogue.get(operation) is None:
            known = ", ".join(d.operation_id for d in self.catalogue.descriptors())
            self.add(
                IssueCode.UNKNOWN_OPERATION,
                f"Operation {operation!r} is not registered. Known operations: {known}.",
                node_id=node_id,
            )
            return None
        entry = self.catalogue.get(operation, version)
        if entry is None:
            self.add(
                IssueCode.UNKNOWN_OPERATION_VERSION,
                f"Operation {operation!r} has no version {version}.",
                node_id=node_id,
            )
        return entry

    # ── Resource checks ───────────────────────────────────────────

    def check_resources(self) -> None:
        if self.host is None:
            return
        for node in self.graph.nodes:
            entry = self.ops.get(node.id)
            if entry is None or not node.enabled:
                continue
            for reason in capability_reasons(entry.descriptor, self.host.capabilities):
                self.add(IssueCode.CAPABILITY_UNAVAILABLE, reason, node_id=node.id)
            self._check_options(node.id, entry)
            self._check_identity(node.id, entry)

    def _check_options(self, node_id: str, entry: RegisteredOperation) -> None:
        host, params = self.host, self.params.get(node_id)
        if host is None or params is None:
            return
        for param, set_name in entry.descriptor.option_params.items():
            option_set = host.options.get(set_name)
            value = getattr(params, param, None)
            if option_set is None or value is None or value not in option_set.unavailable:
                continue
            self.add(
                IssueCode.OPTION_UNAVAILABLE,
                f"Setting '{param}' selects '{value}', which this host cannot use: "
                f"{option_set.unavailable[value]} Install the package and restart OMRS, "
                "or choose another value or Inherit.",
                node_id=node_id,
            )

    def _check_identity(self, node_id: str, entry: RegisteredOperation) -> None:
        host, collection = self.host, self.collections.get(node_id)
        if host is None or host.embedding is None or host.collections is None or collection is None:
            return
        ports = (*entry.descriptor.inputs, *entry.descriptor.outputs)
        if not any(p.type.embedding_identity for p in ports):
            return
        stored = host.collections.embedding_identity(collection)
        if stored is None or stored.same_space(host.embedding):
            return
        self.add(
            IssueCode.EMBEDDING_IDENTITY_MISMATCH,
            f"Collection {collection!r} was indexed with {stored.label()}, but this host embeds "
            f"with {host.embedding.label()}. Equal vector dimensions do not make two models "
            "compatible. Choose a collection built with the host model, or start OMRS with the "
            "collection's embedding settings.",
            node_id=node_id,
        )

    def check_commits(self) -> None:
        commits = [
            (node.id, self.collections.get(node.id))
            for node in self.graph.nodes
            if node.enabled
            and node.id in self.ops
            and self.ops[node.id].descriptor.effect is EffectClass.SOURCE_COMMIT
        ]
        if len(commits) < 2:
            return
        by_collection: dict[str | None, list[str]] = {}
        for node_id, collection in commits:
            by_collection.setdefault(collection, []).append(node_id)
        for collection, node_ids in by_collection.items():
            if len(node_ids) > 1:
                self.add(
                    IssueCode.CONFLICTING_COMMIT,
                    f"Nodes {', '.join(node_ids)} all commit sources into collection "
                    f"{collection!r}. Keep one commit node per collection.",
                    node_id=node_ids[1],
                )
        if len(by_collection) > 1:
            self.add(
                IssueCode.MULTIPLE_COMMIT_DESTINATIONS,
                "An ingestion graph can commit to one collection only. Remove the extra commit "
                f"nodes ({', '.join(n for n, _ in commits[1:])}) or run them as separate graphs.",
                node_id=commits[1][0],
            )

    # ── Runtime inputs ────────────────────────────────────────────

    def check_inputs(self, inputs: Mapping[str, Any]) -> None:
        declared = {gi.name: gi for gi in self.graph.inputs}
        for name, graph_input in declared.items():
            if graph_input.required and name not in inputs:
                self.add(IssueCode.MISSING_GRAPH_INPUT, f"Supply a value for graph input {name!r}.")
        for name in inputs:
            if name not in declared:
                self.add(
                    IssueCode.UNKNOWN_GRAPH_INPUT,
                    f"Input {name!r} is not declared. "
                    f"Declared inputs: {', '.join(declared) or 'none'}.",
                )


def preflight(
    definition: PipelineDefinition | GraphDocument,
    catalogue: OperationCatalogue,
    *,
    host: HostContext | None = None,
    inputs: Mapping[str, Any] | None = None,
) -> PreflightReport:
    """Validate a graph and return every issue found.

    Args:
        definition: Definition or bare graph document.
        catalogue: Registered operations.
        host: Host resources. ``None`` skips capability and identity checks.
        inputs: Run inputs. ``None`` skips the run-input check.

    Returns:
        The report. Check :attr:`PreflightReport.ok`.
    """
    graph = definition.graph if isinstance(definition, PipelineDefinition) else definition
    checker = _Checker(graph, catalogue, host)
    checker.check_document()
    checker.check_nodes()
    topology: TopologyResult = analyse_topology(graph, checker.ops)
    checker.issues.extend(topology.issues)
    checker.check_resources()
    checker.check_commits()
    if inputs is not None:
        checker.check_inputs(inputs)
    return PreflightReport(
        issues=tuple(checker.issues),
        order=topology.order,
        resolved_versions={n: e.descriptor.version for n, e in checker.ops.items()},
        params=dict(checker.params),
        collections=dict(checker.collections),
    )


def validate_pipeline(
    definition: PipelineDefinition | GraphDocument,
    catalogue: OperationCatalogue,
    *,
    host: HostContext | None = None,
    inputs: Mapping[str, Any] | None = None,
) -> PreflightReport:
    """Validate a graph and raise when it is invalid.

    Raises:
        PipelineValidationError: With every issue found.
    """
    report = preflight(definition, catalogue, host=host, inputs=inputs)
    report.raise_for_issues()
    return report
