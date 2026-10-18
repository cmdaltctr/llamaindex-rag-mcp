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
    "engine_answer.py": "the public Engine: answer composition",
    "engine_embedders.py": "the public Engine: embedders by (provider, model)",
    "engine_lifecycle.py": "the public Engine: release of resources on close",
    "engine_profiles.py": "the public Engine: pipelines of a user profile in a request",
    "engine_providers.py": "the public Engine: live LLM provider values (generation swap)",
    "compose.py": "composition root",
    "compose_answer.py": "composition root: answer models",
    "compose_connections.py": "composition root: provider connection summary and test targets",
    "compose_llamacpp.py": "composition root: settings view of the managed llama.cpp server",
    "compose_embedding.py": "composition root: embedding providers and Check model",
    "compose_engine.py": "composition root: build_engine",
    "compose_experiments.py": "composition root: experiment contexts",
    "compose_pipelines.py": "composition root: Engine graph state",
    "compose_pipeline_runs.py": "composition root: per-run planning and provenance",
    "compose_profile_embedding.py": "composition root: embedding model of a profile",
    "compose_profile_setup.py": "composition root: profile upgrade step and factories",
    "compose_profiles.py": "composition root: user profiles that own three pipelines",
    "compose_providers.py": "composition root: saved LLM provider values over settings",
    "compose_settings.py": "composition root: settings resolution",
    "compose_templates.py": "composition root: standard graphs for a profile duplicate",
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
