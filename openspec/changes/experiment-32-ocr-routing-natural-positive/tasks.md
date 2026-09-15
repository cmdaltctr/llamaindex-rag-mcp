# Tasks: Experiment 32 OCR Routing Natural-Positive Study

## 1. Freeze the protocol

- [ ] 1.1 Define document-level and page-level OCR-need labels.
- [ ] 1.2 Freeze the current packaged policy and its `0.5` / `0.10` thresholds as the measured candidate.
- [ ] 1.3 Define primary routing-recall and false-negative measurements before held-out scoring.

## 2. Build the corpus

- [ ] 2.1 Select born-digital negative PDFs.
- [ ] 2.2 Select mixed PDFs with independently assessed OCR-needed and healthy pages.
- [ ] 2.3 Select scanned/image-based positive PDFs.
- [ ] 2.4 Separate prior development documents from independent held-out documents.
- [ ] 2.5 Hash and freeze corpus membership and labels.

## 3. Implement the routing harness

- [ ] 3.1 Add `experiments/32-ocr-routing-natural-positive-<date>/` using repository templates.
- [ ] 3.2 Record classifier outputs, confidence, page counts, OCR-page counts, and routing decisions.
- [ ] 3.3 Emit secret-free runtime manifests and policy identity.
- [ ] 3.4 Keep Stage A routing-only execution separate from Stage B real OCR execution.

## 4. Run Stage A: routing only

- [ ] 4.1 Run the current packaged policy on the frozen held-out corpus.
- [ ] 4.2 Report routing recall, precision, false negatives, false positives, and unnecessary projected OCR work.
- [ ] 4.3 Report outcomes by born-digital, mixed, and scanned/image-based class.

## 5. Authorise and run Stage B if needed

- [ ] 5.1 Record separate operator approval naming the OCR subset, timeout, and runtime budget.
- [ ] 5.2 Provision and fingerprint the OCR worker.
- [ ] 5.3 Run real OCR only on the authorised subset.
- [ ] 5.4 Measure evidence recoverability, Recall@K, MRR@10, elapsed OCR time, and failures.

## 6. Report and close

- [ ] 6.1 State whether the current gate has direct natural-positive recall evidence.
- [ ] 6.2 Preserve ambiguous, timeout, and failure cases.
- [ ] 6.3 If threshold recalibration is warranted, create a separate OpenSpec proposal; do not change defaults here.
