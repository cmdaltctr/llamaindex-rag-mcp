"""Settings view of the llama.cpp server that ``omrg web`` manages (design D12).

A pure function over resolved ``Settings`` and the saved values. It gives the
program, the model and the context window with their source and lock, laid out
like a provider card field, plus the chat address the server listens on.
``compose.llamacpp_server_settings`` is the thin entry that reads the settings;
this module sits beside ``compose.py`` because that file is near the 500-line
ceiling.
"""

from __future__ import annotations

from typing import Any

from .compose_connections import _plain_field
from .compose_providers import ProviderValues, apply_provider_values, locked_fields
from .config import Settings
from .core.providers.llm.llamacpp_rules import LLAMACPP_SERVER_FIELDS

#: Key of each field in the view (``binary``, ``model``, ``context_window``, ``idle_sleep``).
VIEW_KEYS = {
    "server_binary": "binary",
    "server_model": "model",
    "context_window": "context_window",
    "idle_sleep": "idle_sleep",
}


def build_llamacpp_server_view(
    settings: Settings, values: ProviderValues | None = None
) -> dict[str, Any]:
    """Return the four server settings, each with value, source and lock.

    Args:
        settings: Settings as the environment and ``.env`` resolved them.
        values: Saved values from the web workspace, or ``None`` for none.

    Returns:
        ``{"chat_url": str, "binary": field, "model": field, "context_window":
        field, "idle_sleep": field}``. A field holds ``id``, ``label``, ``kind``, ``value``,
        ``min``, ``max``, ``source`` (``env``, ``dotenv``, ``config-file`` or
        ``default``), ``locked`` and ``lock_reason``.
    """
    values = values or ProviderValues()
    applied = apply_provider_values(settings, values)
    locks = locked_fields(applied, applied.provider_explicit)
    view: dict[str, Any] = {"chat_url": applied.llamacpp_chat_url}
    for spec in LLAMACPP_SERVER_FIELDS:
        entry = _plain_field(spec, applied, values, locks)
        view[VIEW_KEYS[spec.id]] = {
            key: entry[key]
            for key in (
                "id",
                "label",
                "kind",
                "value",
                "min",
                "max",
                "source",
                "locked",
                "lock_reason",
            )
        }
    return view
