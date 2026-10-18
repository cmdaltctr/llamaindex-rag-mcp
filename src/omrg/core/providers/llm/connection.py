"""Connection descriptors for LLM providers (design D5).

Each LLM provider module declares one :data:`CONNECTION` descriptor: pure
data plus small pure functions. The web workspace builds a provider card
from it, so a new provider needs a new module and one registry line, with
no change to the card code.

Nothing here imports a provider module, a settings singleton or
``omrg.config`` at run time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ConnectionField:
    """One editable value of a provider.

    Attributes:
        id: Stable field id within the provider, for example ``base_url``.
        label: Short label for the card.
        kind: ``url`` for an address, ``secret`` for an API key.
        settings_field: Name of the ``Settings`` field that holds the value.
        env_var: Environment variable that sets the value.
    """

    id: str
    label: str
    kind: Literal["url", "secret"]
    settings_field: str
    env_var: str


@dataclass(frozen=True)
class ReadOnlyValue:
    """A labelled value the card shows but the user cannot edit here."""

    label: str
    value: str


@dataclass(frozen=True)
class ConnectionTarget:
    """Requests the server sends to test a provider or list its models.

    Attributes:
        urls: Full request URLs. Empty means the provider is not configured.
        headers: Request headers. They can hold the key, so they stay out
            of ``repr`` and are never returned to a client.
    """

    urls: tuple[str, ...]
    headers: dict[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ConnectionDescriptor:
    """Everything a provider card needs to know about one provider.

    Attributes:
        display_name: Name shown on the card.
        locality: ``local`` or ``cloud``.
        requires_module: Module that must import for the provider to run.
        extra: ``pyproject.toml`` extra that supplies the module, or
            ``None`` when the base install has it.
        fields: Editable values.
        read_only: Returns the labelled read-only values for a settings object.
        test_targets: Returns the requests of the connection test.
        models_target: Returns the request that lists models.
        parse_models: Returns model names from a decoded model-list payload;
            an empty list when the payload has an unexpected shape.
    """

    display_name: str
    locality: Literal["local", "cloud"]
    requires_module: str
    extra: str | None
    fields: tuple[ConnectionField, ...]
    read_only: Callable[[Any], list[ReadOnlyValue]]
    test_targets: Callable[[Any], ConnectionTarget]
    models_target: Callable[[Any], ConnectionTarget]
    parse_models: Callable[[object], list[str]]


def join_url(base: str, path: str) -> tuple[str, ...]:
    """Return ``base`` joined to ``path`` as a one-item tuple, or ``()`` for a blank base."""
    base = (base or "").strip().rstrip("/")
    return (f"{base}{path}",) if base else ()


def models_from(payload: object, list_key: str, name_key: str) -> list[str]:
    """Return the string ``name_key`` of each item in ``payload[list_key]``.

    Args:
        payload: Decoded JSON.
        list_key: Key of the item list.
        name_key: Key of the model name in each item.

    Returns:
        Model names in payload order. Any unexpected shape gives ``[]``.
    """
    if not isinstance(payload, dict):
        return []
    items = payload.get(list_key)
    if not isinstance(items, list):
        return []
    return [
        item[name_key]
        for item in items
        if isinstance(item, dict) and isinstance(item.get(name_key), str)
    ]
