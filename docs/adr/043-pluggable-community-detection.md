# ADR-043: Pluggable Community Detection

**Date:** 2026-08-14
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

Both graph consumers, the codebase code graph and the document similarity
graph, called NetworkX Louvain directly. Neither call passed a seed, so
uncached partitions were non-deterministic: repeated runs on the same graph
could return different memberships. There was no extension point, so an
operator who wanted Leiden had no way to select it without coupling external
dependencies into both graph subsystems.

The architecture already required registry dispatch for named strategies,
injected frozen settings, acyclic integration leaves, deterministic graph
construction, and no cross-import between the codebase and document graph
subsystems. Any solution had to satisfy all five at once.

Leiden also had to stay out of the base installation. The project is
local-first and CPU-first, and the base install must not grow scientific
dependencies for an algorithm most operators never select.

## Decision

### Shared strategy package under `core/community/`

`core/community/` owns the flat partition contract, the lazy strategy
registry, and partition validation. A strategy is a callable that takes a
graph and a seed and returns `list[set[Hashable]]`: every node appears in
exactly one non-empty community. Algorithm-specific objects (igraph
partitions, leidenalg results) never cross this boundary.

Both graph consumers dispatch through `partition_graph` and keep everything
else. Graphs with fewer than five nodes bypass partitioning (existing
single-community behaviour). Labels, categories, edge counts, hubs, bridges,
and cross-links are formatted by the consumers after the partition returns.

### Seeded Louvain as the default

The built-in Louvain strategy calls NetworkX with the injected seed. The
default seed is `0`, which makes partitions deterministic and satisfies the
deterministic-graph invariant. Louvain stays the default algorithm and needs
only base dependencies.

### Leiden as an optional strategy behind a lazy adapter

`core/community/leiden.py` delegates at call time to
`integrations/leidenalg.py`, an acyclic integration leaf that imports neither
`core/` nor any other project module. The heavy imports (`leidenalg`,
`igraph`) happen inside the functions, so importing the adapter, resolving it
through the registry, or running a base installation never pulls either
package into `sys.modules`.

The NetworkX-to-igraph conversion preserves stable node identifiers (index
map, membership mapped back to originals), isolated nodes, edge weights, and
the injected seed. It runs `RBConfigurationVertexPartition` at γ=1.0, matching
Louvain's default resolution.

### Explicit selection, no fallback

`COMMUNITY_ALGORITHM` selects the strategy; `COMMUNITY_SEED` (default `0`)
controls algorithm randomness. Both are cross-cutting flat settings injected
through `EffectiveSettings`. `compose.py` validates the name against the
registry at startup and probes optional-dependency availability once.
Selecting `leiden` without the extra installed fails startup with the
installation instruction (`uv sync --extra community-leiden`). Runtime
fallback to Louvain is rejected: an explicit algorithm setting is an operator
contract. There is no `auto` value, because optional-package installation
must not change graph output silently.

### Dependency floors

Research (task 3.1) fixed the floors at `leidenalg>=0.11.0` and
`igraph>=1.0.0`. leidenalg 0.11+ pins `igraph<2.0,>=1.0.0`, so the pair
cannot straddle the igraph 1.x boundary. The lock currently resolves
leidenalg 0.12.0 and igraph 1.0.0, which passes the one-minor drift rule in
`tests/test_dependency_floors.py` without an exemption. Both packages ship
abi3 wheels covering the supported Python and platform matrix (macOS
arm64/x86_64, manylinux x86_64/aarch64, musllinux except aarch64 for
leidenalg, Windows x86_64). Combined download is roughly 4 to 9 MB. The
`seed=` parameter on `find_partition` was confirmed in the 0.10.2, 0.11.0,
and 0.12.0 sources.

### Experiment

`experiments/leiden-vs-louvain-2026-08-14/output/results.md` compared both
algorithms through `partition_graph` at seed 0, five repeats per cell. On the
codebase-style graph (96 nodes, 208 edges) both found 8 communities, largest
community 12, no singletons, internal edge share 0.9231; median runtimes were
3.09 ms (Louvain) and 3.95 ms (Leiden). On the document-style graph (92
nodes, 192 edges) both found 8 communities, largest 15, 2 isolated nodes,
internal edge share 0.9375; medians were 2.76 ms and 3.42 ms. Both
algorithms were deterministic across all five runs, and every partition was
complete, disjoint, and non-empty. Partitions were equivalent; the runtime
difference is sub-millisecond per graph build.

## Alternatives considered

| Option | Rejected because |
|--------|-----------------|
| **NetworkX Leiden dispatch** | NetworkX exposes the dispatch API only from 3.6, the project supports 3.2, and NetworkX ships no default implementation: it needs an external backend such as cuGraph, which is unsuitable for a CPU-first baseline |
| **`graspologic` hierarchical Leiden** (the LlamaIndex GraphRAG cookbook path) | This change needs a flat partition, not a hierarchy, and graspologic pulls in SciPy and scikit-learn as new transitive dependencies |
| **Local algorithm port** | Algorithm maintenance and correctness for Leiden exceed this project's responsibility |
| **Direct seeded Louvain in each consumer, no registry** | Duplicated dispatch, seeding, and validation would drift between the two graph subsystems, and the registry-dispatch invariant forbids it |
| **`auto` selection (pick Leiden when installed)** | Optional-package installation would silently change graph output; selection must be explicit |
| **Do nothing** | Unseeded partitions stay non-deterministic and Leiden stays impossible without forking both graph modules |

## Consequences

### Positive

- Deterministic partitions by default: same graph, same settings, same
  membership, for both graphs and both algorithms.
- One flat contract lets a new algorithm register with one file and one
  `register()` call; consumers need no algorithm-specific branch.
- Leiden is available without adding anything to the base installation, and
  the lazy adapter keeps `leidenalg`/`igraph` out of a base install's import
  surface.
- Startup fails with an actionable instruction instead of a runtime crash or
  a silent algorithm swap.

### Negative

- Seeded Louvain can produce a different first partition from a previous
  unseeded run. The codebase-map cache is keyed by git commit hash, so the
  partition rebuilds the next time the commit changes; an old cached
  partition persists until then.

### Neutral

- No migration of stored vectors or documents; community detection writes no
  persisted data outside the codebase-map cache.
- The flat `list[set[Hashable]]` contract is stable and validated on every
  call, so future strategies are checked against complete, disjoint,
  non-empty coverage for free.

## Verification

- Shared strategy-contract tests (`tests/test_community_strategies.py`) cover
  dispatch through both consumers, determinism, unknown names, missing-extra
  failure, weighted and isolated-node graphs, and the no-LLM and
  no-algorithm-object-leak boundaries.
- Baseline partition-contract tests (`tests/test_community_baseline.py`) lock
  the output shapes (labels, edge counts, hubs, bridges, categories) across
  the strategy extraction.
- Subprocess import checks confirm the boundary from the test side: community
  modules, both consumers, and the adapter import neither `llama_index` nor
  `rag_mcp.core.providers`, and a base install never loads `leidenalg` or
  `igraph` into `sys.modules`. Formal import-linter coverage for
  `core.community` (task 5.1) is still open at the time of writing.
- Dependency floors pass `tests/test_dependency_floors.py` and the `floors` CI
  job.

## References

- OpenSpec change: `openspec/changes/add-pluggable-community-detection/`
- Experiment: `experiments/leiden-vs-louvain-2026-08-14/output/results.md`
- Registry: `src/rag_mcp/core/community/registry.py`
- Adapter: `src/rag_mcp/integrations/leidenalg.py`
- Related: [ADR-022](./022-code-graph-via-tree-sitter-ast.md),
  [ADR-023](./023-document-graph-via-embedding-similarity.md),
  [ADR-037](./037-architecture-v2-conformance.md),
  [ADR-042](./042-dependency-floor-integrity.md)
