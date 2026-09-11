"""Unit tests for the OCR worker provisioning guard (task 2.1a).

Only the pure check functions are exercised here. Provisioning itself
installs a multi-gigabyte Paddle environment and belongs to the
dedicated worker smoke test (task 2.15), never to the main suite.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PROVISION_SCRIPT = REPO_ROOT / "ocr-worker" / "provision.py"


def _load_provision_module():
    """Import provision.py directly from its script path."""
    spec = importlib.util.spec_from_file_location("omrg_ocr_provision", PROVISION_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def provision():
    """Load the provisioning module once for the test module."""
    return _load_provision_module()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3.12", (3, 12)),
        ("3.11", (3, 11)),
        ("3.13", (3, 13)),
        ("3.12.7", (3, 12)),
        ("3.13.2", (3, 13)),
        ("3.14.0rc1", (3, 14)),
    ],
)
def test_parse_python_version(provision, text: str, expected: tuple[int, int]) -> None:
    """The parser reads major.minor from version strings."""
    assert provision.parse_python_version(text) == expected


def test_parse_python_version_rejects_garbage(provision) -> None:
    """Unparsable text raises ValueError, not a stack trace."""
    with pytest.raises(ValueError):
        provision.parse_python_version("not-a-version")
    with pytest.raises(ValueError):
        provision.parse_python_version("")


@pytest.mark.parametrize("version", [(3, 11), (3, 12), (3, 13)])
def test_supported_versions_are_accepted(provision, version: tuple[int, int]) -> None:
    """3.11, 3.12, and 3.13 pass the guard."""
    provision.ensure_supported_python(version)


@pytest.mark.parametrize("version", [(2, 7), (3, 9), (3, 10), (3, 14), (3, 15), (4, 0)])
def test_unsupported_versions_are_rejected(provision, version: tuple[int, int]) -> None:
    """Out-of-range versions fail with an actionable, named error."""
    with pytest.raises(provision.UnsupportedPythonError) as excinfo:
        provision.ensure_supported_python(version)
    message = str(excinfo.value)
    assert ">=3.11,<3.14" in message, "error must name the supported range"
    assert "3.11" in message and "3.13" in message, "error must name usable versions"


def test_guard_matches_the_worker_manifest() -> None:
    """The guard's range must equal the worker manifest declaration."""
    worker_manifest = tomllib.loads(
        (REPO_ROOT / "ocr-worker" / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert worker_manifest["project"]["requires-python"] == ">=3.11,<3.14"


def test_provision_script_never_targets_the_repo_root(provision) -> None:
    """The provisioning working directory is the worker directory itself."""
    assert provision.WORKER_DIR == (REPO_ROOT / "ocr-worker").resolve()
    assert provision.WORKER_DIR != REPO_ROOT
