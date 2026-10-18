"""Tests for the OS keychain adapter (design D1; tasks 4.3 to 4.6).

Every test installs an in-memory backend through ``keyring.set_keyring``, so
no test reads or writes a real keychain on any operating system.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

keyring = pytest.importorskip("keyring")

from keyring.backend import KeyringBackend  # noqa: E402
from keyring.backends import fail, null  # noqa: E402
from keyring.backends.chainer import ChainerBackend  # noqa: E402
from keyring.errors import KeyringError  # noqa: E402

from omrg.integrations import keychain  # noqa: E402
from omrg.integrations.keychain import (  # noqa: E402
    SERVICE,
    KeychainStore,
    KeychainUnavailableError,
    Secret,
)

KEY = "sk-or-v1-0123456789abcdef-SECRET"  # gitleaks:allow


class MemoryBackend(KeyringBackend):
    """An in-memory keyring of priority 5."""

    priority = 5  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.data: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.data.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.data[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.data.pop((service, username), None)


@pytest.fixture
def backend() -> Iterator[MemoryBackend]:
    previous = keyring.get_keyring()
    fake = MemoryBackend()
    keyring.set_keyring(fake)
    yield fake
    keyring.set_keyring(previous)


@pytest.fixture
def store() -> KeychainStore:
    return KeychainStore(timeout=2.0)


# ── Save, read, delete ───────────────────────────────────────────────────


def test_save_read_delete_use_service_omrg_and_provider_as_user(
    backend: MemoryBackend, store: KeychainStore
) -> None:
    assert store.available
    store.save("openrouter", KEY)
    assert backend.data == {("omrg", "openrouter"): KEY}
    assert SERVICE == "omrg"
    value = store.read("openrouter")
    assert isinstance(value, Secret) and value.reveal() == KEY
    store.delete("openrouter")
    assert backend.data == {}
    assert store.read("openrouter") is None


def test_state_names_the_missing_entry(backend: MemoryBackend, store: KeychainStore) -> None:
    assert store.state("openrouter", saved=False) == "unset"
    assert store.state("openrouter", saved=True) == "keychain-missing"
    store.save("openrouter", KEY)
    assert store.state("openrouter", saved=True) == "ok"


def test_an_unreadable_entry_reports_keychain_unreadable(
    backend: MemoryBackend, store: KeychainStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(service: str, username: str) -> str:
        raise KeyringError("denied")

    monkeypatch.setattr(backend, "get_password", boom)
    assert store.state("openrouter", saved=True) == "keychain-unreadable"


def test_a_slow_keychain_call_times_out(
    backend: MemoryBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    def slow(service: str, username: str) -> str:
        time.sleep(1.0)
        return KEY

    monkeypatch.setattr(backend, "get_password", slow)
    quick = KeychainStore(timeout=0.05)
    started = time.monotonic()
    assert quick.state("openrouter", saved=True) == "keychain-unreadable"
    assert time.monotonic() - started < 0.8


def test_repr_of_the_store_and_the_secret_hides_the_key(
    backend: MemoryBackend, store: KeychainStore
) -> None:
    store.save("openrouter", KEY)
    secret = store.read("openrouter")
    assert secret is not None
    store.load(["openrouter"])
    for shown in (repr(store), str(store), repr(secret), str(secret), f"{secret}", f"{store!r}"):
        assert KEY not in shown
        assert "SECRET" not in shown


# ── No keychain ──────────────────────────────────────────────────────────


class LowPriority(MemoryBackend):
    priority = 0.5  # type: ignore[assignment]


class PlaintextFile(MemoryBackend):
    """Pretends to be a keyrings.alt plaintext file backend."""


PlaintextFile.__module__ = "keyrings.alt.file"


class _EmptyChainer(ChainerBackend):
    backends = ()  # type: ignore[assignment]


def _empty_chainer() -> KeyringBackend:
    return _EmptyChainer()


@pytest.fixture(
    params=["fail", "null", "empty-chainer", "low-priority", "keyrings-alt"],
)
def dead_backend(request: pytest.FixtureRequest) -> Iterator[KeyringBackend]:
    previous = keyring.get_keyring()
    makers = {
        "fail": fail.Keyring,
        "null": null.Keyring,
        "empty-chainer": _empty_chainer,
        "low-priority": LowPriority,
        "keyrings-alt": PlaintextFile,
    }
    fake = makers[request.param]()
    keyring.set_keyring(fake)
    yield fake
    keyring.set_keyring(previous)


def test_an_unusable_backend_reports_unavailable_and_saves_nothing(
    dead_backend: KeyringBackend,
) -> None:
    store = KeychainStore(timeout=2.0)
    assert store.available is False
    with pytest.raises(KeychainUnavailableError) as raised:
        store.save("openrouter", KEY)
    assert KEY not in str(raised.value)
    data = getattr(dead_backend, "data", None)
    if data is not None:
        assert data == {}
    assert store.read("openrouter") is None


def test_a_forced_plaintext_backend_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``PYTHON_KEYRING_BACKEND`` can force a backend; it is still refused."""
    previous = keyring.get_keyring()
    fake = PlaintextFile()
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyrings.alt.file.PlaintextKeyring")
    keyring.set_keyring(fake)
    try:
        store = KeychainStore(timeout=2.0)
        assert store.available is False
        with pytest.raises(KeychainUnavailableError):
            store.save("openrouter", KEY)
        assert fake.data == {}
    finally:
        keyring.set_keyring(previous)


def test_a_module_under_keyrings_alt_counts_as_plaintext() -> None:
    assert keychain.is_usable_backend(MemoryBackend()) is True
    assert keychain.is_usable_backend(PlaintextFile()) is False
    assert keychain.is_usable_backend(LowPriority()) is False


def test_importing_the_module_does_not_import_keyring() -> None:
    import subprocess

    code = "import sys, omrg.integrations.keychain;sys.exit(1 if 'keyring' in sys.modules else 0)"
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0


# ── No plaintext copy of a saved key (task 4.6) ──────────────────────────


def test_a_saved_key_is_in_no_row_file_or_env(
    backend: MemoryBackend, store: KeychainStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository
    from omrg.integrations.workspace_sqlite.settings import WorkspaceSettings

    work = tmp_path / "cwd"
    work.mkdir()
    (work / ".env").write_text("OTHER=1\n", encoding="utf-8")
    monkeypatch.chdir(work)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    db = workspace / "workspace.db"
    SqliteWorkspaceRepository(db)
    (workspace / "note.txt").write_text("hello", encoding="utf-8")

    store.save("openrouter", KEY)
    settings = WorkspaceSettings(db)
    settings.set("provider.openrouter.key_saved_at", "2026-10-18T10:00:00+00:00")
    assert backend.data[("omrg", "openrouter")] == KEY

    needle = KEY.encode()
    conn = sqlite3.connect(db)
    try:
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
            for row in conn.execute(f'SELECT * FROM "{table}"'):  # noqa: S608
                assert needle not in repr(row).encode()
    finally:
        conn.close()
    for base in (workspace, work):
        for path in base.rglob("*"):
            if path.is_file():
                assert needle not in path.read_bytes(), path


def test_the_scan_catches_a_plaintext_copy(tmp_path: Path) -> None:
    """The scan fails when a key is written to a file, so it tests something."""
    (tmp_path / ".env").write_text(f"OPENROUTER_API_KEY={KEY}\n", encoding="utf-8")
    hits = [p for p in tmp_path.rglob("*") if p.is_file() and KEY.encode() in p.read_bytes()]
    assert hits
