# Experiment 6: Markdown-Aware Chunking Quality

**ID**: `markdown-chunking-quality-2026-05-27`
**Date**: 2026-05-27
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent (for automation)
**Status**: PLANNED
**Related OpenSpec change**: `rag-retrieval-quality-improvements` (Tier 2)

---

## What this experiment is for

The Tier 2 OpenSpec change adds a Markdown-aware branch to the chunker. For
files with extension `.md`, ingestion now runs the documents through
LlamaIndex's `MarkdownNodeParser` first, then through the existing
`SentenceSplitter` as a size cap. The expected payoff is better retrieval on
**heading-targeted queries** ("under section X, what does the doc say about
Y?") because chunk boundaries now align with heading boundaries instead of
splitting mid-section at arbitrary token counts.

The risk is that on prose-heavy or unstructured Markdown, the new chunker
either produces oddly-sized chunks or breaks something subtle. This
experiment confirms:

1. Heading-targeted queries get better Hit@1 / MRR with the new chunker.
2. General queries on the same Markdown corpus do not regress.
3. The size cap actually fires when a heading section exceeds `CHUNK_SIZE` —
   no chunk should silently grow beyond `CHUNK_SIZE * 1.1`.

---

## Hypothesis

The chained `MarkdownNodeParser` → `SentenceSplitter(chunk_size=512, chunk_overlap=100)`
chunker improves Hit@1 and MRR on heading-targeted Markdown queries by at
least 5 percentage points relative to the `SentenceSplitter`-only baseline,
while holding general-query Hit@1 within ±2 percentage points of the
baseline. No chunk in either configuration exceeds `CHUNK_SIZE * 1.1` in
character length.

---

## Background

The current chunker uses a single `SentenceSplitter(chunk_size=512,
chunk_overlap=64)` for every file type. For Markdown documents — especially
docs sites, READMEs, and technical references — this means chunks frequently
straddle heading boundaries: half of section A and half of section B end up
in the same chunk, which makes "under section A, what is X?" queries harder.

The proposed change uses a two-stage pipeline:

1. `MarkdownNodeParser` — splits on heading boundaries (H1, H2, H3, …).
2. `SentenceSplitter(chunk_size=512, chunk_overlap=100)` — caps any
   heading-bounded section that is longer than `CHUNK_SIZE`.

Both parsers ship with `llama-index-core` so no new dependency is needed.
The "chained splitter" pattern matters because `MarkdownNodeParser` alone
will happily emit a single 10K-character node for a long H2 section, which
defeats embedding batch sizing and produces one chunk that drowns out the
rest of the document at retrieval time.

References from the Tier 2 proposal reading list:

- Pham, V. & Luong, T. (2025). *Heading-aware chunking for RAG on
  technical documentation*. Hit@1 +12 pp.
- Lavarec, R. & Du, X. (2026). *Structure-aware chunkers for SPA-rendered
  docs*. MRR +0.08.
- Stäbler, F. et al. (2025). *Empirical chunking benchmarks at scale*.
  100-token overlap is the sweet spot (informs the related `CHUNK_OVERLAP`
  bump in Exp 7).

The `CHUNK_OVERLAP=100` default is already in place by the time this
experiment runs (Tier 2 task 3.1). We use 100 here to match the shipped
config.

---

## Variables

| Type        | Variable                          | Values                                                                            |
| ----------- | --------------------------------- | --------------------------------------------------------------------------------- |
| Independent | Chunker                           | `SentenceSplitter` only (baseline) / `MarkdownNodeParser → SentenceSplitter` (new) |
| Dependent   | Hit@1, Hit@3, Hit@5, MRR          | Per query category (heading-targeted, general)                                    |
| Dependent   | Chunk count per document          | —                                                                                 |
| Dependent   | Mean chunk length (chars)         | —                                                                                 |
| Dependent   | P95 chunk length (chars)          | —                                                                                 |
| Dependent   | Max chunk length (chars)          | Must be ≤ `CHUNK_SIZE * 1.1` = 563 chars                                          |
| Controlled  | Embedding model                   | `qwen3-embedding:0.6b` (1024-dim)                                                 |
| Controlled  | Reranker                          | **Disabled** — we want to isolate the chunker effect                              |
| Controlled  | `CHUNK_SIZE`                      | 512                                                                               |
| Controlled  | `CHUNK_OVERLAP`                   | 100 (post-Tier-2 default)                                                         |
| Controlled  | Similarity threshold              | 0.0 (no filtering)                                                                |
| Controlled  | Hardware                          | Apple Silicon Mac, 16 GB                                                          |

> **Why reranker disabled?** The Markdown chunker affects which chunks exist,
> not how they are scored. If the reranker is on, it will paper over chunker
> mistakes — we'd be measuring "reranker + chunker" instead of "chunker
> alone". Re-enable in Exp 9 if you want the combined picture.

---

## Environment & Prerequisites

| Requirement   | Version / Value                    |
| ------------- | ---------------------------------- |
| Python        | 3.12                               |
| Ollama models | `qwen3-embedding:0.6b`             |
| Hardware      | Apple Silicon Mac, 16 GB           |
| Code branch   | Tier 2 with Markdown branch wired in (`tasks.md` 1.1–1.7) |

```bash
# Verify prerequisites
ollama list   # qwen3-embedding:0.6b must be present
uv sync
```

---

## Step 1: Prepare the corpus

Place 4–6 Markdown documents into `corpus/`. Aim for a mix of structured and
prose-heavy:

```
experiments/6-markdown-chunking-quality-2026-05-27/corpus/
├── structured/
│   ├── nuxt-readme.md            (long README with many H2 sections)
│   ├── pinia-getting-started.md  (heading-heavy docs page)
│   └── django-rest-quickstart.md (tutorial with stepwise H2/H3)
├── prose/
│   └── essay-on-rag.md           (mostly prose, few headings)
└── edge/
    └── no-headings.md            (pure prose, no Markdown headings)
```

Guidelines:

- **Structured (3 files)**: long Markdown with many H2/H3 sections each
  shorter than `CHUNK_SIZE`. Heading-targeted queries should benefit most.
- **Prose (1 file)**: mostly running text with occasional headings.
  Tests that the new chunker does not hurt prose-heavy Markdown.
- **Edge (1 file)**: a Markdown file with no headings at all. The
  Markdown branch should still produce non-empty chunks (Tier 2 task 1.7).

Sources you can use:

| Type       | Easy source                                                        |
| ---------- | ------------------------------------------------------------------ |
| Structured | Any popular OSS README (clone the repo, copy `README.md`)          |
| Structured | A Nuxt / Vue / FastAPI docs page exported via "view source"        |
| Prose      | A long Substack post saved as Markdown                             |
| Edge       | Any `.txt` essay renamed to `.md`                                  |

---

## Step 2: Write ground-truth queries

This is the most important step. **Write queries before running the
experiment** so the chunker change cannot bias query selection.

Edit `ground-truth.json`. Aim for 18–24 queries total, partitioned:

| Category            | Count    | Example                                                              |
| ------------------- | -------- | -------------------------------------------------------------------- |
| Heading-targeted    | 10–12    | "Under the 'Authentication' section, how does Nuxt handle JWT?"      |
| General             | 6–8      | "What does the Pinia getting-started doc recommend for state shape?" |
| Cross-domain (negative) | 2–4 | "How do I configure Django REST permissions?" (must NOT match Nuxt)  |

For each query, pre-write:

```json
{
  "query": "Under the Authentication section, how does Nuxt handle JWT?",
  "expected_source": "nuxt-readme.md",
  "expected_section": "Authentication",
  "expected_answer": "JWT tokens are stored in",
  "category": "heading-targeted"
}
```

`expected_section` is the heading you expect the gold chunk to live under.
The eval script checks whether the top-ranked chunk's metadata records that
heading (when the new chunker is active — heading metadata is one of its
side effects).

---

## Step 3: Ingest under both chunkers

Two fresh ChromaDBs, one for each chunker config, so we can run the same
query set against both:

```bash
# Baseline (SentenceSplitter only). Run on a branch BEFORE Tier 2 task 1.x lands,
# OR run on the post-Tier-2 branch with the Markdown branch flag-disabled.
CHROMA_PERSIST_DIR=./chroma_md_baseline \
  CHUNK_OVERLAP=100 \
  uv run rag-mcp ingest experiments/6-markdown-chunking-quality-2026-05-27/corpus

# New chunker (MarkdownNodeParser → SentenceSplitter). Post-Tier-2 branch.
CHROMA_PERSIST_DIR=./chroma_md_new \
  CHUNK_OVERLAP=100 \
  uv run rag-mcp ingest experiments/6-markdown-chunking-quality-2026-05-27/corpus
```

If your Tier 2 implementation does not have a flag to disable the Markdown
branch, the cleanest baseline is to git-stash the branch change and re-run
ingest. The eval script does not care which method you use — it just reads
two different ChromaDB directories.

---

## Step 4: Run the eval

```bash
cd experiments/6-markdown-chunking-quality-2026-05-27
uv run python run_eval.py \
  --baseline-dir ./chroma_md_baseline \
  --candidate-dir ./chroma_md_new
```

The script:

1. Loads `ground-truth.json` (18–24 queries).
2. For each chunker config:
   - Runs every query, captures top-5 sources, top-5 scores, top-1 metadata.
   - Computes Hit@1 / Hit@3 / Hit@5 / MRR per category.
   - Records chunk-length stats from each ChromaDB (mean / P95 / max chars).
3. Prints a comparison table.
4. Saves raw data to `eval_results.json`.

---

## Step 5: Interpret the results

```
┌──────────────────────────┬───────────┬───────────┬───────────┬───────┬───────┐
│ Config / Category        │  Hit@1    │  Hit@3    │  Hit@5    │  MRR  │ Chunks│
├──────────────────────────┼───────────┼───────────┼───────────┼───────┼───────┤
│ Baseline / heading-targeted│  60.0%  │  80.0%    │  90.0%    │ 0.700 │       │
│ New      / heading-targeted│  85.0%  │  92.5%    │  95.0%    │ 0.875 │       │
│ Baseline / general         │  78.0%  │  88.0%    │  90.0%    │ 0.815 │       │
│ New      / general         │  78.0%  │  90.0%    │  92.0%    │ 0.825 │       │
│ Baseline / chunk stats     │   —     │   —       │   —       │   —   │ 142   │
│ New      / chunk stats     │   —     │   —       │   —       │   —   │ 158   │
└──────────────────────────┴───────────┴───────────┴───────────┴───────┴───────┘
Baseline  mean chunk =  486 chars,  P95 =  511,  max = 512
New       mean chunk =  402 chars,  P95 =  511,  max = 512   (no overruns)
```

Key questions:

1. **Heading-targeted improvement**: did Hit@1 lift by ≥ 5 pp on
   heading-targeted queries? If yes, the chunker change is earning its
   complexity. If no, dig into per-query failures — the new chunker may be
   making worse splits on this corpus shape.
2. **General-query non-regression**: Hit@1 within ±2 pp of baseline?
3. **Size cap honoured**: max chunk length ≤ `CHUNK_SIZE * 1.1` = 563 chars
   under the new chunker? If a section is bigger than that, the
   `SentenceSplitter` cap is not firing and Tier 2 task 1.5 has a bug.

---

## Success Criteria

| Check                                       | Pass condition                                                                  |
| ------------------------------------------- | ------------------------------------------------------------------------------- |
| Heading-targeted Hit@1 improves             | New chunker Hit@1 (heading-targeted) − Baseline Hit@1 (heading-targeted) ≥ 5 pp |
| General-query non-regression                | New chunker Hit@1 (general) ≥ Baseline Hit@1 (general) − 2 pp                   |
| Size cap honoured                           | New chunker max chunk length ≤ `CHUNK_SIZE * 1.1` = 563 chars                   |
| No-headings file still chunked              | New chunker produces non-empty chunks for `edge/no-headings.md`                 |
| Heading metadata attached                   | New chunker chunks carry a heading-path metadata field (sanity)                 |

---

## What to do if the experiment fails

If heading-targeted Hit@1 does not improve by ≥ 5 pp:

1. Inspect the per-query failures in `eval_results.json`. Likely causes:
   - Markdown documents have inconsistent heading levels (e.g. starting at
     H3 instead of H1). Check whether `MarkdownNodeParser` is splitting
     where you expect.
   - Queries are not actually heading-targeted enough. If the gold answer
     is in the middle of a section, baseline chunking might already
     capture it.
2. Tighten the corpus toward more obviously heading-aligned content and
   re-run.
3. If the chunker is genuinely not helping on this corpus, document the
   negative result in `results.md`. The Tier 2 design lets us ship the
   change anyway because it is a structural improvement, but the experiment
   should record that the corpus didn't show a measurable gain.

If general-query Hit@1 regresses by more than 2 pp:

1. Inspect chunk-length stats. If new chunker produces many short chunks,
   the splitter cap is firing too often and breaking sentences mid-flow.
2. Consider widening the chunk size or revisit the chained-splitter design.
3. This is a real regression. Loop back to Tier 2 task 1.x and revise.

If max chunk length exceeds 563 chars:

1. The size cap is broken. Re-read Tier 2 task 1.5.
2. Confirm `SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)`
   is genuinely chained after `MarkdownNodeParser`, not replacing it.
3. Add a unit test asserting cap behaviour and re-run.

---

## Cleanup

```bash
rm -rf ./chroma_md_baseline ./chroma_md_new
```

---

## References

- `openspec/changes/rag-retrieval-quality-improvements/design.md` — Decision 1
- `openspec/changes/rag-retrieval-quality-improvements/tasks.md` — tasks 1.1–1.7
- LlamaIndex `MarkdownNodeParser`:
  https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/markdown/
- Pham, V. & Luong, T. (2025). *Heading-aware chunking for RAG on technical documentation*.
- Lavarec, R. & Du, X. (2026). *Structure-aware chunkers for SPA-rendered docs*.
- Stäbler, F. et al. (2025). *Empirical chunking benchmarks at scale*.
- Qu, S., Tu, B. & Bao, Y. (2024). *Semantic chunking is not always worth it*. (Cited as the rejected alternative.)

---

## Artefacts

| File                | Description                                                                |
| ------------------- | -------------------------------------------------------------------------- |
| `protocol.md`       | This file — hypothesis, method, reproduction steps                         |
| `corpus/`           | Markdown test documents (structured / prose / edge subfolders)             |
| `ground-truth.json` | Pre-written queries with expected_source, expected_section, expected_answer |
| `questions.md`      | Human-readable companion to `ground-truth.json`                            |
| `run_eval.py`       | Automation script (queries × 2 configs)                                    |
| `eval_results.json` | Raw per-query results for both configs                                     |
| `results.md`        | Comparison tables, chunk-length stats, decision                            |
