"""Metadata-only capability probe tests for the OCR worker (task 2.6).

The probe runs the worker's ``--capabilities`` command with a short
timeout, parses its fingerprint JSON, and returns a frozen
``OcrWorkerFingerprint``. Every unavailability mode — missing command,
failed spawn, non-zero exit, malformed output, wrong protocol version,
incompatible output schema, probe timeout — MUST return the ONE stable
unavailable fingerprint, and the probe must never leave a process
running (design D2.4).
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from omrg.capabilities import (
    UNAVAILABLE_OCR_WORKER_FINGERPRINT,
    probe_ocr_worker,
    reset_ocr_fingerprint_cache,
)
from omrg.integrations.ocr_worker.fingerprint import OcrWorkerFingerprint

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_WORKER = REPO_ROOT / "tests" / "fixtures" / "ocr_worker" / "stub_worker.py"

PROBE_TIMEOUT = 10.0


def _stub_command(*extra: str) -> list[str]:
    """Build the stub worker launch command."""
    return [sys.executable, str(STUB_WORKER), *extra]


@pytest.fixture(autouse=True)
def _fresh_fingerprint_cache() -> Iterator[None]:
    """Every test probes with a cold cache; nothing leaks between tests."""
    reset_ocr_fingerprint_cache()
    yield
    reset_ocr_fingerprint_cache()


# ── The available fingerprint ──────────────────────────────────────────────


def test_probe_returns_the_full_fingerprint_from_the_stub() -> None:
    """A healthy capabilities command yields every required identity field."""
    fingerprint = probe_ocr_worker(_stub_command(), timeout=PROBE_TIMEOUT)
    assert isinstance(fingerprint, OcrWorkerFingerprint)
    assert fingerprint.available is True
    assert fingerprint.protocol_version == "1.0"
    assert dict(fingerprint.packages) == {"stub-worker": "1.0"}
    assert fingerprint.pipeline_identity == "stub-pipeline"
    assert fingerprint.pipeline_revision == "1"
    assert fingerprint.model_identity == "stub-model"
    assert fingerprint.model_revision == "1"
    assert fingerprint.output_schema_id == "omrg.ocr.parse_output"
    assert fingerprint.output_schema_version == "1"


def test_probe_result_is_frozen_and_hashable() -> None:
    """The fingerprint is an immutable value object (identity payload, D8)."""
    fingerprint = probe_ocr_worker(_stub_command(), timeout=PROBE_TIMEOUT)
    with pytest.raises(Exception):  # noqa: B017 - frozen dataclass contract
        fingerprint.available = False  # type: ignore[misc]
    assert hash(fingerprint) == hash(probe_ocr_worker(_stub_command(), timeout=PROBE_TIMEOUT))


def test_probe_is_memoised_per_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """The composition boundary resolves the probe once, not per file.

    After the first probe, even a broken process launcher returns the
    cached fingerprint for the same command.
    """
    first = probe_ocr_worker(_stub_command(), timeout=PROBE_TIMEOUT)
    assert first.available is True

    def _exploding_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("probe re-ran the capabilities command")

    import omrg.capabilities as capabilities_module

    monkeypatch.setattr(capabilities_module.subprocess, "run", _exploding_run)
    second = probe_ocr_worker(_stub_command(), timeout=PROBE_TIMEOUT)
    assert second is first


# ── Every unavailability mode returns the ONE stable fingerprint ──────────


@pytest.mark.parametrize(
    ("label", "command"),
    [
        ("missing-command", []),
        ("failed-spawn", ["/definitely/not/an/executable-omrg-test"]),
        (
            "non-zero-exit",
            _stub_command("--capabilities", "fail"),
        ),
        (
            "malformed-output",
            _stub_command("--capabilities", "bad-json"),
        ),
        (
            "wrong-protocol",
            _stub_command("--capabilities", "wrong-protocol"),
        ),
        (
            "wrong-schema",
            _stub_command("--capabilities", "wrong-schema"),
        ),
    ],
)
def test_unavailability_modes_return_one_stable_fingerprint(label: str, command: list[str]) -> None:
    """Missing, unusable, malformed, or incompatible → the same constant."""
    fingerprint = probe_ocr_worker(command, timeout=PROBE_TIMEOUT)
    assert fingerprint is UNAVAILABLE_OCR_WORKER_FINGERPRINT
    assert fingerprint.available is False


def test_probe_timeout_returns_the_stable_fingerprint() -> None:
    """A capabilities command that never answers is unavailable, promptly."""
    fingerprint = probe_ocr_worker(_stub_command("--capabilities", "hang"), timeout=1.0)
    assert fingerprint is UNAVAILABLE_OCR_WORKER_FINGERPRINT


# ── The probe leaves no process behind ─────────────────────────────────────


def test_capabilities_command_is_one_shot() -> None:
    """The stub capabilities mode prints its payload and exits by itself."""
    completed = subprocess.run(
        _stub_command("--capabilities"),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() != ""


def test_real_worker_capabilities_command_is_one_shot() -> None:
    """``python -m omrg_ocr_worker --capabilities`` prints and exits.

    Runs against the real worker package from ocr-worker/src in the
    MAIN environment: the capabilities module must be importable and
    one-shot without Paddle (the import boundary test pins the rest).
    """
    worker_src = REPO_ROOT / "ocr-worker" / "src"
    completed = subprocess.run(
        [sys.executable, "-m", "omrg_ocr_worker", "--capabilities"],
        cwd=worker_src,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() != ""


def test_real_worker_fingerprint_via_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """The probe accepts the real worker's capabilities payload."""
    worker_src = REPO_ROOT / "ocr-worker" / "src"
    monkeypatch.setenv("PYTHONPATH", str(worker_src))
    fingerprint = probe_ocr_worker([sys.executable, "-m", "omrg_ocr_worker"], timeout=PROBE_TIMEOUT)
    assert fingerprint.available is True
    assert fingerprint.protocol_version == "1.0"
    assert "omrg-ocr-worker" in dict(fingerprint.packages)
