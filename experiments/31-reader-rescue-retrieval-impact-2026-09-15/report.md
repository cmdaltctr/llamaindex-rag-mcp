# Experiment 31: Reader Rescue Retrieval Impact — Report

**Verdict: The tiered LiteParse-first rescue chain retrieves gold evidence materially worse than the historical pypdf-only guard on this corpus (paired hit@10 delta −0.208, bootstrap 95% CI [−0.375, −0.083]). Rescued text DOES produce direct downstream retrieval evidence in both rescue cells — but the LiteParse tier silently loses or mangles text on WinAnsi-without-/ToUnicode PDFs, and those losses reach the index.**

- **Experiment**: `31-reader-rescue-retrieval-impact-2026-09-15`
- **Status**: PASS (question answered decisively; the answer is negative for the candidate)
- **Operator**: a-build agent, 2026-09-15; OpenSpec change `experiment-31-reader-rescue-retrieval-impact`
- **Protocol**: `protocol.md`; frozen inputs verified before the measured run (14/14 preflight checks)

## Bottom line

1. Any rescue beats no rescue, and rescued text survives chunking and
   embedding well enough to retrieve gold evidence in both rescue cells
   (Cell B Recall@10 = 0.583; Cell C = 0.792, against 0.0 for the
   pdf-inspector-only sanity cell by construction).
2. The current production chain (Cell B) is **materially worse** than the
   pypdf-only guard (Cell C) on this corpus. The paired per-query
   hit@10 difference is −0.208 with a 95% bootstrap confidence interval
   of [−0.375, −0.083] — the interval excludes zero.
3. The loss decomposes into two failure modes across the five
   disagreement queries:
   - **Parser-stage loss (4 queries, both Type B ACL papers)**: the gold
     span is absent from LiteParse's extraction at character level (best
     word-8-gram overlap 0.18–0.39 against the frozen 0.85 threshold);
     pypdf's extraction contains it and retrieves it at rank 1–2.
   - **Retrieval-stage miss (1 query, a Type A IA book)**: the span is
     fully present in Cell B's extraction (overlap 1.000) yet absent
     from its top-10, while Cell C retrieves it at rank 1.
4. Extraction speed still favours the chain overwhelmingly (median
   held-out reader time 3.9 s vs 28.7 s — the LiteParse tier is ~7x
   faster than the pypdf retry on these books).

## Context

Production retries silent-empty `text_based` extractions through
LiteParse (OCR disabled) then pypdf (ADR-066). Experiment 30 validated
text recovery and speed; it did not measure retrieval. Experiment 31
asks whether rescued text retrieves gold evidence, and whether the
LiteParse-first chain retrieves as well as the historical pypdf-only
guard (commit 928f030).

Three cells, one manipulated variable (the reader path), everything
downstream frozen: `documents` profile (top_k=10, reranker on, dense
only), markdown model-token chunking (1024 tokens, Qwen tokenizer,
overlap 100), local Ollama `qwen3-embedding:0.6b` embeddings, LanceDB
(one table per cell), metadata extraction disabled, OCR disabled in all
cells. Preflight verified the controlled variables identical across
cells and the freeze intact.

Corpus (frozen by SHA-256 before the measured run):

| Group | Count | Notes |
| --- | --- | --- |
| Held-out | 8 natural PDFs meeting the exact trigger (`text_based`, pages > 0, empty extraction) | 6 Type A (IA GlyphLessFont), 2 Type B (ACL WinAnsi without `/ToUnicode`); 1 partial extraction excluded during sourcing |
| Distractors | 11 healthy born-digital PDFs | indexed with the held-out group in every cell |
| Development | 5 Experiment 30 pathological/control documents | harness checks only; never indexed, never scored |

24 queries (3 per held-out PDF), gold spans labelled from poppler
`pdftotext` output — an extractor used by no cell — and verified
single-page against the source before freezing.

## Results

Primary metrics (24 queries per cell; higher is better except no-hit):

| Metric | A sanity | B candidate (chain) | C reference (pypdf guard) |
| --- | --- | --- | --- |
| Evidence recoverability | 0.000 | **0.792** | **1.000** |
| Evidence Recall@1 | 0.000 | 0.542 | 0.625 |
| Evidence Recall@3 | 0.000 | 0.542 | 0.750 |
| Evidence Recall@5 | 0.000 | 0.583 | 0.792 |
| Evidence Recall@10 | 0.000 | 0.583 | 0.792 |
| MRR@10 | 0.000 | 0.552 | 0.698 |
| No-hit rate | 1.000 | 0.417 | 0.208 |

Paired candidate-vs-reference (per-query, n = 24, 10,000-resample
bootstrap, seed 31):

| Measure | Mean B−C | 95% CI |
| --- | --- | --- |
| hit@10 | −0.208 | [−0.375, −0.083] |
| reciprocal rank@10 | −0.146 | [−0.323, 0.021] |

Disagreements (C hits, B misses): q16 (h06, Type A — recovered in B's
extraction but not retrieved), q19/q22/q23/q24 (h07/h08, Type B — span
absent from LiteParse's extraction at 0.18–0.39 8-gram overlap).

Secondary outcomes:

| Measure | A | B | C |
| --- | --- | --- | --- |
| Held-out reader seconds (median) | 3.28 | 3.94 | 28.67 |
| Held-out characters (total) | 0 | 4,421,347 | 5,050,211 |
| Chunks in index | 2,737 | 4,404 | 5,041 |
| Index size | 26.0 MB | 41.1 MB | 44.8 MB |
| Embedding tokens | not exposed by the ingest surface | same | same |

## Discussion

**Rescued text has direct downstream retrieval evidence.** Both rescue
cells retrieve gold evidence from rescued text at rank 1 for most
queries — a rescue converts guaranteed zero-retrieval documents into
retrievable ones. The open question from the proposal is answered
positively for the mechanism and negatively for the tier order.

**The LiteParse tier's losses are not only volume.** Experiment 30
attributed the 2–16% character shortfall to omitted textless pages and
joining differences. Experiment 31 shows a harsher failure on Type B
(WinAnsi TrueType without `/ToUnicode`) PDFs: LiteParse's rendering of
the same invisible text layer differs at character level, so 4 of 6
Type B queries lose their gold span entirely (8-gram overlap 0.18–0.39
vs the 0.85 threshold). Those documents are `rescued` by characters
counted (45k and 21.6k) while their content is partially unreadable —
a silent quality loss no character-volume gate would catch.

**One Type A retrieval miss (q16) shows a second-order effect.** The
span is fully present in Cell B's extraction yet absent from its top-10
while Cell C ranks it first. With ~12% fewer characters and 163 fewer
chunks in Cell B's index, the reranker's candidate pool or chunk
boundaries differ enough to lose a rank-1 answer. A single query is a
small-sample observation, retained as a negative finding, not a
general claim about Type A documents (the other 17 Type A queries hit
in both cells).

**Speed/quality trade-off.** The chain's LiteParse tier is ~7x faster
than the pypdf retry on the held-out books (3.9 s vs 28.7 s median).
That speed advantage is real and large — but it currently buys a
measured retrieval regression concentrated on Type B documents.

### Limitations

- 24 queries over 8 held-out documents (6 Type A, 2 Type B): small
  sample. The bootstrap interval is reported because n >= 20, but the
  corpus covers only two failure types; other silent-empty aetiologies
  may behave differently.
- The gold spans come from poppler, another cmap consumer. A span
  pypdf and poppler agree on but LiteParse renders differently is
  scored as a LiteParse loss — that is the intended direction (the
  guard must recover what standard extractors recover), but it means
  "recoverability" is defined relative to mainstream extractor
  behaviour, not to an oracle rendering.
- The French volume's (h01) spans carry heavy OCR noise; its three
  queries hit in both rescue cells, so noise alone did not decide the
  comparison.
- Embedding token counts were not exposed by the ingest result
  surface; chunk count and index size stand in as the cost proxies.
- Retrieval used one frozen configuration (`documents` profile, local
  0.6B embeddings). A different embedding model or reranker setting
  could shift absolute numbers; the paired design keeps the B-vs-C
  comparison internally valid.

## Conclusion

The tiered LiteParse-first chain (ADR-066) carries a measured,
CI-backed retrieval regression against the pypdf-only guard on this
corpus: −0.208 hit@10 (95% CI [−0.375, −0.083]), driven by
parser-stage text loss on WinAnsi-without-/ToUnicode documents plus one
retrieval-stage miss. The regression coexists with a ~7x extraction
speed advantage.

Per the protocol's decision rule this experiment does NOT change
production behaviour. If production behaviour should change — for
example reordering the chain to pypdf-first for `text_based` documents,
or gating the LiteParse tier on a post-rescue text-integrity check —
that requires a separate OpenSpec proposal with its own decision
record. The natural follow-up experiment would measure whether a
pypdf-first order keeps the chain's latency budget on large documents.

## Artefacts

| Artefact | Path |
| --- | --- |
| Protocol (frozen) | `protocol.md` |
| Frozen input hashes | `output/frozen.manifest.json` |
| Cell definitions + controlled variables | `cells.json` |
| Corpus manifest (public) | `corpus_manifest.json`; sourcing detail: `corpus/SOURCING.md` (local) |
| Queries + gold spans | `queries/qrels.json` (local, gitignored) |
| Extraction manifest | `output/extraction_manifest.json` |
| Runtime manifests | `output/runtime_manifest_{A,B,C}.json` |
| Preflight | `output/preflight.json` (14/14 PASS) |
| Per-query results | `output/eval_results.json` (local); checkpoint beside it |
| Summary | `output/eval_results.summary.json` |
| Analysis notebook source | `analysis.py` (Jupytext; notebook gitignored) |
| Indexes | `output/lancedb/` (local, ~113 MB total) |
