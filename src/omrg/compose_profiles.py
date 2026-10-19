"""Profile service: user profiles that own three pipelines (design D4 to D12, D18, D21, D23).

The web server builds one :class:`ProfileService` per launch. It is part of
the composition root: it joins the workspace database (profiles, pipelines and
revisions) with the Engine (graph checks, standard graphs, collections).

* :meth:`~ProfileService.list_profiles` and :meth:`~ProfileService.get_profile`
  describe built-in and user profiles with readiness and ``used_by``.
* :meth:`~ProfileService.create_profile` duplicates a built-in or a user
  profile, or starts empty. A rename changes the title and the description
  only. A delete is a soft delete and is refused while a collection uses the
  profile.
* Readiness (D9) and the binding check run the draft graph check, so a profile
  is ready only when each pipeline can run.

The service holds no state besides one lock. Delete and bind run inside it
(:attr:`~ProfileService.lock`), so they cannot cross.
"""

from __future__ import annotations

import threading
import unicodedata
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from .compose_profile_embedding import ProfileEmbedding
from .compose_templates import profile_templates
from .core.profiles.catalogue import BUILTIN_PROFILES, SLOT_CONTRACTS
from .core.profiles.readiness import (
    contract_reasons,
    issue_reasons,
    no_graph_reason,
)

if TYPE_CHECKING:
    from .core.profiles.catalogue import ProfileCatalogue
    from .core.vectordb.identity import EmbeddingIdentity
    from .core.workspace import ProfileRepository, WorkspaceRepository

SLOTS: tuple[str, ...] = tuple(c.slot for c in SLOT_CONTRACTS)
TITLE_MAX = 80
_BUILTIN_TEXT: dict[str, tuple[str, str]] = {
    "documents": (
        "Documents",
        "Papers, reports and prose. Dense retrieval with the reranker on.",
    ),
    "codebase": (
        "Codebase",
        "Source code. Dense and sparse retrieval with fusion, reranker off.",
    ),
}


class ProfileError(Exception):
    """Base class of the errors that the profile service raises."""


class UnknownProfileError(ProfileError, KeyError):
    """The profile does not exist, or it was deleted."""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else "unknown profile"


class BuiltinProfileError(ProfileError, ValueError):
    """The change is not allowed on a built-in profile."""


class ProfileInUseError(ProfileError, ValueError):
    """The profile is in use by collections.

    Attributes:
        used_by: Names of the collections that use the profile.
    """

    def __init__(self, message: str, used_by: list[str]) -> None:
        super().__init__(message)
        self.used_by = used_by


class ProfileDeletedError(ProfileError, ValueError):
    """The pipeline belongs to a deleted profile and cannot change."""


class ProfileNotReadyError(ProfileError, ValueError):
    """The profile cannot be used yet.

    Attributes:
        reasons: Plain-English lines that say what to fix.
    """

    def __init__(self, reasons: list[str]) -> None:
        super().__init__(" ".join(reasons))
        self.reasons = reasons


def _clean_title(title: str) -> str:
    """Return the trimmed title, or raise for an empty, long or control-character title."""
    cleaned = title.strip()
    if not 1 <= len(cleaned) <= TITLE_MAX:
        raise ValueError(f"The title must hold 1 to {TITLE_MAX} characters.")
    if any(unicodedata.category(ch) == "Cc" for ch in cleaned):
        raise ValueError("The title must not contain control characters.")
    return cleaned


class ProfileService:
    """List, create, rename and delete profiles, and check them for readiness.

    Args:
        engine: The Engine that validates graphs and builds standard graphs.
        workspace: The workspace repository (pipelines and revisions).
        profiles: The profile repository.
        catalogue: Read access to profiles, as other processes see them.
        collection_tags: Returns ``{collection: stored profile tag or None}``.
        host_identity: Returns the server default embedding model. ``None``
            reads it from the settings.
    """

    def __init__(
        self,
        engine: Any,
        workspace: WorkspaceRepository,
        profiles: ProfileRepository,
        catalogue: ProfileCatalogue,
        *,
        collection_tags: Callable[[], Mapping[str, str | None]],
        host_identity: Callable[[], EmbeddingIdentity] | None = None,
    ) -> None:
        self._engine = engine
        self._workspace = workspace
        self._profiles = profiles
        self._catalogue = catalogue
        self._collection_tags = collection_tags
        self._lock = threading.RLock()
        self.embedding = ProfileEmbedding(self, host_identity)

    @property
    def lock(self) -> threading.RLock:
        """The lock that a delete and a bind both hold, so they cannot cross."""
        return self._lock

    @property
    def catalogue(self) -> ProfileCatalogue:
        """The catalogue that reads user profiles."""
        return self._catalogue

    # ── Reading ─────────────────────────────────────────────────────

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return built-in profiles, then user profiles that are not deleted."""
        tags = dict(self._collection_tags())
        items = [self._builtin_item(name, tags) for name in BUILTIN_PROFILES]
        items += [self._user_item(r, tags) for r in self._profiles.list_profiles()]
        return items

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        """Return one profile.

        A built-in carries ``standard_graphs`` (the Ingest, Search and Answer
        graphs that a duplicate would get). A user profile carries ``None``.

        Raises:
            UnknownProfileError: If the profile does not exist or was deleted.
        """
        tags = dict(self._collection_tags())
        if profile_id in BUILTIN_PROFILES:
            item = self._builtin_item(profile_id, tags)
            item["standard_graphs"] = profile_templates(self._engine, profile_id)
            return item
        item = self._user_item(self._user_record(profile_id), tags)
        item["standard_graphs"] = None
        return item

    def _user_record(self, profile_id: str) -> dict[str, Any]:
        try:
            record = dict(self._profiles.get_profile(profile_id))
        except KeyError:
            record = {}
        if not record or record["archived_at"]:
            raise UnknownProfileError(f"Unknown profile {profile_id!r}.")
        return record

    @staticmethod
    def _used_by(profile_id: str, tags: Mapping[str, str | None]) -> list[str]:
        return sorted(name for name, tag in tags.items() if tag == profile_id)

    def _builtin_item(self, name: str, tags: Mapping[str, str | None]) -> dict[str, Any]:
        title, description = _BUILTIN_TEXT[name]
        used_by = self._used_by(name, tags)
        return {
            "profile_id": name,
            "kind": "builtin",
            "title": title,
            "description": description,
            "base_profile": name,
            "slots": dict.fromkeys(SLOTS),
            "ready": True,
            "not_ready_reasons": [],
            "used_by": used_by,
            **self.embedding.fields(None, used_by),
        }

    def _user_item(
        self, record: Mapping[str, Any], tags: Mapping[str, str | None]
    ) -> dict[str, Any]:
        reasons = self.readiness_reasons(record)
        used_by = self._used_by(record["profile_id"], tags)
        return {
            "profile_id": record["profile_id"],
            "kind": "user",
            "title": record["title"],
            "description": record["description"],
            "base_profile": record["base_profile"],
            "slots": {slot: record[f"{slot}_pipeline_id"] for slot in SLOTS},
            "ready": not reasons,
            "not_ready_reasons": reasons,
            "used_by": used_by,
            **self.embedding.fields(record, used_by),
        }

    # ── Readiness (D9) ──────────────────────────────────────────────

    def slot_document(self, record: Mapping[str, Any], slot: str) -> dict[str, Any] | None:
        """Return the current saved graph of one slot pipeline, or ``None``."""
        pipeline = self._workspace.get_pipeline(record[f"{slot}_pipeline_id"])
        revision_id = pipeline["current_revision_id"]
        return (
            None if revision_id is None else self._workspace.get_revision(revision_id)["document"]
        )

    def readiness_reasons(
        self, record: Mapping[str, Any], *, collection: str | None = None
    ) -> list[str]:
        """Return why a profile is not ready; an empty list means ready.

        Args:
            record: The profile record.
            collection: A target collection. The check then includes the
                embedding model of that collection.
        """
        reasons: list[str] = []
        for slot in SLOTS:
            document = self.slot_document(record, slot)
            if document is None:
                reasons.append(no_graph_reason(slot))
            else:
                reasons += self.graph_reasons(slot, document, collection=collection)
        return reasons

    def graph_reasons(
        self, slot: str, document: Mapping[str, Any], *, collection: str | None = None
    ) -> list[str]:
        """Return why a graph does not fit ``slot``: the draft check, then the purpose."""
        from .core.pipelines import PipelineValidationError, parse_definition

        keep = collection is not None
        try:
            graph = parse_definition({"graph": dict(document)}).graph
        except PipelineValidationError as exc:
            return issue_reasons(slot, exc.issues, keep_collection_issues=keep)
        try:
            self._engine.validate_pipeline(document, collection=collection)
            issues = []
        except PipelineValidationError as exc:
            issues = list(exc.issues)
        catalogue = self._engine._pipelines.catalogue()
        return issue_reasons(slot, issues, keep_collection_issues=keep) + contract_reasons(
            slot, graph, catalogue
        )

    def binding_reasons(self, profile_id: str, collection: str) -> list[str]:
        """Return why a user profile cannot be bound to ``collection``.

        Raises:
            UnknownProfileError: If the profile does not exist or was deleted.
        """
        return self.readiness_reasons(self._user_record(profile_id), collection=collection)

    def check_binding(self, profile_id: str, collection: str) -> None:
        """Check that a profile can be bound to a collection.

        A user profile must exist, not be deleted, and be ready for the target
        collection. Any profile must use the model that the collection holds
        vectors for (ADR-081).

        Raises:
            UnknownProfileError: If the profile does not exist or was deleted.
            ProfileNotReadyError: With the reasons, if a pipeline is not ready.
            EmbeddingMismatchError: If the collection holds vectors from another model.
        """
        if profile_id not in BUILTIN_PROFILES:
            reasons = self.binding_reasons(profile_id, collection)
            if reasons:
                raise ProfileNotReadyError(reasons)
        self.embedding.check_binding(profile_id, collection)

    def fingerprint(self, profile_id: str) -> str:
        """Return a token that changes when a bound profile changes.

        It holds the delete time and the current revision of each pipeline, so a
        confirmation issued before a save or a delete is stale. Built-in
        profiles never change: the token is empty.
        """
        if profile_id in BUILTIN_PROFILES:
            return ""
        try:
            record = self._profiles.get_profile(profile_id)
        except KeyError:
            return "unknown"
        revisions = [
            self._workspace.get_pipeline(record[f"{slot}_pipeline_id"])["current_revision_id"]
            for slot in SLOTS
        ]
        return ",".join([str(record["archived_at"] or ""), *(r or "-" for r in revisions)])

    # ── Slot pipelines (D7, D8, D19) ────────────────────────────────

    def owner_of(self, pipeline_id: str) -> tuple[dict[str, Any], str] | None:
        """Return the profile record and the slot that a pipeline fills, or ``None``.

        A deleted profile is returned too: its pipelines stay readable.
        """
        found = self._profiles.find_profile_by_pipeline(pipeline_id)
        return None if found is None else (dict(found[0]), found[1])

    def check_slot_editable(self, pipeline_id: str) -> None:
        """Refuse a change to a pipeline of a deleted profile.

        Raises:
            ProfileDeletedError: If the pipeline belongs to a deleted profile.
        """
        owner = self.owner_of(pipeline_id)
        if owner is not None and owner[0]["archived_at"]:
            raise ProfileDeletedError(
                f"This pipeline belongs to the deleted profile {owner[0]['profile_id']!r}, "
                f"so it cannot change."
            )

    def check_slot_save(self, pipeline_id: str, document: Mapping[str, Any]) -> list[str] | None:
        """Check a new revision of a pipeline before it is saved.

        Args:
            pipeline_id: The pipeline that receives the revision.
            document: The graph document of the new revision.

        Returns:
            ``None`` for a pipeline that belongs to no profile. Otherwise the
            names of the collections that use the profile (maybe none), which
            the save affects.

        Raises:
            ProfileDeletedError: If the profile was deleted.
            ValueError: If the graph does not name the base profile.
            ProfileNotReadyError: If the profile is in use and the graph would
                make it not ready.
        """
        owner = self.owner_of(pipeline_id)
        if owner is None:
            return None
        record, slot = owner
        self.check_slot_editable(pipeline_id)
        base = record["base_profile"]
        if document.get("profile") != base:
            raise ValueError(
                f"The graph of a profile pipeline must name the base profile {base!r} as its "
                f"profile. Set the profile of the graph to {base!r}."
            )
        used_by = self._used_by(record["profile_id"], dict(self._collection_tags()))
        if used_by:
            reasons = self.graph_reasons(slot, document)
            if reasons:
                raise ProfileNotReadyError(reasons)
        return used_by

    # ── Writing ─────────────────────────────────────────────────────

    def create_profile(
        self, title: str, *, source: str | None = None, description: str | None = None
    ) -> dict[str, Any]:
        """Create a user profile.

        Args:
            title: The profile title (1 to 80 characters).
            source: A built-in id (standard graphs), a user profile id (a copy
                of its current revisions and layouts) or ``None`` (empty
                pipelines, base profile ``documents``).
            description: Optional description.

        Raises:
            ValueError: If the title is not valid.
            UnknownProfileError: If ``source`` is unknown or deleted.
        """
        from .core.pipelines.models import SCHEMA_VERSION

        title = _clean_title(title)
        layouts: dict[str, Mapping[str, Any]] = {}
        embedding: tuple[str, str, int | None] | None = None
        slots: dict[str, Any]
        if source is None:
            base, slots = "documents", dict.fromkeys(SLOTS)
        elif source in BUILTIN_PROFILES:
            base, slots = source, dict(profile_templates(self._engine, source))
        else:
            record = self._user_record(source)
            base = record["base_profile"]
            slots = {slot: self.slot_document(record, slot) for slot in SLOTS}
            if record.get("embed_provider") and record.get("embed_model"):
                embedding = (
                    record["embed_provider"],
                    record["embed_model"],
                    record.get("embed_dimensions"),
                )
            for slot in SLOTS:
                pipeline = self._workspace.get_pipeline(record[f"{slot}_pipeline_id"])
                layouts[slot] = dict(pipeline["layout"])
        created = self._profiles.create_profile(
            title,
            base_profile=base,
            slots=slots,
            schema_version=SCHEMA_VERSION,
            description=description or "",
            layouts=layouts,
            embedding=embedding,
        )
        return self._user_item(created, dict(self._collection_tags()))

    def set_embedding(
        self, profile_id: str, provider: str | None, model: str | None
    ) -> dict[str, Any]:
        """Check and save the embedding model of a user profile (ADR-081).

        See :meth:`ProfileEmbedding.save` for the errors.
        """
        self.embedding.save(profile_id, provider, model)
        return self._user_item(self._user_record(profile_id), dict(self._collection_tags()))

    def rename_profile(
        self, profile_id: str, *, title: str | None = None, description: str | None = None
    ) -> dict[str, Any]:
        """Change the title or the description of a user profile. The id stays.

        Raises:
            BuiltinProfileError: For a built-in profile.
            UnknownProfileError: If the profile does not exist or was deleted.
            ValueError: If the title is not valid.
        """
        if profile_id in BUILTIN_PROFILES:
            raise BuiltinProfileError("A built-in profile cannot be changed.")
        self._user_record(profile_id)
        new_title = None if title is None else _clean_title(title)
        self._profiles.update_profile(profile_id, title=new_title, description=description)
        return self._user_item(self._user_record(profile_id), dict(self._collection_tags()))

    def delete_profile(self, profile_id: str) -> dict[str, Any]:
        """Soft-delete a user profile that no collection uses.

        Returns:
            The profile as it was before the delete.

        Raises:
            BuiltinProfileError: For a built-in profile.
            UnknownProfileError: If the profile does not exist or was deleted.
            ProfileInUseError: While a collection uses the profile.
        """
        if profile_id in BUILTIN_PROFILES:
            raise BuiltinProfileError("A built-in profile cannot be deleted.")
        with self._lock:
            item = self.get_profile(profile_id)
            if item["used_by"]:
                names = ", ".join(item["used_by"])
                raise ProfileInUseError(
                    f"The profile {profile_id!r} is in use by: {names}. "
                    f"Change those collections to another profile first.",
                    item["used_by"],
                )
            self._profiles.archive_profile(profile_id)
        item.pop("standard_graphs", None)
        return item

    # ── Upgrade (D10) ───────────────────────────────────────────────

    def upgrade_saved_pipelines(self) -> list[str]:
        """Turn each saved Studio pipeline that belongs to no profile into a profile.

        See :func:`omrg.compose_profile_setup.upgrade_saved_pipelines`.
        """
        from .compose_profile_setup import upgrade_saved_pipelines

        return upgrade_saved_pipelines(self)
