# Experiment 36: Reader-output normalisation

**ID**: `36-reader-output-normalisation-2026-09-25`  
**Date planned**: 2026-09-25  
**Operator**: Dr Muhammad Aizat Bin Md Hawari (removed-text review), with pi coding agent (measurement)  
**Status**: PLANNED  
**Relation**: OpenSpec `normalise-reader-markdown`, Experiment 34, TDR-028

## Why this experiment exists

Experiment 34 found reader-produced HTML tags and image blocks in PDF Markdown.
The normaliser removes a closed set of tags before chunking. This experiment checks
whether it preserves visible document characters and whether image blocks hide captions.
The result decides whether the rules need revision before Experiment 34 review pages are rebuilt.

## Hypothesis and decisions

1. Every page retains all visible characters outside removed image blocks.
2. An operator finds no real caption inside the removed image blocks.
3. The operator decides whether a `[figure]` marker improves figure-heavy pages.

If a real caption is removed, tighten the rule, bump `NORMALISER_VERSION`, and repeat the measurement.
Rebuild Experiment 34 review pages only after the final rules and marker decision.

## Inputs and controls

| Item | Value |
| --- | --- |
| Source | `experiments/34-worker-sample-review-2026-09-19/output/{pdf_inspector,liteparse,worker}/<doc>/pNNN.md` |
| Sample | Existing Experiment 34 page outputs, including `eq01` p11 |
| Baseline | Raw reader Markdown, read-only |
| Candidate | `omrg.core.ingestion.normalise.normalise_reader_text` |
| Control | LiteParse output without known markup noise |
| Not changed | Reader settings, OCR outputs, page selection, retrieval, embeddings |

## Measurement

| Metric | Definition |
| --- | --- |
| Removed tags | Count by engine, page, and rule: formatting, image-bearing div, text-only div, bare image, table attributes, and breaks |
| Visible-character delta | Count after entity decoding and removal of HTML tags, excluding all text inside removed image blocks; ignore whitespace and generated Markdown emphasis |
| Removed image-block text | Full list with engine, document, page, and block position for operator review |
| Text-only divs | Count unwrapped blocks by engine and page |
| Equation guard | Compare protected maths byte-for-byte, including `&`, `<`, and LaTeX commands |

Save per-page observations and aggregates to `output/summary.json`. Include `NORMALISER_VERSION`,
the input file list, per-page counts, and the removed-text list. Do not rewrite source pages.

## Procedure

1. Commit this protocol before running the measurement.
2. Inventory existing Experiment 34 page files under the three reader directories.
3. Process each page with the normaliser and save a checkpoint after each page.
4. Write `output/summary.json` atomically from a temporary file.
5. Ask the operator to inspect every removed image-block text for real captions.
6. Record the verdict and `[figure]` marker decision in `report.md` and the change design.
7. If rules change, bump the version and repeat steps 3–6 before rebuilding review pages.

Runner command from the repository root (after task 4.1 is committed):

```bash
uv run python experiments/36-reader-output-normalisation-2026-09-25/measure.py --resume
```

## Gates and interpretation

| Gate | Pass condition |
| --- | --- |
| Visible text | Zero lost visible characters outside removed image blocks on every page |
| Protected content | Code, tables' cell text, and LaTeX maths retain their characters |
| Caption review | Operator confirms no real caption was removed, or rules are revised and rerun |
| Reproducibility | Every measured page is listed, and each source remains byte-identical |

A zero character loss and an approved removed-text review permit the Experiment 34 page rebuild.
A loss outside image blocks fails the measurement: identify the rule, fix it, bump the version,
and rerun. A missing source page makes the result INCONCLUSIVE until the inventory is reconciled.

## Safety and artefacts

This is a file-only experiment. It uses the existing `uv` environment and no model or network.
Write checkpoints and the final JSON under this experiment's `output/` only; use `.tmp` then rename.
Keep the Experiment 34 raw Markdown unchanged. Keep `output/summary.json` and `report.md` as evidence.
Expected files: `protocol.md`, `measure.py`, `output/summary.json`, `report.md`, and `analysis.py`.

## References

- `experiments/34-worker-sample-review-2026-09-19/report.md` and `output/`
- `openspec/changes/normalise-reader-markdown/{proposal.md,design.md,tasks.md}`
- `docs/tdr/028-normalise-reader-markdown-before-chunking.md`
