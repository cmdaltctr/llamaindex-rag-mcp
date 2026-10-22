"""Setup of the profile service: the upgrade step and the factories (design D10, D11).

* :func:`upgrade_saved_pipelines` turns each saved Studio pipeline that belongs
  to no profile into a user profile.
* :func:`build_profile_service` builds the service of the web server.
* :func:`workspace_profile_catalogue` builds the read-only catalogue for the
  processes that do not own the workspace.
* :func:`engine_collection_tags` reads the profile tag of each collection.

The code lives here so that ``compose_profiles.py`` stays under the file-size
ceiling.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .compose_profiles import SLOTS, TITLE_MAX, ProfileService
from .compose_templates import profile_templates
from .core.profiles.catalogue import BUILTIN_PROFILES, SLOT_CONTRACTS
from .core.workspace import TASK_LAYOUT_KEY

if TYPE_CHECKING:
    from .core.vectordb.identity import EmbeddingIdentity
    from .core.workspace import ProfileRepository, WorkspaceRepository


def upgrade_saved_pipelines(service: ProfileService) -> list[str]:
    """Turn each saved Studio pipeline that belongs to no profile into a profile.

    Workspace job pipelines (layout key ``omrg_task``) are skipped. A
    pipeline fills the slot whose ports its current graph matches (Ingest,
    Search, Answer first match), else the Search slot. The other slots get
    the standard graphs of the base profile. The step is safe to run on
    each start: it handles only pipelines that belong to no profile,
    deleted profiles included.

    Returns:
        The ids of the profiles that this call made.
    """
    with service.lock:
        owned = {
            record[f"{slot}_pipeline_id"]
            for record in service._profiles.list_profiles(include_archived=True)
            for slot in SLOTS
        }
        standard: dict[str, dict[str, dict[str, Any]]] = {}
        created = []
        for pipeline in service._workspace.list_pipelines():
            layout = pipeline["layout"] or {}
            if pipeline["pipeline_id"] in owned or TASK_LAYOUT_KEY in layout:
                continue
            created.append(_upgrade_one(service, pipeline, standard))
        return created


def _upgrade_one(
    service: ProfileService,
    pipeline: Mapping[str, Any],
    standard: dict[str, dict[str, dict[str, Any]]],
) -> str:
    """Make a profile around one saved pipeline; return the profile id."""
    from .core.pipelines import PipelineValidationError, parse_definition

    revision_id = pipeline["current_revision_id"]
    document = service._workspace.get_revision(revision_id)["document"] if revision_id else None
    raw = document if isinstance(document, dict) else {}
    profile = raw.get("profile")
    base = profile if profile in BUILTIN_PROFILES else "documents"
    slot = "search"
    try:
        graph = parse_definition({"graph": raw}).graph if revision_id else None
    except PipelineValidationError:
        graph = None
    if graph is not None:
        slot = _matching_slot(graph) or slot
        if profile != base:
            # Slot graphs must name their base profile (D8). Earlier revisions stay.
            service._workspace.save_revision(
                pipeline["pipeline_id"],
                {**raw, "profile": base},
                schema_version=graph.schema_version,
            )
    if base not in standard:
        standard[base] = profile_templates(service._engine, base)
    slots: dict[str, Mapping[str, Any] | str | None] = {
        other: standard[base][other] for other in SLOTS
    }
    slots[slot] = pipeline["pipeline_id"]
    from .core.pipelines.models import SCHEMA_VERSION

    created = service._profiles.create_profile(
        _upgrade_title(pipeline),
        base_profile=base,
        slots=slots,
        schema_version=SCHEMA_VERSION,
    )
    return str(created["profile_id"])


def _upgrade_title(pipeline: Mapping[str, Any]) -> str:
    """Return the canvas title when it holds text, else the pipeline title, made valid."""
    canvas = (pipeline["layout"] or {}).get("title")
    raw = canvas if isinstance(canvas, str) and canvas.strip() else pipeline["title"]
    cleaned = "".join(ch for ch in str(raw) if unicodedata.category(ch) != "Cc")
    return cleaned.strip()[:TITLE_MAX].strip() or "Untitled"


def _matching_slot(graph: Any) -> str | None:
    """Return the first slot whose input and output ports the graph has."""
    for contract in SLOT_CONTRACTS:
        graph_input = next((i for i in graph.inputs if i.name == contract.input_name), None)
        has_output = any(o.name == contract.output_name for o in graph.outputs)
        if graph_input and graph_input.kind.value == contract.input_kind and has_output:
            return contract.slot
    return None


def engine_collection_tags(engine: Any) -> Callable[[], dict[str, str | None]]:
    """Return a reader of the profile tag of every collection in the Engine's store.

    The reader lists the collections and reads one metadata dict for each. A
    collection with no tag, or an unreadable one, reports ``None``.
    """

    def read() -> dict[str, str | None]:
        store = engine.store
        tags: dict[str, str | None] = {}
        for name in engine.list_collections():
            try:
                meta = store.get_collection_metadata(name)
            except Exception:
                meta = None
            tag = meta.get("profile") if isinstance(meta, dict) else None
            tags[name] = tag if isinstance(tag, str) and tag else None
        return tags

    return read


def build_profile_service(engine: Any, workspace: Path) -> ProfileService:
    """Build the profile service of the web server over its workspace folder.

    Args:
        engine: The web server's Engine.
        workspace: The workspace folder (``omrs web --workspace``).
    """
    from .core.workspace import WorkspaceLayout
    from .integrations.workspace_sqlite import (
        SqliteProfileCatalogue,
        SqliteProfileRepository,
        SqliteWorkspaceRepository,
    )

    records = WorkspaceLayout(workspace).records
    return ProfileService(
        engine,
        cast("WorkspaceRepository", SqliteWorkspaceRepository(records)),
        cast("ProfileRepository", SqliteProfileRepository(records)),
        SqliteProfileCatalogue(records),
        collection_tags=engine_collection_tags(engine),
        host_identity=_engine_host_identity(engine),
    )


def build_chat_repository(workspace: Path) -> Any:
    """Build the chat store of the web server over its workspace folder (ADR-082).

    The workspace database must already be open through ``build_profile_service``,
    which runs the migrations.

    Args:
        workspace: The workspace folder (``omrs web --workspace``).
    """
    from .core.workspace import WorkspaceLayout
    from .integrations.workspace_sqlite.chats import SqliteChatRepository

    return SqliteChatRepository(WorkspaceLayout(workspace).records)


def _engine_host_identity(engine: Any) -> Callable[[], EmbeddingIdentity] | None:
    """Return the Engine's own server default model, so checks match its writes.

    ``None`` (an Engine with no host identity) keeps the settings fallback.
    """
    embedders = getattr(engine, "_embedders", None)
    host = getattr(embedders, "host_identity", None)
    return (lambda: host) if host is not None else None


def workspace_profile_catalogue(root: Path | None = None) -> Any:
    """Return a read-only catalogue for a process that does not own the workspace.

    The stdio MCP server, the CLI and the watcher use it. The folder is
    ``root``, else the default workspace (``~/.omrs/workspace``). The function
    never creates, migrates or writes the folder or the file.

    Args:
        root: The workspace folder. ``None`` uses the default folder.

    Returns:
        A :class:`~omrs.integrations.workspace_sqlite.SqliteProfileCatalogue`,
        or ``None`` when the database file does not exist.
    """
    from .core.workspace import WorkspaceLayout, default_workspace
    from .integrations.workspace_sqlite import SqliteProfileCatalogue

    records = WorkspaceLayout(Path(root) if root is not None else default_workspace()).records
    return SqliteProfileCatalogue(records) if records.is_file() else None
