# Experiment 24 Results: OCR Routing Evaluation (task 5.1)

**ID**: `24-ocr-routing-eval-2026-09-08`  
**Date run**: 2026-09-08  
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  
**Status**: FAIL — quality structure-marker gate failed; root cause is contentless evaluation fixtures, evidenced below  
**Raw data**: [`output/ablation.json`](./output/ablation.json)

---

## TL;DR / Decision

- The routed pipeline works end to end: routing decision, worker dispatch,
  structured response, metadata stamping, and per-page latency all behave.
- Four of five frozen gate checks pass.
- The structure-marker quality check **fails**: both OCR-routed fixtures
  (`eval_scanned.pdf`, `eval_image.pdf`) are 605-byte PDFs containing **no
  image data and no text operators** — blank pages. PaddleOCR-VL correctly
  returns an image placeholder for blank input. There is nothing to extract.
- Per task 5.5 the frozen gate stands: verdict FAIL, packaged default stays
 `OCR_FALLBACK_ENABLED=false`, ADR-062 stays Proposed. Fixtures, not the
  gate, are what needs repair (see Remediation).

## What ran

| Cell | Reader | OCR gate | Fixtures |
| --- | --- | --- | --- |
| fast_path_baseline | pdf-inspector, fallback off | n/a | 5 evaluation PDFs |
| routed_worker_candidate | wrapped, fallback on | 0.5 / 0.5 | 5 evaluation PDFs |

Routed by the frozen gate: `eval_scanned.pdf`, `eval_image.pdf`
(classified `scanned` → unconditional). Kept on the fast path:
`eval_clean_text.pdf`, `eval_two_column.pdf`, `eval_mixed.pdf`.

## Frozen gate checks

| Gate | Rule | Measured | Verdict |
| --- | --- | --- | --- |
| Quality: structured failures | 0 | 0 | ✅ PASS |
| Quality: structure markers | every routed fixture ≥ 1 | 0 markers on eval_image.pdf, eval_scanned.pdf | ❌ FAIL |
| Regression: fast-path byte-identity | 0 altered | 3/3 identical | ✅ PASS |
| Latency: worker s/page p95 | ≤ 180 | 104.6 s worst page | ✅ PASS |
| Latency: routing p95 | ≤ 50 ms | 2.26 ms | ✅ PASS |

## Worker output on the routed fixtures

Both routed fixtures returned a centred image placeholder and nothing else
(`imgs/img_in_image_box_…`, `imgs/img_in_chart_box_…`; 123/124 characters,
zero headings, zero lists, zero tables). No error, no timeout: the worker
completed normally in ~104 s/page.

## Fixture-content evidence

| Fixture | Bytes | /Image XObject | DCT (JPEG) | Flate stream | Extractable content |
| --- | ---: | --- | --- | --- | --- |
| eval_scanned.pdf | 605 | no | no | no | none |
| eval_image.pdf | 605 | no | no | no | none |
| cal_table_text.pdf (smoke reference) | 946 | no | no | no | text operators |

A 605-byte PDF with no image and no text operators is a blank page. The
same placeholder behaviour on contentless scanned pages was already
documented in `ocr-worker/SMOKE_RESULTS.md` (the smoke runner switched
its default fixture for exactly this reason). Task 1.1 promised
"representative scanned content"; these two fixtures do not meet that
promise. This mismatch should have been caught at gate-freeze time.

## Other observations

- `eval_mixed.pdf` stays on the fast path at gate 0.5/0.5 (confidence 0.5
  is not below the 0.5 threshold; 0/2 flagged pages) — its silently missing
  second page remains, as pinned. Baseline and candidate outputs are
  byte-identical for all three fast-path fixtures.
- Worker per-page times: 104.4 s and 104.6 s including model load from the
  preserved cache; well inside the 180 s gate.
- Worker fingerprint matched the smoke evidence exactly (PaddleOCR-VL 1.6,
  paddleocr 3.7.0, paddlepaddle 3.3.1, paddlex 3.7.2).

## Remediation (gate unchanged)

1. Repair the task 1.1 evaluation fixtures: give `eval_scanned.pdf` and
   `eval_image.pdf` real rasterised content (self-authored text with a
   heading and a table, rendered to an image and embedded as a genuinely
   scanned page). Content authored independently of worker output.
2. Re-run this experiment against the SAME frozen gates.
3. The gate file `plan.json` is not modified by this failure.

## Reproduction

```bash
cd ocr-worker && uv sync --locked   # venv from lockfile
ln -sfn ~/Development/DATA/omrg/ocr-worker/model-cache .model-cache
cd ..
uv run python experiments/24-ocr-routing-eval-2026-09-08/run_ablation.py --resume
uv run python experiments/24-ocr-routing-eval-2026-09-08/summarise_eval.py
```

## Artefacts

| File | Description |
| --- | --- |
| `plan.json` / `protocol.md` | frozen gates and plan |
| `run_ablation.py` | ablation runner (checkpoint/resume) |
| `measure_routing_overhead.py` | routing-decision latency baseline |
| `output/ablation.json` | per-fixture rows, both cells |
| `output/eval_results.summary.json` | gate checks, machine-readable |