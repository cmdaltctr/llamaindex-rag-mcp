# omrg-ocr-worker

The isolated PaddleOCR-VL document-parsing worker for OMRG.

This project is one half of the OpenSpec change
`improve-rag-input-quality-5` (Stage 2). It owns every Paddle package.
The OMRG main project keeps none of them. Read the change documents
under `openspec/changes/improve-rag-input-quality-5/` for the design
decisions (D2, D2.1 to D2.4).

## Purpose

The worker runs as a local subprocess. It parses a whole PDF with the
full PaddleOCR-VL document pipeline: layout analysis, region
handling, reading order, recognition, and result assembly. It returns
structured Markdown.

The two processes talk over JSON Lines:

- OMRG writes one request object per line to the worker's standard
  input.
- The worker writes one terminal response object per line to standard
  output. Nothing else may appear there.
- All worker logs and diagnostics go to standard error.

The protocol lives in `src/omrg_ocr_worker/protocol.py`. OMRG keeps an
independent twin. Tests in the main repository prove the two copies
agree byte-for-byte. Do not make one import the other.

## Provisioning

Run the deterministic provisioning script from this directory:

```bash
cd ocr-worker
python3 provision.py                # uses Python 3.12
python3 provision.py --python 3.11
python3 provision.py --python 3.13
python3 provision.py --dry-run      # resolve only, install nothing
```

The script resolves the environment from `uv.lock` only
(`uv sync --locked`). It never changes the OMRG main environment. It
rejects any Python outside the supported range before it installs
anything.

After provisioning, start the worker with:

```bash
uv run python -m omrg_ocr_worker
```

Do not run `uv sync` from the repository root. That installs the OMRG
main environment, not this one.

## Python support

| Version | Status |
| ------- | ------ |
| 3.11    | Supported |
| 3.12    | Supported (provisioning default) |
| 3.13    | Supported |
| 3.10    | Rejected by `provision.py` |
| 3.14+   | Rejected by `provision.py` |

The manifest declares `requires-python = ">=3.11,<3.14"`. The
lockfile resolves for all three supported versions.

## Known caveats

- Apple Silicon: PaddleOCR documents direct Metal inference on Apple
  Silicon, but the project tests it officially on M4 hardware only.
  This worker pins the CPU `paddlepaddle` runtime. Treat
  accelerator variants as unvalidated until the smoke test (task
  2.15) has run on the target machine.
- The full environment is multi-gigabyte. Provision it only on
  machines that will run OCR. OMRG degrades to the `pdf-inspector`
  fast path when the worker is absent.

## Wave status

This wave ships the project manifest, the lockfile, the provisioning
guard, the protocol, and the worker framing loop. The PaddleOCR-VL
pipeline call inside the parse seam is completed with the provisioned
smoke test (task 2.15).
