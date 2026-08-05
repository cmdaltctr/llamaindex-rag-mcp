## Context

Phases 1–5 of the modular refactor shipped as ADR-032 … ADR-036. A conformance
audit compared the resulting tree against the agreed target in
`docs/brainstorm/refactor-proposal/PROPOSAL.md` (§4 the architectural pattern,
§5.1 the folder tree, §6.2/§6.3.1 profiles) and `architecture-diagrams.md`
(Diagrams 1–4). Eleven findings (F1–F11) plus two structural categories
(A: 15 deprecated shims; B: 3 unmigrated v1 modules) were confirmed with
`file:line` evidence.

The shape of the gap is consistent: the **structures** exist (registries,
`compose.py`, `core/vectordb/`, `core/profiles/`, subpackage `settings.py`
models) but they are **not load-bearing**. Dispatch bypasses the registries;
`core/` reaches around dependency injection to a module-level global; `config/`
imports business logic to answer a runtime probe; the abstraction over ChromaDB
is bypassed by one caller. Nothing in CI notices, because the three existing
import-linter contracts at `pyproject.toml:86-135` do not cover any of it.

This change makes the existing structures load-bearing, deletes the v1 surface
that ADR-032's grace period preserved, and adds contracts so the gaps cannot
reopen. It is the last change before v2.0.0.

Two user decisions are settled inputs, not open questions:

1. **F4 conforms.** `EffectiveSettings` is threaded through the operation
   signatures per PROPOSAL §6.3.1:790. Not deferred to a follow-up.
2. **F7+F8 conform as a hard break.** Nested `Settings` per §4.3, nested profile
   YAML per §6.2, no flat-key fallback and no deprecation path. This change
   writes the migrated YAML itself.
3. **Category A deletes now.** All 15 shims plus the PEP 562 alias table, as
   `refactor!:` → v2.0.0, overriding PROPOSAL §11 Decision 2.

## Goals / Non-Goals

**Goals:**

- Close F1–F11, Category A, and Category B so the implemented tree matches
  PROPOSAL §5.1 and §4.
- Make registries the only strategy dispatch path in production code.
- Remove every process-wide settings read and import-time settings snapshot
  from `core/` and `integrations/`.
- Reduce `config/__init__.py` to a ~150-line typed resolver with no imports
  from `core/` business logic and no object construction.
- Confine ChromaDB to `core/vectordb/chroma.py`.
- Make every closed finding enforceable by `lint-imports` or a test, not by
  convention.
- Correct the ADR/doc claims the audit falsified, and record ADR-037.

**Non-Goals:**

- No new retrieval, chunking, or metadata behaviour. Retrieval quality,
  threshold calibration (÷30, AGENTS.md gotcha #3), and profile lever *values*
  are unchanged.
- No REST transport implementation (`transports/api/` stays contract-only).
- No new vector store implementation — only the confinement of the existing one.
- No repair of archived `experiments/*/run_eval.py` scripts (user decision 3).
- No new runtime dependency. PyTorch stays banned; ONNX only.
- `structural.py` / `evidence_md.py` chunking strategies stay deferred
  (PROPOSAL §5.2 H5).

## Decisions

### D1 — `EffectiveSettings` becomes the single settings value object passed into `core/`

**Decision.** Promote the existing `EffectiveSettings`
(`src/rag_mcp/core/profiles/resolver.py:48`) from a Tier-2-levers-only model
into the complete, frozen settings value object that `core/` consumes, and move
it to `src/rag_mcp/core/settings.py` (pure data, no upward imports). It composes
the three subpackage models plus the cross-cutting fields `core/` actually
needs (embed/collection/storage identifiers, magika binary, PDF reader,
document backend, thresholds).

`search()` (`core/retrieval/pipeline.py:148`) and `ingest_path_async()`
(`core/ingestion/pipeline.py:25`) already accept `effective_settings`
(`core/ingestion/pipeline.py:31`, typed `Any`). This change types it as
`EffectiveSettings`, makes it **required** on the internal call path, and
propagates it to every callee that today does
`from ...config import settings` — the 21 sites listed in the audit, including
`core/ingestion/_state.py:17`, `core/ingestion/chunker.py:19`,
`core/retrieval/policy.py:61,225`, `core/retrieval/reranker.py:36`,
`core/retrieval/fusion.py:9`, `core/metadata/{extractor,keyword,ollama,
llamaindex,llamacpp}.py`, `core/vectordb/chroma.py:74,197`,
`core/profiles/resolver.py:263`, `integrations/magika.py:25`,
`integrations/azure.py:18`, `integrations/pdf/liteparse.py:45`.

**Why over the alternatives.** A `contextvars`-based ambient context was
considered: less churn, but it is the same global read wearing a disguise and
would leave §4.1 Layer 3 unmet and untestable by inspection. Passing loose
keyword levers (today's partial approach) was considered: it does not scale —
`policy.py` alone needs four levers, and each new knob re-opens every signature
in the chain. One frozen object is the PROPOSAL §6.3.1:790 contract verbatim.

**Boundary.** `ProfileResolver.resolve(collection)` remains the producer for
profile-bound operations; `compose.py` produces the server-default instance for
paths with no collection (e.g. codebase map). `core/profiles/resolver.py:263`'s
`from ...config import settings` is replaced by the server-default profile name
injected at construction.

### D2 — Registries are the sole dispatch; `register()` is the only registration API

**Decision.** Replace the eager imports at `core/ingestion/chunker.py:25-32`,
the if/elif chain at `core/metadata/extractor.py:36-39` and `:187-193`, and the
eager imports at `core/retrieval/pipeline.py:19-27` with
`registry.get(name)` calls. Each of `core/chunking/registry.py`,
`core/metadata/registry.py`, `core/retrieval/registry.py` exposes
`register(name, import_path)`, `get(name)`, `available()` and makes the
`REGISTRY` dict private (`_registry`), matching the provider registries already
wired at `compose.py:21,47,68` and the contract in PROPOSAL §4.4.

**Why.** The registries exist and are tested (`tests/test_registry_contract.py`)
but have zero production consumers — the audit's F1. Wiring them is what makes
PROPOSAL §4.4 rules 2, 4 and 5 true, and is the precondition for "add a strategy
by dropping in a file", the stated purpose of the whole refactor (§2.1).

**Trade-off accepted.** Lazy `importlib` resolution is invisible to
import-linter, so the `providers-constructed-only-in-compose` contract's
`ignore_imports` pattern is extended rather than tightened. Coverage of lazy
edges is asserted by the registry contract tests instead.

### D3 — Nested `Settings`, nested YAML, renamed subpackage env vars

**Decision.** `Settings` changes from
`class Settings(ChunkingSettings, RetrievalSettings, MetadataSettings, BaseSettings)`
(`config/__init__.py:186`) to nested composition:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__", ...)
    chunking: ChunkingSettings = ChunkingSettings()
    retrieval: RetrievalSettings = RetrievalSettings()
    metadata: MetadataSettings = MetadataSettings()
    # cross-cutting flat fields unchanged: embed_model, chroma_persist_dir, ...
```

Consequences, all deliberate:

- Env vars for subpackage fields are renamed: `TOP_K` → `RETRIEVAL__TOP_K`,
  `CHUNK_SIZE` → `CHUNKING__CHUNK_SIZE`, `METADATA_EXTRACTION_MODE` →
  `METADATA__EXTRACTION_MODE`, and so on. Cross-cutting names
  (`EMBED_MODEL`, `CHROMA_PERSIST_DIR`, `RAG_PROFILE`, `PDF_READER`,
  `VECTOR_STORE`, `DOCUMENT_BACKEND`, `COLLECTION_NAME`, the provider and Azure
  keys) are unchanged.
- Three redundant prefixes are dropped inside the models now that the block name
  carries them: `metadata_extraction_mode` → `metadata.extraction_mode`,
  `metadata_keyword_rules` → `metadata.keyword_rules`,
  `metadata_taxonomy_mode` → `metadata.taxonomy_mode`,
  `chunk_strategy_fallback` → `chunking.strategy_fallback`.
- `_YamlDefaultsSource` and `_ProfileYamlSettingsSource` stop flattening
  SCREAMING_SNAKE keys and deep-merge nested mappings instead.
- `config/defaults.yaml` and all three `config/profiles/*.yaml` are rewritten
  nested. Precedence is unchanged: model defaults < `defaults.yaml` <
  selected profile < `.env` < process env < explicit args.

**Why a hard break over an alias shim.** `AliasChoices` could accept both flat
and nested names, but that reproduces exactly the state the audit criticises:
a documented target plus a live legacy path that nothing forces anyone off.
Since Category A already makes this a major release, the schema break costs one
migration note and buys a config surface that matches §4.3 with no dual
codepath. The user chose this explicitly.

**Deviation from PROPOSAL §6.2 recorded.** §6.2's example bundle writes
`retrieval.reranker_enabled`, `retrieval.hybrid`, `chunking.active_strategy`,
`metadata.mode`, `metadata.taxonomy`. This change keeps the semantically
accurate field names already in the models (`rerank_enabled`, `hybrid_enabled`,
`strategy_fallback`, `taxonomy_mode`) and does not introduce `metadata.mode`,
which in §6.2 conflates the provider mode with the extraction backend. The
**structure** (nested blocks validated against nested Pydantic models) conforms;
the leaf names are the existing, correct ones. ADR-037 records this.

### D4 — `config/` answers no runtime questions; `compose.py` does the probing

**Decision.** Delete `resolve_sparse_backend()` (`config/__init__.py:385`),
`resolve_pdf_reader()` (`:412`), their `_resolve_*` no-arg wrappers, and the
`RESOLVED_*` module constants. Move both probes into `compose.py`, which already
owns construction and may legitimately import `core.retrieval.sparse` and probe
optional packages. `config/__init__.py:395`'s
`from ..core.retrieval.sparse import _detect_native_sparse_capability`
disappears with them.

**Why.** F3: the import violates PROPOSAL §4.1/§4.3 and AGENTS.md's hard 🚫
"never modify `config.py` to depend on business logic". Capability probing is
construction-time behaviour, not settings data. `config/` keeps only the
sanctioned `*.settings` imports at lines 35-37.

### D5 — Category B relocation precedes everything that references the new paths

**Decision.** Move `codebase_map.py`(663) and `code_graph.py`(690) to
`core/codebase/`, and `doc_graph.py`(562) to `core/documents/`, per PROPOSAL
§5.1 — reversing the §12 "accepted deviation".

**Why the deviation is no longer acceptable.** §12 argued the grouping was
aesthetic. The audit shows it is load-bearing: `core/ingestion/pipeline.py:97`
does `from ...codebase_map import detect_file_types` — `core/` reaching
**upward** into a top-level module, which no import-linter contract can express
cleanly while the modules sit outside `core/`. Those three files also host F2
(the ChromaDB leak at `codebase_map.py:476-478`), F5 (the
`integrations/magika.py:81` cycle), and three of the five 500-line overruns.
Closing F2/F5/F11 without moving them means writing contracts against paths that
are about to change.

**Ordering consequence.** Relocation is task group 2, before the ChromaDB
confinement (group 6), the cycle break (group 6), the file splits (group 8), and
the import-linter contracts (group 10) that name `rag_mcp.core.codebase.*` and
`rag_mcp.core.documents.*`.

### D6 — Delete the v1 surface in one commit, do not repair experiments

**Decision.** Remove all 15 shim modules and the PEP 562 alias table
(`config/__init__.py:497-576`) in a single group, plus the coverage `omit`
entries in `pyproject.toml` that exist only for them. `tests/conftest.py:161`'s
`sys.modules.get()` lookup is updated to the `core.*` path.

The ~14 archived `experiments/*/run_eval.py` scripts that import v1 paths are
the only live consumers. They are dated, checkpointed historical artefacts,
never run in CI, and their results are already recorded in each experiment's
`results.md`. They are left broken by design; each experiment directory gets a
one-line note in its `README`/header pointing at the v2.0.0 boundary.

**Why now rather than a grace window.** PROPOSAL §11 Decision 2 promised "one
full minor-version cycle" after Phase 5. That window has no external consumers
to protect — the shims have zero inbound imports from `src/`, and the project is
a single-maintainer research codebase. Keeping them means the 500-line and
coverage gates carry permanent exemptions for dead files, which is precisely the
"documented target plus live legacy path" pattern this change exists to end.

### D7 — Enforcement: contracts first as failing, then satisfied

**Decision.** Add four import-linter contracts to `pyproject.toml` and one
ceiling test:

| Contract | Type | Closes |
| --- | --- | --- |
| `chromadb-confined-to-vectordb` | forbidden: `rag_mcp` → `chromadb`, ignoring `rag_mcp.core.vectordb.chroma` | F2 |
| `config-is-leaf` | forbidden: `rag_mcp.config` → `rag_mcp.core`, `rag_mcp.compose`, `rag_mcp.transports`, `rag_mcp.integrations`, `rag_mcp.daemon`, allowing only `rag_mcp.core.*.settings` | F3 |
| `integrations-are-leaves` | forbidden: `rag_mcp.integrations` → `rag_mcp.core`, `rag_mcp.transports`, `rag_mcp.daemon` | F5 |
| `core-business-avoids-providers-transports` (extended) | forbidden, source modules extended with `core.vectordb`, `core.profiles`, `core.codebase`, `core.documents`, `daemon` | enforcement gap |
| `test_file_size_ceiling` | pytest assertion over `src/rag_mcp/**/*.py` | F11 |

Contracts are added **before** the fixes in each group so the failing state is
observed first — a contract that was never seen to fail is not evidence.

**Why not a `layers` contract.** A single layered contract over
`transports > daemon > core > integrations > compose > config` is more elegant
but would fail today for reasons unrelated to this change (e.g. `compose` sits
above `core` but `core.profiles` legitimately references store handles), and a
broad failure is a worse signal than four targeted ones. A layers contract is
noted as future work in ADR-037.

### D8 — File splits are mechanical and behaviour-preserving

`code_graph.py` 690 → `core/codebase/code_graph.py` (graph assembly) +
`ast_extract.py` (tree-sitter extraction) + `communities.py` (deterministic
community detection). `codebase_map.py` 663 → `core/codebase/codebase_map.py`
(assembly) + `cache.py` (git-commit-keyed cache, AGENTS.md gotcha #9) +
`format.py` (rendering). `doc_graph.py` 562 → `core/documents/doc_graph.py` +
`similarity.py`. `daemon/watcher.py` 550 → `watcher.py` + `debounce.py`.
`config/__init__.py` 576 → ~150 via D3/D4/D6 alone, no split needed.

Graph construction stays deterministic with no LLM involvement (AGENTS.md
invariant #8).

### D9 — The config guard is `extra="forbid"` first, the legacy tripwire second

**Decision.** Two layers, with clearly separated jobs:

1. **`extra="forbid"` on the three subpackage models** (`ChunkingSettings`,
   `RetrievalSettings`, `MetadataSettings`). The root `Settings` stays
   permissive, because it legitimately carries cross-cutting flat keys
   (`EMBED_MODEL`, `RAG_PROFILE`, provider and Azure credentials) and must not
   reject unrelated process environment entries. This catches the **general
   case**: any unexpected `CHUNKING__*` / `RETRIEVAL__*` / `METADATA__*` key —
   a typo, a custom var, a name nobody enumerated — fails at settings
   resolution with Pydantic naming the offending field and listing the valid
   ones.
2. **The enumerated legacy tripwire** (~30 known pre-v2 flat names) covers the
   one case layer 1 structurally cannot see. A bare `TOP_K` in the environment
   never reaches `RetrievalSettings` at all — with `env_nested_delimiter="__"`
   it is simply an unrecognised root-level key — so no amount of subpackage
   strictness will catch it. The tripwire raises a `ValueError` naming the
   nested replacement.

**Why not the tripwire alone.** That was the earlier plan, and it was wrong:
an enumeration only catches what it enumerates, leaving every unlisted
subpackage key to be swallowed by `extra="ignore"` — reproducing the silent
failure mode this change exists to remove.

**Why not `extra="forbid"` alone.** It cannot see flat legacy names, which is
precisely the population of keys every existing `.env` is full of.

**Lifetime — decided, not deferred.** `extra="forbid"` is **permanent**; it is
part of the schema contract, not a migration aid. The enumerated tripwire is
**permanent through the v2.x line and removed in v3.0.0** — the next major, a
release that exists in the versioning scheme whether or not it is scheduled.
It is deliberately *not* tied to a hypothetical v2.1.0: pinning removal to an
unplanned minor is a non-decision, and would leave a legacy enumeration living
indefinitely inside a change whose entire thesis is that legacy paths must not
outlive their migration. ADR-037 records the removal trigger.

### D10 — `IngestionSettings` is created now, not deferred

**Decision.** `embed_concurrency` and `embed_batch_size` move out of
`ChunkingSettings` into a new `IngestionSettings` block
(`INGESTION__EMBED_CONCURRENCY`, `INGESTION__EMBED_BATCH_SIZE`), making a fourth
nested prefix.

**Why now.** These are ingestion concerns, not chunking concerns; they sit in
`ChunkingSettings` only because the flat schema had nowhere better. The earlier
plan deferred the move to avoid a fourth renamed prefix — but that reasoning
inverts the actual cost. **The rename cost is already being paid in full**: this
change rewrites every `.env`, every profile bundle, and `.env.example` anyway.
Placing these two fields correctly now costs two extra lines in the migration
table. Deferring costs a *second* breaking rename in a future release, for
which no other break would justify the disruption. Doing the honest thing is
cheapest at exactly the moment the schema is already breaking.

**Scope.** `IngestionSettings` is a pure-data model alongside its three
siblings, covered by the `settings-models-are-pure-data` contract, and
`EffectiveSettings` gains a matching `ingestion:` block.

## Risks / Trade-offs

**[Hard-break config schema silently changes behaviour for existing `.env`
files]** → An operator with `TOP_K=20` in `.env` gets `top_k=10` after upgrade
with no error, because `extra="ignore"` swallows the now-unknown key. This is
the exact silent-behaviour-change failure mode the whole change exists to
eliminate, so the mitigation is two layers, not one — see D9. In short:
(a) `extra="forbid"` on `ChunkingSettings`, `RetrievalSettings` and
`MetadataSettings` makes *any* unexpected `CHUNKING__*` / `RETRIEVAL__*` /
`METADATA__*` key — typo, custom var, or unenumerated name — fail loudly and
self-documenting, covering the general case; (b) a startup tripwire enumerating
the ~30 known pre-v2 flat names raises a `ValueError` naming the nested
replacement, covering the one case `extra="forbid"` structurally cannot see
(a bare `TOP_K` never reaches a subpackage model); (c) `.env.example` rewritten;
(d) a full migration table in ADR-037.

**[DI threading blast radius]** → 25 call sites (21 enumerated at proposal time, plus four that group 2's relocation moved into `core/` — see tasks 5.6a) plus every intermediate function
between the two entry points and the leaves. Signature churn risks a partially
threaded state where some modules read the (now deleted) global and fail at
import. Mitigation: sequence the work leaf-first — thread the parameter into
callees while the global still exists (group 4), then delete the global last
(group 5.4), so the tree is runnable at every intermediate commit. A grep for
`from ...config import settings` under `src/rag_mcp/core` and
`src/rag_mcp/integrations` returning zero hits is the acceptance gate.

**[Test-fixture churn]** → Tests today override behaviour by patching
`rag_mcp.config.settings` attributes — a pattern the current
`config-composition-root` spec explicitly blesses. Every such test must switch
to constructing an `EffectiveSettings` and passing it. Combined with the profile
YAML rewrite and the 15 deleted modules, this touches most of the ~30 test
files. Mitigation: add a shared `effective_settings(**overrides)` factory
fixture in `tests/conftest.py` (group 4.1) *before* touching any test, so each
migration is a one-line change; keep `reset_model_cache()` discipline
(AGENTS.md gotcha #2) intact throughout.

**[Coverage floors regress mid-change]** → Deleting shims raises the
denominator's quality, but from group 2 onward the new `core/codebase/`,
`core/documents/` and split modules arrive with the old files' coverage
attribution broken. AGENTS.md treats the coverage floor as a commit-time gate,
so a developer committing at the group 2 boundary with `--cov` would fail on
attribution drift rather than on logic — and the predictable response is to
stop passing `--cov`, which erodes the gate permanently.

Mitigation: **the coverage gate is explicitly suspended for groups 2–11.**
Intermediate commits run `uv run pytest -m "not slow"` *without* `--cov`; the
fast suite staying green is the intermediate gate. The coverage floors
(Core+MCP ≥95%, Orchestration ≥85%, Overall ≥90%) are re-asserted at group 12
(coverage repair, measured against the group 1.1 baseline) and again at final
verification (14.1). This suspension is deliberate and bounded — not a
standing exemption — and no commit may reach `main` without 14.1 passing.

**[Registry lazy resolution hides an ImportError until first use]** → A typo in
a `register()` import string surfaces at query time, not at startup. Mitigation:
the registry contract tests resolve every registered name (`available()` →
`get()`) so CI catches it; `compose.py` resolves the *active* strategies at
startup, so a misconfigured deployment still fails fast.

**[Deliberately broken archived experiments]** → Accepted per user decision.
Risk is that a future reader treats the breakage as a bug. Mitigation: the
one-line note per experiment directory and an explicit paragraph in ADR-037.

**[Relocating three modules churns the graphify graph and any external
tooling]** → Groups 2–9 churn the tree heavily (3 relocations, 5 splits, 15
deletions) while `graphify update .` does not run until group 13. AGENTS.md
instructs agents to query graphify *before* grep, so any mid-change consultation
would hit a graph describing the pre-refactor tree and silently return dead
paths. Mitigation: (a) an intermediate `graphify update .` immediately after the
group 2 relocation and again after the group 9 deletions, so the two largest
structural jumps are reflected promptly (tasks 2.9 and 9.8); (b) an explicit
note in `tasks.md` that between group 2 and group 13 graphify results must be
verified against the working tree before being acted on; (c) the final
`graphify update .` at 13.12 remains the authoritative refresh. AGENTS.md's
invariant #6 is rewritten to name the new paths.

## Migration Plan

**Deploy.** This is a source-level change with no data migration. Sequence:

1. Branch `refactor/complete-architecture-v2-conformance` off `main`.
2. Work `tasks.md` top to bottom; the ordering is a dependency order
   (see D5 and the DI risk mitigation above). Commit at each group boundary
   with `uv run pytest -m "not slow"` green.
3. Before merge: `uv run lint-imports` (new contracts), full
   `uv run pytest -m "not slow" --cov=rag_mcp` at the AGENTS.md floors, and
   `openspec validate --all --strict`.
4. Merge to `main` with a `refactor!:` commit. `python-semantic-release` cuts
   **v2.0.0** automatically — never hand-edit `version` in `pyproject.toml`.

**Operator migration (required, one-time).**

- Rename subpackage env vars in `.env` per the ADR-037 table
  (`TOP_K` → `RETRIEVAL__TOP_K`, `CHUNK_SIZE` → `CHUNKING__CHUNK_SIZE`,
  `METADATA_EXTRACTION_MODE` → `METADATA__EXTRACTION_MODE`, …). The startup
  tripwire names the replacement for any legacy key it finds.
- Replace any `from rag_mcp.{server,cli,ingestion,retrieval,reranker,
  sparse_retriever,metadata_extractor,watcher,azure_reader,readers} import …`
  with the `rag_mcp.core.*` / `rag_mcp.transports.*` equivalent.
- Custom profile YAML must be converted to nested blocks. The three shipped
  bundles are converted by this change; a custom bundle's conversion is
  mechanical (`TOP_K: 10` → `retrieval:\n  top_k: 10`).
- No action for ChromaDB data, collection profile tags, MCP clients, or CLI
  usage.

**Rollback.** Pin to the last v1.x release (`uv add rag-mcp==<last-1.x>` or
`git revert` the merge commit). Because there is no data migration and no
collection-metadata change, rollback is a code-only operation: v1.x reads the
same `output/chroma_*` collections, including profile tags written under v2.
The only manual step is restoring the pre-migration `.env`, so operators are
told to keep a copy. Partial rollback of individual groups is not supported —
groups 3–5 (registries, nested config, DI) are mutually dependent.

## Open Questions

**Resolved during proposal review** (previously open, now decided — recorded
here so the reasoning is not lost):

- *Tripwire lifetime.* **Resolved by D9.** `extra="forbid"` is permanent; the
  enumerated legacy tripwire is permanent through v2.x and removed in v3.0.0.
  The earlier "remove in v2.1.0" proposal was withdrawn — no v2.1.0 is scoped,
  and deferring to an unplanned release is a non-decision that would have left
  the enumeration permanent by accident.
- *`IngestionSettings`.* **Resolved by D10.** Created now.
  `embed_concurrency` / `embed_batch_size` move to `INGESTION__*` rather than
  staying misfiled under `chunking:`. Deferring would have cost a second
  breaking rename later; doing it now costs two lines in a migration table that
  is being written regardless.

**Still open:**

- A single import-linter `layers` contract (D7) is deferred to future work
  rather than in-scope, because a broad layers contract fails today for reasons
  unrelated to this change and would produce worse signal than the four
  targeted contracts. Confirm at ADR-037 review.
- `EffectiveSettings` is threaded as a required parameter on the internal call
  path (5.1). Whether the *public* `search()` / `ingest_path_async()` signatures
  should default it to `None` and resolve from `compose.py` when omitted is left
  to implementation: the internal contract is what the spec fixes, and either
  public shape satisfies it. Decide at 5.1 and record in ADR-037.
