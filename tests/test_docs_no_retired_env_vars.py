"""Guard test: operator-facing docs never instruct setting a retired variable.

Enforces the config-retirement-policy spec requirement: no operator-facing
document SHALL instruct the reader to assign a value to a retired
configuration variable.  Detection keys on **assignment form**
(``^\\s*#?\\s*NAME=``), not substring: most mentions of retired names are
correct migration prose, and a substring check would flag ~35 files of
legitimate documentation.  Assignment form yields exactly the real bugs.

See ``openspec/changes/tripwire-retirement-and-provider-symmetry/`` and
``design.md`` D3 for the measurement that calibrated this check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from rag_mcp.config.legacy import _RETIRED_ENV_VARS

# Operator-facing paths: files an operator copies from or follows to
# configure a deployment.  Historical records (CHANGELOG, ADRs, TDRs,
# archived proposals) are excluded — they describe the past, not instructions.
_REPO_ROOT = Path(__file__).resolve().parent.parent

_OPERATOR_PATHS: list[Path] = [
    _REPO_ROOT / ".env.example",
    _REPO_ROOT / "README.md",
]
# Scan the guides directory as a directory, not an enumerated file list,
# so new guides are covered automatically (design.md Risks).
_OPERATOR_DIRS: list[Path] = [
    _REPO_ROOT / "docs" / "guides",
]


def _operator_files() -> list[Path]:
    """Return every operator-facing file to scan."""
    files = [p for p in _OPERATOR_PATHS if p.exists()]
    for dir_path in _OPERATOR_DIRS:
        if dir_path.is_dir():
            files.extend(sorted(dir_path.rglob("*.md")))
    return files


def _find_retired_assignments() -> list[tuple[Path, int, str, str]]:
    """Scan operator-facing docs for retired-variable assignments.

    Returns a list of ``(file, line_number, retired_name, replacement)``
    tuples — empty when the tree is clean.
    """
    # Build one regex per retired name: ^\s*#?\s*NAME=
    # The optional ``#`` covers commented assignments (``# TOP_K=10``),
    # which are just as misleading in ``.env.example`` as live ones.
    patterns: list[tuple[str, str, re.Pattern[str]]] = [
        (name, replacement, re.compile(rf"^\s*#?\s*{re.escape(name)}\s*="))
        for name, replacement in _RETIRED_ENV_VARS.items()
    ]

    findings: list[tuple[Path, int, str, str]] = []
    for file_path in _operator_files():
        text = file_path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for name, replacement, pattern in patterns:
                if pattern.match(line):
                    findings.append((file_path, lineno, name, replacement))
    return findings


def test_no_operator_doc_assigns_a_retired_variable() -> None:
    """No operator-facing document SHALL instruct setting a retired name.

    Naming a retired variable to explain its replacement is permitted;
    assigning it (``NAME=value``) is not.  This distinction is what makes
    the check survivable — see design.md D3.
    """
    findings = _find_retired_assignments()
    if findings:
        details = "\n".join(
            f"  {path.relative_to(_REPO_ROOT)}:{lineno}  "
            f"{name}  ->  use {replacement}"
            for path, lineno, name, replacement in findings
        )
        pytest.fail(
            "Operator-facing document(s) instruct setting a retired "
            f"configuration variable:\n{details}"
        )


def test_prose_mention_does_not_trip_the_check() -> None:
    """A prose mention of a retired name SHALL NOT be flagged.

    Pins the assignment-vs-mention distinction: ``README.md`` names
    ``TOP_K`` in migration prose (``"`TOP_K` is now `RETRIEVAL__TOP_K`"``)
    and that is correct documentation, not an instruction to set it.
    """
    findings = _find_retired_assignments()
    # Filter to README.md findings for TOP_K — there must be none,
    # because the mention is inside backticks, not in assignment form.
    readme_topk = [
        f for f in findings
        if f[0].name == "README.md" and f[2] == "TOP_K"
    ]
    assert readme_topk == [], (
        "Prose mention of TOP_K in README.md was flagged — "
        "the check must distinguish assignment from mention"
    )
