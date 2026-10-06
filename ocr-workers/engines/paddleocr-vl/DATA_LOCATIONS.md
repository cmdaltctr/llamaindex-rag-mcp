# PaddleOCR-VL engine data locations

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

The engine sets `PADDLE_PDX_CACHE_HOME` (PaddleX) and `PADDLE_OCR_BASE_DIR`
(PaddleOCR legacy) itself, by assignment, before it imports Paddle. An
inherited value of either variable is overwritten. To use the preserved
weights, point the shared cache variable at a folder whose `paddleocr-vl`
entry is the preserved cache (change modular-ocr-workers-dots-mocr,
design D8):

```bash
mkdir -p ~/Development/DATA/omrg/ocr-models
ln -s ~/Development/DATA/omrg/ocr-worker/model-cache \
  ~/Development/DATA/omrg/ocr-models/paddleocr-vl
export OMRG_OCR_MODEL_CACHE=~/Development/DATA/omrg/ocr-models
```

The engine then loads weights from
`$OMRG_OCR_MODEL_CACHE/paddleocr-vl/` and performs no model download.
The dots-mocr engine uses `$OMRG_OCR_MODEL_CACHE/dots-mocr/` under the
same variable.

## Re-provisioning the engine environment

The virtual environment is deliberately NOT preserved. Rebuild it from
the committed lockfile:

```bash
python3 ocr-workers/provision.py paddleocr-vl
```

The uv global wheel cache makes this a seconds-long operation.
