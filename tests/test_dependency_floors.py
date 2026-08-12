"""Executable dependency-floor integrity check.

Asserts that every declared lower bound in ``pyproject.toml`` sits at most
one minor release below the version locked in ``uv.lock``, and never above
the locked version. Mirrors ``tests/test_file_size_ceiling.py``: stdlib
only, ``tomllib`` for both files, no fixtures, reports every offender rather
than the first.

See ADR-042 and the ``raise-dependency-floors`` OpenSpec change.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_UV_LOCK = _REPO_ROOT / "uv.lock"

# Per-package exemptions from the one-minor drift rule. Each entry names the
# reason so it is reviewable. A silent skip list is how the floors rotted in
# the first place (design D3) — every exemption here is a deliberate decision
# recorded in ADR-042, not a workaround.
_EXEMPT: dict[str, str] = {
    # ADR-040: 1.0 was the only relevant break (requests→httpx, removed
    # legacy params); all 1.x minors are compatible.
    "huggingface-hub": "ADR-040: 1.0 was the only relevant break; all 1.x compatible",
    # Transitive only, not imported directly; 0.21.0 break was dropping
    # Python 3.7/3.8 (below this project's floor).
    "tokenizers": "transitive only, not imported directly; 0.21.0 dropped Python 3.7/3.8",
    # Gap too small to carry signal; no API break in 0.25→0.27.
    "typer": "gap too small to carry signal; no API break in range",
    # Stable ``load_dotenv`` across 1.x.
    "python-dotenv": "stable load_dotenv across 1.x",
    # Upstream ships no formal changelog and releases near-daily, so a
    # tighter floor is evidence-light (ADR-042).
    "liteparse": "upstream ships no formal changelog; tighter floor is evidence-light",
    # No known API break in the 4.x→5.x jump for the PdfDocument surface
    # this project calls (ADR-042).
    "pypdfium2": "no known API break in 4.x→5.x for the PdfDocument surface",
    # v3 uses activation_fct, activation_fn did not exist until v4, v5.4+
    # changed persistence on predict(). Floor set by the existing pyproject
    # comment and ADR-038.
    "sentence-transformers": "v3/v4/v5 API changes documented; floor >=5.0 is intentional",
    # ADR-040: coupled with huggingface-hub 1.0; 5.0 was the only relevant
    # break. In the torch extra only.
    "transformers": "ADR-040: 5.0 was the only relevant break; coupled with huggingface-hub 1.0",
    # No breaking change in 0.7→0.9 for the ``validate()`` call site used in
    # CI's OpenAPI validation step.
    "openapi-spec-validator": "no breaking change for the validate() call site",
    # Several minors below locked but no breaking change in 4.x.
    "pre-commit": "no breaking change in 4.x",
    # ── ADR-042 evidence-based floors (design D1: floor = lowest proven  ──
    # ── safe, not the locked version). These gaps are intentional and   ──
    # ── documented in the ADR's per-package evidence table.              ──
    # 1.0.0 is the version that reverted list_collections() to returning
    # Collection objects; 0.6.0–0.9.x returned bare strings.
    "chromadb": "ADR-042: 1.0.0 is the list_collections fix; no API break in 1.x",
    # First version requiring core>=0.13.0; the floor follows the tightest
    # sibling (design D6).
    "llama-index-embeddings-ollama": "ADR-042: 0.7.0 is the first requiring core>=0.13.0 (D6)",
    # No Python InferenceSession API break in 1.20–1.28 range.
    "onnxruntime": "ADR-042: no InferenceSession API break in 1.20–1.28 range",
    # 5.0.0 renamed internal classes; floor set at the rename boundary.
    "watchdog": "ADR-042: 5.0.0 is the rename boundary; no break through 6.0.0",
    # 0.23.0 is the minimum declared by tree-sitter-language-pack itself.
    "tree-sitter": "ADR-042: 0.23.0 is the minimum declared by tree-sitter-language-pack",
    # 1.12.3 fixes the silent AST failure mode (vendored parser on 3.14).
    "tree-sitter-language-pack": (
        "ADR-042: 1.12.3 fixes the silent AST failure; no break through 1.14.3"
    ),
    # 3.2 is a modest bump past immediate post-3.0 churn; no break through 3.6.1.
    "networkx": "ADR-042: 3.2 is past post-3.0 churn; no break through 3.6.1",
    # First version requiring core>=0.13.0; same core-coupling logic (D6).
    "llama-index-llms-openai-like": "ADR-042: 0.5.0 is the first requiring core>=0.13.0 (D6)",
}


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse a PEP 440 version string into a comparable int tuple.

    Handles the simple ``major.minor[.patch]`` forms used by every
    dependency in this project. Pre/post release segments are ignored —
    none of our floors use them.
    """
    match = re.match(r"(?:\d+!)?(\d+(?:\.\d+)*)(?:[._+-].*)?$", version.strip())
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def _minor_distance(floor: tuple[int, ...], locked: tuple[int, ...]) -> int:
    """Return how many minors the floor sits below the locked version.

    A major-version gap is treated as infinitely far (returns a large
    number), since it is definitely more than one minor.
    """
    floor_major = floor[0] if len(floor) > 0 else 0
    locked_major = locked[0] if len(locked) > 0 else 0
    floor_minor = floor[1] if len(floor) > 1 else 0
    locked_minor = locked[1] if len(locked) > 1 else 0
    if floor_major != locked_major:
        return 1_000_000  # major gap → always exceeds one-minor tolerance
    return locked_minor - floor_minor


def _version_gt(a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    """Return True if version *a* is strictly greater than version *b*."""
    length = max(len(a), len(b))
    a_padded = a + (0,) * (length - len(a))
    b_padded = b + (0,) * (length - len(b))
    return a_padded > b_padded


def _extract_floor(requirement: str) -> tuple[str, tuple[int, ...]] | None:
    """Extract ``(package_name, minimum_version)`` from a PEP 508 requirement.

    Returns the lowest declared bound (the ``>=`` or ``~=`` specifier). If
    the requirement has no version specifier, returns None.
    """
    # Strip environment markers and whitespace.
    req = requirement.split(";")[0].strip()
    # Handle comma-separated specifiers: take the first lower bound.
    for part in re.split(r"\s*,\s*", req):
        match = re.match(
            r"^\s*([A-Za-z0-9._-]+)"
            r"(?:\[[^\]]*\])?"
            r"\s*"
            r"(>=|~=|===)\s*"
            r"([0-9]+(?:\.[0-9]+)*)",
            part,
        )
        if match:
            name = match.group(1).lower().replace("_", "-")
            version = tuple(int(p) for p in match.group(3).split("."))
            return (name, version)
    return None


def _locked_versions() -> dict[str, tuple[int, ...]]:
    """Return ``{package_name: version_tuple}`` from ``uv.lock``."""
    with _UV_LOCK.open("rb") as fh:
        lock = tomllib.load(fh)
    result: dict[str, tuple[int, ...]] = {}
    for pkg in lock.get("package", []):
        name = pkg["name"].lower().replace("_", "-")
        result[name] = _parse_version(pkg["version"])
    return result


def _declared_floors() -> list[tuple[str, str, tuple[int, ...]]]:
    """Return ``(package_name, source_table, floor_version)`` for every declared dep.

    Covers ``[project.dependencies]``, every group in
    ``[project.optional-dependencies]``, and ``[dependency-groups]``.
    """
    with _PYPROJECT.open("rb") as fh:
        pyproject = tomllib.load(fh)

    floors: list[tuple[str, str, tuple[int, ...]]] = []

    for req in pyproject.get("project", {}).get("dependencies", []):
        parsed = _extract_floor(req)
        if parsed:
            name, version = parsed
            floors.append((name, "project.dependencies", version))

    for group, reqs in pyproject.get("project", {}).get("optional-dependencies", {}).items():
        for req in reqs:
            parsed = _extract_floor(req)
            if parsed:
                name, version = parsed
                floors.append((name, f"optional-dependencies[{group}]", version))

    for group, reqs in pyproject.get("dependency-groups", {}).items():
        for req in reqs:
            parsed = _extract_floor(req)
            if parsed:
                name, version = parsed
                floors.append((name, f"dependency-groups[{group}]", version))

    return floors


def _fmt(version: tuple[int, ...]) -> str:
    """Format a version tuple back to a string."""
    return ".".join(str(p) for p in version)


def test_declared_floors_match_lockfile() -> None:
    """Every declared floor sits within one minor of its locked version.

    Fails when:
    - a floor sits more than one minor below its locked version (drift), or
    - a floor sits above its locked version (the lockfile would violate the
      declared contract), or
    - a declared package is not found in ``uv.lock``.
    """
    locked = _locked_versions()
    floors = _declared_floors()

    drift_offenders: list[str] = []
    above_offenders: list[str] = []
    missing_offenders: list[str] = []

    for name, source, floor in floors:
        if name in _EXEMPT:
            continue
        if name not in locked:
            missing_offenders.append(f"  {name} ({source}): not found in uv.lock")
            continue
        locked_version = locked[name]

        # Floor above lock → the lockfile violates the declared contract.
        if _version_gt(floor, locked_version):
            above_offenders.append(
                f"  {name} ({source}): floor {_fmt(floor)} above locked {_fmt(locked_version)}"
            )
            continue

        # Floor more than one minor below lock → drift.
        distance = _minor_distance(floor, locked_version)
        if distance > 1:
            drift_offenders.append(
                f"  {name} ({source}): floor {_fmt(floor)} "
                f"is {distance} minors below locked {_fmt(locked_version)}"
            )

    messages: list[str] = []
    if missing_offenders:
        messages.append(
            f"{len(missing_offenders)} package(s) not found in uv.lock:\n"
            + "\n".join(missing_offenders)
        )
    if above_offenders:
        messages.append(
            f"{len(above_offenders)} package(s) with floor above locked version:\n"
            + "\n".join(above_offenders)
        )
    if drift_offenders:
        messages.append(
            f"{len(drift_offenders)} package(s) drifted more than one minor from lock:\n"
            + "\n".join(drift_offenders)
        )

    if messages:
        pytest.fail("\n\n".join(messages))
