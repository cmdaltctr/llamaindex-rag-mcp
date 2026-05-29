# Design — Experiment 6c: Markdown Chunking Quick-Wins

## Context

OpenSpec change `2-rag-retrieval-quality-improvements` shipped a Markdown-aware chunking branch in `_read_and_chunk_file_async`. The chained parser (`MarkdownNodeParser → SentenceSplitter`) was the simplest possible heading-aware composition. Experiment 6 (5-doc Markdown corpus) showed Hit@1 saturation and could not discriminate the chunkers; Experiment 6b (20-paper Qasper-dev with evidence-level metrics) recorded the chunker as a real **negative result** at default settings.

This design document explains the architectural decisions behind 6c's four interventions and the deferred big-swings, with reference to the 6b post-mortem and the literature scan that informed the diagnosis.

## Problem statement

Two things must be true at once for the production answer to be "ship the Markdown chunker":

1. **Pass A non-regression**: chunker isolation, reranker off. Evidence Recall@5 ≥ baseline − 2 pp.
2. **Pass B lift**: production shape, reranker on. Evidence Recall@5 ≥ baseline + 2 pp.

6b cleared neither. The dominant cause (per the per-query drill) is that the candidate retrieves the right paper but its evidence-bearing chunk is at rank 6–15 instead of inside top-5, because the candidate has 49% more chunks for the same papers. The fix could be on either side of the equation: widen the retrieval window, or reduce the chunk-count rise. Both directions are tested in 6c; whichever wins on the smaller blast-radius gets the recommendation.

## Decision 1 — Knobs default to "no behaviour change"

All three new env vars (`MARKDOWN_CHUNK_SIZE`, `MARKDOWN_HEADING_PREPEND`, `MARKDOWN_MIN_CHUNK_FRACTION`) default to identical-to-current behaviour:

- `MARKDOWN_CHUNK_SIZE` defaults to `CHUNK_SIZE` — the existing single value.
- `MARKDOWN_HEADING_PREPEND` defaults to `false` — no prepend.
- `MARKDOWN_MIN_CHUNK_FRACTION` defaults to `0.0` — no floor.

This is a deliberate decision to keep the OpenSpec change *experiment scaffold*, not *behaviour change*. Production stays bit-for-bit identical until 6c writes `results.md` and a follow-up `5-experiment-6c-promote-defaults` change moves a default. If 6c records a second negative result, this change can be archived as scaffolding without rolling back any production behaviour.

The alternative considered was "ship the most promising knob enabled by default and treat 6c as the validation". We rejected that because it conflates the experiment with the production decision and makes the experiment less informative — if knob X is on by default, we can't measure baseline behaviour without re-rolling it.

## Decision 2 — Defensive metadata copy is always-on

`_ensure_heading_metadata` runs unconditionally in the `is_markdown` branch. There is no env var to disable it.

Rationale: the DeepWiki source review (LlamaIndex v0.14.21) confirmed that `_postprocess_parsed_nodes` already merges `header_path` from parent into child via two paths. The defensive `setdefault` call is therefore a no-op in the common case and only fires when LlamaIndex's internal propagation misses an edge case. Since it cannot regress correctness (it only adds metadata that should already be there) and it closes a real test-coverage gap (`tests/test_markdown_chunking.py` had zero assertions on metadata), there is no value in making it toggleable. Always-on is simpler.

If the per-query drill on 6c results shows Section Match@1 unchanged from 6b's metadata-copy-disabled run, that is informative — it confirms `_postprocess_parsed_nodes` already does the work and the `setdefault` is genuinely a no-op in our deployed corpus. We accept that as a possible outcome; the test gap is closed regardless.

## Decision 3 — `MARKDOWN_CHUNK_SIZE` is per-extension, not global

The Markdown branch reads `MARKDOWN_CHUNK_SIZE`; the bare-splitter branch (everything that's not `.md`) keeps reading `CHUNK_SIZE`. They are independent.

Two reasons:

- **Different file types have different optimal chunk sizes.** Bhat et al. 2025 [2] show 64–128 token chunks are optimal for factoid queries on short documents and 512–1024 are optimal for documents needing broader contextual understanding. Markdown is structurally rich and benefits from larger chunks (preserves heading sections); plain text and PDFs in our typical corpus often don't have heading structure to preserve and the existing default works.
- **6c's research question is the Markdown branch only.** Widening `CHUNK_SIZE` globally would conflate "Markdown chunker improvement" with "global chunk-size change" and obscure which one helped.

The alternative was to add per-file-extension chunk-size config (e.g. `CHUNK_SIZE_MD`, `CHUNK_SIZE_PDF`). We rejected the more general scheme as YAGNI — only the Markdown branch has a heading parser before the splitter, and only the Markdown branch is affected by 6b's regression. If a future experiment needs PDF-specific chunk sizes we can add a knob then.

## Decision 4 — Heading prepend writes to `node.text`, not a new metadata key

`_apply_heading_prepend` modifies `node.text` in place: `node.text = f"[{heading_path}] {node.text}"`. It does NOT write to a new `node.metadata["chunk_text_with_heading"]` key.

The reason is the embedding surface. The embedder embeds `node.text` and only `node.text`. Putting the heading in a metadata field would not affect retrieval scoring at all. The whole point of H is to give the embedder heading keywords for queries like "what experiments did they run for the Setup section" — the heading needs to be embedded.

This means H is a *destructive* change — it modifies the chunk text. Two safeguards:

- **Idempotence guard**: skip prepend when `node.text` already starts with `[` followed by a path. Re-ingestion of an already-prepended chunk does not double-prepend.
- **Reversibility**: structured `node.metadata["header_path"]` is unchanged. If H is later disabled, the next ingestion writes fresh chunks without the prefix and ChromaDB upserts replace the old ones.

The alternative was to embed `f"{heading_path}\n\n{node.text}"` (newline-separated rather than bracketed). We picked the bracketed form because it is more obviously a synthetic prefix and easier to spot in eval debug output.

## Decision 5 — Min-size floor drops, doesn't merge (for now)

`_drop_small_chunks` filters out small chunks rather than merging them with a sibling. The simpler "drop" variant ships first.

Trade-off: dropping loses information; merging preserves it. But:

- Orienting `## Introduction\n\nWe study X.` chunks are near-pure noise on Qasper — the substantive content lives in the next section. Dropping them is information-preserving in practice.
- Merging requires knowing the sibling order and updating heading metadata on the merged chunk. The implementation is non-trivial in the chained `MarkdownNodeParser → SentenceSplitter` pipeline because the second stage doesn't preserve sibling order across multi-section inputs the way you'd want.
- HiChunk's Auto-Merge (Lu et al. 2025 [4]) does retrieval-time merging, not ingestion-time merging. Their reported gains rely on the wider candidate pool semantics and retrieval-side merging is a separate OpenSpec change.

We accept that F may be too aggressive on some files. If 6c's Phase 3 shows F regressing nDCG@5 on the general/evidence-dense split, the fallback is to ship the merge variant in a follow-up change.

## Decision 6 — Defer HierarchicalNodeParser + AutoMergingRetriever and contextual retrieval

These are the bigger swings; both are real options. They are not in 6c.

Decision rationale:

- **Cross-module change**: HierarchicalNodeParser + AutoMergingRetriever touches `ingestion.py`, `retrieval.py`, and the `search()` output shape. It needs a `SimpleDocumentStore` + `StorageContext`, which is a meaningful new dependency surface. The full work is at least a 100+ LOC change spread across 3 modules with new tests.
- **Latency budget**: contextual retrieval via local Ollama `qwen3:0.6b` adds 7–14 minutes of ingestion time on the 20-paper corpus and a non-trivial behaviour change to `_read_and_chunk_file_async`. The reported lift in Anthropic's blog is large (~35% retrieval-failure reduction) but unverified in our deployment context.
- **No evidence yet that small-bore is insufficient**: the reranker (Pass B) already recovers ~67% of the 6b regression. A `top_k=10` change might recover the rest by itself. We don't yet have data justifying disproportionate effort.

The escalation path is explicit in `tasks.md` outcome F: if 6c's best cell does not reach Pass B parity, the deferred big-swings get a fresh OpenSpec change with their own evidence base from 6c.

## Decision 7 — Copy 6b's corpus and ground truth, then rebuild indexes locally

6c copies 6b's `corpus/` and `ground-truth.json` into the 6c experiment directory. It then rebuilds `chroma_baseline/` and each candidate ChromaDB from the 6c-local corpus. No symlinks are used at runtime.

This keeps the scientific control from 6b — same papers, same ground truth, same embedder — while making 6c self-contained and avoiding stale ChromaDB metadata paths that point back to the old 6b directory.

The cost is that 6c spends extra time rebuilding indexes. We accept that cost because each experiment directory should be portable and professional on its own. The recommended fallback corpora (MultiHop-RAG, GutenQA) are listed in 6b's References for a future experiment 7-series cross-corpus replication.

## Risks

1. **Phase 1 stop rule may be too lenient.** If `top_k=10` brings Pass A to baseline − 1.5 pp and Pass B to baseline + 0.5 pp, the rule says "Phase 1 closes it". But that's a much weaker production claim than the original 6b ≥ 5 pp lift target. Mitigation: `results.md` reports the absolute numbers and lets the operator decide whether parity-or-better is shippable for their use case.
2. **`chunk_size=1024` may exceed embedder context.** `qwen3-embedding:0.6b` has a context window of around 8K tokens, so 1024-token chunks are well within it. But if a future embed-model swap reduces context, the experiment results don't transfer. Mitigation: the experiment records the embed model in every output JSON.
3. **Heading prepend may shift embedding centroids in a way that hurts non-heading-targeted queries.** The "general/evidence-dense Evidence Recall@5 non-regression" criterion in `protocol.md` catches this. If H regresses general queries by more than 2 pp, we don't ship H.
4. **The candidate is now dependent on three env vars.** Operator misconfiguration (e.g. setting `MARKDOWN_HEADING_PREPEND=true` without re-ingesting) produces an inconsistent index. Mitigation: the env vars are read at ingestion time only; retrieval-time changes are impossible. Document this clearly in `.env.example`.

## Open questions for the user

- Should the `top_k` change in `retrieval.py` be a default change or a `top_k` parameter on every MCP tool call? Current code has a default but tools accept overrides. If 6c's outcome A wins, we need to decide which path. (Recommendation: change the default; tools that override are unaffected.)
- Should `MARKDOWN_HEADING_PREPEND=true` apply to non-`.md` files that happen to have heading-like text (e.g. PDFs converted from Markdown sources)? Current scope is `.md` only. (Recommendation: keep `.md`-only for 6c; broaden in a future change if needed.)
