"""Parsers for the OpenRouter model catalogue and key answers (add-chat-reasoning-and-usage D5).

Pure functions over decoded JSON. The web transport sends the requests and
passes the payload here. Any unexpected shape gives an empty map or
``None``, so the Settings page falls back to the text box and the usage line
shows no credit.

Shapes recorded on 2026-10-23:

- ``GET /api/v1/models``: ``{"data": [{"id": ..., "reasoning": {"supported_efforts":
  [...], "default_effort": ..., "mandatory": bool}}]}``. A model without
  reasoning has ``"reasoning": null`` or no key.
- ``GET /api/v1/key``: ``{"data": {"limit": number | null, "limit_remaining": number | null}}``.
"""

from __future__ import annotations

import re
from typing import Any

#: A level the Settings page can save (same rule as ``AnswerSettings.reasoning``).
_LEVEL = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def _levels_of(reasoning: object) -> dict[str, Any] | None:
    """Return ``{"levels", "default", "mandatory"}`` for one ``reasoning`` object, or ``None``."""
    if not isinstance(reasoning, dict):
        return None
    efforts = reasoning.get("supported_efforts")
    if not isinstance(efforts, list):
        return None
    levels = [e for e in efforts if isinstance(e, str) and _LEVEL.fullmatch(e)]
    if not levels:
        return None
    default = reasoning.get("default_effort")
    return {
        "levels": levels,
        "default": default if default in levels else None,
        "mandatory": reasoning.get("mandatory") is True,
    }


def parse_reasoning_levels(payload: object) -> dict[str, dict[str, Any]]:
    """Return a map of model id to its level list from the model catalogue.

    Models with no usable level list are left out, so a lookup for them
    finds nothing and the route answers ``{"known": false}``.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return {}
    found: dict[str, dict[str, Any]] = {}
    for item in payload["data"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        if (entry := _levels_of(item.get("reasoning"))) is not None:
            found[item["id"]] = entry
    return found


def _number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def parse_credit(payload: object) -> dict[str, float] | None:
    """Return ``{"limit_usd", "remaining_usd"}`` from a ``GET /key`` answer, or ``None``.

    A key with no spending limit has ``limit: null`` and gives ``None``.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    limit, remaining = data.get("limit"), data.get("limit_remaining")
    if not (_number(limit) and _number(remaining)):
        return None
    return {"limit_usd": limit, "remaining_usd": remaining}
