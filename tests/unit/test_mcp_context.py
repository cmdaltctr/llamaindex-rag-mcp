"""McpContext and PathPolicy (design D2, spec: file paths stay inside roots)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from omrg.transports.api.grants import RootGrants
from omrg.transports.mcp.context import McpContext, PathDenied, PathPolicy, no_admission


def test_allow_all_returns_the_path_unchanged(tmp_path: Path) -> None:
    assert PathPolicy.allow_all().check("relative/or/missing") == "relative/or/missing"
    assert PathPolicy.allow_all().check(str(tmp_path)) == str(tmp_path)


def test_from_grants_accepts_a_path_inside_a_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("x")
    policy = PathPolicy.from_grants(RootGrants.from_paths([root]))

    assert policy.check(str(root / "a.txt")) == str((root / "a.txt").resolve())


def test_from_grants_refuses_a_path_outside_the_roots(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    policy = PathPolicy.from_grants(RootGrants.from_paths([root]))

    with pytest.raises(PathDenied):
        policy.check(str(outside))


def test_from_grants_refuses_a_symlink_that_escapes_the_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x")
    (root / "link").symlink_to(outside)
    policy = PathPolicy.from_grants(RootGrants.from_paths([root]))

    with pytest.raises(PathDenied):
        policy.check(str(root / "link" / "secret.txt"))


def test_denial_message_does_not_disclose_the_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    policy = PathPolicy.from_grants(RootGrants.from_paths([root]))

    with pytest.raises(PathDenied) as info:
        policy.check("/etc/passwd")

    assert "/etc/passwd" not in str(info.value)


def test_no_admission_is_an_async_context_manager() -> None:
    async def run() -> str:
        async with no_admission():
            return "ran"

    assert asyncio.run(run()) == "ran"


def test_mcp_context_is_frozen() -> None:
    ctx = McpContext(engine=object(), paths=PathPolicy.allow_all(), admit=no_admission)
    with pytest.raises(AttributeError):
        ctx.engine = object()  # type: ignore[misc]
