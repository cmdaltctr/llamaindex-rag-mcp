# ADR-037: Architecture v2 Conformance

**Date:** 2026-08-05
**Status:** Accepted
**Phase:** Conformance — closing the gap left by Phases 1–5
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

ADRs 032–036 recorded a five-phase refactor from the flat v1 layout to the
target architecture in `docs/brainstorm/refactor-proposal/PROPOSAL.md`. The
phases shipped, but a conformance audit against that proposal found the
implemented tree did not match it. The shape was right; several of the
load-bearing claims were not true.

What the audit found, in order of severity:

1. **The strategy registries were dead code.** Five `registry.py` modules
   existed with the §4.4 shape, but only the two *provider* registries had
   production consumers. Chunking, metadata and retrieval still dispatched
   through eager imports and `if/elif` chains, so §4.4 rule 4 — "a new
   strategy is one file plus one `register()` line, no other file touched" —
   was false. This is the flagship promise of the whole refactor.
2. **ChromaDB leaked out of its abstraction.** `codebase_map.py` constructed
   a `chromadb.PersistentClient` directly, contradicting ADR-034's "never
   through ChromaDB APIs directly" and silently breaking under any second
   store implementation.
3. **`config` imported business logic.** `resolve_sparse_backend()` pulled in
   `core.retrieval.sparse`, inverting the layering that AGENTS.md lists as a
   hard rule.
4. **`core/` read a process-wide settings singleton in 25 places** rather
   than receiving settings as a parameter (§4.1 Layer 3, §6.3.1). ADR-033
   disclosed this honestly as an accepted deviation, but the proposal still
   described an architecture the code did not implement.
5. **A circular import** between `integrations/magika.py` and `codebase_map`,
   existing only to preserve a test monkeypatch target.
6. **`config.py` had not shrunk.** The target was ~150 lines; it was 576 —
   four lines *longer* than the 572-line v1 monolith it replaced.
7. **The v1 surface was still shipping**: 15 deprecated re-export modules and
   a ~55-entry PEP 562 legacy-constant table, plus three modules (`codebase_map`,
   `code_graph`, `doc_graph`) that no phase ever relocated.

Shipping v2.0.0 while these stood would have made the ADR record dishonest.

## Decision

**Close every finding, delete the v1 surface, and add machine enforcement so
the gaps cannot silently reopen.**

### 1. Registries become the real dispatch

`chunker.py`, `extractor.py` and `pipeline.py` resolve strategies through
`registry.get()`. The metadata `if/elif` chain over strategy names — which
the spec forbids explicitly — is gone; `local` is now a provider-selection
alias that maps to a registered name via a dict, and `openrouter` is
registered rather than reached by a branch. All five extractors share a
uniform `(text, file_name, settings)` signature so dispatch is uniform.

`compose.py` resolves the *configured* strategies at startup and lets their
errors propagate. The previous implementation walked all five registries ×
all names and swallowed every `ImportError` into `logger.debug` — it was
fail-*silent*, and it eagerly imported the ONNX reranker and every optional
provider on each boot, defeating §4.4 rule 2's lazy-import rationale.

### 2. Settings are injected

A frozen `EffectiveSettings` (`core/settings.py`) is threaded through
`search()` and `ingest_path_async()` and down into every `core/` and
`integrations/` module. All 25 singleton reads are gone;
`tests/test_no_global_settings_reads.py` enforces zero.

Entry points resolve settings **once at the boundary**: an explicitly passed
instance wins, otherwise the composition root's installed default is used.
Everything below takes settings as a required parameter and performs no
lookup. This mirrors `core.vectordb.get_default_store` — the DI pattern this
codebase already uses — rather than inventing a second one.

All four nested blocks are frozen, not just the root. `model_copy` shares
block instances by reference between overlays, so a mutable block would have
let one operation silently rewrite another's configuration.

### 3. Nested configuration schema — **BREAKING**

`Settings` composes the subpackage models by nesting with
`env_nested_delimiter="__"` (§4.3). A new `IngestionSettings` takes
`embed_concurrency` and `embed_batch_size` out of `ChunkingSettings`, where
they only lived because the flat schema had nowhere better.

**Environment variable migration** (cross-cutting names are unchanged):

| Pre-v2.0.0 | v2.0.0 |
|---|---|
| `CHUNK_SIZE` | `CHUNKING__CHUNK_SIZE` |
| `CHUNK_OVERLAP` | `CHUNKING__CHUNK_OVERLAP` |
| `MARKDOWN_CHUNK_SIZE` | `CHUNKING__MARKDOWN_CHUNK_SIZE` |
| `MARKDOWN_HEADING_PREPEND` | `CHUNKING__MARKDOWN_HEADING_PREPEND` |
| `MARKDOWN_MIN_CHUNK_FRACTION` | `CHUNKING__MARKDOWN_MIN_CHUNK_FRACTION` |
| `CHUNK_STRATEGY_FALLBACK` | `CHUNKING__STRATEGY_FALLBACK` |
| `EMBED_CONCURRENCY` | `INGESTION__EMBED_CONCURRENCY` |
| `EMBED_BATCH_SIZE` | `INGESTION__EMBED_BATCH_SIZE` |
| `TOP_K` | `RETRIEVAL__TOP_K` |
| `SIMILARITY_THRESHOLD` | `RETRIEVAL__SIMILARITY_THRESHOLD` |
| `RERANK_ENABLED` | `RETRIEVAL__RERANK_ENABLED` |
| `RERANK_ENABLED_FOR_SEMANTIC` | `RETRIEVAL__RERANK_ENABLED_FOR_SEMANTIC` |
| `HARD_TECHNICAL_THRESHOLD` | `RETRIEVAL__HARD_TECHNICAL_THRESHOLD` |
| `RERANK_FETCH_MULTIPLIER` | `RETRIEVAL__RERANK_FETCH_MULTIPLIER` |
| `RERANK_MAX_FETCH` | `RETRIEVAL__RERANK_MAX_FETCH` |
| `RERANK_MODEL` | `RETRIEVAL__RERANK_MODEL` |
| `HYBRID_ENABLED` | `RETRIEVAL__HYBRID_ENABLED` |
| `HYBRID_RRF_K` | `RETRIEVAL__HYBRID_RRF_K` |
| `HYBRID_SPARSE_BACKEND` | `RETRIEVAL__HYBRID_SPARSE_BACKEND` |
| `METADATA_EXTRACTION_MODE` | `METADATA__EXTRACTION_MODE` |
| `METADATA_KEYWORD_RULES` | `METADATA__KEYWORD_RULES` |
| `METADATA_TAXONOMY_MODE` | `METADATA__TAXONOMY_MODE` |
| `OLLAMA_CLASSIFY_MODEL` | `METADATA__OLLAMA_CLASSIFY_MODEL` |
| `OLLAMA_CLASSIFY_MAX_ATTEMPTS` | `METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS` |
| `OLLAMA_CLASSIFY_TIMEOUT` | `METADATA__OLLAMA_CLASSIFY_TIMEOUT` |

> **Update (rename-classify-settings, 2026-08-07):** the last two rows record
> the v2.0.0 targets, which have since been retired. Both knobs govern *all*
> metadata LLM backends, not just Ollama, so they are now
> `METADATA__CLASSIFY_MAX_ATTEMPTS` and `METADATA__CLASSIFY_TIMEOUT`.
> `METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS` and
> `METADATA__OLLAMA_CLASSIFY_TIMEOUT` are themselves tripwired and will fail
> at startup — migrate straight to the `CLASSIFY_*` forms. The third row,
> `METADATA__OLLAMA_CLASSIFY_MODEL`, is unaffected: it really is
> Ollama-specific.

`defaults.yaml` and all three profile bundles are rewritten nested and ship
with this change; a bundle using the flat schema, or a `hybrid.yaml`
carrying lever blocks, is now rejected with the offending key named.

**Two guards, not one.** Unknown configuration must never be silently
dropped:

* `extra="forbid"` on the four subpackage models catches *any* unexpected
  nested key — a typo, a custom var, a name nobody enumerated. This is the
  general case, and it is permanent.
* A startup tripwire enumerating the ~25 known pre-v2 flat names covers the
  one case `extra="forbid"` structurally cannot see: a bare `TOP_K` never
  reaches a subpackage model, so with `env_nested_delimiter` it is simply an
  unrecognised root key that `extra="ignore"` would swallow.

The tripwire's **removal trigger is v3.0.0** — permanent through the v2.x
line. It is deliberately not tied to a hypothetical v2.1.0: pinning removal
to an unplanned release is a non-decision, and would have left a legacy
enumeration living indefinitely inside a change whose thesis is that legacy
paths must not outlive their migration.

### 4. Boundaries restored and enforced

* The codebase map reads through a `CollectionView` over a new
  `VectorStore.fetch_all`, so ChromaDB is confined to `core/vectordb/chroma.py`.
* The capability probes (sparse backend, PDF reader) move to `compose.py`.
  Asking the runtime a question is construction work; keeping it in `config`
  forced the layering inversion.
* The `integrations.magika` → `codebase_map` back-import is deleted and the
  delegation inverted, so patches on the owning module propagate.
* `codebase_map.py`, `code_graph.py` → `core/codebase/`; `doc_graph.py` →
  `core/documents/`. This removes `core/`'s upward import into a top-level
  module.

Enforcement is **four targeted import-linter contracts**, not one broad
`layers` contract — a layers contract fails today for reasons unrelated to
this change and would produce worse signal. Each contract was added *first,
observed failing on its known offender*, and only then satisfied; the
pre-fix output is recorded in the change's `notes/lint-imports-before.md`
so the evidence does not live only in a commit diff.

All contracts set `unmatched_ignore_imports_alerting = "error"`. This is
what makes a temporary suppression temporary: when its underlying violation
is fixed the ignore goes stale and *fails the build*. Every TEMPORARY entry
added during this change was removed that way rather than by remembering to.
`tests/test_contract_coverage.py` asserts every package is covered by some
contract, so a new package forces a conscious boundary decision.

### 5. A stale suppression fails the build

All contracts set `unmatched_ignore_imports_alerting = "error"`.
Import-linter's default is `"none"`: an `ignore_imports` entry that no
longer matches any real import is silently accepted. That default is what
makes "temporary suppression" a fiction — nothing ever forces the entry out
once its fix lands, and the contract goes on passing while the exception
remains.

With `"error"`, removing a violation makes its ignore stale, and a stale
ignore **fails the run**. The failure is the notification.

This is not theoretical. During this change it fired **six times**: on the
ChromaDB leak, the Magika cycle, the four `integrations → config` edges, and
the `config → core.retrieval.sparse` probe. Each time, the build refused to
pass until the now-pointless suppression was deleted. Under the default
setting all six would have survived as permanent exceptions wearing the word
TEMPORARY, and the audit that produced this ADR had already found exactly
that pattern — a documented target with a live legacy path that nothing
forced anyone off.

The general principle: **a deprecation needs a mechanism, not a comment.**
A `# TEMPORARY` note records an intention; a failing build enforces one.
Where the two disagree, only the second one survives contact with a busy
week. `tests/test_contract_coverage.py` applies the same reasoning to
packages — a new package fails the suite until someone decides which
boundary governs it.

### 6. The v1 surface is deleted — **BREAKING**

The 15 re-export modules and the PEP 562 alias table are gone.
`src/rag_mcp/` now contains only `__init__.py` and `compose.py` at the top
level — the §5.1 target tree. This overrides §11 Decision 2's
one-minor-cycle grace period: carrying both architectures on `main` was
judged worse than one clean break.

No file exceeds the 500-line ceiling; `tests/test_file_size_ceiling.py`
enforces it.

## Consequences

**Positive**

* §4.4 rule 4 is now true: a new strategy is one file plus one `register()`
  line.
* Per-collection profiles are correct under concurrency. Two `search()`
  calls in one process each honour their own settings — previously not even
  expressible as a test.
* The ADR record matches the code, and four contracts plus three tests keep
  it that way.
* `config/__init__.py`: 576 → 316 lines, split with `sources.py` and
  `legacy.py`. Short of the ~150 target but no longer the largest module.

**Negative**

* Every operator must migrate `.env`. The tripwire makes this a loud,
  mechanical failure rather than silent misbehaviour, but it is still work.
* Custom profile YAML must be converted to nested blocks.
* Archived `experiments/*/run_eval.py` scripts import the removed surface and
  are intentionally **not** repaired: their results are already recorded in
  `results.md`, they are not run in CI, and rewriting them would change the
  code that produced the recorded numbers. Each carries a header saying so.
* The composition root installs a process-wide default `EffectiveSettings`.
  This is a global, though a frozen one that `core/` only reads at an entry
  point — weaker than pure parameter-passing from `main()`, and the same
  trade-off `get_default_store` already made.

## Alternatives Considered

| Option | Rejected because |
|---|---|
| Amend the proposal to match the code, rather than the code to match the proposal | Four of the seven findings were defects, not documentation drift: dead dispatch machinery, a leaked abstraction, an inverted dependency, and a cycle. Rewriting the target to describe them would have made the documents accurate and the architecture wrong. |
| Keep the 15 shims until a natural v2.0.0 (PROPOSAL §11 Decision 2's grace period) | Carrying both architectures on `main` costs more than one clean break. Nothing in `src/` or `tests/` imported them; the only consumers were archived experiment scripts that are not run in CI. |
| Provide flat→nested env var aliases via `AliasChoices` | Reproduces the state this ADR exists to correct: a documented target plus a live legacy path with no forcing function. Since the shim deletion already made this a major release, the schema break costs one migration note. |
| Enumerated legacy-name tripwire alone, without `extra="forbid"` | An enumeration only catches what it enumerates. A typo or an unlisted key would still be swallowed silently — the precise failure mode being eliminated. |
| `extra="forbid"` alone, without the tripwire | Cannot see flat legacy names: with `env_nested_delimiter`, a bare `TOP_K` never reaches a subpackage model. That is the population every existing `.env` is full of. |
| One broad import-linter `layers` contract instead of four targeted ones | Fails today for reasons unrelated to this change, producing noise rather than signal. Deferred, not dismissed. |
| Leave the graph modules top-level, as §12 accepted | See "Correcting the record" below — the stated rationale was factually wrong. |

## Correcting the record: PROPOSAL §12 was wrong, not merely stale

§12 recorded the three unmigrated graph modules as an accepted deviation,
reasoning that they "already satisfy the invariant of sharing only
`config.py` (AGENTS.md invariant #6)" and that "the grouping was aesthetic
(making the use-case boundary visible in the tree), not structural", so
moving them "would add import churn for no behavioural benefit."

Every clause of that is false, and the distinction matters more than the
correction:

* **They did not satisfy invariant #6.** `core/ingestion/pipeline.py`
  imported `detect_file_types` from the top-level `codebase_map`, so `core/`
  was reaching upward out of its own package — the specific coupling the
  invariant exists to prevent.
* **The grouping was structural.** Those three files hosted the ChromaDB
  abstraction leak, the `integrations.magika` circular import, and three of
  the five 500-line ceiling breaches. They were where the architecture was
  leaking, not where it was untidy.
* **"No behavioural benefit" was unfalsifiable as written.** No one had
  looked. The relocation surfaced two defects immediately.

This is recorded as a decision because the *failure mode* is reusable. §12
was written in good faith and reads as diligent: it names the deviation,
cites the invariant, and gives a rationale. But the invariant was asserted
rather than checked, and once written down the assertion became the thing
future readers would trust. A deviation recorded with a wrong rationale is
worse than one recorded with none, because it forecloses the question.

The lesson applied elsewhere in this change: every claim the audit tested
was either verified against the code or corrected. Where ADR-033 disclosed
its weakened DI contract honestly, that disclosure held up and is credited
in the amendment. Where ADR-034 asserted "never through ChromaDB APIs
directly" without a contract to enforce it, the assertion had already
drifted from the code by the time anyone read it.

**Corollary, now enforced:** an architectural invariant that no test or
contract checks is a comment. Invariant #6 is now covered by
`core-business-avoids-providers-transports` and
`tests/test_contract_coverage.py`.

## Deviations from the proposal, recorded

1. **§6.2 leaf names.** The proposal writes `retrieval.reranker_enabled`,
   `chunking.active_strategy`, `metadata.mode`. This change conforms to the
   nested *structure* but keeps the existing, semantically accurate field
   names (`rerank_enabled`, `strategy_fallback`, `taxonomy_mode`) and does
   not introduce `metadata.mode`, which conflates the provider mode with the
   extraction backend.
2. **`watcher.py` split.** design.md D8 proposed `debounce.py`; the debounce
   timers are per-file state owned by `DocumentIngestHandler` and cannot be
   lifted out without inventing a seam. The split is on daemon lifecycle
   (`runner.py`) instead.
3. **`config.py` line count.** 316, not ~150. Further reduction would mean
   splitting the `Settings` model itself, which would scatter the single
   source of truth the model exists to be.
4. **`ingestion.embed_concurrency` / `embed_batch_size`** were moved now
   rather than deferred (design.md D10): the breaking rename was already
   being paid for, and deferring would have bought a second break later.

## Deferred

A single import-linter `layers` contract expressing the full stack. It fails
today for reasons unrelated to this change; the four targeted contracts give
better signal until that is addressed separately.

## References

* `docs/brainstorm/refactor-proposal/PROPOSAL.md` — the target architecture
* `openspec/changes/complete-architecture-v2-conformance/` — proposal,
  design (D1–D10), specs, tasks, and the lint-imports before/after evidence
* ADR-031 — three-layer config/compose DI, which this completes
* ADR-032 … ADR-036 — the five phases this change reconciles with the proposal
