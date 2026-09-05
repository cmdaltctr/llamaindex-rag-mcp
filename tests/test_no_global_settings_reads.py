"""No global settings singleton reads inside the production package.

Asserts that no module under ``src/omrg/`` — core, integrations,
transports, daemon, config and top-level — reads the resolved settings
singleton except the sanctioned composition-root siblings:
``compose.py``, ``compose_answer.py`` and ``compose_engine.py``. Every
other module must receive its configuration as an injected
``EffectiveSettings`` parameter or through a composition-root surface
(PROPOSAL §6.3.1, settings-dependency-injection spec).

Detection covers both read shapes:
- importing the ``settings`` singleton or ``get_settings`` (any alias)
  from a ``config`` module, including function-local imports;
- calling ``get_settings()`` directly or through a ``config.`` qualifier.

``#`` comments are stripped before matching so prose mentioning the API
(the definition site's documentation, for example) is not flagged.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "omrg"

# Matches ``from ...config import settings`` / ``from ..config import settings``
# and the inline ``from ...config import settings`` inside functions.
_SETTINGS_IMPORT_RE = re.compile(
    r"^\s*from\s+\S*\.?config\s+import\s+.*\bsettings\b",
    re.MULTILINE,
)

# Matches ``get_settings`` imports with any alias, module- or
# function-local (``from omrg.config import get_settings as gs``).
_GET_SETTINGS_IMPORT_RE = re.compile(
    r"^\s*from\s+\S*config\s+import\s+[^#\n]*\bget_settings\b",
    re.MULTILINE,
)

# Matches qualified calls (``config.get_settings(...)``).
_QUALIFIED_CALL_RE = re.compile(r"\bconfig\.get_settings\s*\(")

# Matches bare calls that are neither the definition (``def
# get_settings(``), a longer identifier (``get_settings_extra(``) nor a
# different attribute (``other.get_settings`` is the qualified form).
_BARE_CALL_RE = re.compile(r"(?<![\w.])(?<!def )get_settings\s*\(")

_COMMENT_RE = re.compile(r"#.*$")

# Composition-root siblings permitted to call ``get_settings()``, by
# exact path relative to ``src/omrg`` — basename matching would exempt
# any file named ``compose.py`` anywhere in the tree.
_PERMITTED_PATHS = frozenset({"compose.py", "compose_answer.py", "compose_engine.py"})


def _strip_comments(text: str) -> str:
    """Drop ``#`` comments per line, preserving the line structure."""
    return "\n".join(_COMMENT_RE.sub("", line) for line in text.splitlines())


def _scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, snippet)`` for every forbidden settings read.

    Args:
        text: Python source text.

    Returns:
        Sorted hits; one per pattern match (a line matching two patterns
        reports both, which is desirable for a guard).
    """
    stripped = _strip_comments(text)
    hits: list[tuple[int, str]] = []
    for pattern in (
        _SETTINGS_IMPORT_RE,
        _GET_SETTINGS_IMPORT_RE,
        _QUALIFIED_CALL_RE,
        _BARE_CALL_RE,
    ):
        for match in pattern.finditer(stripped):
            line_no = stripped.count("\n", 0, match.start()) + 1
            hits.append((line_no, match.group(0).strip()))
    return sorted(hits)


def _production_files() -> list[Path]:
    """Return every ``.py`` file in the production package, all subpackages."""
    return sorted(p for p in _SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_global_settings_reads_in_production_package() -> None:
    """No module outside the composition root may read the settings singleton."""
    assert _SRC_ROOT.is_dir(), f"configured source root is missing: {_SRC_ROOT}"
    hits: list[tuple[Path, int, str]] = []
    for path in _production_files():
        relative = path.relative_to(_SRC_ROOT).as_posix()
        if relative in _PERMITTED_PATHS:
            continue
        for line_no, snippet in _scan_text(path.read_text(encoding="utf-8")):
            hits.append((path, line_no, snippet))

    if hits:
        lines = [
            f"  {path.relative_to(_SRC_ROOT.parent)}:{line_no}: {snippet}"
            for path, line_no, snippet in hits
        ]
        pytest.fail(f"{len(hits)} settings-singleton read(s) found:\n" + "\n".join(lines))


# ── Regression fixtures: the guard catches what it claims ────────────


@pytest.mark.parametrize(
    ("source", "expected_fragment"),
    [
        ("from omrg.config import get_settings", "get_settings"),
        ("from ..config import get_settings as gs\ngs()", "import get_settings"),
        (
            "def helper():\n    from .config import get_settings\n    return get_settings()",
            "from .config import get_settings",
        ),
        ("import omrg.config\nomrg.config.get_settings()", "config.get_settings("),
        ("value = get_settings()", "get_settings("),
        ("from omrg.config import settings", "settings"),
        ("from ..config import settings as cfg_singleton", "import settings"),
    ],
)
def test_scan_text_flags_forbidden_reads(source: str, expected_fragment: str) -> None:
    """Every forbidden read shape is caught with its line number."""
    hits = _scan_text(source)
    assert hits, f"guard missed a forbidden read: {source!r}"
    assert any(expected_fragment in snippet for _, snippet in hits), hits


@pytest.mark.parametrize(
    "source",
    [
        "def get_settings() -> Settings:\n    return Settings()",
        "async def get_settings() -> Settings:\n    return Settings()",
        "result = get_settings_something()",
        "value = my_config.get_settings_extra()",
        "# get_settings() must not be called here",
        "# from omrg.config import get_settings  # retired",
        "from omrg.config import get_profile_names",
        "settings_like_dict = {}",
        "url = 'https://example.test/#anchor'  # comment with get_settings()",
    ],
)
def test_scan_text_allows_sanctioned_patterns(source: str) -> None:
    """Definitions, longer identifiers and comments are not flagged."""
    assert _scan_text(source) == []
