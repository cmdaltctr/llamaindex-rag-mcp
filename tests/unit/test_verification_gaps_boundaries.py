"""Top-level module allow-list (verification gap B, architecture boundaries).

Business logic lives below ``omrg.core``. The top level of ``src/omrg``
holds only the package marker, the Engine and composition-root helpers.
A new top-level module fails this test, so a reviewer decides whether it
belongs below ``core`` or in the composition root.
"""

from __future__ import annotations

from pathlib import Path

import omrg

#: The top-level modules that exist today, with their role.
_ALLOWED_TOP_LEVEL = {
    "__init__.py": "package marker and PEP 562 lazy public exports",
    "engine.py": "the public Engine",
    "compose.py": "composition root",
    "compose_answer.py": "composition root: answer models",
    "compose_engine.py": "composition root: build_engine",
    "compose_experiments.py": "composition root: experiment contexts",
    "compose_pipelines.py": "composition root: Engine graph state",
    "compose_pipeline_runs.py": "composition root: per-run planning and provenance",
    "compose_settings.py": "composition root: settings resolution",
    "capabilities.py": "composition root: runtime capability probes",
    "pipeline_templates.py": "composition root: canonical graph templates",
}


def _package_dir() -> Path:
    return Path(omrg.__file__).resolve().parent


def test_top_level_modules_match_the_allow_list() -> None:
    """Every ``src/omrg/*.py`` file is on the allow-list, and nothing is missing."""
    found = {path.name for path in _package_dir().glob("*.py")}
    assert found == set(_ALLOWED_TOP_LEVEL), (
        f"unexpected: {sorted(found - set(_ALLOWED_TOP_LEVEL))}, "
        f"missing: {sorted(set(_ALLOWED_TOP_LEVEL) - found)}"
    )


def test_no_top_level_business_package_appears() -> None:
    """Top-level packages are only the known layers; v1 shims stay deleted."""
    packages = {
        path.name
        for path in _package_dir().iterdir()
        if path.is_dir() and (path / "__init__.py").exists()
    }
    assert packages == {"config", "core", "daemon", "integrations", "transports"}
    for removed in ("ingestion", "retrieval", "server", "cli", "readers"):
        assert not (_package_dir() / f"{removed}.py").exists(), removed
