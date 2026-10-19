"""Tests for the ``--allow-origin`` value parser."""

from __future__ import annotations

import pytest

from omrg.transports.api.origins import parse_extra_origin


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://localhost:3000", "http://localhost:3000"),
        ("http://127.0.0.1:3000", "http://127.0.0.1:3000"),
        ("http://[::1]:3000", "http://[::1]:3000"),
        (
            "http://llamaindex-rag-mcp-feat-x.orca.localhost:57977",
            "http://llamaindex-rag-mcp-feat-x.orca.localhost:57977",
        ),
        ("https://app.localhost", "https://app.localhost"),
        ("  HTTP://LocalHost:3000/  ", "http://localhost:3000"),
        ("http://localhost:80", "http://localhost"),
        ("https://localhost:443", "https://localhost"),
        ("http://localhost:443", "http://localhost:443"),
    ],
)
def test_valid_origins_are_normalised(value: str, expected: str) -> None:
    assert parse_extra_origin(value) == expected


@pytest.mark.parametrize(
    ("value", "rule"),
    [
        ("http://localhost:3000/app", "path"),
        ("http://localhost:3000/?x=1", "query"),
        ("http://localhost:3000/#frag", "fragment"),
        ("http://user:pw@localhost:3000", "user information"),
        ("http://*.localhost:3000", "wildcard"),
        ("http://localhost:*", "wildcard"),
        ("ftp://localhost:3000", "scheme"),
        ("localhost:3000", "scheme"),
        ("http://example.com:3000", "loopback"),
        ("http://10.0.0.5:3000", "loopback"),
        ("http://localhost.evil.example", "loopback"),
        ("http://evillocalhost", "loopback"),
        ("http://localhost:99999", "port"),
        ("", "empty"),
    ],
)
def test_invalid_origins_name_the_broken_rule(value: str, rule: str) -> None:
    with pytest.raises(ValueError, match=rule) as caught:
        parse_extra_origin(value)
    assert repr(value.strip()) in str(caught.value) or not value.strip()
