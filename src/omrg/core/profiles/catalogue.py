"""User-profile catalogue: the lookup that profile resolution reads.

A collection tag can name a *user profile* that lives in the workspace
database. The resolver reads it through :class:`ProfileCatalogue`, so
``core`` never imports a storage engine. Composition builds the catalogue:
read-only over the default workspace for the stdio MCP server, the CLI and
the watcher, and over the web server's own workspace for ``omrg web``.

The slot contracts are plain data. They state which input and output ports
each of a profile's three pipelines needs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..vectordb.identity import EmbeddingIdentity


@runtime_checkable
class ProfileCatalogue(Protocol):
    """Read access to user profiles and the graphs of their pipelines.

    Profile mappings carry the keys of ``omrg.core.workspace.ProfileRecord``.
    """

    def get_profile(self, profile_id: str) -> Mapping[str, Any] | None:
        """Return the profile, deleted or not, or ``None`` when unknown."""
        ...

    def list_profiles(self) -> Sequence[Mapping[str, Any]]:
        """Return the profiles that are usable by a collection tag."""
        ...

    def slot_revision(self, profile_id: str, slot: str) -> Mapping[str, Any] | None:
        """Return the current revision of a slot (``revision_id``, ``revision_number``,
        ``document``), or ``None`` when the slot has no saved revision."""
        ...

    def slot_document(self, profile_id: str, slot: str) -> Mapping[str, Any] | None:
        """Return the current graph document of a slot, or ``None``."""
        ...


def uses_ollama_embeddings(catalogue: ProfileCatalogue | None) -> bool:
    """Return whether any usable profile in *catalogue* selects Ollama embeddings.

    Args:
        catalogue: The catalogue, or ``None`` when the process has no workspace.
    """
    if catalogue is None:
        return False
    return any(record.get("embed_provider") == "ollama" for record in catalogue.list_profiles())


@dataclass(frozen=True)
class ProfileBinding:
    """The profile a collection follows.

    Attributes:
        name: The profile id: ``documents`` or ``codebase`` for a built-in, the
            user profile id otherwise.
        base_profile: The built-in profile whose settings apply.
        embedding: The (provider, model) a user profile names for its
            collections (ADR-081), or ``None`` for the server default.
    """

    name: str
    base_profile: str
    embedding: EmbeddingIdentity | None = None

    @property
    def user(self) -> bool:
        """Whether the binding names a user profile."""
        return self.name != self.base_profile


@dataclass(frozen=True)
class SlotContract:
    """The ports and write rule that one pipeline of a profile must meet.

    Attributes:
        slot: ``ingest``, ``search`` or ``answer``.
        title: The pipeline title shown to users.
        input_name: Name of the graph input.
        input_kind: Value kind of the graph input.
        output_name: Name of the graph output.
        output_kind: Value kind of the graph output.
        write_steps: ``"one"`` for exactly one enabled write step, ``"none"``
            for no enabled write step.
    """

    slot: str
    title: str
    input_name: str
    input_kind: str
    output_name: str
    output_kind: str
    write_steps: str


SLOT_CONTRACTS: tuple[SlotContract, ...] = (
    SlotContract("ingest", "Ingest", "path", "sources", "summary", "commit_summary", "one"),
    SlotContract("search", "Search", "query", "query", "results", "context", "none"),
    SlotContract("answer", "Answer", "query", "query", "answer", "answer", "none"),
)

BUILTIN_PROFILES: tuple[str, ...] = ("documents", "codebase")


def _shown_path(path: Path) -> str:
    """Return ``path`` with the home directory written as ``~``."""
    try:
        return f"~/{path.relative_to(Path.home()).as_posix()}"
    except ValueError:
        return str(path)


def no_workspace_message(collection: str, profile_id: str) -> str:
    """Explain that a user profile needs a workspace this process cannot read."""
    # Imported here: a bare ``omrg`` call must not load workspace modules.
    from ..workspace.cleanup import WorkspaceLayout, default_workspace

    path = _shown_path(WorkspaceLayout(default_workspace()).records)
    return (
        f"Collection {collection!r} uses the profile {profile_id!r}, which is not a "
        f"built-in profile. User profiles live in the web workspace, and no workspace "
        f"database was found at {path}. Start `omrg web` once with the default "
        f"workspace, or change the collection's profile to 'documents' or 'codebase'."
    )


def deleted_message(collection: str, profile_id: str) -> str:
    """Explain that a collection names a deleted user profile."""
    return (
        f"Collection {collection!r} uses the profile {profile_id!r}, which was deleted. "
        f"Choose another profile for the collection."
    )


def unknown_message(collection: str, tag: str, user_profiles: Sequence[str]) -> str:
    """Explain that a tag names no profile, and list the profiles that exist."""
    available = ", ".join([*sorted(BUILTIN_PROFILES), *sorted(user_profiles)])
    return (
        f"Collection {collection!r} has an invalid profile tag {tag!r}. "
        f"Available profiles: {available}"
    )
