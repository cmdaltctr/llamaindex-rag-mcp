"""Plain-data records exchanged with the workspace repository.

The records are JSON-compatible dictionaries. They carry no behaviour, so a
persistence adapter can build them without importing this package.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, TypedDict

RunStatus = Literal[
    "queued", "running", "cancelling", "succeeded", "failed", "cancelled", "interrupted"
]
RunOrigin = Literal["submit", "repeat", "retry"]
PluginCompatibility = Literal["unchecked", "compatible", "incompatible"]

TERMINAL_RUN_STATUSES: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled", "interrupted"}
)
# ``cancelling``: cancellation was requested for a running job, which has not stopped yet.
NONTERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"queued", "running", "cancelling"})
RUN_STATUSES: frozenset[str] = TERMINAL_RUN_STATUSES | NONTERMINAL_RUN_STATUSES
RUN_ORIGINS: frozenset[str] = frozenset({"submit", "repeat", "retry"})
PLUGIN_COMPATIBILITY: frozenset[str] = frozenset({"unchecked", "compatible", "incompatible"})


# The three pipelines a user profile owns, one per purpose.
PROFILE_SLOTS: tuple[str, ...] = ("ingest", "search", "answer")
# The built-in profiles a user profile can be based on.
PROFILE_BASES: tuple[str, ...] = ("documents", "codebase")
# Ids a user profile cannot take. ``hybrid`` is a mode selector, not a profile.
RESERVED_PROFILE_IDS: frozenset[str] = frozenset({"documents", "codebase", "hybrid"})
PROFILE_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"

#: Layout key that marks a reserved workspace job pipeline (not a user graph).
TASK_LAYOUT_KEY = "omrs_task"


class PipelineRecord(TypedDict):
    """A pipeline identity with its presentation layout.

    The layout is presentation data only. Saving it never creates a revision.
    """

    pipeline_id: str
    title: str
    current_revision_id: str | None
    layout: dict[str, Any]
    created_at: str
    updated_at: str


class ProfileRecord(TypedDict):
    """A user profile: an id, a base built-in profile and three pipelines.

    The id, the base profile and the three pipeline ids never change after
    creation. ``archived_at`` is set by a soft delete. ``embed_provider`` and
    ``embed_model`` are both set (the profile's embedding choice) or both
    ``None`` (the server default); ``embed_dimensions`` is the vector size of
    the last passing model check (ADR-081).
    """

    profile_id: str
    title: str
    description: str
    base_profile: str
    ingest_pipeline_id: str
    search_pipeline_id: str
    answer_pipeline_id: str
    created_at: str
    updated_at: str
    archived_at: str | None
    embed_provider: str | None
    embed_model: str | None
    embed_dimensions: int | None


class RevisionRecord(TypedDict):
    """An immutable execution document and its content identity."""

    revision_id: str
    pipeline_id: str
    revision_number: int
    content_hash: str
    schema_version: int
    document: dict[str, Any]
    created_at: str


class RunRecord(TypedDict):
    """One admitted run and the provenance it captured at admission.

    ``settings`` holds redacted effective settings. ``resources`` holds
    backend, model, index and operation-version identities. ``inputs`` holds
    input identities or references, never raw source text or vectors.
    """

    run_id: str
    pipeline_id: str
    revision_id: str
    graph_hash: str
    status: str
    origin: str
    source_run_id: str | None
    settings: dict[str, Any]
    resources: dict[str, Any]
    inputs: dict[str, Any]
    failure: dict[str, Any] | None
    result_ref: str | None
    last_sequence: int
    created_at: str
    started_at: str | None
    finished_at: str | None


class RunEventRecord(TypedDict):
    """One persisted run event with its per-run sequence number."""

    run_id: str
    sequence: int
    kind: str
    node_id: str | None
    unit_id: str | None
    summary: dict[str, Any]
    created_at: str


class PluginRecord(TypedDict):
    """An approved external-tool registration and its compatibility state."""

    name: str
    manifest_ref: str
    executable_ref: str
    manifest_hash: str | None
    compatibility_status: str
    detail: dict[str, Any]
    registered_at: str
    checked_at: str | None


def canonical_json(value: Any) -> str:
    """Serialise a JSON-compatible value in one stable form.

    Keys are sorted, separators carry no whitespace, and non-ASCII text is
    kept as is. NaN and infinity are rejected because JSON has no form for them.

    Args:
        value: A JSON-compatible value.

    Returns:
        The canonical JSON text.

    Raises:
        ValueError: If the value is not JSON-compatible.
    """
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except TypeError as exc:
        raise ValueError(f"value is not JSON-compatible: {exc}") from exc


def content_hash(document: Any) -> str:
    """Return the SHA-256 hex digest of a document's canonical JSON.

    Args:
        document: A JSON-compatible execution document.

    Returns:
        A 64-character lowercase hex digest.

    Raises:
        ValueError: If the document is not JSON-compatible.
    """
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()
