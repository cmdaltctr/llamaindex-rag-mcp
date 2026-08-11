"""Base dependency audit test (task 8.4) and resolved-install-graph test.

Asserts that sentence-transformers, torch, optimum, and transformers are
absent from both the declared base dependencies in ``pyproject.toml`` and
the resolved install graph in the current environment. The previous
violation entered through a transitive dependency that no one audited;
these tests turn the prose requirement into automated CI checks.
"""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path


def _read_base_dependencies() -> list[str]:
    """Extract the base dependencies list from pyproject.toml.

    Returns the list of dependency strings inside
    ``[project] dependencies = [...]``, before any optional-dependencies
    section.
    """
    repo_root = Path(__file__).resolve().parent.parent
    with (repo_root / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    return data.get("project", {}).get("dependencies", [])


def test_base_dependencies_exclude_torch_ecosystem() -> None:
    """Base dependencies SHALL NOT include torch-ecosystem packages.

    sentence-transformers, torch, optimum, and transformers pull PyTorch
    into the default install. They must be behind the ``torch`` optional
    extra only.
    """
    deps = _read_base_dependencies()
    deps_lower = [d.lower() for d in deps]

    forbidden = ["sentence-transformers", "torch", "optimum", "transformers"]
    for pkg in forbidden:
        # Check the package name before any version specifier.
        base_names = [
            d.split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip() for d in deps_lower
        ]
        matches = [d for d in base_names if d == pkg]
        assert not matches, (
            f"{pkg!r} must not be a base dependency — it pulls PyTorch "
            f"into the default install. Found: {matches}"
        )


def test_base_dependencies_include_tokenizers() -> None:
    """Base dependencies SHALL include tokenizers (the torch-free tokeniser)."""
    deps = _read_base_dependencies()
    deps_lower = [d.lower() for d in deps]

    assert any(d.startswith("tokenizers") for d in deps_lower), (
        "tokenizers must be a base dependency — it replaces "
        "transformers.AutoTokenizer for the ONNX reranker."
    )


def test_resolved_install_excludes_torch_ecosystem() -> None:
    """The resolved install graph SHALL NOT include torch-ecosystem packages.

    Checks ``importlib.metadata.distributions()`` — the actual installed
    packages in the current environment — not just the declarations in
    ``pyproject.toml``. A base dep could pull torch transitively without
    appearing in the declarations list; this test catches that.

    Skipped when the ``torch`` extra is installed (detected by checking
    if ``sentence_transformers`` is importable), since the extra
    legitimately installs torch.
    """
    # Skip if the torch extra is installed — it legitimately brings torch.
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        pass
    else:
        import pytest

        pytest.skip("torch extra is installed — torch is expected in the graph")

    forbidden = {
        "sentence-transformers",
        "torch",
        "optimum",
        "transformers",
    }
    installed = {dist.metadata["Name"].lower() for dist in importlib.metadata.distributions()}
    found = forbidden & installed
    assert not found, (
        f"Forbidden packages found in the resolved install graph: {found}. "
        f"A base dependency likely pulls torch transitively. "
        f"Run 'uv pip list | grep -iE \"^torch|^transformers\"' to investigate."
    )
