# Experiment 37: dots.mocr routing acceptance on real documents

- **ID**: `37-dots-mocr-routing-acceptance-2026-09-30`
- **Date run**: 2026-10-04 to 2026-10-06
- **Operator**: Dr Muhammad Aizat Bin Md Hawari (labels, noise verdicts, approvals), with Claude Code (runs and analysis)
- **Status**: PASS
- **Verdict**: Accept the built system. The maths-page detector raises no false alarm on pages without maths, dots.mocr emits formulas that all render, and the operator found no invented text from either engine.
- **Raw data**: [`output/summary.json`](./output/summary.json), [`output/pages.json`](./output/pages.json)
- **Change**: `openspec/changes/modular-ocr-workers-dots-mocr`, tasks 7.1 to 7.3 (protocol amendment A1 changes the wording of 7.3)
- **Protocol**: [protocol.md](protocol.md) (version 2), [plan.json](plan.json)

## Bottom line

The built system passes all three acceptance gates. The maths detector flagged 0 of the 64 control pages without maths. dots.mocr emitted 1,893 formulas, and every one rendered in KaTeX. The operator judged 41 engine outputs on 21 pages and found no invented text. dots.mocr is also the stronger engine on scripts and handwriting: median token recall 0.889, against 0.610 for PaddleOCR-VL on CPU. Five findings follow, and none of them blocks acceptance. The most important is that dots.mocr dropped a rotated table on one scanned page.

## What we tested and why

The question: does the system built in `modular-ocr-workers-dots-mocr` behave on real documents as the change claims? The change does three things:

1. A **maths-page detector** reads the fonts on each PDF page. It sends pages that use a maths font straight to OCR.
2. **dots.mocr** becomes the primary OCR engine (on the Mac GPU, through PyTorch MPS).
3. **PaddleOCR-VL** stays as the fallback engine (on the CPU).

Every OCR request went through the host path (`OcrRoutes`, with the engine named in `OCR_ENGINE_PRIMARY`). This acceptance check is task 7 of the change. It does not decide the engine choice, which the operator made on 2026-09-24.

## Setup at a glance

| Item | Value |
| --- | --- |
| Code under test | OMRG `7113571` (experiment branch `f5c43dc`), `MATHS_DETECTOR_VERSION` 1 |
| dots.mocr | `rednote-hilab/dots.mocr` revision `e539fbb`, pipeline `prompt_layout_all_en+omrg-mps-1+layout-1`, MPS bfloat16 |
| PaddleOCR-VL | PaddleOCR-VL 1.6, pipeline `predict+restructure_pages`, CPU |
| Protocol | worker protocol 1.1, one page per request, default timeout 300 s |
| Hardware | Apple M5 Pro, 48 GB |
| Formula check | KaTeX 0.16.22, `throwOnError: true` |
| Maths positives | 5 arXiv papers, 106 pages: `eq01` (Kingma 2013), `mp01` (LIPIcs, glyphtounicode), `mp03` (Ulmer, AMS fonts), `mp04` (Shor 1996), `mp05` (Word, Cambria Math) |
| Negative controls | `bd01`, `bd02`, `bd03` (Experiment 34) and `pc01` (prose-only LaTeX paper), 67 pages |
| Scanned set | 28 Experiment 34 problem pages (`io04`, `io06`, `tl03`) |
| Script and handwriting set | 189 Experiment 33 pages: Devanagari 48, Bengali 60, Arabic 21, Latin handwriting 60 |

The operator labelled all 173 detection pages `maths` or `no_maths` from page images, without seeing the detector's flags. Sources and SHA-256 hashes are in [`sources.json`](sources.json).

## Results

### Pass gates

| Gate | Rule | Measured | Pass? |
| --- | --- | --- | :---: |
| G1 | 0 flagged pages among `D-neg` pages labelled `no_maths` (A1) | 0 of 64 | ✅ |
| G2 | dots.mocr KaTeX error rate ≤ 0.05 over `E-maths` and `E-scan` | 0 of 1,893 (0.000) | ✅ |
| G3 | operator verdict for every page on the noise list | 41 of 41 | ✅ |

### Detection (`D-pos`, `D-neg`)

| Run | Pages | Flagged and `maths` | Flagged and `no_maths` | Missed `maths` | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `D-pos` (maths papers) | 106 | 81 | 10 | 0 | 0.890 | 1.000 |
| `D-neg` (controls) | 67 | 2 | 0 | 1 | 1.000 | 0.667 |

- **The 10 flags on `no_maths` pages in `D-pos`** come from pages that draw a few glyphs in a maths font, such as a title page, a symbol or a reference list. Each of the five papers still crosses the 0.10 whole-document fraction, with flagged shares of 0.79 to 1.00.
- **The 2 flags in `D-neg`** are `bd03` p4 (`CMMI10`) and p6 (`CMSY10`). The operator labelled both `maths` (p6: "chemical equation").
- **The 1 miss** is `bd02` p3. Its maths uses `AdvminionMathIt`, `AdvminionMathEx` and `AdvminionSymbols`, which are not in `MATHS_FONT_PATTERNS`.

### OCR runs (257 pages per engine)

| Engine | Pages with output | Timeout | Empty | Median s per page | Engine time | Peak memory | Worker processes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dots.mocr | 257 | 0 | 0 | 37.0 | 3.31 h | 22.2 GiB | 1 |
| PaddleOCR-VL | 221 | 34 | 2 | 40.2 | 6.06 h | 14.6 GiB | 35 |

| Engine | KaTeX formulas | Render errors | Error rate |
| --- | ---: | ---: | ---: |
| dots.mocr | 1,893 | 0 | 0.000 |
| PaddleOCR-VL | 1,792 | 2 | 0.001 |

### Script and handwriting recall (`E-script`, reported, not gated)

Token recall is the share of reference tokens that the engine output contains. The reference is the Experiment 33 transcription, and the tokeniser is Experiment 33 `build_labels.tokens`. A page with no output scores 0.

| Writing system | Pages | dots.mocr median | dots.mocr share ≥ 0.8 | PaddleOCR-VL median | PaddleOCR-VL pages without output | Experiment 33 local tier median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Devanagari | 48 | 0.985 | 1.00 | 0.875 | 9 | 0.000 |
| Bengali | 60 | 0.887 | 0.92 | 0.506 | 14 | 0.000 |
| Arabic | 21 | 0.873 | 0.57 | 0.644 | 4 | 0.000 |
| Latin handwriting | 60 | 0.812 | 0.53 | 0.596 | 5 | 0.310 |
| All | 189 | 0.889 | 0.78 | 0.610 | 32 | 0.000 |

On PaddleOCR-VL's pages with output only, its overall median is 0.657.

### Noise review (G3)

The operator judged every engine with output on 21 pages. The pages came from an automatic screen (at least 10 words and 15% of the output not in the reference, or a line repeated 3 or more times), 5 random audit pages per engine, and `io06` p53, which the protocol names. Every other engine on those pages was judged too ("paired").

| Engine | Verdicts | Noise | Screen | Audit | Protocol | Paired |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dots.mocr | 21 | 0 | 2 | 5 | 1 | 13 |
| PaddleOCR-VL | 20 | 0 | 10 | 5 | 0 | 5 |

All 10 PaddleOCR-VL screen flags were clean. Old spelling (ſ read as f) and OCR spelling variants set them off, and none was invented text.

## Discussion

1. **The detector is safe on pages without maths.** It reads font names only, so it cannot confuse prose with maths. On these papers it catches every maths page. It also flags some pages without maths, which costs some extra OCR but loses no text.
2. **dots.mocr wins on scripts, handwriting and stability.** It answered all 257 requests with one worker process. PaddleOCR-VL on CPU timed out on 34 pages. Each timeout ends its worker, so the next page reloads the model, which is why PaddleOCR-VL took 6.06 h of engine time against 3.31 h.
3. **Neither engine invented text.** The one page the operator first marked as noise (`tl03` p8, dots.mocr) turned out to be a missing table, not added text (DR-5). It is finding F1 below.

### Findings (not gated)

| ID | Finding | Evidence |
| --- | --- | --- |
| F1 | dots.mocr drops rotated tables or charts | `tl03` p8: dots.mocr output is 45 characters (the caption only). PaddleOCR-VL read the rotated table (1,206 characters). |
| F2 | the detector misses renamed Minion Math fonts | `bd02` p3: `AdvminionMathIt`, `AdvminionMathEx`, `AdvminionSymbols` |
| F3 | the detector cannot see Word + MathType maths | arXiv 1106.0083v2 uses `Symbol` and `MT Extra` (DR-2). It was rejected from the corpus. |
| F4 | PaddleOCR-VL on CPU times out at the 300 s default | 34 of 257 pages, 35 worker processes |
| F5 | dots.mocr peak memory is higher than the smoke test showed | 22.2 GiB here, against 9.5 GiB on 2026-10-04 |

### Limits

1. The script references are Gemini transcriptions from Experiment 33, not human ground truth. Recall measures agreement with them.
2. The two engines ran in parallel from 2026-10-05 09:23 UTC, with dots.mocr on the GPU and PaddleOCR-VL on the CPU. Timings and memory were measured under that shared load. The first 20 dots.mocr pages ran alone.
3. The noise screen compares words, so it cannot see invented formulas, or noise on nearly blank pages. The operator review covers only the 21 listed pages.
4. The maths set is 5 papers. The detector result on font families outside these papers (F2, F3) is not measured.
5. The operator read a description of `bd03` p6 before labelling it (A1 blindness note).

## Conclusion

The experiment answers its question: the built system meets tasks 7.1 to 7.3 on real documents. Ship the detector and the routes as built.

1. **Implementation session:** accept amendment A1 (the G1 wording), then tick tasks 7.1 to 7.3 with this report as the evidence.
2. **Follow-up for F2 and F3:** add Minion Math patterns and a MathType signal in a detector version 2. That is a new change, with its own detection rerun.
3. **Follow-up for F1:** test rotated tables and charts on dots.mocr with more pages. A rotation step before the engine is one option.
4. **Follow-up for F4:** decide whether PaddleOCR-VL stays as the fallback. PaddleOCR-VL on MLX ran about 13 times faster in a 2-page test, with small output differences. A separate experiment should run it over these 257 pages and compare.
5. **Follow-up for F5:** update the memory figure in the configuration guide to about 22 GiB peak for dots.mocr.

## Artefacts

| File | Description |
| --- | --- |
| `output/summary.json` | Gates, detection, engine runs, KaTeX, recall, noise and findings |
| `output/pages.json` | One row per detection page and per OCR page (status, seconds, formulas, recall, verdict) |
| `output/detection.json` | Detector flags and font names per page |
| `output/ocr_state_<engine>.json` | Per-page OCR status, timing and engine fingerprint |
| `output/katex_<engine>.json` | Every formula error per page |
| `output/recall_<engine>.json` | Token recall per script page |
| `output/noise_screen.json` | Noise screen scores and the review list |
| `maths_labels.json` | Operator maths labels, 173 pages (SHA-256 `324ef438…`) |
| `noise_verdicts.json` | Operator noise verdicts, 41 slots (SHA-256 in `output/summary.json`) |
| `sources.json` | Document sources, licences and hashes |
| `run_detection.py`, `run_ocr.py`, `check_katex.mjs`, `score_recall.py`, `make_noise_review.py`, `summarise.py` | Scripts |
| `output/dots-mocr/`, `output/paddleocr-vl/`, `output/.pages/`, `corpus/` | Engine Markdown, page images and PDFs (gitignored) |
