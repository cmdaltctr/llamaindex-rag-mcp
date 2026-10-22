"""Approved experiment contexts for notebook runs (design D10).

Pure core rules: the context registry with approval records, workspace
path checks, leases, revocation and the admission guard. Composition
builds one Engine per context (``omrs.compose_experiments``).
"""

from __future__ import annotations

from .admission import BackendIdentity, check_credential_target, check_experiment_snapshot
from .contexts import (
    DEFAULT_STORE_BACKEND,
    EXPERIMENT_ACTIONS,
    OUTPUT_DIR_NAME,
    STORE_FACTOR,
    ExperimentContext,
    ExperimentLease,
    ExperimentRegistry,
    resolve_workspace,
    verify_containment,
)
from .errors import ExperimentAdmissionError, ExperimentPathError
from .folders import MAX_FOLDER_DEPTH, create_folder, folder_tree, split_folder_path

__all__ = [
    "DEFAULT_STORE_BACKEND",
    "EXPERIMENT_ACTIONS",
    "MAX_FOLDER_DEPTH",
    "OUTPUT_DIR_NAME",
    "STORE_FACTOR",
    "BackendIdentity",
    "ExperimentAdmissionError",
    "ExperimentContext",
    "ExperimentLease",
    "ExperimentPathError",
    "ExperimentRegistry",
    "check_credential_target",
    "check_experiment_snapshot",
    "create_folder",
    "folder_tree",
    "resolve_workspace",
    "split_folder_path",
    "verify_containment",
]
