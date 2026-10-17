"""Graph composition for one Engine: catalogue, host facts, profiles, leases.

The Engine delegates graph validation and execution to
:class:`EnginePipelines`. This module is part of the composition root:

* It builds the :class:`~omrg.core.pipelines.OperationCatalogue` by calling
  each domain registrar. It builds the catalogue on the first validation or
  run, not when the Engine is built, and keeps one catalogue per Engine.
* It describes the Engine to preflight as a ``HostContext``: capabilities
  from the composed resources, the embedding identity of the Engine's
  embedder, and a read-only view of stored collection identities.
* It resolves profiles through the Engine's own resolver. An Engine without
  a resolver uses its own settings and cannot load a named profile.
* It enforces the ``answer()`` request limits on answering graphs.
* It plans each admitted run (``compose_pipeline_runs``): the unit split,
  the ingestion shape and the OCR client of an ingestion graph. The OCR
  client belongs to the Engine. A run borrows it and never builds or
  closes a client of its own.
* It leases the Engine's resources to runs. Graphs that only read run at
  the same time. Graphs with an enabled write step (``SOURCE_COMMIT``) are
  serialised on one Engine with one ``asyncio.Lock``; other Engines are not
  affected.

Heavy imports (the pipeline package and the domain adapters) happen inside
functions, so building an Engine imports nothing new.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .core.pipelines import (
        AdmissionSnapshot,
        EmbeddingRef,
        HostContext,
        OperationCatalogue,
        PipelineIssue,
        PipelineResult,
        PreflightReport,
        ProfileSource,
    )
    from .core.settings import EffectiveSettings

logger = logging.getLogger(__name__)

_REASONS = {
    "store": "This Engine has no vector store.",
    "embedder": "This Engine has no embedding model.",
    "reranker": (
        "This Engine has no reranker model. Install the ONNX Runtime extra and check the "
        "reranker settings, or disable the rerank node."
    ),
    "ocr": "OCR is not enabled for this Engine. Enable OCR in the settings to use OCR nodes.",
}


def build_operation_catalogue() -> OperationCatalogue:
    """Return a catalogue with every domain's graph operations registered."""
    from .core.answer.graph_adapters import register_answer_operations
    from .core.ingestion.graph_adapters import register_ingestion_operations
    from .core.pipelines import OperationCatalogue
    from .core.retrieval.graph_adapters import register_retrieval_operations

    catalogue = OperationCatalogue()
    register_ingestion_operations(catalogue)
    register_retrieval_operations(catalogue)
    register_answer_operations(catalogue)
    return catalogue


def host_embedding(settings: EffectiveSettings, embedder: Any) -> EmbeddingRef:
    """Return the embedding identity, with the same rule as ``retrieve.dense``."""
    from .core.pipelines import EmbeddingRef

    model = getattr(embedder, "model_name", None) or type(embedder).__name__
    return EmbeddingRef(provider=settings.embed_provider, model=str(model))


class StoreCollectionView:
    """Read-only view of the identities stamped on the Engine's collections.

    Stored identities use the store's own vocabulary (for example provider
    ``llamacpp``), and the host identity uses the settings vocabulary (for
    example ``local``). The view compares a stamp with the identity the
    store writes with. A match means the host embeds in the same space.
    Without a store identity the store does not enforce identities, so the
    view reports no stamp.
    """

    def __init__(self, store: Any, host: EmbeddingRef) -> None:
        """Keep the store and the host identity."""
        self._store = store
        self._host = host

    def embedding_identity(self, collection: str) -> EmbeddingRef | None:
        """Return the stored identity, ``None`` for a new or unstamped collection."""
        from .core.pipelines import EmbeddingRef
        from .core.vectordb.identity import IDENTITY_MODEL_KEY, IDENTITY_PROVIDER_KEY

        own = getattr(self._store, "_identity", None)
        if own is None or not self._store.collection_exists(collection):
            return None
        meta = self._store.get_collection_metadata(collection) or {}
        provider, model = meta.get(IDENTITY_PROVIDER_KEY), meta.get(IDENTITY_MODEL_KEY)
        if not isinstance(provider, str) or not isinstance(model, str):
            return None
        if (provider, model) == (own.provider, own.model):
            return self._host
        return EmbeddingRef(provider=provider, model=model)


class FixedProfileSource:
    """Profile source for an Engine built without a profile resolver."""

    def __init__(self, settings: EffectiveSettings) -> None:
        """Keep the Engine settings."""
        self._settings = settings

    def resolve(self, collection: str) -> EffectiveSettings:
        """Return the Engine settings, as ``Engine.search`` does."""
        return self._settings

    def load_profile(self, profile_name: str) -> EffectiveSettings:
        """Refuse: this Engine cannot resolve named profiles.

        Raises:
            ValueError: Always, with the corrective actions.
        """
        raise ValueError(
            f"this Engine has no profile resolver, so it cannot load profile {profile_name!r}. "
            "Remove the graph profile to use the Engine settings, or build the Engine with "
            "Engine.from_environment() or a profile_resolver."
        )

    def environment_keys(self) -> frozenset[str]:
        """Return no keys: explicit settings do not read the environment."""
        return frozenset()


@dataclass(frozen=True)
class GraphHost:
    """What one validation or run needs from the Engine.

    Attributes:
        host: Host facts for preflight.
        profiles: Profile resolution for admission.
        resources: Engine-owned resources by name, borrowed by runs.
        ocr_factory: Returns the Engine-owned OCR client for node settings
            when the Engine was composed without one. The Engine builds the
            client once, on first use, and closes it in ``Engine.close()``.
    """

    host: HostContext
    profiles: ProfileSource
    resources: Mapping[str, Any] = field(default_factory=dict)
    ocr_factory: Callable[[Any], Any] | None = None


def build_graph_host(
    settings: EffectiveSettings,
    *,
    resources: Mapping[str, Any],
    resolver: Any,
    collection: str | None = None,
    ocr_factory: Callable[[Any], Any] | None = None,
) -> GraphHost:
    """Describe the Engine's composition to preflight, admission and the runner.

    Args:
        settings: The Engine's server-default settings.
        resources: Engine resources by name. ``None`` values are omitted
            and their capabilities report a reason.
        resolver: The Engine's profile resolver, or ``None``.
        collection: Default collection; ``None`` uses the settings value.
        ocr_factory: The Engine's lazy OCR client accessor, if any.
    """
    from .core.pipelines import HostContext, ResolverProfileSource

    capabilities = {
        name: None if resources.get(name) is not None else reason
        for name, reason in _REASONS.items()
    }
    embedding = host_embedding(settings, resources.get("embedder"))
    host = HostContext(
        capabilities=capabilities,
        embedding=embedding,
        collections=StoreCollectionView(resources.get("store"), embedding),
        default_collection=collection or settings.collection_name,
    )
    profiles = FixedProfileSource(settings) if resolver is None else ResolverProfileSource(resolver)
    present = {name: value for name, value in resources.items() if value is not None}
    return GraphHost(host, profiles, present, ocr_factory=ocr_factory)


def pipeline_templates(engine: Any, collection: str | None = None) -> tuple[Any, ...]:
    """Return the canonical templates, shaped for one Engine and collection.

    The retrieval chain is hybrid when the collection's resolved settings
    enable ``retrieval.hybrid_enabled``. The rerank node starts bypassed
    when the Engine has no reranker, so each template passes validation.

    Args:
        engine: The Engine that will validate and run the templates.
        collection: Collection the templates name. ``None`` uses the
            Engine's settings collection and leaves the graph field empty.

    Returns:
        :class:`~omrg.pipeline_templates.PipelineTemplate` values, in
        ``ingestion``, ``search``, ``answer`` order.
    """
    from .pipeline_templates import canonical_templates

    settings = engine.resolve_settings(collection)
    capabilities = engine._graph_host(collection).host.capabilities
    return canonical_templates(
        collection,
        hybrid=bool(settings.retrieval.hybrid_enabled),
        rerank=capabilities.get("reranker") is None,
    )


def _out_of_range(value: Any, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and not low <= value <= high


def _answers(graph: Any, catalogue: OperationCatalogue) -> bool:
    """Return whether an enabled node produces an ``answer`` port."""
    from .core.pipelines import PortKind

    for node in graph.nodes:
        entry = catalogue.get(node.operation, node.version)
        if entry is None or not node.enabled:
            continue
        if any(port.type.kind is PortKind.ANSWER for port in entry.descriptor.outputs):
            return True
    return False


def request_limit_issues(
    graph: Any, catalogue: OperationCatalogue, inputs: Mapping[str, Any] | None
) -> list[PipelineIssue]:
    """Return ``answer()`` request-limit issues for a graph that answers.

    The limits apply when an enabled node produces an ``answer`` port. They
    check the query inputs, every ``retrieval.top_k`` value set on a node or
    graph-wide, and every ``expand_window`` parameter. Profile defaults are
    not checked, as ``answer()`` checks only caller values.
    """
    from .core.answer.pipeline import _EXPAND_WINDOW_MAX, _QUERY_MAX_CHARS, _TOP_K_MAX
    from .core.pipelines import IssueCode, PipelineIssue, PortKind

    if not _answers(graph, catalogue):
        return []
    issues: list[PipelineIssue] = []
    for spec in graph.inputs:
        value = (inputs or {}).get(spec.name)
        if spec.kind is PortKind.QUERY and isinstance(value, str) and len(value) > _QUERY_MAX_CHARS:
            message = (
                f"Graph input {spec.name!r} exceeds the {_QUERY_MAX_CHARS}-character limit "
                f"(got {len(value)} characters). Shorten the query."
            )
            issues.append(PipelineIssue(code=IssueCode.INVALID_PARAMETER, message=message))
    top_k_rule = f"top_k must be between 1 and {_TOP_K_MAX} for an answering graph"
    for node in graph.nodes:
        entry = catalogue.get(node.operation, node.version)
        levers = entry.descriptor.lever_params if entry is not None else {}
        for param, value in node.params.items():
            if levers.get(param) == "retrieval.top_k" and _out_of_range(value, 1, _TOP_K_MAX):
                message = f"{top_k_rule} (got {value})."
            elif param == "expand_window" and _out_of_range(value, 0, _EXPAND_WINDOW_MAX):
                message = f"expand_window must be between 0 and {_EXPAND_WINDOW_MAX} (got {value})."
            else:
                continue
            issues.append(
                PipelineIssue(code=IssueCode.INVALID_PARAMETER, message=message, node_id=node.id)
            )
    graph_top_k = graph.overrides.get("retrieval.top_k")
    if _out_of_range(graph_top_k, 1, _TOP_K_MAX):
        issues.append(
            PipelineIssue(
                code=IssueCode.INVALID_OVERRIDE,
                message=f"{top_k_rule} (got {graph_top_k}).",
                lever="retrieval.top_k",
            )
        )
    return issues


def _profile_issues(graph: Any, profiles: ProfileSource) -> list[PipelineIssue]:
    """Check that an explicit graph profile loads (draft validation)."""
    from .core.pipelines import IssueCode, PipelineIssue

    if graph.profile is None:
        return []
    try:
        profiles.load_profile(graph.profile)
    except ValueError as exc:
        return [PipelineIssue(code=IssueCode.PROFILE_RESOLUTION_FAILED, message=str(exc))]
    return []


class EnginePipelines:
    """Graph state that one Engine owns: catalogue, write lock and leases.

    Graphs that only read run at the same time. A graph with an enabled write
    step (``SOURCE_COMMIT``) waits for other writing graphs.

    Attributes:
        active_runs: Runs that hold or wait for this Engine's resources.
    """

    def __init__(self, catalogue_factory: Callable[[], OperationCatalogue] | None = None) -> None:
        """Create empty state. Nothing is imported or built here."""
        self._catalogue_factory = catalogue_factory or build_operation_catalogue
        self._catalogue: OperationCatalogue | None = None
        self._lock = asyncio.Lock()
        self._runs_lock = threading.Lock()
        self._judges: dict[Any, Any] = {}
        self._ocr: Any = None
        self._readers: dict[str, str | None] | None = None
        self.active_runs = 0

    def reader_options(self) -> dict[str, str | None]:
        """Return the PDF reader probe, run once per Engine on first use."""
        from .capabilities import pdf_reader_options

        self._readers = self._readers or pdf_reader_options()
        return self._readers

    def catalogue(self) -> OperationCatalogue:
        """Return this Engine's catalogue, built on first use."""
        if self._catalogue is None:
            self._catalogue = self._catalogue_factory()
        return self._catalogue

    def describe(self, graph_host: GraphHost) -> list[dict[str, Any]]:
        """Return the catalogue listing with availability for this host."""
        return self.catalogue().describe(graph_host.host.capabilities, graph_host.host.options)

    def validate(
        self, definition: Any, graph_host: GraphHost, *, inputs: Mapping[str, Any] | None = None
    ) -> AdmissionSnapshot | PreflightReport:
        """Validate a graph without side effects.

        Returns:
            The admission snapshot when ``inputs`` is given, else the
            preflight report of a draft. The report and the error of a draft
            carry the effective controls of each usable node (``nodes``).

        Raises:
            PipelineValidationError: With every issue found.
        """
        from dataclasses import replace

        from .core.pipelines import (
            PipelineValidationError,
            admit_pipeline,
            parse_definition,
            preflight,
        )
        from .core.pipelines.admission import draft_node_controls

        parsed = parse_definition(definition)
        catalogue = self.catalogue()
        report = preflight(parsed, catalogue, host=graph_host.host, inputs=inputs)
        issues = [*report.issues, *request_limit_issues(parsed.graph, catalogue, inputs)]
        nodes = None
        if inputs is None:
            issues += _profile_issues(parsed.graph, graph_host.profiles)
            nodes = draft_node_controls(
                parsed.graph, report, catalogue, host=graph_host.host, profiles=graph_host.profiles
            )
        if issues:
            raise PipelineValidationError(issues, nodes=nodes)
        if inputs is None:
            return replace(report, nodes=tuple(nodes or ()))
        return admit_pipeline(
            parsed, catalogue, host=graph_host.host, profiles=graph_host.profiles, inputs=inputs
        )

    def ocr_client(self, settings: Any) -> Any:
        """Return the Engine-owned OCR client; build it once, on first use.

        The client is built the same way ``ingest_path_async`` builds one
        (``build_ocr_routes``), from the settings of the first node that
        enables the OCR fallback. Later runs borrow the same client.
        """
        if self._ocr is None:
            from .capabilities import build_ocr_routes

            self._ocr = build_ocr_routes(settings)
        return self._ocr

    def release(self) -> None:
        """Drop cached judges and the catalogue; close the lazy OCR client.

        A close failure is logged, not raised, as for the Engine store.
        """
        self._judges.clear()
        self._catalogue = None
        client, self._ocr = self._ocr, None
        if client is None:
            return
        try:
            client.close()
        except Exception as exc:
            logger.warning("OCR client close() failed during engine close: %s", exc)

    def judge(self, factory: Callable[[Any], Any] | None) -> Callable[[Any], Any] | None:
        """Return a ``verify_llm`` resource that builds each judge once."""
        if factory is None:
            return None

        def build(answer_block: Any) -> Any:
            try:
                hash(answer_block)
            except TypeError:
                return factory(answer_block)
            if answer_block not in self._judges:
                self._judges[answer_block] = factory(answer_block)
            return self._judges[answer_block]

        return build

    async def run(
        self,
        definition: Any,
        graph_host: GraphHost,
        *,
        inputs: Mapping[str, Any] | None = None,
        on_event: Any = None,
        cancellation: Any = None,
        run_id: str | None = None,
    ) -> PipelineResult:
        """Admit (or accept an admitted snapshot), lease, then execute.

        Raises:
            PipelineValidationError: Before any side effect.
            ValueError: If an admitted snapshot comes with separate inputs.
        """
        from .compose_pipeline_runs import SUMMARY_EVENTS, plan_run, with_provenance
        from .core.pipelines import (
            AdmissionSnapshot,
            EffectClass,
            PipelineValidationError,
            run_pipeline,
        )
        from .core.pipelines.cancellation import run_cancellation

        if isinstance(definition, AdmissionSnapshot):
            if inputs is not None:
                raise ValueError("An admitted snapshot carries its inputs; do not pass inputs.")
            snapshot = definition
            issues = request_limit_issues(snapshot.graph, self.catalogue(), snapshot.inputs)
            if issues:
                raise PipelineValidationError(issues)
        else:
            snapshot = cast(
                "AdmissionSnapshot",
                self.validate(definition, graph_host, inputs=dict(inputs or {})),
            )
        token = run_cancellation(cancellation)
        writes = any(n.enabled and n.effect == EffectClass.SOURCE_COMMIT for n in snapshot.nodes)
        # User-profile searches run on worker threads, so the counter needs a lock.
        with self._runs_lock:
            self.active_runs += 1
        try:
            async with contextlib.AsyncExitStack() as stack:
                if writes:
                    await stack.enter_async_context(self._lock)
                plan = plan_run(snapshot, self.catalogue(), graph_host)
                summaries: dict[tuple[str, str | None], dict[str, Any]] = {}

                async def sink(event: Any) -> None:
                    if event.kind in SUMMARY_EVENTS and event.node_id is not None:
                        summaries[(event.node_id, event.unit_id)] = dict(event.data)
                    if on_event is not None:
                        await on_event(event)

                result = await run_pipeline(
                    snapshot,
                    self.catalogue(),
                    {**graph_host.resources, **plan.resources},
                    on_event=sink,
                    cancellation=token,
                    units=plan.units,
                    run_id=run_id,
                )
                return with_provenance(result, snapshot, summaries)
        finally:
            with self._runs_lock:
                self.active_runs -= 1
