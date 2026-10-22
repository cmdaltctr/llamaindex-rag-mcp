"""Admission: validate, resolve profiles once, freeze the run settings.

Profile rules (design D5):

* An omitted graph profile inherits each collection's resolved profile
  through the existing :class:`~omrs.core.profiles.ProfileResolver`.
* An explicit ``documents`` or ``codebase`` profile loads that bundle
  through the same resolver. Collection metadata is never changed.
* ``hybrid`` is a server selector and fails validation.

Control precedence: node override, then graph-wide override, then the
resolved profile and defaults. Environment values keep their existing
priority inside profile resolution.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from ..settings import EffectiveSettings
from .catalogue import OperationCatalogue, OperationDescriptor
from .errors import IssueCode, PipelineIssue, PipelineValidationError
from .levers import ALLOWED_LEVERS, apply_levers, read_lever
from .models import GraphDocument, PipelineDefinition, parse_definition
from .snapshot import (
    AdmissionSnapshot,
    CollectionSnapshot,
    ControlSource,
    EffectiveControl,
    NodeSnapshot,
)
from .validation import HostContext, PreflightReport, validate_pipeline


class ProfileSource(Protocol):
    """Profile resolution supplied by the composition root."""

    def resolve(self, collection: str) -> EffectiveSettings:
        """Return the collection's resolved settings (inherited profile)."""
        ...

    def load_profile(self, profile_name: str) -> EffectiveSettings:
        """Return the named operational profile's settings."""
        ...

    def environment_keys(self) -> frozenset[str]:
        """Return the environment keys profile resolution consulted."""
        ...


class ResolverProfileSource:
    """:class:`ProfileSource` backed by the existing ``ProfileResolver``.

    ``ProfileResolver`` has no public loader for a named profile, so
    :meth:`load_profile` calls its bundle loader directly, the same way the
    profile safety contract does. The environment labels come from the
    resolver's captured snapshot; a resolver without one reads the live
    environment, so the labels do the same.
    """

    def __init__(self, resolver: Any, environment: Mapping[str, str] | None = None) -> None:
        """Wrap ``resolver``.

        Args:
            resolver: A ``ProfileResolver`` instance.
            environment: Environment snapshot used for source labels.
                ``None`` uses the resolver's captured snapshot.
        """
        self._resolver = resolver
        self._environment = environment

    def resolve(self, collection: str) -> EffectiveSettings:
        """Return the collection's resolved settings."""
        return self._resolver.resolve(collection)

    def load_profile(self, profile_name: str) -> EffectiveSettings:
        """Return the named bundle overlaid on the server base."""
        return self._resolver._load_effective(profile_name)

    def environment_keys(self) -> frozenset[str]:
        """Return the environment keys resolution consulted."""
        env = self._environment
        if env is None:
            env = getattr(self._resolver, "_env_overrides", None)
        return frozenset(os.environ if env is None else env)


def _json(value: Any, what: str) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise PipelineValidationError(
            [
                PipelineIssue(
                    code=IssueCode.INVALID_DOCUMENT, message=f"{what} must be JSON values: {exc}"
                )
            ]
        ) from exc


class _Admission:
    def __init__(self, graph: GraphDocument, report: PreflightReport, host: HostContext) -> None:
        self.graph = graph
        self.report = report
        self.default_collection = graph.collection or host.default_collection
        self.collections: dict[str, CollectionSnapshot] = {}
        self.issues: list[PipelineIssue] = []

    def resolve_collections(self, profiles: ProfileSource) -> None:
        names = sorted({*self.report.collections.values(), self.default_collection})
        explicit = self.graph.profile
        explicit_settings: EffectiveSettings | None = None
        for name in names:
            try:
                if explicit is not None:
                    if explicit_settings is None:
                        explicit_settings = profiles.load_profile(explicit)
                    settings, origin = explicit_settings, "graph"
                else:
                    settings, origin = profiles.resolve(name), "collection"
            except ValueError as exc:
                self.issues.append(
                    PipelineIssue(
                        code=IssueCode.PROFILE_RESOLUTION_FAILED,
                        message=f"Collection {name!r}: {exc}",
                    )
                )
                continue
            self.collections[name] = CollectionSnapshot(
                name=name,
                profile_name=settings.profile_name,
                profile_origin=origin,  # type: ignore[arg-type]
                settings=settings,
            )

    def node_snapshot(
        self, node_id: str, descriptor: OperationDescriptor, env_keys: frozenset[str]
    ) -> NodeSnapshot | None:
        node = self.graph.node(node_id)
        params = self.report.params[node_id]
        collection = self.report.collections.get(node_id)
        base = self.collections[collection or self.default_collection]
        try:
            settings, controls = _effective_node(
                self.graph, node_id, descriptor, params, base, env_keys
            )
        except ValidationError as exc:
            self.issues.append(
                PipelineIssue(
                    code=IssueCode.INVALID_PARAMETER,
                    message=f"Node override rejected: {exc.errors()[0].get('msg')}.",
                    node_id=node_id,
                )
            )
            return None
        return NodeSnapshot(
            node_id=node_id,
            operation=descriptor.operation_id,
            version=descriptor.version,
            enabled=node.enabled if node else True,
            effect=descriptor.effect.value,
            collection=collection,
            params_json=json.dumps(
                params.model_dump(mode="json", exclude_unset=True), sort_keys=True
            ),
            controls=controls,
            settings=settings,
        )


def _effective_node(
    graph: GraphDocument,
    node_id: str,
    descriptor: OperationDescriptor,
    params: BaseModel,
    base: CollectionSnapshot,
    env_keys: frozenset[str],
) -> tuple[EffectiveSettings, tuple[EffectiveControl, ...]]:
    """Return one node's effective settings and controls.

    Admission and the draft check both call this function, so the values a
    draft shows are the values admission freezes.

    Args:
        graph: The graph document (graph-wide overrides).
        node_id: Node being resolved.
        descriptor: The node's operation descriptor.
        params: The node's validated parameter model.
        base: Settings resolved for the node's collection.
        env_keys: Environment keys profile resolution consulted.

    Returns:
        The node's settings and its controls, sorted by lever.

    Raises:
        pydantic.ValidationError: If a node or graph value fails its lever.
        KeyError: If a graph override names an unknown lever.
    """
    node_values = {
        lever: getattr(params, param)
        for param, lever in descriptor.lever_params.items()
        if getattr(params, param) is not None
    }
    graph_values = dict(graph.overrides)
    settings = apply_levers(base.settings, {**graph_values, **node_values})
    controls = []
    for lever in sorted({*descriptor.lever_params.values(), *graph_values}):
        if lever in node_values:
            source, detail = ControlSource.NODE, f"node {node_id!r} parameter"
        elif lever in graph_values:
            source, detail = ControlSource.GRAPH, "graph-wide override"
        else:
            in_env = ALLOWED_LEVERS[lever].env_name in env_keys
            source = ControlSource.ENVIRONMENT if in_env else ControlSource.PROFILE
            detail = f"profile {base.profile_name!r} ({base.profile_origin})"
            if in_env:
                detail = f"{ALLOWED_LEVERS[lever].env_name} within {detail}"
        controls.append(
            EffectiveControl(
                lever=lever, value=read_lever(settings, lever), source=source, detail=detail
            )
        )
    return settings, tuple(controls)


def draft_node_controls(
    graph: GraphDocument,
    report: PreflightReport,
    catalogue: OperationCatalogue,
    *,
    host: HostContext,
    profiles: ProfileSource,
) -> list[dict[str, Any]]:
    """Return the effective controls of each usable node of a draft graph.

    The draft check calls this without run inputs. It resolves collections as
    admission does: the node's collection parameter, else ``graph.collection``,
    else the host default collection. A caller with a request collection
    passes a ``host`` whose ``default_collection`` is that collection, and
    builds ``report`` from the same host. It resolves nothing for a graph with
    an unsupported profile, because the preflight issue already says why.

    A node gets controls only when its parameters passed validation, its
    collection's profile resolved and its graph and node values fit their
    levers. Other nodes are left out. The function runs no node, calls no
    model and writes nothing.

    Args:
        graph: The draft graph document.
        report: Preflight report of the same graph, built without run inputs.
        catalogue: Registered operations.
        host: Host resources and default collection.
        profiles: Profile resolution from the composition root.

    Returns:
        One ``{"node_id": str, "controls": list[dict]}`` entry per usable
        node, in document order. Each control holds ``lever``, ``value``,
        ``source`` and ``detail`` as JSON values, and equals the control
        :func:`admit_pipeline` freezes for the same graph.
    """
    if any(issue.code == IssueCode.UNSUPPORTED_PROFILE for issue in report.issues):
        return []
    admission = _Admission(graph, report, host)
    admission.resolve_collections(profiles)
    env_keys = profiles.environment_keys()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in graph.nodes:
        if node.id in seen or node.id not in report.params:
            continue
        seen.add(node.id)
        entry = catalogue.get(node.operation, report.resolved_versions[node.id])
        base = admission.collections.get(
            report.collections.get(node.id) or admission.default_collection
        )
        if entry is None or base is None:
            continue
        try:
            _, controls = _effective_node(
                graph, node.id, entry.descriptor, report.params[node.id], base, env_keys
            )
        except (ValidationError, KeyError):
            continue
        rows.append({"node_id": node.id, "controls": [c.model_dump(mode="json") for c in controls]})
    return rows


def admit_pipeline(
    definition: PipelineDefinition | Mapping[str, Any],
    catalogue: OperationCatalogue,
    *,
    host: HostContext,
    profiles: ProfileSource,
    inputs: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> AdmissionSnapshot:
    """Validate a graph and freeze its run settings.

    Args:
        definition: Definition object or JSON-like data.
        catalogue: Registered operations.
        host: Host resources and default collection.
        profiles: Profile resolution from the composition root.
        inputs: Run inputs; every required graph input must be present.
        now: Admission time (UTC). Defaults to the current time.

    Returns:
        The immutable admission snapshot.

    Raises:
        PipelineValidationError: Before any side effect, when the graph,
            inputs or profile resolution are invalid.
    """
    parsed = parse_definition(definition)
    run_inputs = dict(inputs or {})
    inputs_json = _json(run_inputs, "Run inputs")
    report = validate_pipeline(parsed, catalogue, host=host, inputs=run_inputs)
    graph = parsed.graph
    admission = _Admission(graph, report, host)
    admission.resolve_collections(profiles)
    if admission.issues:
        raise PipelineValidationError(admission.issues)
    env_keys = profiles.environment_keys()
    nodes = []
    for node_id in report.order:
        node = graph.node(node_id)
        entry = catalogue.get(node.operation, report.resolved_versions[node_id]) if node else None
        if entry is None:  # pragma: no cover - preflight guarantees resolution
            continue
        snapshot = admission.node_snapshot(node_id, entry.descriptor, env_keys)
        if snapshot is not None:
            nodes.append(snapshot)
    if admission.issues:
        raise PipelineValidationError(admission.issues)
    return AdmissionSnapshot(
        graph_json=graph.canonical_json(),
        graph_identity=graph.execution_identity(),
        schema_version=graph.schema_version,
        profile_mode="explicit" if graph.profile else "inherited",
        explicit_profile=graph.profile,
        order=report.order,
        collections=tuple(admission.collections[name] for name in sorted(admission.collections)),
        nodes=tuple(nodes),
        inputs_json=inputs_json,
        admitted_at=now or datetime.now(UTC),
    )
