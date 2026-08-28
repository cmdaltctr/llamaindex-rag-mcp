# Louvain vs Leiden comparison (task 3.6)

Seed 0, 5 repeats per cell, via ``core.community.partition_graph``.
Leiden: leidenalg RBConfigurationVertexPartition (γ=1.0), igraph backend.

| Graph | Algorithm | Nodes | Edges | Communities | Largest | Singletons | Internal edge share | Median runtime (ms) | Deterministic |
|---|---|---|---|---|---|---|---|---|---|
| codebase-style | louvain | 96 | 208 | 8 | 12 | 0 | 0.9231 | 2.84 | True |
| codebase-style | leiden | 96 | 208 | 8 | 12 | 0 | 0.9231 | 3.84 | True |
| document-style | louvain | 92 | 192 | 8 | 15 | 2 | 0.9375 | 2.47 | True |
| document-style | leiden | 92 | 192 | 8 | 15 | 2 | 0.9375 | 2.81 | True |

## Notes

- Both strategies satisfied the flat partition contract on every run
  (complete, disjoint, non-empty coverage, including isolated nodes).
- Determinism: all repeats returned identical memberships for both
  algorithms at seed 0.
- Runtime difference at this scale is milliseconds; see ADR-044 for
  the selection rationale (quality of partitions, not speed, drives
  the optional-extra offer).
