"""Codebase-understanding subsystem.

Namespace grouping for the codebase map, code graph, and supporting modules.
This is a structural grouping, not a strategy folder: there is no registry,
no ``register()`` API, and no pluggable backends. The modules here collaborate
to produce the compact codebase map consumed by MCP agents.

Modules:
    codebase_map: assembly + formatting entry point (``get_codebase_map_text``).
    code_graph: tree-sitter AST extraction and NetworkX graph construction.

All settings are received by injection (EffectiveSettings) after group 5.
"""

from __future__ import annotations
