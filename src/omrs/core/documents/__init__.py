"""Document-graph subsystem.

Namespace grouping for the document similarity graph and supporting modules.
This is a structural grouping, not a strategy folder: there is no registry,
no ``register()`` API, and no pluggable backends. The modules here build a
NetworkX graph of document-chunk relationships from embedding similarity and
metadata edges.

Modules:
    doc_graph: document graph construction and community detection.

All settings are received by injection (EffectiveSettings) after group 5.
"""

from __future__ import annotations
