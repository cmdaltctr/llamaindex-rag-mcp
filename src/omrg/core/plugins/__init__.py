"""External-tool plugins: constrained manifests, registration and editor supervision.

This package is pure core logic (design D10). It reads manifest and
executable files to hash them, but it never starts a process itself:
composition injects a probe runner and a process launcher from
``omrg.integrations.process_launcher``. It imports no ``subprocess``,
``socket``, ``sqlite3``, web framework or notebook runtime.
"""

from __future__ import annotations

from omrg.core.plugins.editor import (
    EditorSession,
    LaunchPlan,
    NotebookEditorSupervisor,
    PluginConsentError,
    PluginLaunchError,
    ProcessLauncher,
    build_launch_plan,
)
from omrg.core.plugins.manifest import (
    REQUIRED_LAUNCH_CAPABILITIES,
    SUBSTITUTIONS,
    ManifestError,
    PluginManifest,
    parse_manifest,
    parse_version,
)
from omrg.core.plugins.registration import (
    COMPATIBLE,
    INCOMPATIBLE,
    NEEDS_APPROVAL,
    UNAVAILABLE,
    UNCHECKED,
    ExecutableIdentity,
    PluginRegistry,
    PluginState,
    PluginTrustError,
    ProbeOutput,
    ProbeRunner,
    inspect_executable,
)

__all__ = [
    "COMPATIBLE",
    "INCOMPATIBLE",
    "NEEDS_APPROVAL",
    "REQUIRED_LAUNCH_CAPABILITIES",
    "SUBSTITUTIONS",
    "UNAVAILABLE",
    "UNCHECKED",
    "EditorSession",
    "ExecutableIdentity",
    "LaunchPlan",
    "ManifestError",
    "NotebookEditorSupervisor",
    "PluginConsentError",
    "PluginLaunchError",
    "PluginManifest",
    "PluginRegistry",
    "PluginState",
    "PluginTrustError",
    "ProbeOutput",
    "ProbeRunner",
    "ProcessLauncher",
    "build_launch_plan",
    "inspect_executable",
    "parse_manifest",
    "parse_version",
]
