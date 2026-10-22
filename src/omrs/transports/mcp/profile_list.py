"""Profile items for the stdio MCP server (D11).

The stdio server has no profile service: it has the read-only catalogue of
the default workspace. A thin service over that catalogue gives the same
items as ``GET /v1/profiles``, including readiness and ``used_by``.
"""

from __future__ import annotations

from typing import Any

from ...compose_profile_setup import engine_collection_tags
from ...compose_profiles import ProfileService


class _CatalogueRecords:
    """The profile records of a catalogue, or none without a workspace."""

    def __init__(self, catalogue: Any | None) -> None:
        self._catalogue = catalogue

    def list_profiles(self) -> list[Any]:
        """Return the user profiles that are not deleted."""
        return [] if self._catalogue is None else list(self._catalogue.list_profiles())


class _CatalogueProfileService(ProfileService):
    """A read-only profile service: it reads graphs from the catalogue."""

    def __init__(self, engine: Any, catalogue: Any | None) -> None:
        super().__init__(
            engine,
            None,  # type: ignore[arg-type]  # no workspace repository: the service only reads
            _CatalogueRecords(catalogue),  # type: ignore[arg-type]
            catalogue,  # type: ignore[arg-type]  # None: no workspace, built-ins only
            collection_tags=engine_collection_tags(engine),
        )

    def slot_document(self, record: Any, slot: str) -> dict[str, Any] | None:
        """Return the current saved graph of one slot pipeline, or ``None``."""
        document = self.catalogue.slot_document(record["profile_id"], slot)
        return None if document is None else dict(document)


def catalogue_profile_items(engine: Any) -> list[dict[str, Any]]:
    """Return the profile items that the Engine's own catalogue shows.

    Built-in profiles come first. User profiles follow when the Engine has a
    catalogue; a process without a workspace lists the built-ins only.
    """
    resolver = engine.profile_resolver
    catalogue = None if resolver is None else resolver.catalogue
    return _CatalogueProfileService(engine, catalogue).list_profiles()
