# PaddleOCR-VL smoke results

Date: 2026-09-07

Branch: `feat/ocr-identity-wave3`

Worker commit before results: `e01994c`

## Scope

The smoke runner is separate from the main OMRG test suite.

The initial bare provisioned runs selected the default scanned fixture. That 605-byte one-page PDF has no embedded image data. PaddleOCR-VL returned an image placeholder, so the runner rejected it for lacking a heading, list, or table marker. The same provisioned environments then ran the licence-safe calibration table fixture with an explicit `--fixture` argument.

Bare provisioned runs now select the calibration table fixture. This fixture produces structured Markdown and validates the runner's required output marker check.

## Initial per-Python outcomes

| Python | Provision | Required default fixture | Structured validation fixture | Provision time | Parse time | Worker bytes after parse |
| --- | --- | --- | --- | ---: | ---: | ---: |
| 3.11.13 | PASS | Framing/schema PASS; structured-marker check FAIL | PASS, 1,035 Markdown characters | 21.18 s first run; 4.12 s cached run | 150.81 s default; 106.12 s table | 3,074,673,933 |
| 3.12.13 | PASS | Framing/schema PASS; structured-marker check FAIL | PASS, 1,035 Markdown characters | 28.93 s initial run; 0.10 s cached run; 0.06 s table | 289.75 s initial; 84.03 s cached default; 33.74 s table | 3,071,608,858 |
| 3.13.14 | PASS | Framing/schema PASS; structured-marker check FAIL | PASS, 1,035 Markdown characters | 23.26 s first run; 3.75 s cached run | 156.07 s default; 106.35 s table | 3,068,370,967 |

All three versions provisioned from `ocr-worker/uv.lock`. No wheel was unavailable on this Apple arm64 host.

## Capability fingerprint

Every provisioned probe returned this complete fingerprint:

```json
{
  "model": {
    "identity": "PaddleOCR-VL",
    "revision": "1.6"
  },
  "output_schema": {
    "id": "omrg.ocr.parse_output",
    "version": "1"
  },
  "packages": {
    "omrg-ocr-worker": "0.1.0",
    "paddleocr": "3.7.0",
    "paddlepaddle": "3.3.1"
  },
  "pipeline": {
    "identity": "paddleocr-vl",
    "revision": "predict+restructure_pages"
  },
  "protocol_version": "1.0"
}
```

The probe printed one JSON line and exited without initialising PaddleOCR-VL or loading model weights.

### Post-review fingerprint addendum (2026-09-07)

The branch review found that the fingerprint omitted PaddleX, the
package `PaddleOCRVL` delegates prediction and page restructuring to.
`DECLARED_PACKAGES` now declares it, so a PaddleX-only change invalidates
the worker identity. The same review hardened the worker-local cache
environment (forced assignment instead of `setdefault`) and made the
smoke runner pin `UV_PROJECT`/`UV_PROJECT_ENVIRONMENT` to the worker
project so inherited values cannot redirect provisioning.

A metadata-only probe with the amended code (worktree `PYTHONPATH` over
the provisioned Python 3.13 environment; no model load) reported:

```json
{
  "model": {
    "identity": "PaddleOCR-VL",
    "revision": "1.6"
  },
  "output_schema": {
    "id": "omrg.ocr.parse_output",
    "version": "1"
  },
  "packages": {
    "omrg-ocr-worker": "0.1.0",
    "paddleocr": "3.7.0",
    "paddlepaddle": "3.3.1",
    "paddlex": "3.7.2"
  },
  "pipeline": {
    "identity": "paddleocr-vl",
    "revision": "predict+restructure_pages"
  },
  "protocol_version": "1.0"
}
```

This differs from the initial per-Python evidence above by the added
`paddlex` entry, which is the intended identity change. The table-fixture
parse evidence files remain valid.

### Bare provisioned smoke matrix addendum (2026-09-07)

This addendum supersedes the initial default-fixture result. `DEFAULT_FIXTURE`
now selects `calibration/cal_table_text.pdf`, which produces structured
Markdown. The image-only `calibration/cal_scanned.pdf` result remains
available through an explicit `--fixture` argument.

| Python | Provision | Parse | Disk delta | Result |
| --- | ---: | ---: | ---: | --- |
| 3.11 | 3.97 s | 129.41 s | +6,305,517 bytes | PASS |
| 3.12 | 4.81 s | 135.67 s | -4,618,747 bytes | PASS |
| 3.13 | 4.67 s | 146.17 s | -1,686,780 bytes | PASS |

Each run used `uv sync --locked` in `ocr-worker/.venv`, returned a valid
fingerprint containing `paddlex: 3.7.2`, and produced 1,035 characters
of structured Markdown. PaddleOCR-VL loaded weights from
`ocr-worker/.model-cache`; no model download occurred.

## Parse evidence

The successful table-fixture responses were identical across Python versions:

- Request id: `smoke-test-0001`
- Response type: `parse_result`
- `ok`: `true`
- Protocol: `1.0`
- Output schema: `omrg.ocr.parse_output` version `1`
- Page count: `1`
- OCR backend: `paddleocr-vl`
- Pipeline: `PaddleOCRVL` using `predict+restructure_pages`
- Model: `PaddleOCR-VL` revision `1.6`
- Markdown markers: `## Calibration Table Text Fixture` and an HTML `<table>` block
- Markdown length: `1,035` characters

Evidence files:

```text
ocr-worker/smoke_evidence/parse-python-3-11.json
ocr-worker/smoke_evidence/parse-python-3-11.md
ocr-worker/smoke_evidence/parse-python-3-12.json
ocr-worker/smoke_evidence/parse-python-3-12.md
ocr-worker/smoke_evidence/parse-python-3-13.json
ocr-worker/smoke_evidence/parse-python-3-13.md
```

The initial default scanned-fixture result was:

```text
parse response markdown has no heading, list, or table marker — not structured text
```

The worker still returned a valid correlated `parse_result` with the declared output schema for that fixture. The fixture contains no source content for the document model to recognise.

## Disk cost and cache location

Final worker-owned disk usage:

```text
ocr-worker/.venv        1.0G
ocr-worker/.model-cache 1.9G
```

The final worker directory size measured by the smoke runner was `3,068,370,967` bytes.

The first Python 3.12 run revealed that `PADDLE_OCR_BASE_DIR` controls PaddleOCR's legacy model directory, while PaddleX uses `PADDLE_PDX_CACHE_HOME`. The initial model download therefore went to:

```text
$HOME/.paddlex
```

The cache was moved into `ocr-worker/.model-cache`, the global directory was removed, and the runner and worker now set both variables before any Paddle import. Later runs confirmed model loads from the worker-local path. No model weights or virtual environments are tracked by Git.

## Platform caveat

The host is Apple Silicon M1 Pro. Paddle's official Apple Silicon inference testing targets M4 hardware. CPU inference completed on this M1 Pro for Python 3.11, 3.12, and 3.13. This result is local validation on the stated machine, not an official Paddle hardware-support claim.

## Security scan

The post-fix Aikido ruleset scan covered `ocr-worker/smoke_test.py`,
`tests/test_ocr_worker_smoke_runner.py`, and this record. It reported two
existing `AIK_py_LFI` alerts at the evidence-write calls in
`smoke_test.py` lines 450 and 454. The current diff changes only
`DEFAULT_FIXTURE` at line 56, so both alerts are outside this change.

## Main-environment boundary

The main-environment Paddle-free check ran before every provisioned smoke run and passed. A final metadata check also reported `Paddle-free` for the root OMRG environment.

The worker owns the Paddle packages, virtual environment, and model cache. No sibling worktree was modified. No file under `experiments/` was modified or executed.
