"""MCP tool: change_collection_profile."""

from __future__ import annotations

import asyncio

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from ...core.profiles import apply_profile_change, generate_safety_contract
from .context import mcp_context
from .errors import error_detail, log_tool_error

DESCRIPTION = (
    "Change the profile bound to a ChromaDB collection. Profiles "
    "control retrieval behaviour: 'documents' (quality-first, reranker "
    "on, dense-only) or 'codebase' (speed-first, reranker off, hybrid). "
    "The change is non-destructive — existing chunks are NOT re-chunked "
    "or re-embedded. Query-time levers apply immediately; ingest-time "
    "levers apply to future ingests only. Returns a preview on first "
    "call; pass confirm=true to apply."
)
ANNOTATIONS = ToolAnnotations(read_only_hint=False, destructive_hint=True)


async def change_collection_profile(
    collection: str,
    profile: str,
    confirm: bool = False,
    *,
    ctx: Context,
) -> dict:
    """Change the profile bound to a collection.

    Returns an error dict on any failure (gotcha #1).
    """
    mcp = mcp_context(ctx)
    if profile not in ("documents", "codebase"):
        return {
            "status": "error",
            "message": (f"Invalid profile {profile!r}. Available: documents, codebase."),
        }

    engine = mcp.engine
    if not confirm:
        try:
            async with mcp.admit():
                contract = await asyncio.to_thread(
                    generate_safety_contract,
                    collection,
                    profile,
                    store=engine.store,
                    resolver=engine.profile_resolver,
                )
        except Exception as exc:
            log_tool_error(mcp, "change_collection_profile preview", exc)
            return {"status": "error", "message": error_detail(mcp, exc)}
        return {
            "status": "preview",
            "contract": contract,
            "confirm_required": True,
        }

    try:
        async with mcp.admit():
            return await asyncio.to_thread(
                apply_profile_change, collection, profile, store=engine.store
            )
    except Exception as exc:
        log_tool_error(mcp, "change_collection_profile", exc)
        return {"status": "error", "message": error_detail(mcp, exc)}
