"""Standard-library SQLite adapter for workspace application records.

Composition constructs ``SqliteWorkspaceRepository`` and injects it where
``omrg.core.workspace.WorkspaceRepository`` is expected.
"""

from __future__ import annotations

from omrg.integrations.workspace_sqlite.profiles import (
    SqliteProfileCatalogue,
    SqliteProfileRepository,
)
from omrg.integrations.workspace_sqlite.repository import SqliteWorkspaceRepository
from omrg.integrations.workspace_sqlite.schema import (
    SCHEMA_MIGRATIONS,
    WorkspaceSchemaError,
)

__all__ = [
    "SCHEMA_MIGRATIONS",
    "SqliteProfileCatalogue",
    "SqliteProfileRepository",
    "SqliteWorkspaceRepository",
    "WorkspaceSchemaError",
]
