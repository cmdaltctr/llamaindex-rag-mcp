# Design: fix-embedding-and-structure-fidelity

## Context

Verified against `v3` at `c9d2906` during the 2026-09-01 audit.

- `stamp_source_lineage` (`core/ingestion/source_state.py:359`) is the **only**
  place in `src/` that writes `excluded_embed_metadata_keys`, and it has
  exactly one production call site (`replacement.py:216`). Confirmed with
  ast-grep. That makes it the natural single owner of the exclusion contract.
- `build_index_identity` (`source_state.py:89`) has one production call site
  (`pipeline.py:221`) and already hashes a `schema` version, the embedding
  runtime identity, parser selectors, chunking settings and the metadata
  shape. Adding one more member is a local edit.
- `integrations/pdf/registry.py` registers readers as
  `register(name, import_path, probe_module)`. It carries no per-reader
  metadata today. `core/ingestion/backends/registry.py` already demonstrates
  the pattern for per-strategy metadata (`fallback`, `document_suffixes`,
  `structured_output`).
- `chunker.py:145` computes `is_markdown = file_path.suffix.lower() == ".md"`.
  The chunker receives `BackendRead` from `read_document`, which carries
  `documents` and a `structured` flag but not the text format.
- `SUPPORTED_EXTENSIONS` is a module-level frozen set in
  `core/ingestion/loader.py:23`, read by `gather_supported_files` and by
  `daemon/watcher.py` to build its watch patterns.
- Settings are injected frozen `EffectiveSettings` (ADR-037). `core/` must not
  read a singleton.

## Goals / Non-Goals

**Goals**

- Make the embedding-text composition explicit, centrally owned, and
  invalidating when it changes.
- Stop discarding structure the configured reader already produced.
- Make page provenance either real or honestly absent — never promised and
  null.
- Make the `codebase` profile's declared code strategy actually reachable.

**Non-Goals**

- OCR for scanned PDFs. `pdf_inspector` already classifies and logs them;
  routing them to an OCR path is a separate change.
- Table-aware chunking. `MarkdownElementNodeParser` is installed and would
  index tables as elements, but it costs an LLM call per element. That is an
  experiment with a pre-registered protocol, not a correctness fix.
- Changing the embedding model, chunk sizes, or any calibrated default.
- Retrieval-side behaviour and answer synthesis — separate changes.

## Decisions

### D1: The exclusion set lives in `stamp_source_lineage`, not in each reader

Every node passes through `stamp_source_lineage` exactly once, on the single
production write path. Patching each PDF adapter instead would leave four
places to keep in sync and would still miss the `SimpleDirectoryReader`
defaults and any future reader.

The set is defined as a module constant next to `_SOURCE_METADATA_KEYS` and
unioned with whatever the reader already excluded, so a reader that
legitimately excludes more keeps that behaviour.

Alternatives considered:

- *Per-adapter exclusion (the obvious reading of the audit finding)* — four
  edit sites, no central contract, silently incomplete for future readers.
- *An allow-list instead of a deny-list* — safer in principle, but it would
  silently drop `header_path` and any future extractor output the moment
  someone adds a metadata field. A deny-list fails visibly (a new noisy key
  gets embedded and shows up in the quality gate) rather than invisibly
  (a new useful key gets dropped).

### D2: `file_path` is excluded, `file_name` is retained

This deliberately inverts LlamaIndex's default, which excludes `file_name` and
keeps `file_path` ("extreme important context"). For this project that default
is backwards:

- `file_path` is a machine-specific absolute path
  (`/Users/aizat/Development/…`). It is constant across every chunk of a
  document, so it adds no discriminative signal *within* a document, and its
  directory components are deployment noise that differs between the machine
  that ingested and any other.
- `file_name` carries genuine topical signal — `Kalai et al. - 2025 - Why
  Language Models Hallucinate.pdf` is a useful thing to match a query against.

Neither is removed from stored metadata; `source` in every result row still
comes from `file_path`.

This decision changes retrieval behaviour, so it is gated: the Tier-2 quality
floors must be re-measured after the change and committed. If Recall@10 or
MRR@10 regresses below the existing floor, this decision is reverted and
re-run as an experiment rather than forced through.

### D3: Readers declare a text format; the chunker routes on the declaration

Add `text_format: Literal["plain", "markdown"]` to the PDF reader registry
metadata and thread the producing reader's declaration through `BackendRead`
alongside the existing `structured` flag.

Alternatives considered:

- *Sniff the text for `^#{1,6}\s`* — content sniffing is a heuristic that
  misfires on plain text containing a `#` comment or a Python file. A
  declaration is deterministic and a reader author knows the answer.
- *Reuse the existing `structured_output` flag* — it means something else
  ("the backend returned pre-structured paragraphs/tables, skip file-level
  metadata extraction"). Overloading it would couple two unrelated decisions.
- *Set a metadata key on the emitted `Document`* — works, but metadata is
  per-document and mutable; the format is a property of the reader, and the
  registry is where this project already keeps per-strategy facts.

`document_backend` registrations gain the same field so an Azure structured
read stays correctly routed.

### D4: The extension set becomes profile-scoped, not globally widened

`SUPPORTED_EXTENSIONS` moves from a module constant to a value on
`EffectiveSettings`, defaulted to the current seven and overridden by
`codebase.yaml` to add source extensions.

Alternatives considered:

- *Widen the global set* — a `documents`-profile ingest pointed at a repo
  would suddenly pull in thousands of source files. Silent, surprising, and
  expensive.
- *Delete `strategy_fallback: code` from `codebase.yaml` and document that
  code goes through `get_codebase_map`* — smaller, and defensible, but it
  abandons a capability the profile was created to provide. Kept as the
  fallback if D4 proves noisy in review.

The watcher builds its patterns from the same resolved set so watch and manual
ingest cannot diverge.

### D5: Page provenance — fix `liteparse`, tell the truth about the rest

`liteparse` already knows the page number; emitting `page_label` next to
`page` is one line. `pdf_inspector` genuinely cannot know it — it returns one
document for the whole file — so the contract stops requiring the field
rather than the reader inventing one.

Making `pdf_inspector` page-aware is out of scope here: it would mean either
parsing twice or changing what the upstream library returns. If page citation
matters more than markdown structure, the configured default should change to
`liteparse` — but that is an experiment (14 already compared them), not a
decision to smuggle into a correctness fix.

### D6: Index identity absorbs both new inputs, and the schema version bumps

`_INDEX_IDENTITY_SCHEMA` goes from 2 to 3, and the payload gains:

```
"embedding_text": {"excluded_keys": sorted(EXCLUDED_EMBED_KEYS)},
"parser": {..., "text_format": <declared format>},
```

Bumping the schema version alone would force a one-time global reprocess,
which is correct and desirable here: every stored vector predates the fix.
Including the actual key list means future changes to the set invalidate
precisely, without another schema bump.

## Risks

| Risk | Mitigation |
| --- | --- |
| Excluding `file_path` regresses retrieval quality | Gated on re-measured Tier-2 floors; reverts to an experiment if it regresses |
| Full reprocess surprises an operator with a large corpus | `files_skipped_unchanged` drops to zero on the first run after upgrade; call it out in the changelog and the release notes |
| Profile-scoped extensions cause an unexpectedly large codebase ingest | The `codebase` profile is opt-in per collection; `codebase_map_max_files` already bounds the map, and ingestion reports per-file details |
| Markdown routing changes chunk counts, invalidating experiment baselines | Experiments pin their own settings; the quality gate's fixture-identity hashes will flag any drift rather than silently absorbing it |
