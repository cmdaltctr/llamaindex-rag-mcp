"""Contract tests for the strategy-registration governance audit (task 4.9).

Compares the maintained audit inventory in ``docs/guides/architecture.md``
with the code it audits:

- Every ``.py`` module under ``src/rag_mcp/integrations/`` (``__pycache__``
  excluded) must appear in the ``integration-inventory`` table, and the
  table must name nothing absent from disk.
- Every ``registry-names`` marker block must list exactly the matching
  live registry's ``available()`` names.
- Every inventory row must carry all six audit columns, non-empty.
- The audit must name both strict-valid follow-up change paths, and both
  change directories must exist.
- The PDF and community registries must equal their audited contract
  constants.

Spec: ``openspec/changes/add-pluggable-community-detection/specs/
strategy-registration-governance/spec.md`` — requirements "Existing modules
receive a registration audit" (scenario "Integrations directory changes")
and "Registry inventory is testable".
"""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType

import pytest

from rag_mcp.core.chunking import registry as chunking_registry
from rag_mcp.core.community import registry as community_registry
from rag_mcp.core.ingestion.backends import registry as docbackend_registry
from rag_mcp.core.metadata import registry as metadata_registry
from rag_mcp.core.providers.embeddings import registry as embed_registry
from rag_mcp.core.providers.llm import registry as llm_registry
from rag_mcp.core.retrieval import registry as retrieval_registry
from rag_mcp.core.vectordb import registry as vectordb_registry
from rag_mcp.integrations.pdf import registry as pdf_registry

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE_GUIDE = REPO_ROOT / "docs" / "guides" / "architecture.md"
INTEGRATIONS_DIR = REPO_ROOT / "src" / "rag_mcp" / "integrations"
CHANGES_DIR = REPO_ROOT / "openspec" / "changes"

#: The six audit columns every inventory row must carry, all non-empty.
INVENTORY_COLUMNS = (
    "Module",
    "Availability",
    "Selector",
    "Shared contract",
    "Fallback owner",
    "Disposition",
)

#: Marker kind → live registry module whose ``available()`` is audited.
REGISTRY_KINDS: dict[str, ModuleType] = {
    "community": community_registry,
    "pdf": pdf_registry,
    "chunking": chunking_registry,
    "metadata": metadata_registry,
    "embeddings": embed_registry,
    "llm": llm_registry,
    "retrieval": retrieval_registry,
    "vectordb": vectordb_registry,
    "document-backend": docbackend_registry,
}

#: Behaviour-changing migrations the audit defers to follow-up changes.
#: ``register-document-backend-strategies`` was delivered and left this
#: list: the document-backend registry is now live and audited above.
STRICT_VALID_FOLLOW_UPS = ("implement-native-sparse-backend-strategy",)

# Audited contract constants from the architecture.md strategy-family
# audit. The PDF set is the concrete ``PDF_READER`` values Settings
# accepts excluding ``auto`` — ``auto`` is an ordered capability policy
# owned by compose/factory, deliberately unregistered. Config literals
# in Settings and the configuration guide are covered by separate
# tests; these pins compare the live registries with the audited sets.
AUDITED_PDF_CONCRETE_NAMES = frozenset({"liteparse", "pdf_inspector", "pypdfium2", "pypdf"})
AUDITED_COMMUNITY_NAMES = frozenset({"louvain", "leiden"})

_INVENTORY_BLOCK_RE = re.compile(
    r"<!--\s*integration-inventory:start\s+count=(\d+)\s*-->"
    r"(.*?)"
    r"<!--\s*integration-inventory:end\s*-->",
    re.DOTALL,
)
_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")


def _architecture_text() -> str:
    """Read the architecture guide from the repository root.

    Returns:
        The full guide text.

    Raises:
        AssertionError: If the guide file is missing.
    """
    assert ARCHITECTURE_GUIDE.is_file(), f"missing guide: {ARCHITECTURE_GUIDE}"
    return ARCHITECTURE_GUIDE.read_text(encoding="utf-8")


def _inventory_block() -> tuple[int, str]:
    """Extract the integration-inventory marker block from the guide.

    Returns:
        ``(declared_count, body)`` — the marker's ``count=N`` value and
        the text spanning the start and end markers.

    Raises:
        AssertionError: If the marker pair is absent or malformed.
    """
    match = _INVENTORY_BLOCK_RE.search(_architecture_text())
    assert match, (
        "integration-inventory markers malformed in architecture.md — "
        "expected '<!-- integration-inventory:start count=N -->' paired "
        "with '<!-- integration-inventory:end -->'"
    )
    return int(match.group(1)), match.group(2)


def _inventory_rows(body: str) -> list[list[str]]:
    """Parse the markdown table rows between the inventory markers.

    The ``|---|---|`` separator row is excluded. Header and data rows
    are both returned so cell-count checks cover the header too.

    Args:
        body: Text between the start and end markers.

    Returns:
        Rows as lists of stripped cell strings.
    """
    rows: list[list[str]] = []
    for line in body.splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and all(_SEPARATOR_CELL_RE.match(cell) for cell in cells):
            continue  # Markdown separator row, not content.
        rows.append(cells)
    return rows


def _discovered_integration_modules() -> set[str]:
    """Discover every Python module under ``src/rag_mcp/integrations/``.

    ``__pycache__`` byte-code directories are excluded. ``__init__.py``
    maps to its package name; every other file maps to its module.
    """
    modules: set[str] = set()
    for path in sorted(INTEGRATIONS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        parts = list(path.relative_to(INTEGRATIONS_DIR).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        # A top-level __init__.py maps to the package root itself.
        name = "rag_mcp.integrations" if not parts else "rag_mcp.integrations." + ".".join(parts)
        modules.add(name)
    return modules


def _documented_inventory_modules() -> set[str]:
    """Return module names in the inventory table's Module column.

    Only the first column's backticked names are read, so backticks in
    other columns (selectors, extras, file paths) cannot leak in.
    """
    _, body = _inventory_block()
    modules: set[str] = set()
    for cells in _inventory_rows(body):
        first_cell = cells[0] if cells else ""
        modules.update(re.findall(r"`([^`]+)`", first_cell))
    return modules


def _registry_names_block(kind: str) -> set[str]:
    """Extract backticked names from a registry-names marker block.

    Args:
        kind: Marker kind, e.g. ``"community"`` or ``"pdf"``.

    Returns:
        The set of names listed inside the block.

    Raises:
        AssertionError: If the exact opening/closing marker pair is absent.
    """
    pattern = rf"<!-- registry-names:{kind} -->(.*?)<!-- /registry-names:{kind} -->"
    match = re.search(pattern, _architecture_text(), re.DOTALL)
    assert match, (
        f"no '<!-- registry-names:{kind} -->' block with its exact closing "
        f"marker in architecture.md"
    )
    return set(re.findall(r"`([^`]+)`", match.group(1)))


def _audit_section() -> str:
    """Slice the strategy-family audit and its conclusions from the guide.

    Returns:
        Text from the ``### Strategy-family audit`` heading up to the
        next top-level heading (or end of file), covering the audit
        table, the registry-names blocks, and the audit conclusions.

    Raises:
        AssertionError: If the audit heading is missing.
    """
    text = _architecture_text()
    start = text.find("### Strategy-family audit")
    assert start != -1, "'### Strategy-family audit' heading missing from architecture.md"
    next_h2 = text.find("\n## ", start)
    return text[start:] if next_h2 == -1 else text[start:next_h2]


# ── 1. Inventory table matches disk ────────────────────────────────────


def test_integration_inventory_table_matches_disk() -> None:
    """The inventory table SHALL name exactly the modules on disk.

    Spec scenario "Integrations directory changes": adding a module
    under ``src/rag_mcp/integrations/`` without classifying it in the
    inventory must fail this check.
    """
    discovered = _discovered_integration_modules()
    documented = _documented_inventory_modules()
    assert discovered, "no modules discovered under src/rag_mcp/integrations/"
    assert discovered == documented, (
        "integration inventory in architecture.md drifted from disk.\n"
        f"  undocumented (on disk, missing from table): "
        f"{sorted(discovered - documented)}\n"
        f"  stale documented (in table, absent from disk): "
        f"{sorted(documented - discovered)}"
    )


def test_integration_inventory_marker_count_agrees() -> None:
    """The marker's ``count=N`` SHALL equal both discovered and documented.

    Guards against a hand-edited count that hides an off-by-one drift
    the set-equality test would otherwise surface one row at a time.
    """
    declared, _ = _inventory_block()
    discovered = _discovered_integration_modules()
    documented = _documented_inventory_modules()
    assert declared == len(discovered) == len(documented), (
        f"marker declares count={declared}, but discovered={len(discovered)} "
        f"and documented={len(documented)} modules"
    )


# ── 2. Registry marker blocks match live registries ────────────────────


@pytest.mark.parametrize("kind", sorted(REGISTRY_KINDS))
def test_registry_names_blocks_match_live_registries(kind: str) -> None:
    """Each ``registry-names`` block SHALL equal the live registry's names.

    Spec scenario "A configurable registered name changes": adding,
    removing, or renaming a registered strategy without updating the
    documented inventory fails with both mismatch directions listed.
    """
    registry = REGISTRY_KINDS[kind]
    documented = _registry_names_block(kind)
    live = set(registry.available())
    assert documented == live, (
        f"registry-names:{kind} block in architecture.md drifted from "
        f"{registry.__name__}.\n"
        f"  documented-not-registered: {sorted(documented - live)}\n"
        f"  registered-not-documented: {sorted(live - documented)}"
    )


# ── 3. Inventory rows carry all six audit columns ──────────────────────


def test_integration_inventory_rows_have_six_non_empty_cells() -> None:
    """Every inventory row SHALL carry all six audit columns, non-empty.

    The audit spec requires each module's availability, selector,
    shared contract, fallback owner, and disposition to be recorded —
    an empty cell is an unclassified property, not a stylistic gap.
    """
    _, body = _inventory_block()
    rows = _inventory_rows(body)
    assert rows, "inventory table has no rows between the markers"
    for index, cells in enumerate(rows):
        label = "header row" if index == 0 else f"data row {index}"
        assert len(cells) == len(INVENTORY_COLUMNS), (
            f"{label}: expected {len(INVENTORY_COLUMNS)} cells "
            f"({', '.join(INVENTORY_COLUMNS)}), found {len(cells)}: {cells}"
        )
        for column, cell in zip(INVENTORY_COLUMNS, cells, strict=True):
            assert cell, f"{label}: column '{column}' is empty"


# ── 4. Follow-up change paths are named and exist ──────────────────────


def test_audit_names_strict_valid_follow_up_changes() -> None:
    """The audit SHALL name both deferred follow-ups; both dirs exist.

    The audit defers document backends and native sparse retrieval to
    strict-valid follow-up changes rather than expanding this change
    silently (spec scenario "Audit finds a behaviour-changing
    migration").
    """
    section = _audit_section()
    for name in STRICT_VALID_FOLLOW_UPS:
        assert name in section, (
            f"follow-up change {name!r} not named in the strategy-family "
            f"audit section of architecture.md"
        )
        change_dir = CHANGES_DIR / name
        assert change_dir.is_dir(), f"openspec/changes/{name}/ does not exist"


# ── 5. Audited contract constants match live registries ────────────────


def test_audited_contract_constants_match_registries() -> None:
    """PDF and community registries SHALL equal their audited constants.

    The PDF factory registry holds exactly the concrete ``PDF_READER``
    values Settings accepts excluding ``auto``. The community registry
    holds exactly the two audited algorithms. Settings' own literal
    validation is not introspected here — config literals are
    separately covered by the configuration documentation tests.
    """
    assert set(pdf_registry.available()) == set(AUDITED_PDF_CONCRETE_NAMES), (
        f"PDF registry names {pdf_registry.available()} != audited concrete "
        f"names {sorted(AUDITED_PDF_CONCRETE_NAMES)}"
    )
    assert set(community_registry.available()) == set(AUDITED_COMMUNITY_NAMES), (
        f"community registry names {community_registry.available()} != "
        f"audited names {sorted(AUDITED_COMMUNITY_NAMES)}"
    )
