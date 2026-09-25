# Experiment 34: Worker Sample Review on Real Documents

**ID**: `34-worker-sample-review-2026-09-19`  
**Date run**: 2026-09-19 to 2026-09-24  
**Operator**: Dr Muhammad Aizat Bin Md Hawari (verdicts), with pi coding agent and Claude Code (runs, report)  
**Status**: PASS — scoped to 4 pages (A1); `io04` and `tl03` not evaluated  
**Verdict**: The PaddleOCR-VL worker is safe on clean pages and reads the old book. Task 2.3 goes ahead for `io06`-class pages. dots.mocr earns a full-sample comparison.  
**Raw data**: [`review_verdicts.json`](./review_verdicts.json), [`output/worker_state.json`](./output/worker_state.json), [`output/dots_mocr_state.json`](./output/dots_mocr_state.json)  
**Change**: `openspec/changes/experiment-34-worker-sample-review`; informs deferred task 2.3 of `page-level-ocr-routing`  
**Decision records**: ADR-070 (reader-output normalisation), TDR-028 (rules), TDR-029 (worker page-1 fault, A9), TDR-030 (LiteParse line join, A6)  
**Protocol**: [protocol.md](protocol.md)

## Bottom line

The operator checked 4 pages by eye against the page images. On each page, all four engines were compared. On the 2 clean control pages, the worker did no damage. On the old-book page with text, the text readers returned nothing, but the worker gave a readable transcription. That transcription had one invented-text defect. Both pass gates pass. Deferred task 2.3 can now go ahead: it will build a routing signal that sends `io06`-class pages to the worker. dots.mocr was added as a probe (A2). It was the operator's "best output" on all 5 pages it ran, with no problems ticked, and it runs faster per page. The next step is to compare it with the worker on the full sample.

## What we tested and why

The question: does the worker's Markdown hold text, reading order, headings and tables on real problem pages, and does it leave clean pages undamaged? This is a single-engine review, not an A/B test. The reference is the operator's eyes on the original page image. Two text readers (`pdf_inspector`, `liteparse`) and the dots.mocr probe appear beside the worker for comparison. The result decides whether task 2.3 (the confident-but-wrong routing signal) goes ahead, and what it aims at.

## Setup at a glance

| Item | Value |
| --- | --- |
| Reviewed set (A1) | `bd03` p1, p2 (clean control, two columns); `io06` p28, p53 (17th-century Latin scan; p53 near-blank) |
| Extra page (A4, not in any gate) | `eq01` p11 (Kingma & Welling, display equations) |
| Worker | PaddleOCR-VL 1.6, paddleocr 3.7.0, CPU, protocol 1.1 page-listed requests |
| Probe | dots.mocr (3.04 B), PyTorch 2.14.0, MPS, bfloat16, pages ≥ 1600 px long side |
| Checklist | review v2 (A3): selectable verdicts per page and engine, no free text |

The full sample (42 pages) is frozen in `sample.json`. The worker also ran `bd01`, `bd02`, `io04` and `tl03` in full. Those outputs are timing evidence only: the operator did not review them.

## Results

### Pass gates

| Criterion | Threshold | Measured | Pass? |
| --- | --- | --- | :---: |
| Review completeness | every reviewed page (A1) has a verdict | 4 / 4 (plus `eq01/11`) | ✅ |
| Control guard | `bd03` worker: no `wrong` accuracy, no `lost` structure | `bd03/1`: `all` / `partial`; `bd03/2`: `all` / `kept` | ✅ |
| Timing gate | steady-state per-page cost measured before the full pass | measured (table below); the full pass was replaced by A1 | ✅ |
| Quality bar (decision input) | share of `io06` / `io04` pages at `most`+ and LLM `yes` | `io06`: 1 / 2 (p28); `io04`: not reviewed | — |

### Verdicts per page and engine

Cell format: accuracy · order · structure · problems · LLM-ready. `empty` means that engine produced no output.

| Page | `pdf_inspector` | `liteparse` | `worker` | `dots_mocr` | Best (operator) |
| --- | --- | --- | --- | --- | --- |
| `bd03/1` | all · correct · partial · noise · yes | all · **scrambled** · partial · furniture, noise · yes | all · correct · partial · noise · yes | all · correct · kept · none · yes | pdf_inspector, worker, dots_mocr |
| `bd03/2` | all · correct · kept · noise · yes | all · correct · **lost** · furniture, noise · yes | all · correct · kept · none · yes | all · correct · kept · none · yes | pdf_inspector, worker, dots_mocr |
| `io06/28` | empty | empty | most · correct · kept · **invented** · yes | most · correct · kept · none · yes | worker, dots_mocr |
| `io06/53` | empty | empty | empty | all · correct · kept · none · yes | dots_mocr |
| `eq01/11` | some · correct · kept · chars · **no** | some · correct · kept · chars · **no** | all · correct · kept · none · yes | all · correct · kept · none · yes | worker, dots_mocr |

| Engine | Pages with text | LLM-ready `yes` | Named best |
| --- | ---: | ---: | ---: |
| `pdf_inspector` | 3 / 5 | 2 | 2 |
| `liteparse` | 3 / 5 | 2 | 0 |
| `worker` | 4 / 5 | 4 | 4 |
| `dots_mocr` | 5 / 5 | 5 | 5 |

### Seconds per page

The two engines ran on different hardware: the worker on CPU, dots.mocr on the Apple GPU (MPS). This is not a like-for-like speed test. Worker figures are from the A9 re-run; the first run's figures are kept under `superseded` in `output/worker_state.json`, and the same `bd03` request took 334.5 s then and 156.2 s now.

| Doc | Worker (CPU) s/page | dots.mocr (MPS) s/page |
| --- | ---: | ---: |
| `bd03` (2 pages) | 78.1 | 44.0 |
| `io06` (2 pages) | 42.6 | 11.8 |
| `eq01` (1 page) | 75.7 | 55.7 |
| `bd01` / `bd02` / `io04` / `tl03` | 164.1 / 152.5 / 142.2 / 40.3 | 50.5 / 43.9 / 85.9 / 21.8 (A8) |

The worker produced no `parse_error` on any document. dots.mocr: 0 errors, 0 token-cap hits, valid layout JSON on all 5 pages, about 8.8 GB MPS memory.

Recorded oddities, kept as the operator entered them. (1) `io06/53` dots.mocr is marked `all` · `none`. Its output is two page numbers (`29`, `282`), one line of bleed-through fragments (`io u- n- L c; …`), and `Digitized by Google`. (2) dots.mocr `table` is `ok` on `io06/28` and `eq01/11`, and neither page has a table.

## Discussion

1. **The worker is safe on clean pages.** Both `bd03` pages keep all text and correct two-column order. The worker's single `partial` structure verdict matches `pdf_inspector` on the same page. The `liteparse` verdicts (`scrambled` on p1, `lost` on p2) were given to output from a faulty adapter, our wrapper around the LiteParse library (`src/omrg/integrations/pdf/liteparse.py`), not to LiteParse itself. The adapter put a line break after every text piece, so a title drawn word by word came out one word per line. This is the likely cause of `lost`. The fault was fixed during this experiment (A6), and the `liteparse` panels need a new verdict. The adapter still does not reorder `bd03`'s sidebar layout; that part of `scrambled` is a column-detection limit, not the join.
2. **The worker reads the old book, with defects.** On `io06/28` both text readers are `empty`: the page is a scan, and its text layer holds nothing they can extract. The worker transcribes it in the correct order. The likeliest source of the `invented` tick is the drop cap: the worker turns "PER" into maths, `P $ ^{E R} $`. It also has misreadings: `matgmonia` for matrimonia, `succeliones`, `tranitus`. The local OCR tier (pdf-inspector's own OCR mode, what the pipeline uses today on scans) reads those three words correctly, but misreads others the worker gets right (`dux perfo- na`, `ab co gradu`, `truciusille`): about 5–6 wrong words each. It also keeps the printed line breaks and hyphens (`pro- genie`). By word search, the worker's advantage on this page is layout (joined lines, a heading) more than character accuracy. The local OCR tier is now a review column (A5); its verdicts are pending.
3. **The worker's empty output on `io06/53` is arguably correct.** The page is near-blank. dots.mocr returned page numbers and bleed-through noise, and the operator preferred that. Whether noise is better than nothing for retrieval is an open question. This review does not answer it.
4. **Text readers cannot handle equations.** On `eq01/11` both readers are `some` · `chars` · not LLM-ready. The mechanism is in protocol A4: Computer Modern fonts with no `ToUnicode` map, and a text layer with no maths structure. Both OCR engines return correct LaTeX.
5. **dots.mocr matched or beat the worker on every page.** It kept the structure the worker lost on `bd03/1` (a verdict given to faulty worker output, A9), and it did not invent text on `io06/28`. It ran 1.4–3.6× faster per page on the reviewed pages (A9 re-run timings), but on the GPU, not the CPU.

### Limits

Pending: the `liteparse` verdicts and the local OCR tier column await the operator's review after A5 and A6, and the worker verdict on `bd03/1` after A9 (the panel showed p1 + p2). Until then those rows describe the pre-fix output.

1. The operator reviewed 4 pages. That is enough for a safety check, not for a rate.
2. `io04` (triple column) and `tl03` (tables) have worker output but no verdict. The "needs llm maybe" question is still open.
3. `io06` has one page with real text in the reviewed set, so "reads old books" rests on one page.
4. The timings compare CPU with GPU and cold with warm runs. They show the scale of the difference, not an exact speed-up.
5. The verdicts come from one operator with no second rater.

## Conclusion

The experiment answered its safety question. The worker does not damage clean pages, and it reads a scanned old-book page that the text readers miss. Task 2.3 goes ahead, aimed at routing `io06`-class pages to an OCR engine. It keeps the confident-but-wrong signal as its focus, because the local tier's character accuracy on `io06/28` was already close to the worker's. The `io04` and `tl03` questions stay open. Nothing ships from this experiment. Follow-ups:

1. A full-sample comparison of dots.mocr against PaddleOCR-VL, with verdicts for `io04` and `tl03`. This is the input for the `modular-ocr-workers-dots-mocr` change.
2. A decision on near-blank pages: should an OCR engine's bleed-through noise be indexed or dropped?

## Artefacts

| File | Description |
| --- | --- |
| `review_verdicts.json` | Operator verdicts, schema `exp34-review-v2`, exported 2026-09-24T03:41:20Z, committed unchanged |
| `output/worker/<doc>/pNNN.md`, `output/worker_state.json` | Worker Markdown and per-document seconds |
| `output/dots_mocr/`, `output/dots_mocr_state.json` | dots.mocr probe output and per-page stats |
| `output/pdf_inspector/`, `output/liteparse/`, `output/today/` | Reader columns (LiteParse regenerated after the A6 fix) and the Experiment 33 local-tier baseline |
| `local_ocr_pages.py`, `output/local_ocr/`, `output/local_ocr_state.json` | Local OCR tier column (A5) |
| `output/review_small.html`, `output/review.html` | Review surfaces (reviewed set; full sample) |
| `analysis.py` | Jupytext analysis: verdict tallies, gate checks, timing plot |
