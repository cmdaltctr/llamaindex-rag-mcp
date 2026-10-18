"""MCP tools: list_profiles and change_collection_profile."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from ...core.profiles import apply_profile_change, generate_safety_contract
from .context import McpContext, mcp_context
from .errors import error_detail, log_tool_error

#: Profiles that every process can bind: the operational built-ins.
BUILTIN_PROFILES = ("documents", "codebase")

#: The refusal the stdio server gives for a user profile id (D11).
BINDING_MESSAGE = (
    "Bind user profiles in Knowledge Base > Profile, or through the MCP endpoint of `omrg web`."
)

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

LIST_DESCRIPTION = (
    "List the profiles a collection can use: the built-in profiles "
    "'documents' and 'codebase', then the user profiles from the web "
    "workspace. Each item has profile_id, kind ('builtin' or 'user'), "
    "title, description, base_profile, slots (the ingest, search and "
    "answer pipeline ids), ready, not_ready_reasons and used_by (the "
    "collections that use the profile). Pass a profile_id to "
    "change_collection_profile. Without a web workspace the list holds "
    "the built-in profiles only."
)
LIST_ANNOTATIONS = ToolAnnotations(read_only_hint=True, destructive_hint=False)


async def list_profiles(*, ctx: Context) -> list[dict]:
    """List built-in and user profiles.

    On the web server's MCP endpoint the items are the ones of
    ``GET /v1/profiles``. On the stdio server they come from the read-only
    catalogue of the default workspace, or hold the built-ins only when that
    file does not exist.

    Returns an error list on any failure (gotcha #1).
    """
    mcp = mcp_context(ctx)
    try:
        async with mcp.admit():
            if mcp.profiles is not None:
                return await asyncio.to_thread(mcp.profiles.list_profiles)
            # Lazy: the profile service pulls in the workspace modules.
            from .profile_list import catalogue_profile_items

            return await asyncio.to_thread(catalogue_profile_items, mcp.engine)
    except Exception as exc:
        log_tool_error(mcp, "list_profiles", exc)
        return [{"status": "error", "message": error_detail(mcp, exc)}]


def _invalid_profile(profile: str) -> dict:
    return {
        "status": "error",
        "message": f"Invalid profile {profile!r}. Available: documents, codebase.",
    }


def _failure(mcp: McpContext, exc: Exception) -> dict:
    """Return the error dict of a failed check, with the reasons when it has them."""
    result: dict[str, Any] = {"status": "error", "message": error_detail(mcp, exc)}
    reasons = getattr(exc, "reasons", None)
    if isinstance(reasons, list):
        result["not_ready_reasons"] = reasons
    return result


def _preview(mcp: McpContext, collection: str, profile: str) -> dict:
    engine = mcp.engine
    service = mcp.profiles
    if service is None:
        return generate_safety_contract(
            collection, profile, store=engine.store, resolver=engine.profile_resolver
        )
    # A built-in profile is checked too: it must use the collection's model (ADR-081).
    with service.lock:
        service.check_binding(profile, collection)
        if profile in BUILTIN_PROFILES:
            return generate_safety_contract(
                collection, profile, store=engine.store, resolver=engine.profile_resolver
            )
        return generate_safety_contract(
            collection,
            profile,
            store=engine.store,
            resolver=engine.profile_resolver,
            catalogue=service.catalogue,
        )


def _apply(mcp: McpContext, collection: str, profile: str) -> dict:
    engine = mcp.engine
    service = mcp.profiles
    if service is None:
        return apply_profile_change(collection, profile, store=engine.store)
    # The lock keeps a profile delete from crossing this bind.
    with service.lock:
        service.check_binding(profile, collection)
        if profile in BUILTIN_PROFILES:
            return apply_profile_change(collection, profile, store=engine.store)
        return apply_profile_change(
            collection, profile, store=engine.store, catalogue=service.catalogue
        )


async def change_collection_profile(
    collection: str,
    profile: str,
    confirm: bool = False,
    *,
    ctx: Context,
) -> dict:
    """Change the profile bound to a collection.

    A user profile id binds on the web server's MCP endpoint only, and only
    when the profile is ready for the collection. The stdio server refuses it.

    Returns an error dict on any failure (gotcha #1).
    """
    mcp = mcp_context(ctx)
    if profile not in BUILTIN_PROFILES:
        if profile == "hybrid":
            return _invalid_profile(profile)
        if mcp.profiles is None:
            return {"status": "error", "message": BINDING_MESSAGE}

    if not confirm:
        try:
            async with mcp.admit():
                contract = await asyncio.to_thread(_preview, mcp, collection, profile)
        except Exception as exc:
            log_tool_error(mcp, "change_collection_profile preview", exc)
            return _failure(mcp, exc)
        return {
            "status": "preview",
            "contract": contract,
            "confirm_required": True,
        }

    try:
        async with mcp.admit():
            return await asyncio.to_thread(_apply, mcp, collection, profile)
    except Exception as exc:
        log_tool_error(mcp, "change_collection_profile", exc)
        return _failure(mcp, exc)
