# PaddleOCR-VL smoke results

Date: 2026-09-07

Branch: `feat/ocr-identity-wave3`

Worker commit before results: `e01994c`

## Scope

The smoke runner is separate from the main OMRG test suite.

The required commands ran sequentially:

```text
uv run python ocr-worker/smoke_test.py --python 3.12 --provision
uv run python ocr-worker/smoke_test.py --python 3.11 --provision
uv run python ocr-worker/smoke_test.py --python 3.13 --provision
```

The default calibration scanned fixture is a 605-byte one-page PDF with no embedded image data. PaddleOCR-VL returned an image placeholder for this fixture. The response framing and schema were valid, but the runner correctly rejected the result because it had no heading, list, or table marker.

The same provisioned environments then ran the licence-safe calibration table fixture with an explicit `--fixture` argument. This fixture produced structured Markdown and supplied the committed parse evidence.

## Per-Python outcomes

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

The default scanned-fixture failure was:

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
/Users/aizat/.paddlex
```

The cache was moved into `ocr-worker/.model-cache`, the global directory was removed, and the runner and worker now set both variables before any Paddle import. Later runs confirmed model loads from the worker-local path. No model weights or virtual environments are tracked by Git.

## Platform caveat

The host is Apple Silicon M1 Pro. Paddle's official Apple Silicon inference testing targets M4 hardware. CPU inference completed on this M1 Pro for Python 3.11, 3.12, and 3.13. This result is local validation on the stated machine, not an official Paddle hardware-support claim.

## Main-environment boundary

The main-environment Paddle-free check ran before every provisioned smoke run and passed. A final metadata check also reported `Paddle-free` for the root OMRG environment.

The worker owns the Paddle packages, virtual environment, and model cache. No sibling worktree was modified. No file under `experiments/` was modified or executed.
