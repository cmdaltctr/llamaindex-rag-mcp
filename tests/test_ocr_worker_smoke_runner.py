"""Testable surface of the OCR worker smoke-test runner (task 2.15).

The runner (``ocr-worker/smoke_test.py``) is separate from the main
pytest suite on purpose. These tests cover ONLY its deterministic
surface: argument validation, the supported-Python range rejection,
dry-run plan resolution, and the main-environment Paddle-free
assertion. Nothing here provisions, installs, or runs the worker —
the provisioned path is executed by the operator after approval, which
is why task 2.15 stays unchecked until that run happens.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKER_DIR = REPO_ROOT / "ocr-worker"
CAL_SCANNED = REPO_ROOT / "tests" / "fixtures" / "pdf_baseline" / "calibration" / "cal_scanned.pdf"
CAL_TABLE_TEXT = (
    REPO_ROOT / "tests" / "fixtures" / "pdf_baseline" / "calibration" / "cal_table_text.pdf"
)


def _load_smoke_module() -> Any:
    """Load ``smoke_test.py`` by path with ``provision`` importable."""
    sys.path.insert(0, str(WORKER_DIR))
    try:
        spec = importlib.util.spec_from_file_location(
            "omrg_ocr_smoke_test", WORKER_DIR / "smoke_test.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["omrg_ocr_smoke_test"] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(WORKER_DIR))
    return module


smoke = _load_smoke_module()


# ── Argument validation ────────────────────────────────────────────────────


@pytest.mark.parametrize("requested", ["3.9", "3.10", "3.14", "4.0"])
def test_unsupported_python_is_rejected_naming_the_range(requested: str) -> None:
    """Versions outside >=3.11,<3.14 fail with the supported range named."""
    with pytest.raises(smoke.provision.UnsupportedPythonError) as excinfo:
        smoke.build_plan(requested, CAL_SCANNED, provision_requested=False)
    message = str(excinfo.value)
    assert ">=3.11,<3.14" in message
    assert "3.11, 3.12, or 3.13" in message


@pytest.mark.parametrize("requested", ["3.11", "3.12", "3.13"])
def test_supported_python_versions_build_plans(requested: str) -> None:
    """Every version in the worker manifest's range resolves a plan."""
    plan = smoke.build_plan(requested, CAL_SCANNED, provision_requested=False)
    assert plan["python_version"] == requested
    assert plan["mode"] == "dry-run"


def test_missing_fixture_is_rejected_with_actionable_error(tmp_path: Path) -> None:
    """A missing fixture fails naming the --fixture escape hatch."""
    with pytest.raises(smoke.SmokeTestError, match="--fixture"):
        smoke.build_plan("3.12", tmp_path / "absent.pdf", provision_requested=False)


# ── Dry-run plan resolution ────────────────────────────────────────────────


def test_dry_run_plan_resolves_every_command() -> None:
    """The plan carries provision, probe, and parse commands plus the fixture.

    Probe and parse must target the WORKER venv interpreter — never the
    main environment — and the fixture must match the supplied
    calibration scanned PDF.
    """
    plan = smoke.build_plan("3.12", CAL_SCANNED, provision_requested=False)
    assert plan["fixture"] == str(CAL_SCANNED)
    assert plan["provision_command"][1:] == [
        str(WORKER_DIR / "provision.py"),
        "--python",
        "3.12",
    ]
    worker_python = str(WORKER_DIR / ".venv" / "bin" / "python")
    assert plan["probe_command"] == [
        worker_python,
        "-m",
        "omrg_ocr_worker",
        "--capabilities",
    ]
    assert plan["parse_command"] == [worker_python, "-m", "omrg_ocr_worker"]


def test_main_dry_run_prints_plan_and_runs_no_subprocess(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--no-provision`` (the default) installs nothing and runs nothing.

    The interpreter check is stubbed read-only and ANY subprocess call
    is wired to fail the test, proving the dry-run path never shells
    out or installs.
    """
    monkeypatch.setattr(smoke, "check_interpreter_available", lambda v: (True, "stub-listing"))

    def _no_subprocess(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("dry-run must not run any subprocess")

    monkeypatch.setattr(smoke.subprocess, "run", _no_subprocess)
    monkeypatch.setattr(smoke.subprocess, "Popen", _no_subprocess)

    exit_code = smoke.main(["--python", "3.12", "--no-provision"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "dry-run mode" in output
    assert "commands that WOULD run" in output
    assert "nothing was installed and no worker ran" in output


def test_main_defaults_to_no_provision(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Omitting the flag keeps the safe dry-run default."""
    monkeypatch.setattr(smoke, "check_interpreter_available", lambda v: (True, "stub-listing"))
    monkeypatch.setattr(smoke.subprocess, "run", lambda *a, **k: None)

    exit_code = smoke.main(["--python", "3.12"])

    assert exit_code == 0
    assert "dry-run mode" in capsys.readouterr().out


def test_bare_provision_uses_structured_markdown_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bare ``--provision`` selects the fixture from successful smoke evidence."""
    captured_plan: dict[str, Any] = {}
    monkeypatch.setattr(smoke, "assert_main_environment_paddle_free", lambda: None)
    monkeypatch.setattr(smoke, "check_interpreter_available", lambda v: (True, "stub-listing"))
    monkeypatch.setattr(
        smoke,
        "_run_provisioned",
        lambda plan: captured_plan.update(plan) or 0,
    )

    assert smoke.main(["--python", "3.12", "--provision"]) == 0
    assert captured_plan["fixture"] == str(CAL_TABLE_TEXT)


def test_main_rejects_unsupported_python_with_exit_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI surfaces the range error on stderr with exit status 2."""
    exit_code = smoke.main(["--python", "3.10"])
    assert exit_code == 2
    assert ">=3.11,<3.14" in capsys.readouterr().err


# ── Main-environment Paddle boundary ──────────────────────────────────────


def test_main_environment_is_paddle_free() -> None:
    """The importlib.metadata check passes in the main test environment."""
    smoke.assert_main_environment_paddle_free()


def test_paddle_free_check_names_offending_distributions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installed Paddle package fails the check naming the distribution."""
    monkeypatch.setattr(smoke, "_distribution_installed", lambda name: name == "paddleocr")
    with pytest.raises(smoke.SmokeTestError, match="paddleocr"):
        smoke.assert_main_environment_paddle_free()


# ── Response validation (unit level, no worker) ───────────────────────────


def _success_line(markdown: str) -> str:
    """Build one wire-valid parse_result line for the validator."""
    import json

    return json.dumps(
        {
            "id": smoke.SMOKE_REQUEST_ID,
            "protocol_version": smoke.EXPECTED_PROTOCOL_VERSION,
            "type": smoke.RESPONSE_TYPE_PARSE_RESULT,
            "ok": True,
            "markdown": markdown,
            "metadata": {
                "ocr_backend": "test",
                "page_count": 1,
                "output_schema": {
                    "id": smoke.EXPECTED_OUTPUT_SCHEMA_ID,
                    "version": smoke.EXPECTED_OUTPUT_SCHEMA_VERSION,
                },
            },
        }
    )


def test_parse_response_validator_accepts_structured_markdown() -> None:
    """A conforming response line passes and returns the Markdown."""
    markdown = smoke._validate_parse_response(_success_line("# Heading\n\n- item\n"), "x.pdf")
    assert markdown.startswith("# Heading")


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda d: d.update(id="other"), "correlate"),
        (lambda d: d.update(protocol_version="0.9"), "protocol_version"),
        (lambda d: d.update(ok=False), "failed"),
        (lambda d: d.update(markdown="   "), "empty"),
        (lambda d: d.update(markdown="no structure at all"), "structured text"),
    ],
)
def test_parse_response_validator_rejects_each_breach(mutator: Any, expected: str) -> None:
    """Each framing/structure breach fails with a named reason."""
    import json

    payload = json.loads(_success_line("# Fine\n"))
    mutator(payload)
    with pytest.raises(smoke.SmokeTestError, match=expected):
        smoke._validate_parse_response(json.dumps(payload), "x.pdf")


def test_fingerprint_validator_accepts_a_conforming_payload() -> None:
    """The probe-side validator accepts the full declared contract."""
    smoke._validate_fingerprint(
        {
            "protocol_version": smoke.EXPECTED_PROTOCOL_VERSION,
            "packages": {"paddleocr": "1.0.0", "paddlepaddle": "3.0.0"},
            "pipeline": {"identity": "paddleocr-vl", "revision": "r1"},
            "model": {"identity": "PaddleOCR-VL", "revision": "r1"},
            "output_schema": {
                "id": smoke.EXPECTED_OUTPUT_SCHEMA_ID,
                "version": smoke.EXPECTED_OUTPUT_SCHEMA_VERSION,
            },
        }
    )


def test_fingerprint_validator_rejects_wrong_protocol() -> None:
    """A protocol mismatch is a named failure."""
    with pytest.raises(smoke.SmokeTestError, match="protocol_version"):
        smoke._validate_fingerprint(
            {
                "protocol_version": "0.9",
                "packages": {"paddleocr": "1.0.0"},
                "pipeline": {"identity": "p", "revision": "r"},
                "model": {"identity": "m", "revision": "r"},
                "output_schema": {
                    "id": smoke.EXPECTED_OUTPUT_SCHEMA_ID,
                    "version": smoke.EXPECTED_OUTPUT_SCHEMA_VERSION,
                },
            }
        )


# ── Provisioning target safety ────────────────────────────────────────────


def test_worker_environment_overrides_inherited_uv_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inherited uv project selectors cannot redirect provisioning.

    An absolute ``UV_PROJECT_ENVIRONMENT`` overrides the working
    directory, so an inherited value could aim the exact ``uv sync
    --locked`` at another environment — installing Paddle into it and
    pruning its extraneous packages. The worker environment must pin
    both selectors to worker-owned targets.
    """
    monkeypatch.setenv("UV_PROJECT", "/elsewhere/omrg-test/root")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/elsewhere/omrg-test/root/.venv")
    environment = smoke._worker_environment()
    assert environment["UV_PROJECT"] == str(smoke.WORKER_DIR)
    assert environment["UV_PROJECT_ENVIRONMENT"] == str(smoke.WORKER_DIR / ".venv")
    assert environment["PADDLE_OCR_BASE_DIR"] == str(smoke.MODEL_CACHE_DIR)
    assert environment["PADDLE_PDX_CACHE_HOME"] == str(smoke.MODEL_CACHE_DIR)
