# OCR worker data locations

The PaddleOCR-VL model weights (~1.9 GB) were relocated on 2026-09-07 so
they survive worktree cleanup. They are gitignored and live outside this
repository.

## Preserved model cache

```text
~/Development/DATA/omrg/ocr-worker/model-cache
```

Contents: PaddleOCR-VL revision 1.6 weights as PaddleX stores them
(`official_models/`, `temp/`, locks). Matches the worker fingerprint
asserted by the capability probe.

## Using the preserved cache

The worker honours `PADDLE_PDX_CACHE_HOME` (PaddleX) and
`PADDLE_OCR_BASE_DIR` (PaddleOCR legacy). Point both at the preserved
location before importing Paddle, e.g.:

```bash
export PADDLE_PDX_CACHE_HOME=~/Development/DATA/omrg/ocr-worker/model-cache
export PADDLE_OCR_BASE_DIR=~/Development/DATA/omrg/ocr-worker/model-cache
```

With those set, the worker loads weights locally and performs no model
download.

## Re-provisioning the worker environment

The virtual environment is deliberately NOT preserved. Rebuild it from
the committed lockfile:

```bash
cd ocr-worker && uv sync --locked
```

The uv global wheel cache makes this a seconds-long operation.
