# dots-mocr smoke results

Change `modular-ocr-workers-dots-mocr`, tasks 3.1, 3.4 and 3.5.
Date: 2026-10-04.

## Approvals

- The operator approved provisioning and the model download on 2026-10-04.
- The operator accepted the dots.mocr licence on 2026-10-04 before
  `--accept-model-licence` was passed. See `LICENCE-NOTES.md`.
- The operator approved isolated PyTorch use on 2026-09-24 (proposal).

## Machine

Apple M5 Pro, 48 GB unified memory, macOS 27.0, uv 0.12.18,
engine Python 3.12.14.

## Provisioning

```bash
export OMRG_OCR_MODEL_CACHE=~/Development/DATA/omrg/ocr-models
python3 ocr-workers/provision.py dots-mocr --dry-run --accept-model-licence
python3 ocr-workers/provision.py dots-mocr --python 3.12 --accept-model-licence
```

1. The dry run resolved from `uv.lock` and installed nothing (task 3.1).
2. The real run exited 0. It installed the environment and ran
   `omrg-ocr-fetch`, which downloaded revision
   `e539fbb52280393adc081b289ec597430a0f9031`, applied the patch set and
   wrote `omrg-code-hashes.json`.
3. Disk: model folder 5.7 GB at
   `~/Development/DATA/omrg/ocr-models/dots-mocr/` (outside the
   repository, kept across worktree removal); engine `.venv` 756 MB.
4. The patched `modeling_dots_vision.py` differs from the Experiment 34
   copy only in one patch comment. `modeling_dots_ocr.py`,
   `configuration_dots.py` and `model.safetensors.index.json` are
   identical to the Experiment 34 copy.

## Capability output

```json
{"backend_id": "dots_mocr", "model": {"identity": "rednote-hilab/dots.mocr", "revision": "e539fbb52280393adc081b289ec597430a0f9031"}, "output_schema": {"id": "omrg.ocr.parse_output", "version": "1"}, "packages": {"accelerate": "1.15.0", "omrg-ocr-dots-mocr": "0.1.0", "omrg-ocr-worker-core": "0.1.0", "pillow": "12.3.0", "pypdfium2": "5.13.0", "qwen-vl-utils": "0.0.14", "torch": "2.14.0", "torchvision": "0.29.0", "transformers": "4.57.6"}, "pipeline": {"identity": "dots-mocr-layout", "revision": "prompt_layout_all_en+omrg-mps-1+layout-1"}, "protocol_version": "1.1"}
```

## Offline smoke run (task 3.4)

```bash
python3 ocr-workers/engines/dots-mocr/smoke_test.py --run \
  --case eq01=<exp34>/corpus/eq01.pdf:11 \
  --case io06=<exp33>/corpus/natural/io06.pdf:28
```

One worker process received both requests over the JSON Lines protocol.
It ran under `sandbox-exec` with all network connections denied, so any
download attempt would have failed. The engine also sets
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` itself.

| Page | Result | Seconds | Characters |
| --- | --- | --- | --- |
| `eq01` p11 | ok | 73.8 (includes model load) | 3,590 |
| `io06` p28 | ok | 17.6 | 1,173 |

- `eq01` p11 Markdown is byte-identical to the Experiment 34 probe output
  (`experiments/34-worker-sample-review-2026-09-19/output/dots_mocr/eq01/p011.md`).
- KaTeX 0.16.22 rendered all 4 display formulas and 18 inline formulas on
  `eq01` p11 with `throwOnError: true`: 0 errors. The checker was tested
  first on a file with two broken formulas and reported both.
- `io06` p28 returned non-empty Latin text.

Evidence: `smoke_evidence/` (capability JSON, per-page Markdown,
`run.json`, `katex-check.json`, worker standard error).

## Memory (task 3.5)

Peak memory footprint of the worker process (`/usr/bin/time -l`):
10,242,885,336 bytes (about 9.5 GiB). On Apple Silicon this figure
includes MPS allocations in unified memory, plus the Python process
itself. It sits slightly above the 7–9 GB estimate in the proposal. The
configuration guide's advice stands: on machines short of memory, set
`OCR_ENGINE_PRIMARY=paddleocr-vl`.

## Warnings seen

The worker logged upstream notices only: `torch_dtype` deprecation, the
fast image processor default, and `pad_token_id` set to `eos_token_id`.
None affected the output.
