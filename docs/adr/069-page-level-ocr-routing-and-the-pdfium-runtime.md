# ADR-069: Page-Level OCR Routing with a Local Tier, and the PDFium Runtime

**Date:** 2026-09-18
**Status:** Proposed (implementation complete on `feat/page-level-ocr-routing`; awaiting operator acceptance at PR review)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `openspec/changes/page-level-ocr-routing/` (tasks 3–6)
**Related:** [ADR-050](050-configure-pdf-inspector-as-default-reader.md) (pdf-inspector default), [ADR-065](065-ocr-fallback-gate-promoted-to-packaged-default.md) (document-unit gate), [ADR-066](066-tiered-reader-fallback-chain.md) (reader chain, kept), TDR-026 (false-alarm risk that motivated the unit)

## Context

The shipped OCR unit is the whole PDF. When the calibrated gate fires,
the entire file goes to the PaddleOCR-VL worker at 34–106 s per page. A
40-page report with 3 scanned letter pages pays for 40 pages; a journal
article with unread chart pages either wastes minutes or keeps its chart
text unread. The same all-or-nothing shape drives TDR-026's false-alarm
risk: every extra flagged page (a scan, an illustration) can push an
otherwise healthy book into full-document OCR.

Experiment 33 showed pdf-inspector 1.17.0 already carries the pieces:
`process_pdf_with_ocr` OCRed routed pages selectively with PP-OCRv6
Small on ONNX Runtime (CPU, no PyTorch) and reported per-page
provenance. Its task 6.7 measured the local engine on 464 natural
pages the frozen labels mark `needs_ocr`:

- bimodal by writing system, not page quality: modern Latin-script
  print 0.977 median token recall (84% of pages ≥ 0.8), Devanagari and
  Arabic 0.000 across all 129 pages, handwriting 0.310, the
  early-modern Latin book `io06` 0.609 at median confidence 0.922;
- confidence separates readable from unreadable well (AUC 0.949);
- a 0.8 confidence cut escalates 46.9% of flagged pages and leaves
  11.3% of kept pages below 0.5 recall;
- `hosted_recommended` is precise and nearly deaf (6 of 206 bad pages);
- 0.75 s median per page against the worker's 34–106 s.

The evidence-gate verdict was REWORK with conditions; the operator's
2026-09-18 amendment dropped the originally required script/typography
pre-check: the failures announce themselves after the attempt (all 129
unreadable pages returned empty output), and no measured signal
predicts them beforehand.

The local tier also has runtime needs the document unit never had:
pdf-inspector's OCR engine loads a PDFium shared library
(`PDFIUM_LIB_PATH`) and ONNX Runtime (`ORT_DYLIB_PATH`) at process
level, and resolves one pinned model
(`pp-ocrv6-small@oar-ocr-v0.7.0`, about 31 MB) on first use —
downloading unless offline mode forbids it.

## Decision

1. **Add an opt-in routing unit.** `OCR_ROUTING_UNIT`, values
   `document` (default, unchanged behaviour) and `page`. An invalid
   value raises at startup: the unit feeds the index identity, so a
   warn-and-fallback would index a corpus under a unit nobody chose.
2. **The page unit routes per page.** A full scan of every page is the
   only evidence (no sample, no page-fraction threshold). Flagged
   pages are OCRed locally; unflagged pages keep native Markdown.
   Escalation is decided AFTER the local attempt — empty or
   whitespace-only output, confidence below `OCR_LOCAL_MIN_CONFIDENCE`
   (0.8, from the calibration above; unreported confidence escalates
   too), or `hosted_recommended` — and the escalated pages go to the
   worker in ONE request.
3. **Worker protocol 1.1** carries the page list. A request with
   `pages` speaks 1.1; any other request speaks 1.0, the minimum
   version that expresses it, so a worker still on 1.0 keeps serving
   plain requests during a rolling upgrade. The success envelope gains
   `pages_markdown`, parallel to the request, because the merge must
   place each page's worker text at its own position. The capability
   fingerprint accepts a worker reporting either version and records
   which, so upgrading OMRG alone strands no worker and moves no index
   identity.
4. **One document per file, merged in page order.** Pages join with a
   blank line; each page contributes the text of the highest tier that
   produced any. Four scalar counts (`ocr_pages_native`,
   `ocr_pages_local`, `ocr_pages_worker`, `ocr_pages_unresolved`) sum
   to `page_count`. Degradation follows one rule: an escalated page
   counts worker only when the worker returned non-empty text for it;
   anything else keeps the best available text (local, then native),
   counts unresolved, and inserts no marker into retrieval text. A
   missing local runtime keeps native text for flagged pages with one
   warning per read; a post-dispatch worker failure still fails the
   file. When page routing produces no text anywhere and the wrapped
   reader's ADR-066 chain rescued the document, the rescued text is
   emitted with all-native counts.
5. **The identity carries what changes the emitted text.** Under the
   `page` unit the payload gains the unit, the escalation threshold,
   and the resolved model identity (`name@revision`, from a one-page
   blank-PDF probe cached per process). The model directory and
   offline mode are excluded: a filesystem location and a download
   permission do not change what a page reads as. A document-unit
   install hashes exactly what it hashed; `_INDEX_IDENTITY_SCHEMA`
   stays 5.
6. **The PDFium and ONNX Runtime libraries come from existing base
   dependencies.** LiteParse 2.11.1 (Apache-2.0) ships
   `libpdfium.dylib` inside its package; ONNX Runtime 1.28.0 (MIT)
   ships its dylib in `capi`. PDFium itself is the Chromium project's
   BSD-3-Clause library. OMRG pins neither separately — they ride the
   base-dependency locks in `uv.lock`, and pdf-inspector loads them by
   environment variable. `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` may
   live in `.env`: the composition root runs `load_dotenv()` before
   any read, which exports them into the process environment the Rust
   library sees. Compatibility beyond the load itself is not validated;
   a library that fails to load fails closed — flagged pages keep
   native text, count unresolved, and one warning names the missing
   runtime. No PyTorch enters any tier (ADR-005's rule stands).

## Consequences

- Worker cost scales with pages that need OCR, not total pages, and
  chart pages can be OCRed without moving the whole document.
- The tier halves rather than removes worker cost: on the Experiment 33
  corpus 46.9% of flagged pages still escalate.
- Residual risk is accepted and named: 11.3% of kept pages fall below
  0.8 recall, and the `io06` blind spot (confident, half-wrong
  early-modern typography) survives the confidence cut. The deferred
  retrieval experiment (task 6.1) gates any future default change; the
  default remains `document`.
- Opting into `page` reindexes that install's sources once; the
  document unit is untouched. A local runtime that appears later adds
  the model identity and reindexes exactly then — the moment the
  emitted text could change.
- The worker's Paddle-side page forwarding is validated only by the
  operator-gated smoke test (`ocr-worker/smoke_test.py --provision`),
  which task 4.3 extended with a page-listed request.
