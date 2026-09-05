"""MCP tool: change_collection_profile."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from . import _error_detail, _get_profile_resolver, _log_tool_error, mcp


@mcp.tool(
    description=(
        "Change the profile bound to a ChromaDB collection. Profiles "
        "control retrieval behaviour: 'documents' (quality-first, reranker "
        "on, dense-only) or 'codebase' (speed-first, reranker off, hybrid). "
        "The change is non-destructive — existing chunks are NOT re-chunked "
        "or re-embedded. Query-time levers apply immediately; ingest-time "
        "levers apply to future ingests only. Returns a preview on first "
        "call; pass confirm=true to apply."
    ),
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
)
def change_collection_profile(
    collection: str,
    profile: str,
    confirm: bool = False,
) -> dict:
    """Change the profile bound to a collection.

    Returns an error dict on any failure (gotcha #1).
    """
    from ...core.profiles import apply_profile_change, generate_safety_contract

    if profile not in ("documents", "codebase"):
        return {
            "status": "error",
            "message": (f"Invalid profile {profile!r}. Available: documents, codebase."),
        }

    if not confirm:
        try:
            contract = generate_safety_contract(
                collection, profile, resolver=_get_profile_resolver()
            )
        except Exception as exc:
            _log_tool_error("change_collection_profile preview", exc)
            return {"status": "error", "message": _error_detail(exc)}
        return {
            "status": "preview",
            "contract": contract,
            "confirm_required": True,
        }

    try:
        return apply_profile_change(collection, profile)
    except Exception as exc:
        _log_tool_error("change_collection_profile", exc)
        return {"status": "error", "message": _error_detail(exc)}
