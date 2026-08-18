"""Lightweight machine-readable experiment-plan contract.

The hardening work uses this module only for *structural* validation: a runner
must generate the cells its protocol declared, manipulated-factor values must
come from declared levels, and controlled variables/preflight assertions must
be named explicitly.  It deliberately contains no model, corpus, storage, or
statistics code.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _freeze_mapping(mapping: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    """Return a deterministic shallow representation for equality/sorting."""
    return tuple(sorted(mapping.items(), key=lambda item: item[0]))


@dataclass(frozen=True)
class ExperimentCell:
    """One pre-declared treatment/control cell."""

    id: str
    factors: Mapping[str, Any]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ExperimentCell:
        cell_id = str(payload.get("id", "")).strip()
        if not cell_id:
            raise ValueError("Experiment cell requires a non-empty 'id'")
        factors = payload.get("factors")
        if not isinstance(factors, Mapping):
            raise ValueError(f"Experiment cell {cell_id!r} requires a 'factors' mapping")
        return cls(id=cell_id, factors=dict(factors))

    @property
    def factor_key(self) -> tuple[tuple[str, Any], ...]:
        return _freeze_mapping(self.factors)


@dataclass(frozen=True)
class ExperimentPlan:
    """Minimal protocol representation used before expensive execution."""

    experiment_id: str
    protocol_version: str
    experimental_unit: str
    primary_metric: str
    manipulated_factors: Mapping[str, tuple[Any, ...]]
    controlled_variables: Mapping[str, Any]
    cells: tuple[ExperimentCell, ...]
    required_manifest_assertions: tuple[Mapping[str, Any], ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ExperimentPlan:
        required_strings = {
            name: str(payload.get(name, "")).strip()
            for name in (
                "experiment_id",
                "protocol_version",
                "experimental_unit",
                "primary_metric",
            )
        }
        missing = [name for name, value in required_strings.items() if not value]
        if missing:
            raise ValueError(f"Experiment plan missing required field(s): {', '.join(missing)}")

        raw_factors = payload.get("manipulated_factors")
        if not isinstance(raw_factors, Sequence) or isinstance(raw_factors, (str, bytes)):
            raise ValueError("'manipulated_factors' must be a list of factor declarations")

        factors: dict[str, tuple[Any, ...]] = {}
        for raw in raw_factors:
            if not isinstance(raw, Mapping):
                raise ValueError("Each manipulated factor must be an object")
            name = str(raw.get("name", "")).strip()
            levels = raw.get("levels")
            if not name:
                raise ValueError("Manipulated factor requires a non-empty 'name'")
            if name in factors:
                raise ValueError(f"Duplicate manipulated factor {name!r}")
            if not isinstance(levels, Sequence) or isinstance(levels, (str, bytes)) or not levels:
                raise ValueError(f"Manipulated factor {name!r} requires non-empty 'levels'")
            factors[name] = tuple(levels)

        controls = payload.get("controlled_variables", {})
        if not isinstance(controls, Mapping):
            raise ValueError("'controlled_variables' must be an object")

        raw_cells = payload.get("cells")
        if not isinstance(raw_cells, Sequence) or isinstance(raw_cells, (str, bytes)):
            raise ValueError("'cells' must be a list")
        cells = tuple(ExperimentCell.from_dict(item) for item in raw_cells)
        if not cells:
            raise ValueError("Experiment plan must declare at least one cell")

        assertions = payload.get("preflight_assertions", ())
        if not isinstance(assertions, Sequence) or isinstance(assertions, (str, bytes)):
            raise ValueError("'preflight_assertions' must be a list")

        plan = cls(
            **required_strings,
            manipulated_factors=factors,
            controlled_variables=dict(controls),
            cells=cells,
            required_manifest_assertions=tuple(dict(item) for item in assertions),
        )
        plan.validate()
        return plan

    @classmethod
    def from_json(cls, path: str | Path) -> ExperimentPlan:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("Experiment plan JSON root must be an object")
        return cls.from_dict(payload)

    def validate(self) -> None:
        """Validate cell IDs, factor names, and factor levels."""
        ids = [cell.id for cell in self.cells]
        if len(ids) != len(set(ids)):
            raise ValueError("Experiment cell IDs must be unique")

        declared_names = set(self.manipulated_factors)
        for cell in self.cells:
            unknown = set(cell.factors) - declared_names
            if unknown:
                raise ValueError(f"Cell {cell.id!r} uses undeclared factor(s): {sorted(unknown)}")
            for factor_name, level in cell.factors.items():
                if level not in self.manipulated_factors[factor_name]:
                    raise ValueError(
                        f"Cell {cell.id!r} uses undeclared level {level!r} "
                        f"for factor {factor_name!r}"
                    )

    def assert_runner_cells(self, runner_cells: Sequence[Mapping[str, Any]]) -> None:
        """Fail when a runner's treatment matrix differs from the protocol.

        ``runner_cells`` uses the same shape as the plan's ``cells`` items:
        ``{"id": "...", "factors": {...}}``. Order is intentionally ignored
        because a valid runner may counterbalance or randomise execution order.
        """
        actual = tuple(ExperimentCell.from_dict(item) for item in runner_cells)
        expected_by_id = {cell.id: cell.factor_key for cell in self.cells}
        actual_by_id = {cell.id: cell.factor_key for cell in actual}

        if len(actual_by_id) != len(actual):
            raise AssertionError("Runner generated duplicate experiment cell IDs")
        if actual_by_id != expected_by_id:
            missing = sorted(set(expected_by_id) - set(actual_by_id))
            extra = sorted(set(actual_by_id) - set(expected_by_id))
            changed = sorted(
                cell_id
                for cell_id in set(expected_by_id) & set(actual_by_id)
                if expected_by_id[cell_id] != actual_by_id[cell_id]
            )
            raise AssertionError(
                "Runner cell matrix does not match experiment plan: "
                f"missing={missing}, extra={extra}, changed={changed}"
            )
