# ADR-072: Modular OCR Engines, dots.mocr as Primary Engine, and Maths-Page Routing

**Date:** 2026-10-06
**Status:** Accepted (2026-10-06, PR #104 merged to `v3`)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `openspec/changes/archive/2026-10-06-modular-ocr-workers-dots-mocr/`
**Related:** [ADR-062](062-isolate-paddleocr-vl-in-a-versioned-ocr-worker.md) (isolated OCR worker), [ADR-069](069-page-level-ocr-routing-and-the-pdfium-runtime.md) (page-level routing), [ADR-071](071-ocr-routing-natural-positive-findings.md) (natural-positive findings)
**Evidence:** `experiments/34-worker-sample-review-2026-09-19/report.md`, `experiments/37-dots-mocr-routing-acceptance-2026-09-30/report.md`

## Context

One OCR engine, PaddleOCR-VL, was built into one worker project. Three
problems followed.

1. **Maths pages go unseen.** The text layer of a maths page looks healthy.
   On `eq01` p11 (Kingma and Welling, appendix) pdf-inspector reports
   `needs_ocr=False` and loses Greek letters. No existing gate sends the page
   to OCR.
2. **Scripts and handwriting.** The local OCR tier scored median token
   recall 0.000 on Devanagari, Arabic and Bengali pages (Experiment 33, as
   corrected in the ADR-071 erratum).
3. **PaddleOCR-VL on CPU is slow and fragile.** It needs 34 to 106 s per page
   and times out on some pages.

Experiment 34 tested dots.mocr (3 B parameters, PyTorch) on the reviewed
pages (amendments A2 and A4). The operator judged it the best output on all
five pages and 4 to 7 times faster than the PaddleOCR-VL worker.
The evidence for scanned pages is thin: one real old-book page (`io06`).

## Decision

1. **One folder per engine.** Engines live in `ocr-workers/engines/<engine>/`
   with their own `pyproject.toml` and `uv.lock`. A shared
   `ocr-workers/core/` holds the protocol. `ocr-workers/provision.py <engine>`
   installs one engine. A new engine is one folder and one registered entry
   point, with no `if/elif` over engine names in the host.
2. **Two routes, primary and fallback.** `OCR_ENGINE_PRIMARY` defaults to
   `dots-mocr`. `OCR_ENGINE_FALLBACK` defaults to `paddleocr-vl`. The host
   picks one engine per dispatch, once, before the request. It never retries
   on the other route after dispatch.
3. **dots.mocr is the primary engine.** It runs from a pinned model revision
   (`e539fbb5…`), offline at parse time, in its own environment. The operator
   approved PyTorch for this isolated environment on 2026-09-24. PyTorch stays
   out of the OMRG install and off the retrieval path.
4. **Maths pages route to OCR.** A deterministic detector reads each page's
   font names with `pypdf` and flags pages that use a maths font
   (`MATHS_DETECTOR_VERSION = 1`). A flagged page goes to OCR. At document
   unit, a document goes to OCR when the flagged share reaches
   `OCR_MATHS_PAGE_FRACTION` (default 0.10). `OCR_MATHS_ROUTING_ENABLED=false`
   turns it off.
5. **Index identity changes once.** The identity gains the fallback
   fingerprint and a `maths_routing` block. The schema number stays at 6,
   shared with `normalise-reader-markdown`. Sources processed before this
   change reprocess once.
6. **Licence gate.** Provisioning dots.mocr stops unless the operator passes
   `--accept-model-licence`. An operator who does not accept the terms leaves
   dots.mocr unprovisioned, and PaddleOCR-VL (Apache-2.0) serves every route.

### Licence terms that affect OMRG

The model agreement is MIT-based, with extra clauses. Notes are in
`ocr-workers/engines/dots-mocr/LICENCE-NOTES.md`.

- **3.3(c):** no unauthorised digitisation of publications or bulk scraping.
  Use on copyright-protected material needs permission. With dots.mocr as the
  primary engine, this applies to scanned books and papers.
- **5.2:** limits on processing sensitive personal data without a lawful basis.
- **8:** Chinese governing law, with arbitration in Hangzhou.
- **9:** the licensor can issue revised terms. The licensee must migrate
  within the stated period or the rights end.

The operator accepted the terms on 2026-10-04.

### Acceptance evidence (Experiment 37, PASS)

| Gate | Rule | Result |
| --- | --- | --- |
| G1 | 0 flagged pages among control pages labelled `no_maths` (amendment A1) | 0 of 64 |
| G2 | dots.mocr KaTeX error rate at or below 5 % | 0 of 1,893 formulas |
| G3 | operator verdict on every page of the noise list | 41 verdicts on 21 pages, no invented text from either engine |

The detector reached precision 0.890 and recall 1.000 on 106 operator-labelled
maths pages. Median script recall (reported, not gated) was 0.889 for
dots.mocr and 0.610 for PaddleOCR-VL on CPU.

Amendment A1 changed G1. Two pages of `bd03` (p4, p6) use maths fonts and
draw real maths, a chemical equation. The operator labelled every control
page, and G1 counts only pages labelled `no_maths`. The operator approved A1
on 2026-10-04.

## Consequences

### Positive

- A maths page reaches an engine that writes LaTeX. No existing gate caught
  `eq01` p11.
- dots.mocr answered 257 of 257 pages with one worker process. PaddleOCR-VL on
  CPU timed out on 34 pages and used 35 worker processes.
- A second engine is a folder, not a code change in the host.
- If the operator does not accept the licence, nothing breaks: the fallback
  engine serves every route.

### Negative

- **Memory.** dots.mocr peaked at 22.2 GiB over 257 pages. The smoke test had
  shown 9.5 GiB (finding F5). Machines with less memory must set
  `OCR_ENGINE_PRIMARY=paddleocr-vl`. The figure was measured while
  PaddleOCR-VL ran in parallel, so it may include some shared load.
- **Dropped tables (F1).** dots.mocr dropped a rotated table (`tl03` p8: 45
  characters, against 1,206 from PaddleOCR-VL).
- **Detector gaps (F2, F3).** The detector misses renamed Minion Math fonts
  (`bd02` p3) and Word plus MathType maths (arXiv 1106.0083v2). Those pages
  stay on their normal route.
- **Over-flagging.** Ten pages labelled `no_maths` in the positive set were
  flagged because they draw a few glyphs in a maths font. This costs time, not
  text.
- **Slow fallback on CPU (F4).** PaddleOCR-VL timed out on 34 of 257 pages at
  the 300 s default.
- **One-off reprocessing.** Sources processed before this change reprocess
  once.
- **Licence burden.** Clauses 3.3(c), 5.2, 8 and 9 apply to dots.mocr.

### Neutral

- Scanned-page evidence for dots.mocr still rests mainly on one real
  old-book page and the Experiment 37 scanned set.
- The detector list can grow. Each change to it is a version bump.

## Follow-up work

None of these blocks acceptance, and none changes detector code in this change.

1. **Detector version 2** for F2 and F3: a new OpenSpec change.
2. **Rotated tables and charts (F1):** a follow-up experiment.
3. **PaddleOCR-VL timeouts (F4):** a follow-up experiment. The operator's
   MLX test suggests a large speed gain. It needs its own experiment over the
   same 257 pages and an OpenSpec change for an MLX engine route.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| **One environment with every engine** | Paddle and PyTorch runtimes are multi-gigabyte and pin conflicting packages. One broken engine would break the others. |
| **Copy the protocol into each engine** | The copies would drift, and the host twin test would not catch it. |
| **Vendor the dots.mocr model code** | The licence requires notices to be kept, and upstream fixes would need tracking by hand. A pinned revision with hash checks gives the same safety. |
| **Keep PaddleOCR-VL as the only engine** | It leaves maths pages unseen and times out on CPU. Its memory use is lower, so it stays as the fallback. |
| **Loosen the detector to catch every maths font** | It would flag more pages without maths. The list grows by version bump instead. |
| **Replace `bd03` to keep the old G1 rule** | It would drop a realistic born-digital paper with sporadic maths. |
| **Do nothing** | Maths pages and non-Latin scripts reach the index as junk or nothing. |

## References

- `openspec/changes/archive/2026-10-06-modular-ocr-workers-dots-mocr/design.md` (D1 to D9)
- `experiments/34-worker-sample-review-2026-09-19/protocol.md` (A2, A4) and `report.md`
- `experiments/37-dots-mocr-routing-acceptance-2026-09-30/report.md`, `protocol.md` (A1), `output/summary.json`
- `ocr-workers/engines/dots-mocr/LICENCE-NOTES.md`
- [ADR-062](062-isolate-paddleocr-vl-in-a-versioned-ocr-worker.md), [ADR-069](069-page-level-ocr-routing-and-the-pdfium-runtime.md), [ADR-071](071-ocr-routing-natural-positive-findings.md)
