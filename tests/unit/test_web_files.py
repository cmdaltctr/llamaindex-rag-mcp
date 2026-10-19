"""Tests for canonical root grants and managed uploads (task 6.3).

Covers traversal, symlink escape, indexed-metadata path denial, the
per-file size limit, supported-type preflight, archive and URL refusal,
and removal of partial uploads after a failure.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from omrg.core.ingestion.settings import DEFAULT_INGEST_EXTENSIONS  # noqa: E402
from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.grants import GrantDenied, RootGrants  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.security import AccessPolicy  # noqa: E402
from omrg.transports.api.uploads import (  # noqa: E402
    DEFAULT_MAX_UPLOAD_BYTES,
    UploadRejected,
    UploadStore,
)

BASE = "http://127.0.0.1:8765"
ORIGIN = {"Origin": BASE}


# ── Root grants ──────────────────────────────────────────────────────────


@pytest.fixture
def tree(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "approved"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.md").write_text("# a", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    return {"root": root, "outside": outside}


def test_relative_path_inside_root_resolves(tree: dict[str, Path]) -> None:
    grants = RootGrants.from_paths([tree["root"]])
    (root_id,) = [r["id"] for r in grants.describe()]
    resolved = grants.resolve(root_id, "docs/a.md")
    assert resolved == (tree["root"] / "docs" / "a.md").resolve()


@pytest.mark.parametrize(
    "relative",
    ["../outside/secret.txt", "docs/../../outside/secret.txt", "/etc/passwd", "docs/\x00a.md"],
)
def test_traversal_is_denied(tree: dict[str, Path], relative: str) -> None:
    grants = RootGrants.from_paths([tree["root"]])
    root_id = grants.describe()[0]["id"]
    with pytest.raises(GrantDenied):
        grants.resolve(root_id, relative)


def test_symlink_escape_is_denied(tree: dict[str, Path]) -> None:
    link = tree["root"] / "docs" / "escape"
    link.symlink_to(tree["outside"])
    grants = RootGrants.from_paths([tree["root"]])
    root_id = grants.describe()[0]["id"]
    with pytest.raises(GrantDenied):
        grants.resolve(root_id, "docs/escape/secret.txt")
    with pytest.raises(GrantDenied):
        grants.check(link / "secret.txt")


def test_symlink_inside_root_is_allowed(tree: dict[str, Path]) -> None:
    (tree["root"] / "alias.md").symlink_to(tree["root"] / "docs" / "a.md")
    grants = RootGrants.from_paths([tree["root"]])
    root_id = grants.describe()[0]["id"]
    assert grants.resolve(root_id, "alias.md") == (tree["root"] / "docs" / "a.md").resolve()


def test_unknown_root_id_is_denied(tree: dict[str, Path]) -> None:
    grants = RootGrants.from_paths([tree["root"]])
    with pytest.raises(GrantDenied):
        grants.resolve("not-a-root", "docs/a.md")


def test_indexed_metadata_path_outside_roots_is_denied(tree: dict[str, Path]) -> None:
    """A source path read from indexed metadata never grants access."""
    grants = RootGrants.from_paths([tree["root"]])
    metadata_path = str(tree["outside"] / "secret.txt")
    with pytest.raises(GrantDenied):
        grants.check(metadata_path)
    with pytest.raises(GrantDenied):
        grants.check("relative/from/metadata.md")
    assert grants.check(str(tree["root"] / "docs" / "a.md")).name == "a.md"


def test_root_prefix_sibling_is_not_inside(tmp_path: Path) -> None:
    """``/x/root2`` is not inside ``/x/root`` despite the shared prefix."""
    root = tmp_path / "root"
    sibling = tmp_path / "root2"
    root.mkdir()
    sibling.mkdir()
    (sibling / "f.md").write_text("x", encoding="utf-8")
    grants = RootGrants.from_paths([root])
    with pytest.raises(GrantDenied):
        grants.check(sibling / "f.md")


def test_roots_must_exist_and_be_directories(tmp_path: Path) -> None:
    file_root = tmp_path / "file.txt"
    file_root.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        RootGrants.from_paths([tmp_path / "missing"])
    with pytest.raises(ValueError):
        RootGrants.from_paths([file_root])


def test_root_ids_are_stable_and_hide_nothing_extra(tree: dict[str, Path]) -> None:
    one = RootGrants.from_paths([tree["root"]]).describe()
    two = RootGrants.from_paths([tree["root"]]).describe()
    assert one == two
    assert one[0]["path"] == str(tree["root"].resolve())


# ── Upload store ─────────────────────────────────────────────────────────


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


def _store(tmp_path: Path, limit: int = DEFAULT_MAX_UPLOAD_BYTES) -> UploadStore:
    return UploadStore(tmp_path / "ws" / "uploads", max_bytes=limit)


def _no_files_left(store: UploadStore) -> bool:
    return [p for p in store.directory.rglob("*") if p.is_file()] == []


def test_default_limit_is_50_mib() -> None:
    assert DEFAULT_MAX_UPLOAD_BYTES == 50 * 1024 * 1024


def test_upload_is_stored_privately(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record = asyncio.run(
        store.receive("note.md", _chunks(b"# hi", b"\n"), 5, DEFAULT_INGEST_EXTENSIONS)
    )
    path = store.path_for(record["id"])
    assert path.read_bytes() == b"# hi\n"
    assert record["size"] == 5
    assert record["name"] == "note.md"
    assert len(record["sha256"]) == 64
    assert oct(path.stat().st_mode & 0o777) == oct(0o600)
    assert oct(store.directory.stat().st_mode & 0o777) == oct(0o700)
    assert not list((store.directory / ".partial").iterdir())


@pytest.mark.parametrize(
    "name",
    [
        "archive.zip",
        "bundle.tar.gz",
        "program.exe",
        "../escape.md",
        "dir/a.md",
        "dir\\a.md",
        "https://example.com/a.md",
        "",
        ".md",
        "a\x00.md",
    ],
)
def test_preflight_rejects_unsupported_names(tmp_path: Path, name: str) -> None:
    store = _store(tmp_path)
    with pytest.raises(UploadRejected):
        store.preflight(name, 10, DEFAULT_INGEST_EXTENSIONS)


def test_preflight_uses_the_supplied_extension_set(tmp_path: Path) -> None:
    """The allowed set comes from settings; the store has no list of its own."""
    store = _store(tmp_path)
    with pytest.raises(UploadRejected):
        store.preflight("main.py", 10, DEFAULT_INGEST_EXTENSIONS)
    store.preflight("main.py", 10, (*DEFAULT_INGEST_EXTENSIONS, ".py"))


def test_preflight_rejects_declared_size_over_limit(tmp_path: Path) -> None:
    store = _store(tmp_path, limit=10)
    with pytest.raises(UploadRejected) as info:
        store.preflight("a.md", 11, DEFAULT_INGEST_EXTENSIONS)
    assert info.value.status_code == 413


def test_stream_over_limit_is_removed(tmp_path: Path) -> None:
    """A body larger than its declared size still stops at the limit."""
    store = _store(tmp_path, limit=10)
    with pytest.raises(UploadRejected) as info:
        asyncio.run(
            store.receive("a.md", _chunks(b"12345", b"67890", b"X"), 3, DEFAULT_INGEST_EXTENSIONS)
        )
    assert info.value.status_code == 413
    assert _no_files_left(store)


def test_failed_stream_is_removed(tmp_path: Path) -> None:
    store = _store(tmp_path)

    async def broken() -> AsyncIterator[bytes]:
        yield b"partial"
        raise ConnectionResetError("client went away")

    with pytest.raises(ConnectionResetError):
        asyncio.run(store.receive("a.md", broken(), None, DEFAULT_INGEST_EXTENSIONS))
    assert _no_files_left(store)


def test_cancelled_stream_is_removed(tmp_path: Path) -> None:
    store = _store(tmp_path)

    async def slow() -> AsyncIterator[bytes]:
        yield b"partial"
        await asyncio.sleep(10)
        yield b"never"

    async def scenario() -> None:
        task = asyncio.create_task(store.receive("a.md", slow(), None, DEFAULT_INGEST_EXTENSIONS))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert _no_files_left(store)


def test_stale_partials_are_purged(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.prepare()
    stale = store.directory / ".partial" / "old.part"
    stale.write_bytes(b"x")
    store.purge_partials()
    assert not stale.exists()


def test_unknown_upload_id_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for bad in ("../../etc", "nope", ""):
        with pytest.raises(UploadRejected):
            store.path_for(bad)


# ── HTTP routes ──────────────────────────────────────────────────────────


class FakeEngine:
    def close(self) -> None:
        return None


def _app(tmp_path: Path, roots: tuple[Path, ...] = (), limit: int = 64) -> tuple[Any, Any]:
    config = WebConfig(
        workspace=tmp_path / "ws",
        host="127.0.0.1",
        port=8765,
        roots=roots,
        static_dir=None,
        max_upload_bytes=limit,
    )
    policy = AccessPolicy.for_launch("127.0.0.1", 8765)
    return create_app(config, policy=policy, engine_factory=FakeEngine), policy


def _login(client: TestClient, policy: AccessPolicy) -> None:
    assert (
        client.post(
            "/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers=ORIGIN
        ).status_code
        == 200
    )


def test_upload_route_stores_supported_file(tmp_path: Path) -> None:
    app, policy = _app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        _login(client, policy)
        response = client.post(
            "/v1/uploads",
            content=b"# title\n",
            headers={**ORIGIN, "X-Upload-Name": "title.md"},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["upload"]["name"] == "title.md"
    assert str(tmp_path) not in response.text  # server paths are not disclosed


def test_upload_route_rejects_oversize_without_residue(tmp_path: Path) -> None:
    app, policy = _app(tmp_path, limit=8)
    with TestClient(app, base_url=BASE) as client:
        _login(client, policy)
        response = client.post(
            "/v1/uploads", content=b"x" * 100, headers={**ORIGIN, "X-Upload-Name": "big.md"}
        )
    assert response.status_code == 413
    assert response.json()["status"] == "error"
    uploads = tmp_path / "ws" / "uploads"
    assert [p for p in uploads.rglob("*") if p.is_file()] == []


def test_upload_route_rejects_archives_and_url_names(tmp_path: Path) -> None:
    app, policy = _app(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        _login(client, policy)
        archive = client.post(
            "/v1/uploads", content=b"PK", headers={**ORIGIN, "X-Upload-Name": "a.zip"}
        )
        url = client.post(
            "/v1/uploads",
            content=b"x",
            headers={**ORIGIN, "X-Upload-Name": "http://example.com/a.md"},
        )
        missing = client.post("/v1/uploads", content=b"x", headers=ORIGIN)
    assert archive.status_code == 415
    assert url.status_code == 400
    assert missing.status_code == 400


def test_upload_preflight_route(tmp_path: Path) -> None:
    app, policy = _app(tmp_path, limit=8)
    with TestClient(app, base_url=BASE) as client:
        _login(client, policy)
        ok = client.post("/v1/uploads/preflight", json={"name": "a.md", "size": 8}, headers=ORIGIN)
        big = client.post("/v1/uploads/preflight", json={"name": "a.md", "size": 9}, headers=ORIGIN)
    assert ok.status_code == 200
    assert ok.json()["max_bytes"] == 8
    assert big.status_code == 413


def test_upload_requires_session_not_bearer(tmp_path: Path) -> None:
    app, policy = _app(tmp_path)
    token = policy.issue_bearer({"graph", "read", "run"}).token
    with TestClient(app, base_url=BASE) as client:
        response = client.post(
            "/v1/uploads",
            content=b"x",
            headers={"Authorization": f"Bearer {token}", "X-Upload-Name": "a.md"},
        )
    assert response.status_code == 403


def test_roots_route_lists_operator_roots_and_managed_uploads(tmp_path: Path) -> None:
    root = tmp_path / "approved"
    root.mkdir()
    app, policy = _app(tmp_path, roots=(root,))
    with TestClient(app, base_url=BASE) as client:
        _login(client, policy)
        response = client.get("/v1/roots")
    roots = response.json()["roots"]
    kinds = sorted(r["kind"] for r in roots)
    assert kinds == ["managed", "operator"]
    assert any(r["path"] == str(root.resolve()) for r in roots)


def test_startup_purges_stale_partials(tmp_path: Path) -> None:
    partial = tmp_path / "ws" / "uploads" / ".partial"
    partial.mkdir(parents=True)
    (partial / "crash.part").write_bytes(b"x")
    app, _ = _app(tmp_path)
    with TestClient(app, base_url=BASE):
        assert not (partial / "crash.part").exists()


def test_workspace_directory_is_private(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    with TestClient(app, base_url=BASE):
        mode = os.stat(tmp_path / "ws").st_mode & 0o777
    assert mode == 0o700
