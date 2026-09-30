"""Tests for the primary and fallback OCR routes (tasks 4.1 to 4.4).

Covers the six route settings, command resolution, the explicit-command
override of the primary route, the shared client for an identical
fallback, ``OcrRoutes.select()``, the page-scaled request timeout and
the composition wiring. Engines are fake folders with an executable
``.venv/bin/python`` that runs the stub worker; nothing real starts.
"""

from __future__ import annotations

import logging
import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from omrg.capabilities import build_ocr_routes, probe_ocr_worker, reset_ocr_fingerprint_cache
from omrg.config import Settings
from omrg.integrations.ocr_worker.fingerprint import UNAVAILABLE_OCR_WORKER_FINGERPRINT
from omrg.integrations.ocr_worker.routes import (
    WORKER_CORE_MODULE,
    OcrRoutes,
    RouteCommand,
    backend_id_of,
    build_route_clients,
    request_timeout,
    reset_route_log,
    resolve_engine_command,
    resolve_route_command,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_WORKER = REPO_ROOT / "tests" / "fixtures" / "ocr_worker" / "stub_worker.py"


@pytest.fixture(autouse=True)
def _fresh_caches() -> Iterator[None]:
    reset_ocr_fingerprint_cache()
    reset_route_log()
    yield
    reset_ocr_fingerprint_cache()
    reset_route_log()


def make_engine(workers_dir: Path, name: str, backend_id: str) -> Path:
    """Create a fake provisioned engine whose python runs the stub worker.

    The fake interpreter ignores ``-m omrg_ocr_worker_core`` and runs the
    stub with the given backend id, so the probe and a parse both work.
    """
    engine_dir = workers_dir / "engines" / name
    bin_dir = engine_dir / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text(
        "#!/bin/sh\n"
        'shift 2  # drop "-m omrg_ocr_worker_core"\n'
        f'exec "{sys.executable}" "{STUB_WORKER}" --backend-id {backend_id} "$@"\n',
        encoding="utf-8",
    )
    python.chmod(python.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return engine_dir


def settings_for(effective_settings: Any, **overrides: Any) -> Any:
    """EffectiveSettings with OCR enabled and the given route overrides."""
    overrides.setdefault("ocr_fallback_enabled", True)
    return effective_settings(**overrides)


# ── Settings (task 4.1) ────────────────────────────────────────────────────


def test_route_setting_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defaults: dots-mocr primary, paddleocr-vl fallback, maths on at 0.10."""
    for name in (
        "OCR_WORKERS_DIR",
        "OCR_ENGINE_PRIMARY",
        "OCR_ENGINE_FALLBACK",
        "OCR_MATHS_ROUTING_ENABLED",
        "OCR_MATHS_PAGE_FRACTION",
        "OCR_WORKER_SECONDS_PER_PAGE",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.ocr_workers_dir == ""
    assert settings.ocr_engine_primary == "dots-mocr"
    assert settings.ocr_engine_fallback == "paddleocr-vl"
    assert settings.ocr_maths_routing_enabled is True
    assert settings.ocr_maths_page_fraction == 0.10
    assert settings.ocr_worker_seconds_per_page == 120.0


def test_route_settings_parse_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flat env names parse; a blank fallback means no fallback."""
    monkeypatch.setenv("OCR_WORKERS_DIR", " /opt/ocr-workers ")
    monkeypatch.setenv("OCR_ENGINE_PRIMARY", "paddleocr-vl")
    monkeypatch.setenv("OCR_ENGINE_FALLBACK", " ")
    monkeypatch.setenv("OCR_MATHS_ROUTING_ENABLED", "false")
    monkeypatch.setenv("OCR_MATHS_PAGE_FRACTION", "0.25")
    monkeypatch.setenv("OCR_WORKER_SECONDS_PER_PAGE", "90")
    settings = Settings(_env_file=None)
    assert settings.ocr_workers_dir == "/opt/ocr-workers"
    assert settings.ocr_engine_primary == "paddleocr-vl"
    assert settings.ocr_engine_fallback == ""
    assert settings.ocr_maths_routing_enabled is False
    assert settings.ocr_maths_page_fraction == 0.25
    assert settings.ocr_worker_seconds_per_page == 90.0


@pytest.mark.parametrize("value", ["-0.01", "1.01"])
def test_maths_page_fraction_bounds(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """``OCR_MATHS_PAGE_FRACTION`` must lie in 0.0 to 1.0."""
    monkeypatch.setenv("OCR_MATHS_PAGE_FRACTION", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["0.0", "1.0"])
def test_maths_page_fraction_accepts_the_ends(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Both ends of the range are valid; 0.0 is the disabled sentinel."""
    monkeypatch.setenv("OCR_MATHS_PAGE_FRACTION", value)
    assert Settings(_env_file=None).ocr_maths_page_fraction == float(value)


def test_effective_settings_carry_the_route_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """The composition root copies the six fields into EffectiveSettings."""
    from omrg.compose_settings import settings_to_effective

    monkeypatch.setenv("OCR_ENGINE_FALLBACK", "")
    monkeypatch.setenv("OCR_MATHS_PAGE_FRACTION", "0.3")
    effective = settings_to_effective(Settings(_env_file=None))
    assert effective.ocr_engine_primary == "dots-mocr"
    assert effective.ocr_engine_fallback == ""
    assert effective.ocr_maths_page_fraction == 0.3
    assert effective.ocr_worker_seconds_per_page == 120.0


# ── Command resolution (task 4.2) ──────────────────────────────────────────


def test_engine_command_comes_from_the_workers_dir(tmp_path: Path) -> None:
    """``<dir>/engines/<name>/.venv/bin/python -m omrg_ocr_worker_core``, cwd the folder."""
    engine_dir = make_engine(tmp_path, "any-engine", "any_engine")
    route = resolve_engine_command("any-engine", str(tmp_path))
    assert route == RouteCommand(
        command=(str(engine_dir / ".venv" / "bin" / "python"), "-m", WORKER_CORE_MODULE),
        cwd=str(engine_dir),
    )


@pytest.mark.parametrize(
    ("engine", "workers_dir"),
    [
        ("", "WORKERS"),
        ("dots-mocr", ""),
        ("not-provisioned", "WORKERS"),
        ("../escape", "WORKERS"),
        ("..", "WORKERS"),
    ],
)
def test_unresolvable_engine_has_no_command(tmp_path: Path, engine: str, workers_dir: str) -> None:
    """Empty, unprovisioned or path-like names resolve to no command."""
    (tmp_path / "engines" / "not-provisioned").mkdir(parents=True)
    root = str(tmp_path) if workers_dir == "WORKERS" else workers_dir
    assert resolve_engine_command(engine, root).command == ()


def test_explicit_command_overrides_the_primary_route_only(
    effective_settings: Any, tmp_path: Path
) -> None:
    """Spec: "The explicit command overrides the primary route".

    The fallback route still resolves from the workers directory.
    """
    make_engine(tmp_path, "paddleocr-vl", "paddleocr_vl")
    settings = settings_for(
        effective_settings,
        ocr_worker_command="/opt/legacy/python -m omrg_ocr_worker",
        ocr_worker_env_dir=" /opt/legacy ",
        ocr_workers_dir=str(tmp_path),
    )
    primary = resolve_route_command("dots-mocr", settings, primary=True)
    fallback = resolve_route_command("paddleocr-vl", settings, primary=False)
    assert primary == RouteCommand(
        command=("/opt/legacy/python", "-m", "omrg_ocr_worker"), cwd="/opt/legacy"
    )
    assert fallback.command[0] == str(
        tmp_path / "engines" / "paddleocr-vl" / ".venv" / "bin" / "python"
    )


def test_explicit_command_without_env_dir_has_no_cwd(effective_settings: Any) -> None:
    """``OCR_WORKER_ENV_DIR`` stays optional with an explicit command."""
    settings = settings_for(effective_settings, ocr_worker_command="worker --flag")
    assert resolve_route_command("x", settings, primary=True) == RouteCommand(
        command=("worker", "--flag"), cwd=None
    )


# ── Route clients and selection (tasks 4.2, 4.4) ───────────────────────────


def test_missing_primary_hands_the_request_to_the_fallback(
    effective_settings: Any, tmp_path: Path
) -> None:
    """Spec: "A missing primary engine hands the request to the fallback"."""
    make_engine(tmp_path, "paddleocr-vl", "paddleocr_vl")
    settings = settings_for(effective_settings, ocr_workers_dir=str(tmp_path))
    routes = build_route_clients(settings, probe=probe_ocr_worker)
    try:
        assert routes.fingerprint.available is False  # dots-mocr not provisioned
        assert routes.fallback_fingerprint.available is True
        assert routes.select() is routes.fallback
        assert backend_id_of(routes.select()) == "paddleocr_vl"
    finally:
        routes.close()


def test_fallback_does_not_start_while_the_primary_serves(
    effective_settings: Any, tmp_path: Path, small_pdf: Path
) -> None:
    """Spec: "The fallback does not start while the primary serves"."""
    make_engine(tmp_path, "dots-mocr", "dots_mocr")
    make_engine(tmp_path, "paddleocr-vl", "paddleocr_vl")
    settings = settings_for(effective_settings, ocr_workers_dir=str(tmp_path))
    routes = build_route_clients(settings, probe=probe_ocr_worker)
    try:
        assert not routes.primary.is_started and not routes.fallback.is_started
        for _ in range(2):
            client = routes.select()
            assert client is routes.primary
            client.parse(str(small_pdf))
        assert routes.primary.is_started
        assert routes.primary.process_generations == 1
        assert not routes.fallback.is_started
        assert routes.fallback.process_generations == 0
        assert backend_id_of(routes.primary) == "dots_mocr"
    finally:
        routes.close()


def test_unknown_engine_name_degrades(effective_settings: Any, tmp_path: Path) -> None:
    """Spec: "An unknown engine name degrades" to the unavailable fingerprint."""
    settings = settings_for(
        effective_settings,
        ocr_workers_dir=str(tmp_path),
        ocr_engine_primary="no-such-engine",
        ocr_engine_fallback="also-missing",
    )
    routes = build_route_clients(settings, probe=probe_ocr_worker)
    assert routes.fingerprint is UNAVAILABLE_OCR_WORKER_FINGERPRINT
    assert routes.fallback_fingerprint is UNAVAILABLE_OCR_WORKER_FINGERPRINT
    assert routes.select() is None


def test_identical_fallback_shares_the_primary_client(
    effective_settings: Any, tmp_path: Path
) -> None:
    """A fallback naming the primary's engine shares one client (one process)."""
    make_engine(tmp_path, "paddleocr-vl", "paddleocr_vl")
    settings = settings_for(
        effective_settings,
        ocr_workers_dir=str(tmp_path),
        ocr_engine_primary="paddleocr-vl",
        ocr_engine_fallback="paddleocr-vl",
    )
    probes: list[list[str]] = []

    def counting_probe(command: list[str]) -> Any:
        probes.append(command)
        return probe_ocr_worker(command)

    routes = build_route_clients(settings, probe=counting_probe)
    assert routes.fallback is routes.primary
    assert len(probes) == 1


def test_empty_fallback_means_no_fallback(effective_settings: Any, tmp_path: Path) -> None:
    """``OCR_ENGINE_FALLBACK=`` builds no fallback client."""
    make_engine(tmp_path, "paddleocr-vl", "paddleocr_vl")
    settings = settings_for(
        effective_settings, ocr_workers_dir=str(tmp_path), ocr_engine_fallback=""
    )
    routes = build_route_clients(settings, probe=probe_ocr_worker)
    assert routes.fallback is None
    assert routes.fallback_fingerprint is UNAVAILABLE_OCR_WORKER_FINGERPRINT
    assert routes.select() is None  # dots-mocr is not provisioned


def test_disabled_ocr_probes_nothing(effective_settings: Any, tmp_path: Path) -> None:
    """With OCR off, no route is probed even when engines exist."""
    make_engine(tmp_path, "dots-mocr", "dots_mocr")

    def forbidden_probe(command: list[str]) -> Any:
        raise AssertionError("probe must not run when OCR is disabled")

    settings = effective_settings(ocr_fallback_enabled=False, ocr_workers_dir=str(tmp_path))
    routes = build_route_clients(settings, probe=forbidden_probe)
    assert routes.select() is None


def test_explicit_command_keeps_working_through_composition(
    effective_settings: Any,
) -> None:
    """``OCR_WORKER_COMMAND`` alone still yields an available primary route."""
    settings = settings_for(
        effective_settings, ocr_worker_command=f"{sys.executable} {STUB_WORKER}"
    )
    routes = build_ocr_routes(settings)
    try:
        assert routes.fingerprint.available is True
        assert routes.select() is routes.primary
        assert routes.fallback_fingerprint.available is False  # no OCR_WORKERS_DIR
    finally:
        routes.close()


def test_start_up_log_names_both_engines_once(
    effective_settings: Any, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The resolved primary and fallback engines are logged once per process."""
    make_engine(tmp_path, "paddleocr-vl", "paddleocr_vl")
    settings = settings_for(effective_settings, ocr_workers_dir=str(tmp_path))
    with caplog.at_level(logging.INFO, logger="omrg.integrations.ocr_worker.routes"):
        build_route_clients(settings, probe=probe_ocr_worker)
        build_route_clients(settings, probe=probe_ocr_worker)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("OCR routes:")]
    assert lines == [
        "OCR routes: primary=dots-mocr [unavailable], fallback=paddleocr-vl [available]"
    ]


def test_routes_close_each_distinct_client_once() -> None:
    """Closing routes closes the primary and a distinct fallback once each."""

    class _Client:
        def __init__(self) -> None:
            self.closed = 0

        def close(self) -> None:
            self.closed += 1

    shared = _Client()
    OcrRoutes(primary=shared, fallback=shared).close()
    assert shared.closed == 1
    primary, fallback = _Client(), _Client()
    OcrRoutes(primary=primary, fallback=fallback).close()
    assert (primary.closed, fallback.closed) == (1, 1)
    assert OcrRoutes.of(None).select() is None
    routes = OcrRoutes(primary=primary)
    assert OcrRoutes.of(routes) is routes


def test_backend_id_of_a_legacy_worker_is_generic() -> None:
    """A worker that predates backend_id is named ``ocr_worker``, not guessed."""

    class _Legacy:
        fingerprint = UNAVAILABLE_OCR_WORKER_FINGERPRINT

    assert backend_id_of(_Legacy()) == "ocr_worker"
    assert backend_id_of(None) == "ocr_worker"


# ── Timeout scaling (task 4.3) ─────────────────────────────────────────────


def test_a_long_request_gets_a_longer_timeout(effective_settings: Any) -> None:
    """Spec: 300 s floor, 120 s per page, 14 pages → 1,680 s."""
    settings = effective_settings(ocr_worker_request_timeout=300.0)
    assert settings.ocr_worker_seconds_per_page == 120.0
    assert request_timeout(settings, 14) == 1680.0


@pytest.mark.parametrize(("pages", "expected"), [(0, 300.0), (1, 300.0), (2, 300.0), (3, 360.0)])
def test_timeout_never_drops_below_the_floor(
    effective_settings: Any, pages: int, expected: float
) -> None:
    """Short requests keep the per-request timeout."""
    settings = effective_settings(ocr_worker_request_timeout=300.0)
    assert request_timeout(settings, pages) == expected


def test_timeout_reaches_the_client(effective_settings: Any, tmp_path: Path) -> None:
    """The managed client forwards the per-request timeout to the subprocess client."""
    from omrg.integrations.ocr_worker.managed import ManagedOcrClient

    seen: dict[str, Any] = {}

    class _Inner:
        is_started = True

        def parse(self, pdf_path: str, *, pages: Any = None, timeout: Any = None) -> str:
            seen["timeout"] = timeout
            return "ok"

    client = ManagedOcrClient(
        fingerprint=probe_ocr_worker([sys.executable, str(STUB_WORKER)]),
        command=[sys.executable, str(STUB_WORKER)],
    )
    client._client = _Inner()  # type: ignore[assignment]
    assert client.parse("x.pdf", timeout=1680.0) == "ok"
    assert seen["timeout"] == 1680.0


@pytest.fixture
def small_pdf(tmp_path: Path) -> Path:
    """A minimal PDF file for request payloads."""
    pdf = tmp_path / "small.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< >>\n%%EOF\n")
    return pdf


def test_fake_engines_are_executable(tmp_path: Path) -> None:
    """Guard: the fake interpreter is executable on this platform."""
    engine_dir = make_engine(tmp_path, "e", "e")
    assert os.access(engine_dir / ".venv" / "bin" / "python", os.X_OK)


# ── Engine-owned lifecycle with two routes (task 4.4) ──────────────────────


def test_engine_close_stops_both_route_processes(
    effective_settings: Any, tmp_path: Path, small_pdf: Path
) -> None:
    """The engine owns the route pair; close() stops every started route."""
    from unittest.mock import MagicMock

    from omrg.core.vectordb.lancedb import LanceVectorStore
    from omrg.engine import Engine

    make_engine(tmp_path, "dots-mocr", "dots_mocr")
    make_engine(tmp_path, "paddleocr-vl", "paddleocr_vl")
    settings = settings_for(
        effective_settings,
        ocr_workers_dir=str(tmp_path),
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    routes = build_ocr_routes(settings)
    routes.primary.parse(str(small_pdf))
    routes.fallback.parse(str(small_pdf))
    assert routes.primary.is_started and routes.fallback.is_started
    embed_model = MagicMock()
    embed_model.model_name = "test-model"
    engine = Engine(
        settings,
        store=LanceVectorStore(uri=str(tmp_path / "lancedb")),
        embed_model=embed_model,
        ocr_client=routes,
    )
    engine.close()
    assert not routes.primary.is_started and not routes.fallback.is_started
    with pytest.raises(RuntimeError, match="closed"):
        routes.fallback.parse(str(small_pdf))


def test_operation_owned_routes_close_after_ingest(
    effective_settings: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without an injected client, ingestion builds its own routes and closes them."""
    import asyncio

    from omrg.core.ingestion.pipeline import ingest_path_async

    closed: list[bool] = []
    real_build = build_ocr_routes

    def recording_build(settings: Any) -> OcrRoutes:
        routes = real_build(settings)
        original = routes.close

        def close() -> None:
            closed.append(True)
            original()

        object.__setattr__(routes, "close", close)
        return routes

    monkeypatch.setattr("omrg.capabilities.build_ocr_routes", recording_build)
    source = tmp_path / "note.txt"
    source.write_text("plain text", encoding="utf-8")
    settings = effective_settings(
        ocr_fallback_enabled=True,
        **{"metadata.extraction_mode": "disabled"},
    )
    asyncio.run(ingest_path_async(str(source), effective_settings=settings, collection_name="ops"))
    assert closed == [True]


@pytest.mark.parametrize(("backend_id", "expected"), [(7, None), ("dots_mocr", "dots_mocr")])
def test_fingerprint_backend_id_must_be_a_string(backend_id: Any, expected: Any) -> None:
    """A non-string ``backend_id`` makes the payload invalid; a string is kept."""
    from omrg.integrations.ocr_worker.fingerprint import fingerprint_from_payload

    payload = {
        "protocol_version": "1.1",
        "backend_id": backend_id,
        "packages": {},
        "pipeline": {"identity": "p", "revision": "1"},
        "model": {"identity": "m", "revision": "1"},
        "output_schema": {"id": "omrg.ocr.parse_output", "version": "1"},
    }
    fingerprint = fingerprint_from_payload(payload)
    assert (fingerprint.backend_id if fingerprint else None) == expected
