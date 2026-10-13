# Design: Repair modular core boundaries

## Context

See `proposal.md` for scope. This change prepares existing operations for the separate web plan. Implementation is reserved for a new session.

The review used `v3` at `1b5b747`. It reproduced these paths:

| Evidence | Observed behaviour |
|---|---|
| `core/ingestion/chunker.py:129-142,180-191` | Both document branches call private sentence helpers directly; a registered replacement is ignored. |
| `core/chunking/sentence.py:70-129` | The registered callable already accepts reader-produced documents and owns Markdown post-processing. |
| `core/ingestion/pipeline.py:348-358` | Settings reach the chunker, but the owning store does not. |
| `core/metadata/{extractor,taxonomy,ollama}.py` | Metadata dispatch has no store argument; category gathering reads the default store; its error is swallowed into seed-only lookup. |
| `core/codebase/cache.py:20,61,93` | Cache imports map models and reads default settings independently. |
| `core/codebase/codebase_map.py:292,334,352,373,455-459` | Map construction uses defaults and omitted document thresholds, then re-imports cache helpers. |
| `tests/test_no_global_settings_reads.py` | The guard covers config singleton/getter spellings, not default-effective-settings or default-store leaf reads. |

The existing 22 focused tests, eight import contracts, and 183-file size check passed. Fresh cache-first import failed; map-first succeeded. These are review results, not proof that the repair is implemented.

Graphify exposes the extracted call edge from `_build_ollama_prompt` to `_gather_existing_categories`. Source inspection and offline probes establish the defect; the graph alone does not establish runtime isolation.

## Goals / Non-Goals

**Goals**

- Production document dispatch honours registered replacements.
- Engine-driven classification and codebase mapping use supplied dependencies.
- Existing map model imports work in either fresh import order.
- Tests detect these exact regressions, including swallowed global-access failures.

**Non-Goals**

- Graph execution, web code, plugins, new strategies, or dependency changes.
- Splitting the 410-line ingestion or 306-line search orchestration functions.
- Automatic index repair, reclassification of stored chunks, or editing experiment evidence.
- Removing every documented legacy boundary fallback throughout the package.

## Decisions

### D1. Use the existing document strategy contract

Resolve `sentence` through the chunking registry after the existing reader/content-type decision. Await the callable with the documents, logging path, Markdown declaration, effective sizes/settings, and resolved Markdown chunking value.

Use that callable in both structured and unstructured branches. It already performs splitting and Markdown post-processing. Remove the chunker's duplicate helper invocation; do not apply post-processing twice. Retain metadata attachment and `_ChunkResult` degradation reporting in their existing owner.

Keep code/config routing and `.md` or reader-declared Markdown precedence. Do not introduce a new strategy interface or read the file a second time. Replacement tests must prove the production dispatcher invokes a registered sentinel, including through ordinary ingestion.

### D2. Add one optional store keyword through metadata

Add an optional keyword-only `store` to the chunker, metadata entry points/local dispatch, registered backends, and shared prompt builder. Preserve their existing positional settings arguments. Forward the already resolved ingestion store, including through LlamaIndex's local/keyword fallback paths.

Keyword and disabled modes do not need category lookup, but their callable signatures remain compatible with dispatch. Custom internal strategy doubles and documentation must accept the same keyword. Do not use signature inspection or name-specific branching to accommodate obsolete doubles.

Category lookup receives a supplied store or no store. With a store, scan all its collections through `VectorStore`, preserving paging, normalisation, sorting, and failure handling. Without a store, return no stored labels and use seed categories. Omission is not an error and does not mark metadata degraded. A real supplied-store failure keeps the existing warning/seed fallback.

Keep optional settings resolution at the existing documented metadata entry boundary. Once resolved, forward settings explicitly; leaves do not fetch defaults. Do not construct clients in taxonomy, attach store handles to pure-data settings, or install process defaults to make tests pass.

Test captured prompts with two disjoint stores and seed configurations. Use fake model completions; real model/API calls are unnecessary. Poisoned or absent defaults must not affect the supplied-store path.

### D3. Inject the codebase context end to end

The existing MCP handler obtains its resolved settings/store inside its error boundary and passes them to core. Its `path`, `refresh`, annotations, and JSON error shape remain unchanged.

Give core map entry points explicit keyword context. Preserve existing positional path/refresh arguments; update internal callers and tests to supply dependencies. A deliberate store-less map can produce inventory/code information with empty document communities, never a hidden default-store query. Settings resolution remains at a documented entry boundary; explicit callers bypass defaults entirely.

Forward settings to detection and community selection, and pass `doc_similarity_threshold` to both document-graph calls. Pass the cache-directory value and cache context to load/save. These leaves never obtain default settings. Do not change root-path validation, source discovery, graph algorithms, or output formatting.

### D4. Move shared model definitions only

Create `core/codebase/models.py` for `FileInventory` and `CodebaseMap`. Keep their fields, defaults, methods, and map-module re-exports. `FileEntry` stays in `integrations/magika.py`.

Cache imports the shared model module directly. The map facade imports those same classes. A typing-only cache import would not work because deserialisation constructs the models. No general package rearrangement is needed.

Verify fresh subprocess imports in both cache-first and map-first orders. Also retain formatter imports and existing class-import/round-trip tests.

### D5. Cache reuse must prove its context

The commit remains a required cache key. Keep the cache filename and serialised map payload. Add a small owner-context field in the cache envelope, supplied from the map boundary. It identifies effective map settings and the actual supplied store/collection, using existing identity/validity surfaces rather than a global store or a guessed URI from settings.

A cache hit requires matching commit and proven context. Missing old context, mismatched settings/store, or an unavailable reliable context is a miss. Preserve old files until an explicit map build replaces its ordinary cache; do not delete them eagerly. Non-Git paths remain uncached.

An opaque process-local identity does not prove cross-process ownership. Where a durable owner/validity context cannot be established, disable persistent reuse for that context. This favours correct output over a speculative cache hit. Document any reduced reuse. No cache service, schema migration framework, or new vector-store requirement is needed.

Test separate cache directories and the same directory with different owner contexts. The latter prevents injection tests from passing while returning another Engine's cached document map.

### D6. Strengthen guards at real leaves

Extend the existing tests with AST-aware detection of default accessors and aliases in the repaired leaves and unconditional map paths. Preserve narrow documented compatibility boundaries such as `core.settings.resolve_effective_settings`; do not add a package-wide ban that flags sanctioned boundary resolution or a broad module exemption that hides leaf calls.

Guard fixtures must fail for direct, qualified, aliased, and function-local forbidden reads. Behavioural tests with poisoned defaults remain necessary because static checks cannot prove the runtime value is correct.

### D7. Keep repair and web responsibilities separate

The repair owns the three correctness fixes and their regressions. Web tasks reuse the repaired callables and context contract. Per-source extraction, graph events, cancellation leases, stage fingerprints, and marimo remain in the web change.

Before applying the web plan, verify this repair's tested implementation is integrated into its base checkout. Archive location or checked tasks alone do not prove integration. Read the repair commit and recorded regression results, then run the focused gate on the target base. Reconcile overlapping `modular-core-extraction` deltas against the repaired baseline so archiving the web change retains the repair's tests/scenarios.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Markdown hooks run twice or metadata markers disappear. | Compare old/new output fixtures and test both production branches. |
| One backend or fallback loses the store keyword. | Capture prompts across Ollama, llama.cpp, OpenRouter, and both LlamaIndex fallbacks using stubs. |
| Standalone calls still query a global store. | Seed-only omission contract and poisoned-default tests. |
| Cache context does not describe the actual store. | Use supplied store identity; test shared-directory owner mismatches; fail closed if context is unproven. |
| Legacy cache reuse decreases. | Preserve files/payloads and document safe recomputation; vectors remain untouched. |
| Model movement breaks import or test patch targets. | Keep class re-exports; patch functions in their owning modules; test fresh import orders. |
| Existing helper tests continue hiding the bypass. | Assert sentinel calls through real dispatch, not through a private helper shared by both test paths. |

## Migration Plan

1. Create the approved feature worktree and retain environment files unchanged.
2. Add regressions and observe their failures before implementing each fix.
3. Apply narrow source changes and update signature-sensitive tests and guides.
4. Run focused checks, strict OpenSpec validation, and the approved broader repository gate.
5. Record verification and integrate the repair before starting the web implementation.

No dependency installation, vector migration, or automatic re-index is part of this repair. Existing metadata reflects its original extraction until an operator explicitly re-ingests a source. Rollback restores code and preserves cache/vector/experiment files.

## Verification Record Required

The implementation session must record test commands and results, before/after failure evidence, its tested commit, and the checkout where it was integrated. Include fresh import-order checks, production sentence replacement, owning-store prompts, fallback forwarding, cache context, and forbidden default accessors. Leave web tasks unchecked.
