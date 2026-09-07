#!/usr/bin/env python3
"""Dedicated OCR worker smoke-test runner (task 2.15).

SEPARATE from the main OMRG pytest suite on purpose: it provisions the
isolated worker environment from the worker-owned lockfile, then checks
the real worker end to end — capability probe, ONE parse request over
the real JSON Lines protocol, response framing, and structured
Markdown. The main test suite must never need the worker environment.

Two modes:

``--no-provision`` (default, DRY-RUN)
    Validates arguments, resolves every command it would run, checks
    interpreter availability READ-ONLY (``uv python list --only-installed``
    — no downloads, no installs), asserts the MAIN environment is
    Paddle-free, and prints the plan. This is the mode CI and agents
    run.

``--provision``
    Additionally runs ``provision.py`` (deterministic, worker lockfile
    only), the capability probe, and one parse request against the
    fixture. The operator runs this mode explicitly after approving the
    multi-gigabyte Paddle installation; nothing here runs implicitly.

Usage::

    python ocr-worker/smoke_test.py --python 3.12
    python ocr-worker/smoke_test.py --python 3.13 --provision
    python ocr-worker/smoke_test.py --python /path/to/python3.11 --fixture doc.pdf

Supported interpreters: Python 3.11, 3.12, and 3.13 (the range the
worker manifest declares, ``>=3.11,<3.14``).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import provision

WORKER_DIR = Path(__file__).resolve().parent
REPO_ROOT = WORKER_DIR.parent
MODEL_CACHE_DIR = WORKER_DIR / ".model-cache"
EVIDENCE_DIR = WORKER_DIR / "smoke_evidence"
DEFAULT_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "pdf_baseline" / "calibration" / "cal_table_text.pdf"
)

#: The three Paddle distributions that must NEVER enter the main OMRG
#: environment (task 2.1/2.1b boundary). Checked with importlib.metadata
#: so no import of the packages themselves is attempted.
PADDLE_DISTRIBUTIONS: tuple[str, ...] = ("paddleocr", "paddlex", "paddlepaddle")

# The expected wire contract. Deliberately declared HERE rather than
# imported from ``src/omrg``: the smoke test validates the contract from
# the outside, so its expected values must be independent of the code
# under test (they mirror
# src/omrg/integrations/ocr_worker/protocol.py and
# ocr-worker/src/omrg_ocr_worker/protocol.py).
EXPECTED_PROTOCOL_VERSION = "1.0"
EXPECTED_OUTPUT_SCHEMA_ID = "omrg.ocr.parse_output"
EXPECTED_OUTPUT_SCHEMA_VERSION = "1"
REQUEST_TYPE_PARSE = "parse"
RESPONSE_TYPE_PARSE_RESULT = "parse_result"

#: A response line is ONE complete line; the terminal envelope must
#: carry the correlated request id, the declared protocol version, and
#: the declared output-schema identity and version.
SMOKE_REQUEST_ID = "smoke-test-0001"

_STRUCTURED_MARKDOWN_RE = re.compile(r"^(?:#{1,6} \S|\s*[-*+] \S|\|)", re.MULTILINE)


class SmokeTestError(Exception):
    """One smoke-test validation failure with an actionable message."""


def assert_main_environment_paddle_free() -> None:
    """Fail when any Paddle distribution is installed in THIS environment.

    Raises:
        SmokeTestError: Naming every offending distribution. The check
            uses ``importlib.metadata`` (metadata only — the packages
            are never imported).
    """
    offending = sorted(name for name in PADDLE_DISTRIBUTIONS if _distribution_installed(name))
    if offending:
        raise SmokeTestError(
            f"Main environment contains Paddle packages {offending}. The "
            "isolated OCR worker must be the only environment carrying "
            "them; check `uv sync` ran without the worker project "
            "attached, and rebuild the main virtual environment."
        )


def _distribution_installed(name: str) -> bool:
    """Return whether one distribution is present (metadata lookup only)."""
    try:
        importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return False
    return True


def _resolve_python_version(python_arg: str) -> tuple[int, int]:
    """Return the ``(major, minor)`` version of a version OR interpreter path.

    Args:
        python_arg: A version string (``3.12``) or an interpreter path.

    Returns:
        The ``(major, minor)`` pair.

    Raises:
        SmokeTestError: When the argument is neither a readable version
            nor an interrogable interpreter path.
    """
    requested = python_arg
    if Path(requested).exists():
        probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [requested, "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            raise SmokeTestError(f"cannot interrogate interpreter {requested!r}")
        requested = probe.stdout.strip()
    try:
        return provision.parse_python_version(requested)
    except ValueError as exc:
        raise SmokeTestError(str(exc)) from exc


def build_plan(python_arg: str, fixture: Path, *, provision_requested: bool) -> dict[str, Any]:
    """Resolve and validate every command the smoke test would run.

    Pure function: NO subprocess runs here beyond the read-only version
    probe for an interpreter-path argument, and nothing is installed.

    Args:
        python_arg: Requested Python version or interpreter path.
        fixture: Fixture PDF the parse request will carry.
        provision_requested: Whether provisioning will run.

    Returns:
        A plan dict with the validated python version, the fixture, and
        the resolved provision / probe / parse commands.

    Raises:
        SmokeTestError: When the Python version is outside the supported
            range (the error names the range) or the fixture is missing.
        provision.UnsupportedPythonError: Range rejection from the shared
            provision helper.
    """
    version = _resolve_python_version(python_arg)
    provision.ensure_supported_python(version)
    if not fixture.is_file():
        raise SmokeTestError(
            f"fixture {str(fixture)!r} does not exist; pass --fixture with a "
            "path to a small licence-safe PDF"
        )
    venv_python = WORKER_DIR / ".venv" / "bin" / "python"
    return {
        "python_arg": python_arg,
        "python_version": f"{version[0]}.{version[1]}",
        "mode": "provision" if provision_requested else "dry-run",
        "fixture": str(fixture),
        "provision_command": [
            sys.executable,
            str(WORKER_DIR / "provision.py"),
            "--python",
            python_arg,
        ],
        "worker_venv_python": str(venv_python),
        "probe_command": [str(venv_python), "-m", "omrg_ocr_worker", "--capabilities"],
        "parse_command": [str(venv_python), "-m", "omrg_ocr_worker"],
    }


def check_interpreter_available(version: tuple[int, int] | str) -> tuple[bool, str]:
    """Check READ-ONLY whether a Python version is already installed.

    Queries ``uv python list --only-installed`` — a pure listing with no
    downloads and no installs. A version uv would have to download is
    reported as unavailable; fetching it is provisioning, which only
    ``--provision`` may do.

    Args:
        version: The ``(major, minor)`` pair or its ``"3.12"`` text.

    Returns:
        ``(available, detail)`` — detail names the matching line or the
        reason no installed interpreter matched.
    """
    text = f"{version[0]}.{version[1]}" if isinstance(version, tuple) else str(version)
    uv_path = shutil.which("uv")
    if uv_path is None:
        return False, "uv is not on PATH (install it from https://docs.astral.sh/uv/)"
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [uv_path, "python", "list", "--only-installed"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return False, "uv python list --only-installed failed; cannot verify read-only"
    for line in completed.stdout.splitlines():
        if text in line and "python" in line.lower():
            return True, line.strip()
    return False, f"no installed interpreter matches Python {text}"


def _worker_environment() -> dict[str, str]:
    """Return the worker environment pinned to worker-owned targets.

    The uv selectors are FORCED to the worker project and worker venv:
    an inherited ``UV_PROJECT``/``UV_PROJECT_ENVIRONMENT`` (an absolute
    path overrides the working directory) would otherwise let the exact
    ``uv sync --locked`` install Paddle into — and prune — an
    environment outside ``ocr-worker/``, typically the root project's.
    """
    environment = os.environ.copy()
    environment["PADDLE_OCR_BASE_DIR"] = str(MODEL_CACHE_DIR)
    environment["PADDLE_PDX_CACHE_HOME"] = str(MODEL_CACHE_DIR)
    environment["UV_PROJECT"] = str(WORKER_DIR)
    environment["UV_PROJECT_ENVIRONMENT"] = str(WORKER_DIR / ".venv")
    return environment


def _directory_size(path: Path) -> int:
    """Return the size of regular files below a worker-owned directory."""
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            total += child.stat().st_size
    return total


def _print_plan(plan: dict[str, Any], interpreter: tuple[bool, str]) -> None:
    """Print the resolved plan (dry-run output)."""
    print(f"smoke-test plan ({plan['mode']} mode)")
    print(f"  python requested : {plan['python_arg']} ({plan['python_version']})")
    print(
        f"  interpreter      : {'available' if interpreter[0] else 'NOT installed'}"
        f" — {interpreter[1]}"
    )
    print(f"  fixture          : {plan['fixture']}")
    print("  commands that WOULD run:")
    print(f"    provision : {' '.join(plan['provision_command'])}")
    print(f"    probe     : {' '.join(plan['probe_command'])}")
    print(f"    parse     : {' '.join(plan['parse_command'])}  (one request, JSON Lines)")
    if plan["mode"] == "dry-run":
        print("dry-run only: nothing was installed and no worker ran.")


def _validate_fingerprint(payload: dict[str, Any]) -> None:
    """Validate the probe fingerprint fields against the declared contract.

    Raises:
        SmokeTestError: Naming the first field that disagrees.
    """
    if payload.get("protocol_version") != EXPECTED_PROTOCOL_VERSION:
        raise SmokeTestError(
            f"probe protocol_version {payload.get('protocol_version')!r} != "
            f"{EXPECTED_PROTOCOL_VERSION!r}"
        )
    packages = payload.get("packages")
    if not isinstance(packages, dict) or not packages:
        raise SmokeTestError("probe packages must be a non-empty name→version mapping")
    for name, exact in packages.items():
        if not isinstance(exact, str) or not exact:
            raise SmokeTestError(f"package {name!r} has no exact version")
    for pair_name in ("pipeline", "model"):
        pair = payload.get(pair_name)
        if not isinstance(pair, dict):
            raise SmokeTestError(f"probe {pair_name} must be an identity/revision object")
        for key in ("identity", "revision"):
            if not isinstance(pair.get(key), str) or not pair[key]:
                raise SmokeTestError(f"probe {pair_name}.{key} must be a non-empty string")
    schema = payload.get("output_schema")
    if not isinstance(schema, dict):
        raise SmokeTestError("probe output_schema must be an id/version object")
    if schema.get("id") != EXPECTED_OUTPUT_SCHEMA_ID:
        raise SmokeTestError(
            f"probe output_schema id {schema.get('id')!r} != {EXPECTED_OUTPUT_SCHEMA_ID!r}"
        )
    if schema.get("version") != EXPECTED_OUTPUT_SCHEMA_VERSION:
        raise SmokeTestError(
            f"probe output_schema version {schema.get('version')!r} != "
            f"{EXPECTED_OUTPUT_SCHEMA_VERSION!r}"
        )


def _validate_parse_response(line: str, pdf_path: str) -> str:
    """Validate ONE response line and return the extracted Markdown.

    Checks the full framing contract: one line, correlated id, declared
    protocol version, terminal ``parse_result`` type, success flag, the
    declared output-schema identity and version, and non-empty
    structured Markdown (a heading, list, or table marker is present).
    """
    try:
        response = json.loads(line)
    except json.JSONDecodeError as exc:
        raise SmokeTestError(f"parse response is not one JSON line: {exc}") from exc
    if response.get("id") != SMOKE_REQUEST_ID:
        raise SmokeTestError(
            f"parse response id {response.get('id')!r} does not correlate "
            f"with request {SMOKE_REQUEST_ID!r}"
        )
    if response.get("protocol_version") != EXPECTED_PROTOCOL_VERSION:
        raise SmokeTestError(
            f"parse response protocol_version {response.get('protocol_version')!r} != "
            f"{EXPECTED_PROTOCOL_VERSION!r}"
        )
    if response.get("type") != RESPONSE_TYPE_PARSE_RESULT:
        raise SmokeTestError(
            f"parse response type {response.get('type')!r} is not the terminal "
            f"{RESPONSE_TYPE_PARSE_RESULT!r}"
        )
    if response.get("ok") is not True:
        raise SmokeTestError(f"parse request failed: {json.dumps(response)[:400]}")
    markdown = response.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise SmokeTestError(f"parse response markdown is empty for {pdf_path!r}")
    if not _STRUCTURED_MARKDOWN_RE.search(markdown):
        raise SmokeTestError(
            "parse response markdown has no heading, list, or table marker — not structured text"
        )
    schema = (response.get("metadata") or {}).get("output_schema") or {}
    if schema.get("id") != EXPECTED_OUTPUT_SCHEMA_ID or (
        schema.get("version") != EXPECTED_OUTPUT_SCHEMA_VERSION
    ):
        raise SmokeTestError(
            f"parse response output_schema {schema!r} does not declare "
            f"{EXPECTED_OUTPUT_SCHEMA_ID!r}/{EXPECTED_OUTPUT_SCHEMA_VERSION!r}"
        )
    return markdown


def _run_provisioned(plan: dict[str, Any]) -> int:
    """Provision, probe, and parse once. Operator-approved path only."""
    environment = _worker_environment()
    size_before = _directory_size(WORKER_DIR)
    provision_started = time.perf_counter()
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        plan["provision_command"],
        cwd=WORKER_DIR,
        env=environment,
        check=False,
    )
    provision_seconds = time.perf_counter() - provision_started
    size_after_provision = _directory_size(WORKER_DIR)
    print(f"provision elapsed seconds: {provision_seconds:.2f}")
    print(f"worker bytes before/after provision: {size_before}/{size_after_provision}")
    if completed.returncode != 0:
        print("error: provisioning failed; see the output above", file=sys.stderr)
        return completed.returncode

    probe_started = time.perf_counter()
    probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
        plan["probe_command"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        cwd=WORKER_DIR,
        env=environment,
    )
    print(f"capability probe elapsed seconds: {time.perf_counter() - probe_started:.2f}")
    if probe.stderr:
        print("capability probe stderr:", file=sys.stderr)
        print(probe.stderr.rstrip(), file=sys.stderr)
    if probe.returncode != 0 or not probe.stdout.strip():
        print(f"capability probe stdout: {probe.stdout!r}", file=sys.stderr)
        print("error: capability probe failed or printed nothing", file=sys.stderr)
        return 1
    try:
        fingerprint = json.loads(probe.stdout.splitlines()[0])
        _validate_fingerprint(fingerprint)
    except (json.JSONDecodeError, SmokeTestError) as exc:
        print(f"capability probe stdout: {probe.stdout!r}", file=sys.stderr)
        print(f"error: capability fingerprint invalid: {exc}", file=sys.stderr)
        return 1
    print(f"capability fingerprint: {json.dumps(fingerprint, sort_keys=True)}")
    print("capability probe valid: protocol, packages, pipeline, model, output schema")

    request = json.dumps(
        {
            "id": SMOKE_REQUEST_ID,
            "protocol_version": EXPECTED_PROTOCOL_VERSION,
            "type": REQUEST_TYPE_PARSE,
            "pdf_path": plan["fixture"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    parse_started = time.perf_counter()
    try:
        parse = subprocess.run(  # noqa: S603 - fixed argv, no shell
            plan["parse_command"],
            input=request + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=WORKER_DIR,
            env=environment,
            timeout=1800,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        print(f"parse elapsed seconds: {time.perf_counter() - parse_started:.2f}")
        print(f"error: parse timed out after {exc.timeout} seconds", file=sys.stderr)
        return 1
    parse_seconds = time.perf_counter() - parse_started
    size_after_parse = _directory_size(WORKER_DIR)
    print(f"parse elapsed seconds: {parse_seconds:.2f}")
    print(f"worker bytes after parse: {size_after_parse}")
    if parse.stderr:
        print("worker stderr:", file=sys.stderr)
        print(parse.stderr.rstrip(), file=sys.stderr)
    response_lines = [line for line in parse.stdout.splitlines() if line.strip()]
    if parse.returncode != 0 or len(response_lines) != 1:
        print(f"worker exit status: {parse.returncode}", file=sys.stderr)
        print(f"worker stdout: {parse.stdout!r}", file=sys.stderr)
        print("error: worker did not emit exactly one response line", file=sys.stderr)
        return 1
    line = response_lines[0]
    try:
        response = json.loads(line)
        markdown = _validate_parse_response(line, plan["fixture"])
    except (json.JSONDecodeError, SmokeTestError) as exc:
        print(f"parse response line: {line}", file=sys.stderr)
        print(f"error: {exc}", file=sys.stderr)
        return 1

    evidence_name = plan["python_version"].replace(".", "-")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / f"parse-python-{evidence_name}.json").write_text(
        json.dumps(response, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (EVIDENCE_DIR / f"parse-python-{evidence_name}.md").write_text(
        markdown,
        encoding="utf-8",
    )
    response_without_markdown = dict(response)
    response_without_markdown.pop("markdown", None)
    print(f"parse response framing: {json.dumps(response_without_markdown, sort_keys=True)}")
    print(f"parse response valid; extracted {len(markdown)} characters of Markdown")
    print(f"worker disk delta bytes: {size_after_parse - size_before}")
    print("OCR worker smoke test PASSED")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the smoke test in the requested mode.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        The process exit status.
    """
    parser = argparse.ArgumentParser(
        description="Smoke-test the isolated OCR worker (provision, probe, one parse)."
    )
    parser.add_argument(
        "--python", default="3.12", help="Python version or interpreter path (default: 3.12)"
    )
    parser.add_argument("--fixture", default=None, help=f"fixture PDF (default: {DEFAULT_FIXTURE})")
    parser.add_argument(
        "--provision",
        dest="provision",
        action="store_true",
        help="provision the worker venv and run the real probe and parse",
    )
    parser.add_argument(
        "--no-provision",
        dest="provision",
        action="store_false",
        help="dry-run: validate and print the plan only (default)",
    )
    parser.set_defaults(provision=False)
    args = parser.parse_args(argv)

    try:
        assert_main_environment_paddle_free()
    except SmokeTestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    fixture = Path(args.fixture).expanduser().resolve() if args.fixture else DEFAULT_FIXTURE
    try:
        plan = build_plan(args.python, fixture, provision_requested=args.provision)
    except (SmokeTestError, provision.UnsupportedPythonError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    version_text = plan["python_version"]
    interpreter = check_interpreter_available(version_text)
    _print_plan(plan, interpreter)
    if not args.provision:
        return 0
    if not interpreter[0]:
        print(
            f"error: Python {version_text} is not installed; provisioning would "
            "download it — install it first or choose an installed version",
            file=sys.stderr,
        )
        return 1
    return _run_provisioned(plan)


if __name__ == "__main__":
    raise SystemExit(main())
