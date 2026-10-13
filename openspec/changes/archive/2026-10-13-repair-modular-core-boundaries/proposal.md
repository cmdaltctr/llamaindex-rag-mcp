# Proposal: Repair modular core boundaries

## Why

Verified dispatch and dependency leaks would make executable graph stages and isolated experiments use the wrong implementation or store. Repair these narrow correctness defects before implementing `add-local-web-pipeline-workspace`.

## What Changes

- Route both structured and unstructured document splitting through the registered sentence strategy. Preserve reader-declared Markdown, heading processing, chunk overrides, content-type precedence, and metadata-degradation reporting.
- Forward the ingestion Engine's store through metadata dispatch, every supported classification backend, fallback paths, and the shared category prompt. Category lookup scans all collections of that supplied store.
- Define store-less standalone classification as seed-only. It does not consult a process-default store or report missing-store degradation.
- Pass explicit settings and store context through codebase-map generation, document-graph thresholds, and cache load/save. Legacy MCP defaults are resolved in its transport boundary; its tool signature remains unchanged.
- Move `FileInventory` and `CodebaseMap` into a data-only module and retain existing map imports as re-exports. Fresh import order must not affect success.
- Preserve cache payloads, filenames, Git-commit validation, and non-Git behaviour. Reuse a cache only when its owner/settings context is proven; unscoped old records are safe misses, not automatic deletions.
- Add production-dispatch, captured-prompt, explicit-cache-context, fresh-import, and strengthened dependency-guard regressions. Existing passing file/import checks remain useful alongside these cases.

No new dependencies, public Engine methods, MCP parameters, or RAG defaults are required. Existing vector data and experiment evidence remain untouched. Large orchestration extraction stays in the web change.

## Capabilities

### New Capabilities

None. This repairs and strengthens existing contracts.

### Modified Capabilities

- `modular-core-extraction`: Document splitting must exercise the selected registered strategy; metadata strategies receive an optional keyword-only store without changing existing positional settings arguments.
- `metadata-extraction`: Existing-category prompts use the supplied store rather than a global or Chroma-specific client, with explicit seed-only standalone behaviour.
- `settings-dependency-injection`: Codebase/cache leaves receive explicit settings; guards detect forbidden default accessors as well as configuration-singleton reads.
- `internal-maintainability`: Codebase helpers import independently; cache reuse respects supplied context; retire the obsolete metadata-owned Chroma client-cache requirement.

## Impact

**Source:** `core/ingestion/{pipeline,chunker}.py`, metadata dispatcher/backends/prompt/taxonomy, `core/codebase/{codebase_map,cache}.py`, a small shared models module, and the MCP codebase wrapper. Registry dispatch and existing domain algorithms are reused. No graph runner or web runtime is added here.

**Compatibility:** Preserve existing caller-visible metadata/result shapes, registered strategy names, map model imports, MCP errors, path checks, and replacement behaviour. Internal map/cache callers will pass context explicitly. Metadata callers retain their existing positional arguments; context-free calls use seed categories. Custom internal metadata strategies must accept the documented optional store keyword.

**Cache:** Owner context is an additive cache-envelope check. Missing or unverifiable context causes recomputation. It does not migrate vector stores or change source/index identities.

**Verification:** Reuse the previously reproduced gaps, then write failing regression tests before fixes. Test structured/plain/Markdown paths, interleaved disjoint stores, no/poisoned defaults, provider fallbacks, two cache directories and shared-directory context mismatches, and fresh subprocess import orders.

**Sequence:** Implement, verify, and integrate this repair first. The web plan checks the resulting commit and regression evidence before resource-backed graph work. A new session can apply this change without implementing the web plan.

**Excluded:** Per-source orchestration extraction, broad clean-up, new algorithms, cache services, automatic re-indexing, web/SQLite/plugin code, dependency upgrades, and optimisation.
