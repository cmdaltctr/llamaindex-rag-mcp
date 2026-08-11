"""Base dependency audit test (task 8.4).

Asserts that sentence-transformers, torch, optimum, and transformers are
absent from [project.dependencies] in pyproject.toml. The previous
violation entered through a transitive dependency that no one audited;
this test turns the prose requirement into an automated CI check.
"""

from __future__ import annotations

import re
from pathlib import Path


def _read_base_dependencies() -> list[str]:
    """Extract the base dependencies list from pyproject.toml.

    Returns the list of dependency strings inside
    ``[project] dependencies = [...]``, before any optional-dependencies
    section.
    """
    repo_root = Path(__file__).resolve().parent.parent
    text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")

    # Find the [project] section's dependencies array. It starts after
    # "dependencies = [" and ends at the closing "]".
    match = re.search(
        r"^dependencies\s*=\s*\[(.*?)^\]",  # noqa: UP032
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, "Could not find dependencies array in pyproject.toml"

    # Extract quoted strings from the block.
    deps = re.findall(r'["\']([^"\']+)["\']', match.group(1))
    return deps


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
