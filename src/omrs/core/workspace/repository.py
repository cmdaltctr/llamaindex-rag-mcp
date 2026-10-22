"""Repository contract for workspace application records.

Composition injects an implementation. Workspace services depend on this
protocol only and never on a storage engine.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any, Protocol, runtime_checkable

from omrs.core.workspace.records import (
    PipelineRecord,
    PluginRecord,
    ProfileRecord,
    RevisionRecord,
    RunEventRecord,
    RunRecord,
)


@runtime_checkable
class ProfileRepository(Protocol):
    """Persistence for user profiles and the pipelines they own.

    Lookups of an unknown profile raise ``KeyError``. Invalid values raise
    ``ValueError``. A deleted (archived) profile stays readable by id.
    """

    def create_profile(
        self,
        title: str,
        *,
        base_profile: str,
        slots: Mapping[str, Mapping[str, Any] | str | None],
        schema_version: int,
        description: str = "",
        layouts: Mapping[str, Mapping[str, Any]] | None = None,
        embedding: tuple[str, str, int | None] | None = None,
    ) -> ProfileRecord:
        """Create a profile, its pipelines and their first revisions at once.

        The id comes from the title. A taken or reserved id gets ``-2``, ``-3``
        and so on, and an archived id is never reused.

        ``slots`` maps each of ``ingest``, ``search`` and ``answer`` to one
        of: a graph document (a new pipeline whose first revision is that
        graph), ``None`` (a new pipeline with no revision) or a pipeline id
        string (an existing pipeline that becomes the slot). ``layouts`` gives
        the presentation layout of each new pipeline, by slot. ``embedding`` is
        the (provider, model, vector size) choice of the new profile; ``None``
        means the server default.

        Everything is written in one transaction: when any step fails, no row
        stays.

        Raises:
            ValueError: If a slot is missing or unknown, the base profile is
                not built-in, or an existing pipeline already fills a slot.
            KeyError: If a named existing pipeline does not exist.
        """
        ...

    def get_profile(self, profile_id: str) -> ProfileRecord:
        """Return one profile, deleted or not."""
        ...

    def list_profiles(self, *, include_archived: bool = False) -> list[ProfileRecord]:
        """Return profiles in creation order; deleted ones only on request."""
        ...

    def update_profile(
        self, profile_id: str, *, title: str | None = None, description: str | None = None
    ) -> ProfileRecord:
        """Change the title or the description. The id never changes."""
        ...

    def set_profile_embedding(
        self,
        profile_id: str,
        *,
        provider: str | None,
        model: str | None,
        dimensions: int | None,
    ) -> ProfileRecord:
        """Save the embedding choice of a profile (ADR-081).

        ``provider`` and ``model`` are both set or both ``None``; ``None``
        returns the profile to the server default. The caller decides whether
        the lock rule allows the change.

        Raises:
            KeyError: If the profile does not exist.
            ValueError: If only one of provider and model is set.
        """
        ...

    def archive_profile(self, profile_id: str) -> ProfileRecord:
        """Soft-delete a profile. Archiving twice keeps the first time."""
        ...

    def find_profile_by_pipeline(self, pipeline_id: str) -> tuple[ProfileRecord, str] | None:
        """Return the profile and the slot a pipeline fills, or ``None``."""
        ...


@runtime_checkable
class WorkspaceRepository(Protocol):
    """Persistence for pipelines, revisions, runs, events and plugins.

    Lookups of an unknown identifier raise ``KeyError``. Invalid values or
    state transitions raise ``ValueError``. Revisions have no update or delete
    operation.
    """

    def create_pipeline(
        self, title: str, *, layout: Mapping[str, Any] | None = None
    ) -> PipelineRecord:
        """Create a pipeline with no revision yet."""
        ...

    def get_pipeline(self, pipeline_id: str) -> PipelineRecord:
        """Return one pipeline."""
        ...

    def list_pipelines(self) -> list[PipelineRecord]:
        """Return all pipelines in creation order."""
        ...

    def save_layout(self, pipeline_id: str, layout: Mapping[str, Any]) -> PipelineRecord:
        """Replace the presentation layout without creating a revision."""
        ...

    def save_revision(
        self, pipeline_id: str, document: Mapping[str, Any], *, schema_version: int
    ) -> RevisionRecord:
        """Store an execution document and make it the current revision.

        Identical content returns the existing revision unchanged.
        """
        ...

    def get_revision(self, revision_id: str) -> RevisionRecord:
        """Return one revision."""
        ...

    def list_revisions(self, pipeline_id: str) -> list[RevisionRecord]:
        """Return a pipeline's revisions by revision number."""
        ...

    def create_run(
        self,
        revision_id: str,
        *,
        settings: Mapping[str, Any],
        resources: Mapping[str, Any],
        inputs: Mapping[str, Any],
        origin: str = "submit",
        source_run_id: str | None = None,
    ) -> RunRecord:
        """Admit a queued run of a revision and write its first event."""
        ...

    def get_run(self, run_id: str) -> RunRecord:
        """Return one run."""
        ...

    def list_runs(
        self,
        *,
        pipeline_id: str | None = None,
        statuses: Collection[str] | None = None,
        limit: int | None = None,
    ) -> list[RunRecord]:
        """Return runs, newest first, optionally filtered."""
        ...

    def record_update(
        self,
        run_id: str,
        *,
        kind: str,
        summary: Mapping[str, Any],
        status: str | None = None,
        node_id: str | None = None,
        unit_id: str | None = None,
        failure: Mapping[str, Any] | None = None,
        result_ref: str | None = None,
    ) -> tuple[RunRecord, RunEventRecord]:
        """Apply a run update and append its event in one transaction.

        The event receives the next per-run sequence number. Notify
        subscribers only after this method returns.
        """
        ...

    def list_events(
        self, run_id: str, *, after_sequence: int = 0, limit: int | None = None
    ) -> list[RunEventRecord]:
        """Return a run's events after a sequence number, in order."""
        ...

    def delete_runs(self, run_ids: Collection[str]) -> dict[str, int]:
        """Delete finished runs and their events in one transaction.

        Pipelines, revisions and plugin registrations stay. Only explicit,
        previewed workspace cleanup calls this method.

        Returns:
            ``{"runs": n, "events": m}``, the number of rows removed.

        Raises:
            KeyError: If a run does not exist. Nothing is deleted.
            ValueError: If a run is still active, or a run that stays
                refers to it as its retry source. Nothing is deleted.
        """
        ...

    def register_plugin(
        self,
        name: str,
        *,
        manifest_ref: str,
        executable_ref: str,
        manifest_hash: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> PluginRecord:
        """Record or replace an approved plugin; compatibility resets.

        ``detail`` is stored in the same write; without it it resets to ``{}``.
        """
        ...

    def unregister_plugin(self, name: str) -> PluginRecord:
        """Remove a plugin registration and return it. Unknown names raise ``KeyError``."""
        ...

    def set_plugin_compatibility(
        self, name: str, status: str, *, detail: Mapping[str, Any] | None = None
    ) -> PluginRecord:
        """Record the result of a plugin compatibility check."""
        ...

    def get_plugin(self, name: str) -> PluginRecord:
        """Return one plugin registration."""
        ...

    def list_plugins(self) -> list[PluginRecord]:
        """Return all plugin registrations by name."""
        ...
