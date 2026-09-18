# Design: page-level OCR routing

## Context

The `pdf-reader` spec requires whole-PDF dispatch and forbids merging page fragments from two engines. That rule kept the first OCR implementation simple. Experiments 29 and 33 show its cost: OCR price scales with total pages, not with pages that need OCR, and every extra flagged page (a scan or an illustration) moves the whole document.

pdf-inspector 1.17.0 facts (Experiment 33, synthetic probe files only):

- `extract_pages_markdown(path)` returns per-page Markdown and `needs_ocr` for every page (no 8-page sample).
- `process_pdf_with_ocr(path, mode, page_numbers, dpi, minimum_confidence, hosted_recommendation_confidence, model_directory, offline)` OCRs routed pages with PP-OCRv6 Small (`oar-ocr-v0.7.0`) on ONNX Runtime and returns per-page Markdown with provenance (`source`, `ocr_confidence`, `ocr_model`, warnings) plus `pages_recommending_hosted`.
- Probe pb03: routed exactly pages 2, 10 and 14; local OCR produced no text on those heavily degraded pages and recommended hosted OCR for all three.
- Synthetic scan sy01: about 2.3 s per page; token recall against the clean source 0.66 to 0.96 on 6 pages and 0.04 to 0.15 on 4 pages, which carried confidence 0.51 to 0.61.
- It needs a PDFium shared library (`PDFIUM_LIB_PATH`). The LiteParse-bundled library worked in the probe; compatibility is not validated.

## Goals

- OCR cost proportional to pages that need OCR.
- Chart and drawing pages can be OCRed without moving the whole document.
- Keep PaddleOCR-VL quality for pages the local engine cannot read.
- Keep today's behaviour as the default until evidence supports a change.

## Non-Goals

- No default change in this proposal.
- No replacement of PaddleOCR-VL and no cloud OCR.
- No change to the `document` unit's thresholds.

## Decisions

1. **Opt-in unit.** `OCR_ROUTING_UNIT`, values `document` (default) and `page`, validated at startup.

   The name is flat, one underscore, like every OCR and PDF setting beside it.
   `pydantic-settings` resolves its `__` delimiter only into nested blocks, and
   the OCR settings are flat top-level fields, so a nested spelling would match
   nothing and be discarded in silence. The nested spellings this change's own
   planning documents used first are listed in `config/legacy.py` under
   never-shipped aliases, so anyone who writes one gets an error naming the flat
   replacement.

   An invalid value raises rather than warning and falling back, unlike
   `PDF_READER` and `RAG_PROFILE`. Those two resolve `auto` as a capability
   policy, where falling back to a working backend is the point. A typo in a
   two-value enum is a configuration error, and the unit feeds the index
   identity, so a fallback would index a corpus under a unit nobody chose.
2. **Page evidence.** `page` mode takes per-page `needs_ocr` from a full scan. No sampled evidence and no page-fraction threshold: every flagged page is handled.
3. **Tier 1: local OCR.** pdf-inspector selective OCR on flagged pages only, CPU, in-process, GIL released. Model directory and offline mode come from settings; no network in offline mode. Every flagged page is tried locally first: at 0.75 s median per page against 34 to 106 s hosted, trying and escalating costs less than any attempt to predict failure would save.
4. **Tier 2: escalation, decided after the attempt.** A page escalates when any of these holds:

   - local OCR returns empty or whitespace-only text;
   - `ocr_confidence` is below `OCR_LOCAL_MIN_CONFIDENCE` (0.8);
   - `hosted_recommended` is set.

   Experiment 33 task 6.7 supports each term. Empty output catches the classes
   the packaged model cannot read at all: all 129 Devanagari and Arabic pages
   scored recall 0.000. The 0.8 confidence cut escalates 46.9% of `needs_ocr`
   pages and leaves 11.3% of kept pages below 0.5 recall. `hosted_recommended`
   is weak on natural documents — it fired on 6 of the 206 pages below 0.5
   recall — and is kept because it costs nothing and fired on no page that
   scored recall ≥ 0.8 (n=124); all six pages it flagged scored 0.000.

   **No script or typography signal is used, because none was measured.** A
   pre-check would have to judge a page before OCR runs, when the page is still
   an image; task 6.7 measured which documents fail, not a signal that predicts
   it beforehand. Escalating after the attempt reaches the same pages on
   evidence that exists.

   Escalated pages go to the PaddleOCR-VL worker in one request with a page
   list (protocol 1.1, optional `pages`).

   **The 1.1 wire rules (task 4.3).** A request carrying `pages` speaks 1.1;
   a request without it speaks 1.0, the minimum version that expresses the
   payload, so a worker still on 1.0 keeps serving plain requests during a
   rolling upgrade. Both endpoints accept 1.0 and 1.1 and answer in the
   version the request spoke. The success envelope gains an optional
   `pages_markdown` list, parallel to the requested pages: one document per
   page is the merge's shape, so the client must be able to place each
   page's worker text at its own position, and a single merged blob could
   not do that for non-contiguous escalated pages. `pages` and
   `pages_markdown` are absent from 1.0 envelopes; the output schema stays
   at `omrg.ocr.parse_output` version 1, because the `markdown` field's
   meaning is unchanged and the per-page list is additive. The worker
   builds it with a second, non-concatenating assembly pass over the same
   page results — re-prediction, the expensive part, is never repeated.
   The Paddle-side page forwarding (`predict(page_num=...)`) is validated
   only by the operator-gated `--provision` smoke test, which task 4.3
   extends with a page-listed request; the pytest suite stubs the parse
   seam and cannot reach it.
5. **Merge.** One document per file, as today: the unit changes which engine
   reads each page, not how many documents a PDF becomes. Pages join in page
   order with a blank line between them, so a heading at the top of page 2 does
   not fuse into page 1's last paragraph and the chunker's Markdown routing
   still sees the headings it expects. Each page contributes the text of the
   highest tier that produced any, and contributes once.

   Metadata carries four scalar counts — `ocr_pages_native`, `ocr_pages_local`,
   `ocr_pages_worker`, `ocr_pages_unresolved` — which sum to `page_count`. They
   join `EXCLUDED_EMBED_METADATA_KEYS`, so they never reach embedding text.
   Vector-store metadata values must be scalars in both backends and nothing
   sanitises them on the way in, which is why `pages_needing_ocr` is already a
   count rather than the page list.

   **Correction to the original decision:** it said readers with page
   provenance would also emit a per-page `source`. This path emits one document
   per file, so there is no per-page metadata row to carry it, and a list would
   break the scalar rule. On this path the four counts are the provenance. A
   per-page `source` becomes possible only if a later change splits this reader
   into one document per page.

   An unresolved page contributes whatever native text it had, which for a
   scanned page is usually nothing. No marker is inserted: a string like
   `[page 4: OCR unavailable]` would enter retrieval text and be retrieved. The
   count and a warning carry that signal instead.

5a. **The four existing diagnostics under the page unit.** They stay scalars,
   keep their document-unit meaning, and none of them may tell an existing
   consumer something false.

   | Key | Document unit | Page unit |
   | --- | --- | --- |
   | `ocr_required` | the gate selected OCR for this PDF | at least one page was flagged |
   | `ocr_used` | the worker produced the text | OCR produced the text of at least one page, local or worker |
   | `ocr_backend` | `pdf_inspector` or `paddleocr_vl` | the one backend that produced all the text, or `mixed` |
   | `pages_needing_ocr` | count of flagged pages | unchanged — the same count, from a complete scan rather than an 8-page sample |

   `ocr_backend` is the only one that needs a new value. Three tiers may each
   produce part of one document, and one string cannot name three. Emitting the
   **highest tier used** would be false: a 200-page document where the worker
   read one page would report `paddleocr_vl`, and a consumer filtering on that
   to find worker-parsed documents would collect documents the worker barely
   touched. `mixed` says exactly what is true — more than one backend produced
   this text — and sends the reader to the counts, which answer precisely.

   The values are therefore `pdf_inspector` (every page native),
   `pdf_inspector_ocr` (pdf-inspector's own selective OCR produced all the OCR
   text and no page came from the worker), `paddleocr_vl` (every page from the
   worker) and `mixed` (more than one of those produced text). A document-unit
   run can still only emit the first and third, exactly as today.
6. **Degradation.** Worker unavailable: keep tier 1 text and count unresolved pages. Local runtime or PDFium unavailable: keep native text for flagged pages, count them unresolved, warn once per operation. Never fail the file for a missing optional tier. The unified rule these reduce to: an escalated page counts worker only when the worker returned non-empty text for it; anything else — worker missing before dispatch, a response that cannot be attributed per page, or an empty per-page entry — keeps the best available text (local, then native) and counts unresolved. A worker failure AFTER a complete request was flushed stays a file failure, the same post-dispatch boundary the document unit applies. When page routing produces no text on any page yet the wrapped reader's ADR-066 fallback chain recovered the document, the rescued text is emitted with all-native counts, the whole-document claim the document unit makes for a rescued file.
7. **Identity.** The routing unit, the local tier's escalation threshold, the
   resolved local OCR model identity and the worker fingerprint join the source
   index identity, so switching units re-ingests affected sources.

   The rule for what belongs there: the identity carries **what changes the
   emitted text**, and not where files live or how they are fetched. The
   routing unit changes which engine reads which page. The escalation threshold
   changes which pages the worker rereads. A model's identity changes what it
   reads them as. A model *directory* is a filesystem location, so including it
   would reindex a corpus for moving a cache; offline mode decides only whether
   a download may happen, and its one route to different text — whether the
   model resolves at all — is what the resolved model identity records. Neither
   is in the payload.

   They are added **conditionally**, only when the unit is not `document`, so
   an install on the default hashes exactly what it hashes today and nothing
   reindexes. `_INDEX_IDENTITY_SCHEMA` stays at 5 for the same reason: bumping
   it would reprocess every corpus, including those that never opt in. The cost
   is a payload whose shape varies by configuration, which is harder to read
   than a fixed one; the absence of `routing_unit` unambiguously means
   `document`, because no other configuration emits that key.

   Task 3.2 adds the unit and the threshold. The **resolved model identity
   arrives in task 4.2**, where the model is actually resolved: at
   identity-build time nothing has loaded it, and pdf-inspector reports
   `ocr_model.name@revision` only after OCR runs. That addition moves the
   page-unit identity a second time, which is correct and affects only installs
   that have opted in.
8. **Heading consistency.** Merged pages keep per-page Markdown; the chunker's Markdown routing is unchanged. A retrieval experiment checks chunk quality before any default change.

## Risks

- PDFium binary compatibility and packaging (ADR required).
- Fingerprint rolling compatibility: the probe accepts a worker speaking
  1.0 or 1.1 and records which, so an OMRG-side upgrade alone strands no
  provisioned worker and moves no index identity. A worker upgraded from
  1.0 to 1.1 changes its own reported version and re-fingerprints once —
  reingesting on a real worker change is the fingerprint working as
  designed, and no document-unit install reindexes from this change alone.
- The `io06` blind spot is accepted and named: early-modern Latin type reads at median confidence 0.922 and median recall 0.609, so the 0.8 cut keeps it. No measured signal separates confident-but-wrong typography; task 2.3 is where that evidence would come from.
- Residual: 11.3% of pages kept at the 0.8 cut fall below recall 0.8. Task 6.1 judges whether that is acceptable for retrieval.
- Escalation is 46.9% of `needs_ocr` pages on the Experiment 33 corpus, so the tier halves worker cost rather than removing it.
- Mixed-engine Markdown can differ in heading style across pages.
- Worker protocol change touches the twin protocol copy and its byte-for-byte test.

## Evidence gate 1 result (Experiment 33 task 6.7, 2026-09-17)

pdf-inspector 1.17.0 `process_pdf_with_ocr` in `force` mode (PP-OCRv6 Small,
ONNX Runtime, CPU) on 464 natural pages the frozen Experiment 33 labels mark
`needs_ocr`, across 28 documents. 731 s wall clock, no error, no document over
the 900 s soft limit. Token recall against a vision-model reference
transcription. Source: `experiments/33-ocr-routing-natural-positive-2026-09-17/output/local_ocr/summary.json`.

| Measurement | Value |
| --- | ---: |
| Pages measured | 464 (399 body `needs_ocr`, 65 figure-only) |
| Body recall ≥ 0.8 | 0.311 |
| Body recall < 0.5 | 0.516 |
| Pages with no text | 0.003 |
| `hosted_recommended` | 0.015 |
| Seconds per page | 1.58 mean, 0.75 median |

The aggregate is bimodal. What decides the outcome is the writing system and
the typography, not page quality:

| Class | Pages | Median recall | ≥ 0.8 |
| --- | ---: | ---: | ---: |
| Modern Latin-script print | 144 | 0.977 | 0.840 |
| Early-modern Latin book (`io06`) | 66 | 0.609 | 0.015 |
| Handwriting (`rf06`, `rf07`) | 60 | 0.310 | 0.033 |
| Devanagari and Arabic (`io01`, `io02`, `io03`, `io07`) | 129 | 0.000 | 0.000 |

Confidence calibration for decision 4 and task 2.2:

| Cut | Escalation share | Kept, recall ≥ 0.8 | Kept, recall < 0.5 |
| ---: | ---: | ---: | ---: |
| 0.5 | 0.015 | 0.316 | 0.509 |
| 0.6 | 0.160 | 0.370 | 0.424 |
| 0.7 | 0.381 | 0.502 | 0.219 |
| 0.8 | 0.469 | 0.571 | 0.113 |
| 0.9 | 0.597 | 0.652 | 0.025 |

Confidence separates readable from unreadable pages well (AUC 0.949 over the
399 body pages). A 0.8 cut escalates `io01` 1.00, `io03` 1.00, `io07` 1.00,
`io02` 0.94, `tl01` 0.92, `rf07` 0.65 and `rf06` 0.63, and leaves every
modern-print document at 0.00. It has one blind spot: `io06` escalates at 0.08
while reading at median recall 0.609, because the model is confident and half
wrong on early-modern typography.

`pages_recommending_hosted` fired on 6 pages, all genuinely bad, out of 206
pages below 0.5 recall. It is precise and nearly deaf; the confidence cut has
to carry decision 4.

## Evidence gate 1 verdict (task 1.2, operator decision 2026-09-17)

**REWORK.** Evidence gate 1 half-passes. Local OCR is viable for modern
Latin-script print (84% of pages at recall ≥ 0.8, 0.75 s median) and unusable
for non-Latin scripts (129 pages, recall 0.000) and handwriting (0.310).
Confidence separates the two (AUC 0.949).

Conditions before implementation:

1. Add a pre-check before the local tier: pages whose script or typography is
   outside the supported set skip local OCR and escalate directly. The
   supported set is named from the task 6.7 per-class table: modern
   Latin-script print. Devanagari, Arabic and handwriting are outside it.
2. `OCR_LOCAL_MIN_CONFIDENCE = 0.8` (escalation 46.9%, wrongly kept 11.3%).
3. The `io06` blind spot is an accepted, named risk: early-modern Latin type
   reads at confidence 0.922 with recall 0.609, so a confidence cut keeps it.
   Do not invent a typography heuristic without measurement; it is a
   calibration task with its own evidence (task 2.3).
4. Keep `hosted_recommended` as an escalation trigger, noting it is weak here
   (fired on 6 of 206 pages below 0.5 recall).
5. Residual: 11.3% of kept pages fall below recall 0.8. The retrieval
   experiment in task 6.1 decides whether that is acceptable.

Tasks 3 to 6 proceed under these conditions.

**Amendment, 2026-09-18 (operator).** Condition 1 above called for a script and
typography pre-check. It is dropped. The failures it aimed at announce
themselves after the attempt — empty output covers the 129 unreadable pages —
and a pre-check would need a signal nobody has measured. Decision 4's
post-check rule replaces it. Conditions 2 to 5 stand unchanged.

## Evidence gates

1. Experiment 33 local-OCR stage: token recall of local OCR against the reference transcription on natural pages labelled `needs_ocr`, confidence calibration, escalation rate, seconds per page.
2. New retrieval experiment: `page` vs `document` units on a corpus with mixed documents (Recall@K, MRR@10, ingestion time) before changing the default.
