"""``GET /v1/connections`` names each provider's install extra (add-chat-reasoning-and-usage).

The Settings page builds the install command from ``extra`` instead of
parsing ``install_hint``. ``extra`` is the descriptor's ``pyproject.toml``
extra, or ``None`` when the base install has the provider.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests.unit.test_connection_summary import make_settings, summary

from omrs.core.providers.llm import registry


def test_each_entry_carries_the_descriptor_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    result: dict[str, Any] = summary(monkeypatch, make_settings())
    descriptors = registry.describe_all()
    assert result["connections"]
    for entry in result["connections"]:
        assert "extra" in entry
        assert entry["extra"] == descriptors[entry["provider"]].extra
    by_name = {entry["provider"]: entry["extra"] for entry in result["connections"]}
    assert by_name["openrouter"] == "openrouter"
