# ADR-013: Hybrid Category Taxonomy for Ollama Metadata Extraction

**Status**: Accepted
**Date**: 2026-05-20
**Change**: `enhance-metadata-extraction`

## Context

The `ollama` metadata extraction mode currently uses a fixed, hardcoded list of
categories in its classification prompt:

```
Classify into exactly one of: AI, Philosophy, Biology, Marketing, Programming, uncategorised
```

This works for the original five domains but has two critical failures:

1. **Novel domains are invisible**: A "Music Theory" document gets classified as
   `"uncategorised"` because `"music"` is not in the fixed list. The document is
   unfilterable via `metadata_filter={"category": "music"}`.

2. **No category growth**: The taxonomy never evolves. Every document outside the
   original five domains is permanently uncategorisable.

The opposite extreme — fully open-ended classification — introduces its own failure
mode. Within 50 documents, the same domain gets labelled `"Machine Learning"`,
`"machine_learning"`, `"ML"`, `"Deep Learning"`, and `"Neural Networks"`. Because
ChromaDB uses **exact string matching** for `where` clauses,
`metadata_filter={"category": "ai"}` returns zero results for any of these variants.

Constraints:
1. **ChromaDB uses exact string matching** — no fuzzy `where` queries, no embedding-based category matching
2. **No new Python dependencies** — the ollama mode must remain `urllib`-only (stdlib)
3. **Backward compatibility** — existing documents tagged `"AI"` must still be filterable
4. **No PyTorch** — per project boundaries

## Decision

**Implement a hybrid category taxonomy system that queries ChromaDB for existing
categories before each classification, merges them with seed categories from the
keyword mode, and instructs the LLM to prefer existing labels while allowing it to
propose new concise labels when nothing fits.**

### Architecture

```
┌──────────────────────────┐
│  _gather_existing_cats() │ ← queries all ChromaDB collections
│  → ["ai", "biology", ...]│
└───────────┬──────────────┘
            │ merge
┌───────────┴──────────────┐
│  seed categories         │ ← from keyword mode rules
│  → ["ai", "philosophy",  │     "biology", "marketing",
│      "programming"]      │     "uncategorised"
└───────────┬──────────────┘
            │ deduplicate + normalise (lowercase)
            ▼
┌──────────────────────────┐
│  merged taxonomy          │
│  → ["ai", "biology",     │
│      "philosophy",       │
│      "programming",      │
│      "marketing",        │
│      "uncategorised"]    │
└───────────┬──────────────┘
            │ inject into prompt
            ▼
┌──────────────────────────┐
│  Ollama prompt:          │
│  "EXISTING CATEGORIES:   │
│   ai, biology, ...       │
│   Prefer existing but    │
│   propose new if needed. │
│   Reply with JSON."      │
└───────────┬──────────────┘
            │ LLM responds
            ▼
┌──────────────────────────┐
│  normalise output:       │
│  lowercase, underscores, │
│  max 3 words,            │
│  reject >3 words →       │
│  "uncategorised"         │
└──────────────────────────┘
```

This pattern is literally what Microsoft uses in Bing Copilot (TnT-LLM paper,
KDD 2024) — sample the corpus, build a taxonomy, then lock it and classify into
it. We're doing the continuous-ingestion version of that.

### Key design choices

| Decision | Choice | Rationale | Alternatives Considered |
|----------|--------|-----------|------------------------|
| **Category source** | ChromaDB query across all collections + seed categories from keyword mode | Self-healing: as the LLM proposes new categories, they accumulate in ChromaDB and appear in future prompts. Seed categories provide the initial taxonomy on first run when ChromaDB is empty. | ChromaDB query only (empty on first run → LLM invents everything); seed categories only (novel domains permanently invisible). |
| **LLM instruction** | "Prefer existing categories. If no existing category fits, propose ONE new concise label (1-3 words)." | Controls proliferation — the LLM is an order of magnitude more likely to reuse an existing label when it's presented as an option. The escape hatch exists for genuinely novel domains but is not the default path. | "Always pick from this list" (misses novel domains); "Invent any label" (proliferation within 20 docs). |
| **Normalisation** | Lowercase, underscores for spaces, max 3 words, reject >3 words → `"uncategorised"` | Ensures `metadata_filter={"category": "ai"}` always works. ChromaDB's `where` clause is exact-match — `"AI"` ≠ `"ai"` ≠ `"Artificial_Intelligence"`. Normalisation prevents fragmentation. | No normalisation (guarantees filter misses); case-insensitive ChromaDB queries (not supported in ChromaDB's `where`). |
| **ChromaDB query scope** | All collections (`PersistentClient.list_collections()`, then `collection.get(include=["metadatas"])`) | A `music` category discovered in the `research` collection should be available when ingesting into the `work` collection. The taxonomy is global, not per-collection. | Per-collection only (misses categories from other collections); separate taxonomy file (extra management surface). |
| **Seed categories** | The keyword mode's built-in rules provide the five default categories (`ai`, `biology`, `philosophy`, `marketing`, `programming`) plus `"uncategorised"` | Zero-config taxonomy on first run. Users who switch from `keyword` to `ollama` mode see the same categories initially, making the transition seamless. | Start with empty taxonomy (every classification invents a new label — chaos on first run). |
| **ChromaDB query failure** | Log WARNING, fall back to seed categories only | Metadata extraction must never fail ingestion. A database lock or I/O error should not prevent document classification. The seed categories are the reliable fallback. | Raise exception (breaks ingestion); skip classification entirely (documents get no metadata). |

## Consequences

### Positive

- **Self-healing taxonomy**: As more documents in a domain are ingested, the category
  label stabilises. The LLM reuses existing labels with high probability because they
  are presented as the preferred option.
- **Novel domain discovery**: Users ingesting documents from entirely new fields
  (music, law, chemistry, etc.) get meaningful, searchable categories without
  pre-configuring anything.
- **Filter reliability**: Normalisation guarantees that `metadata_filter={"category": "ai"}`
  always matches, regardless of how the LLM originally formatted the label.
- **Zero-config on first run**: Seed categories from keyword mode ensure the initial
  prompt has a useful taxonomy, even with an empty ChromaDB.
- **Graceful degradation**: ChromaDB query failure → seed categories. Ollama
  unreachable → uncategorised. Ingestion never crashes because of metadata.
- **Backward compatible**: Existing documents with legacy category values (e.g.,
  `"AI"` instead of `"ai"`) remain filterable via their original labels. New
  documents use the normalised form.
- **Cross-mode taxonomy growth**: The `llamaindex` mode also writes normalised
  categories (derived from extracted document titles via
  `_aggregate_llamaindex_metadata` → `_normalise_category`) into ChromaDB.
  These categories are picked up by `_gather_existing_categories()` on the
  next ollama-mode run, so switching between modes — or running mixed
  ingestions — accretes a single shared taxonomy rather than two parallel
  ones.

### Neutral

- **Taxonomy drift possible**: Over hundreds of documents, slightly different labels
  for the same domain may emerge (e.g., `"machine_learning"` and `"deep_learning"`).
  This is inherent to LLM-based classification and is accepted for v1. A future
  reconciliation pass (ADR-014 or later) could cluster similar categories via
  embedding similarity.
- **ChromaDB query overhead**: One extra metadata query per file (~milliseconds).
  Negligible compared to the ~2s Ollama call. The PersistentClient is cached as a
  module-level singleton to avoid re-opening the database on every file during
  batch ingestion.
- **Category proliferation is bounded**: The "prefer existing" instruction and
  3-word normalisation cap mean the taxonomy grows at most linearly with genuinely
  distinct domains, not exponentially with every document.

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Small model (0.6B) ignores "prefer existing" instruction** | Medium | Medium | The model still produces a normalised 1-3 word label. Even if it invents a synonym (e.g., "ml" instead of "ai"), the next run will include it in the taxonomy. Test with qwen3:0.6b to validate prompt adherence. |
| **ChromaDB metadata query slow on large collections** | Low | Low | The query fetches only the `category` field (not full vectors). ChromaDB metadata queries are indexed. Cap the result set if needed. |
| **Category normalisation loses semantic meaning** | Low | Low | `"natural_language_processing"` → `"natural_language_process"` (4-word truncation). Acceptable trade-off for filter reliability. Users can manually merge categories later. |
| **Seed categories become stale** | Low | Medium | As the taxonomy grows organically, the five seed categories remain but new ones accumulate. The seeds fade into the background naturally. No intervention needed. |

## Alternatives Considered

1. **Pure fixed list (current)**: Keep the hardcoded five categories. Rejected —
   novel domains are permanently invisible to metadata filtering.

2. **Pure open-ended**: Remove all category constraints. Rejected — within 20
   documents, metadata_filter becomes unreliable due to label fragmentation.

3. **Embedding-based category matching**: Instead of exact string match, embed the
   filter value and find the nearest existing category. Rejected — requires an
   embedding call per filter, changes ChromaDB query semantics, and is overkill for
   a v1 feature.

4. **External taxonomy file**: Maintain a YAML/JSON file of allowed categories. User
   edits it to add new categories. Rejected — adds configuration surface, requires
   manual maintenance, defeats the zero-config goal.

5. **Per-collection taxonomy**: Each collection tracks its own categories
   independently. Rejected — categories should be global so a domain discovered in
   one collection is available for others.

## Implementation Notes

### llamaindex mode runs sync-over-async LlamaIndex APIs

`_extract_llamaindex` calls `IngestionPipeline.run()`, which is a sync facade
over an internally-async pipeline.  When ingestion is triggered from inside an
already-running event loop (the MCP server path, or the file-watcher path),
LlamaIndex's nested-loop guard raises:

> Detected nested async. Please use `nest_asyncio.apply()` to allow nested event
> loops. Or, use async entry methods like `aquery()`, `aretriever`, `achat`, etc.

The fix is to detect a running loop with `asyncio.get_running_loop()` and, if
present, hand `pipeline.run()` to a fresh `ThreadPoolExecutor` worker thread.
The worker thread sees no running loop, the guard passes, and we block on
`.result()` for the answer.  The CLI path has no running loop and calls
`pipeline.run()` directly.

Tradeoffs to record so future-me (or future-AI) doesn't re-litigate:

- **Blocks the event loop while ingest runs.**  `.result()` blocks the calling
  thread, so MCP requests queue behind a long ingest.  Same blocking behaviour
  `nest_asyncio.apply()` would give.  The proper cure is making the ingest path
  `async def` end-to-end — tracked separately under
  `openspec/changes/make-ingest-path-async/`.
- **Fresh `ThreadPoolExecutor` per file.**  Pool creation is sub-millisecond
  next to ~30s of Ollama calls.  A module-level singleton would save nothing
  measurable and adds shutdown lifecycle questions.  Not worth optimising.
- **Pattern lives only inside `_extract_llamaindex`.**  Not extracted into a
  helper like `run_sync_in_thread()` because there is exactly one call site.
  By the **Rule of Three**, wait until a third call site appears before
  extracting — premature abstraction has no shape.  If retrieval (or anything
  else) later hits the same nested-loop error, copy the pattern; on the third
  copy, refactor to a shared helper.

## References

- **TnT-LLM**: Wan, M., et al. (2024). "TnT-LLM: Text Mining at Scale with Large
  Language Models." KDD 2024. https://arxiv.org/abs/2405.06327 — The two-phase
  taxonomy-generation-then-classification pattern that inspired this design.
- **TELEClass**: Zhang, Y., et al. (2024). "TELEClass: Taxonomy Enrichment and LLM
  Enhanced Hierarchical Text Classification with Minimal Supervision."
- **TaxoAdapt**: (2025). Dynamic taxonomy adaptation via hierarchical classification.
- OpenSpec change: `openspec/changes/enhance-metadata-extraction/`
- Specs: `openspec/changes/enhance-metadata-extraction/specs/metadata-extraction/spec.md`
- Source:
  - `src/rag_mcp/metadata_extractor.py` — `_extract_ollama()`, `_gather_existing_categories()`
  - `src/rag_mcp/config.py` — `METADATA_EXTRACTION_MODE`, `OLLAMA_CLASSIFY_MODEL`
- Parent ADR: [ADR-011](./011-multi-collection-and-metadata-extraction.md) — introduced the four-mode metadata extraction system
