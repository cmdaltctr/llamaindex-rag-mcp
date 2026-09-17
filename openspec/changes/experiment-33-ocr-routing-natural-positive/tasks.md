# Tasks: Experiment 33 OCR Routing Natural-Positive Study

## 1. Freeze the protocol

- [x] 1.1 Define document-level routing labels and page-level labels (`usable`, `needs_ocr`, `unrecoverable`, `ambiguous`); freeze the text-layer usability rule judged against the rendered page image; score routing per document, use page labels for unnecessary OCR pages and at-risk evidence.
- [x] 1.2 Freeze the shipped policy as the measured candidate: `OCR_FALLBACK_ENABLED=true`, `0.5` / `0.10` thresholds, unconditional `scanned`/`image_based`, and the reader fallback chain.
- [x] 1.3 Define primary routing-recall and false-negative measurements before held-out scoring.

## 2. Build the natural corpus

- [x] 2.1 Select born-digital negative PDFs.
- [x] 2.2 Select mixed PDFs with independently assessed OCR-needed and healthy pages.
- [x] 2.3 Select image-only scanned/image-based positive PDFs.
- [x] 2.4 Select scanned PDFs with an existing OCR text layer, covering faithful and junk text layers.
- [x] 2.5 Select reader-failure PDFs (usable text layer that `pdf-inspector` cannot read) and label them apart from scanned positives.
- [ ] 2.6 Select unrecoverable examples (pure noise, photographed page at an angle).
- [x] 2.7 Separate prior development documents (Experiment 29 dev set, Experiment 30 and 31 corpora) from independent held-out documents.
- [x] 2.8 Log title, source URL, licence, page count, and SHA-256 per document in `corpus/SOURCING.md`.
- [ ] 2.9 Hash and freeze corpus membership and labels.

## 3. Implement the routing harness

- [x] 3.1 Add `experiments/33-ocr-routing-natural-positive-<date>/` using repository templates.
- [x] 3.2 Run `OcrRoutedPdfInspector` with `ocr_client=None` and record classifier outputs, confidence, page counts, post-chain `pages_needing_ocr`, `pages_needing_ocr_before_fallback`, `extraction_fallback_backend`, and the stamped `ocr_required`.
- [x] 3.3 Emit secret-free runtime manifests, policy identity, and the content-type detection path (Magika version or suffix fallback).
- [x] 3.4 Keep Stage A routing-only execution separate from Stage B real OCR execution.

## 4. Run Stage A: routing only

- [ ] 4.1 Run the current packaged policy on the frozen natural held-out corpus.
- [ ] 4.2 Report routing recall, precision, false negatives, false positives, and unnecessary projected OCR work.
- [ ] 4.3 Report outcomes by born-digital, mixed, image-only scanned, scanned-with-text-layer, and reader-failure class; report reader-quality loss apart from OCR false negatives.
- [ ] 4.4 Report routing decisions for unrecoverable documents separately, outside recall and precision denominators.

## 5. Build the synthetic degraded set

- [x] 5.1 Select clean born-digital source PDFs and extract their reference text.
- [x] 5.2 Render, degrade (skew 0.5 to 2 degrees, Gaussian noise, JPEG quality 40 to 60, slight blur), and re-wrap as PDF; record parameters, seed, and source SHA-256.
- [ ] 5.3 Optional: operator prints and re-scans a small subset.
- [ ] 5.4 Optional: run a page-fraction boundary probe through the Stage A harness and report it as exploratory.

## 6. Authorise and run Stage B if needed

- [ ] 6.1 Record separate operator approval naming the OCR subset, timeout, and runtime budget.
- [ ] 6.2 Provision and fingerprint the OCR worker.
- [ ] 6.3 Run real OCR only on the authorised subset.
- [ ] 6.4 Measure evidence recoverability, Recall@K, MRR@10, elapsed OCR time, and failures.
- [ ] 6.5 Measure CER on synthetic documents against the source PDF text.
- [ ] 6.6 Record unrecoverable-page outcomes: failure reported or text emitted.

## 7. Report and close

- [ ] 7.1 State whether the current gate has direct natural-positive recall evidence; synthetic documents do not count.
- [ ] 7.2 Preserve ambiguous, unrecoverable, timeout, and failure cases.
- [ ] 7.3 If threshold recalibration is warranted, create a separate OpenSpec proposal; do not change defaults here.
