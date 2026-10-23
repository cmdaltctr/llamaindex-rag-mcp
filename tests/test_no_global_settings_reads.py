"""No global settings singleton reads inside the production package.

Asserts that no module under ``src/omrs/`` — core, integrations,
transports, daemon, config and top-level — reads the resolved settings
singleton except the sanctioned composition-root siblings:
``compose.py``, ``compose_answer.py``, ``compose_embedding.py``,
``compose_engine.py`` and ``compose_settings.py`` — the composition root, split across files to stay
under the size ceiling. Every
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

import ast
import re
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "omrs"

# Matches ``from ...config import settings`` / ``from ..config import settings``
# and the inline ``from ...config import settings`` inside functions.
_SETTINGS_IMPORT_RE = re.compile(
    r"^\s*from\s+\S*\.?config\s+import\s+.*\bsettings\b",
    re.MULTILINE,
)

# Matches ``get_settings`` imports with any alias, module- or
# function-local (``from omrs.config import get_settings as gs``).
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
# exact path relative to ``src/omrs`` — basename matching would exempt
# any file named ``compose.py`` anywhere in the tree.
_PERMITTED_PATHS = frozenset(
    {
        "compose.py",
        "compose_answer.py",
        "compose_embedding.py",
        "compose_engine.py",
        "compose_providers.py",
        "compose_settings.py",
    }
)


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
        ("from omrs.config import get_settings", "get_settings"),
        ("from ..config import get_settings as gs\ngs()", "import get_settings"),
        (
            "def helper():\n    from .config import get_settings\n    return get_settings()",
            "from .config import get_settings",
        ),
        ("import omrs.config\nomrs.config.get_settings()", "config.get_settings("),
        ("value = get_settings()", "get_settings("),
        ("from omrs.config import settings", "settings"),
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
        "# from omrs.config import get_settings  # retired",
        "from omrs.config import get_profile_names",
        "settings_like_dict = {}",
        "url = 'https://example.test/#anchor'  # comment with get_settings()",
    ],
)
def test_scan_text_allows_sanctioned_patterns(source: str) -> None:
    """Definitions, longer identifiers and comments are not flagged."""
    assert _scan_text(source) == []


# ── Default-accessor guard at repaired leaves (design D6) ────────────
#
# The regex guard above covers the ``config`` singleton. The repaired
# leaves below must also not reach the composition-root *defaults*:
# ``core.settings.get_default_effective_settings`` and
# ``core.vectordb.get_default_store`` (plus their private backing globals).
# Detection is AST-based so it sees bare, qualified (``mod.attr``),
# aliased (``import ... as`` / ``from ... import ... as``), function-local
# and ``getattr(mod, "name")`` reads, and ignores comments and strings.
#
# Sanctioned boundary: ``core.settings.resolve_effective_settings`` stays
# allowed. It is the documented compatibility entry resolution (design D2,
# D3, D6) and only falls back when explicit settings are omitted. There is
# no sanctioned default-*store* fallback in these leaves: an omitted store
# means seed-only categories (D2) or empty document communities (D3).
#
# The guard applies to an explicit file list, never a package-wide ban, so
# boundary modules outside the repair scope keep their documented
# behaviour. Each listed file must exist; a stale entry fails the build.

_FORBIDDEN_ACCESSORS = frozenset(
    {
        "get_default_effective_settings",
        "_default_effective",
        "get_default_store",
        "_default_store",
    }
)

# Leaves repaired by ``repair-modular-core-boundaries`` and the graph
# adapters added after it, relative to
# ``src/omrs``. ``models.py`` is the shared-model module from design D4.
_GUARDED_LEAVES = (
    "core/ingestion/chunker.py",
    "core/metadata/_common.py",
    "core/metadata/extractor.py",
    "core/metadata/keyword.py",
    "core/metadata/llamacpp.py",
    "core/metadata/llamaindex.py",
    "core/metadata/ollama.py",
    "core/metadata/openrouter.py",
    "core/metadata/registry.py",
    "core/metadata/taxonomy.py",
    "core/codebase/cache.py",
    "core/codebase/codebase_map.py",
    "core/codebase/communities.py",
    "core/codebase/models.py",
    # Shared seams and graph adapters from add-local-web-pipeline-workspace
    # (design D4, task 3.8). Each adapter receives store and settings from
    # its NodeContext; a default-accessor read here would mix engines.
    "core/retrieval/operations.py",
    "core/retrieval/graph_adapters.py",
    "core/retrieval/graph_adapters_catalogue.py",
    "core/retrieval/graph_adapters_retrieve.py",
    "core/retrieval/graph_adapters_values.py",
    "core/answer/stages.py",
    "core/answer/results.py",
    "core/answer/graph_adapters.py",
    "core/ingestion/sources.py",
    "core/ingestion/commit.py",
    "core/ingestion/graph_adapters.py",
    "core/ingestion/graph_adapters_catalogue.py",
    "core/ingestion/graph_adapters_values.py",
    "core/ingestion/graph_fingerprint.py",
)


def _scan_default_accessors(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, description)`` for every default-accessor read.

    Args:
        text: Python source text.

    Returns:
        Sorted hits. An aliased import reports the import and each use of
        the alias, so the failure names every line that reads the default.
    """
    tree = ast.parse(text)
    aliases: dict[str, str] = {}
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _FORBIDDEN_ACCESSORS:
                    bound = alias.asname or alias.name
                    aliases[bound] = alias.name
                    label = f" as {bound}" if alias.asname else ""
                    hits.append((node.lineno, f"import {alias.name}{label}"))
                elif alias.name == "*" and (node.module or "").rsplit(".", 1)[-1] in {
                    "settings",
                    "vectordb",
                }:
                    hits.append((node.lineno, f"star import from {node.module}"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ACCESSORS:
            hits.append((node.lineno, f"qualified read .{node.attr}"))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in _FORBIDDEN_ACCESSORS:
                hits.append((node.lineno, f"read {node.id}"))
            elif node.id in aliases:
                hits.append((node.lineno, f"read {node.id} (alias of {aliases[node.id]})"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in _FORBIDDEN_ACCESSORS
        ):
            hits.append((node.lineno, f"getattr(..., {node.args[1].value!r})"))
    return sorted(set(hits))


def test_guarded_leaves_exist() -> None:
    """Every guarded leaf exists, so the list cannot silently go stale."""
    missing = [rel for rel in _GUARDED_LEAVES if not (_SRC_ROOT / rel).is_file()]
    assert not missing, f"guarded leaf path(s) missing: {missing}"


@pytest.mark.parametrize("relative", _GUARDED_LEAVES)
def test_repaired_leaf_has_no_default_accessor_reads(relative: str) -> None:
    """Repaired leaves receive settings/store; they never read the defaults."""
    path = _SRC_ROOT / relative
    if not path.is_file():
        pytest.fail(f"guarded leaf missing: src/omrs/{relative}")
    hits = _scan_default_accessors(path.read_text(encoding="utf-8"))
    if hits:
        lines = [f"  src/omrs/{relative}:{line_no}: {what}" for line_no, what in hits]
        pytest.fail(f"{len(hits)} default-accessor read(s):\n" + "\n".join(lines))


@pytest.mark.parametrize(
    ("source", "expected_fragment"),
    [
        # direct
        (
            "from ..settings import get_default_effective_settings\n"
            "x = get_default_effective_settings()",
            "read get_default_effective_settings",
        ),
        (
            "from ..vectordb import get_default_store\nstore = get_default_store()",
            "read get_default_store",
        ),
        # qualified
        (
            "from .. import vectordb\nstore = vectordb.get_default_store()",
            "qualified read .get_default_store",
        ),
        (
            "import omrs.core.settings\nomrs.core.settings.get_default_effective_settings()",
            "qualified read .get_default_effective_settings",
        ),
        # aliased
        (
            "from ..vectordb import get_default_store as _gds\ns = _gds()",
            "read _gds (alias of get_default_store)",
        ),
        (
            "import omrs.core.settings as cs\ncs.get_default_effective_settings()",
            "qualified read .get_default_effective_settings",
        ),
        (
            "from omrs.core import vectordb as vdb\nvdb.get_default_store()",
            "qualified read .get_default_store",
        ),
        # function-local
        (
            "def f():\n    from ..vectordb import get_default_store\n"
            "    return get_default_store()",
            "import get_default_store",
        ),
        (
            "def f():\n    from ..settings import get_default_effective_settings as g\n"
            "    return g().doc_similarity_threshold",
            "read g (alias",
        ),
        # boundary-style conditional fallback inside a leaf is still a read
        (
            "def f(s=None):\n    from ..settings import get_default_effective_settings\n"
            "    return s if s is not None else get_default_effective_settings()",
            "read get_default_effective_settings",
        ),
        # private globals, reference without call, getattr, star import
        ("from ..settings import _default_effective", "import _default_effective"),
        (
            "from ..vectordb import get_default_store\nfactory = get_default_store",
            "read get_default_store",
        ),
        (
            "import omrs.core.vectordb as v\ngetattr(v, 'get_default_store')()",
            "getattr(..., 'get_default_store')",
        ),
        ("from ..vectordb import *", "star import"),
    ],
)
def test_scan_default_accessors_flags_forbidden_reads(source: str, expected_fragment: str) -> None:
    """Every forbidden default-accessor shape is caught with its line number."""
    hits = _scan_default_accessors(source)
    assert hits, f"guard missed a default-accessor read: {source!r}"
    assert any(expected_fragment in what for _, what in hits), hits
    assert all(line_no >= 1 for line_no, _ in hits)


@pytest.mark.parametrize(
    "source",
    [
        # sanctioned compatibility boundary
        "from ..settings import resolve_effective_settings\n"
        "resolved = resolve_effective_settings(settings)",
        "from .. import settings as s\nresolved = s.resolve_effective_settings(None)",
        # supplied values only
        "def f(text, settings, *, store=None):\n    return store",
        "from ..settings import EffectiveSettings",
        "from ..vectordb import VectorStore",
        # definitions, comments, strings and longer identifiers
        "def get_default_store():\n    return None",
        "# get_default_store() must not be called here",
        "doc = 'never call get_default_effective_settings()'",
        "x = get_default_store_for_tests()",
        "my_default_store = None",
    ],
)
def test_scan_default_accessors_allows_sanctioned_forms(source: str) -> None:
    """The sanctioned boundary and supplied-value forms are not flagged."""
    assert _scan_default_accessors(source) == []
