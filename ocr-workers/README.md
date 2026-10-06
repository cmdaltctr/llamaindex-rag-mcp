# OMRG OCR workers

This folder holds the isolated OCR engines that OMRG calls for scanned
PDFs, gate-selected PDFs, escalated pages and maths pages. OpenSpec change
`modular-ocr-workers-dots-mocr` sets the layout (design D1 to D9).

```
ocr-workers/
  README.md        this file
  provision.py     provisions one engine: python3 provision.py <engine>
  core/            omrg-ocr-worker-core: protocol, framing, capabilities, engine contract
  engines/
    dots-mocr/     primary engine (PyTorch, licence gate)
    paddleocr-vl/  fallback engine (PaddlePaddle)
```

## How OMRG talks to an engine

Each engine runs as a local subprocess in its own environment. OMRG and the
engine exchange JSON Lines over standard input and standard output:

- OMRG writes one request object per line.
- The engine writes one terminal response object per line. Nothing else goes
  to standard output.
- All logs go to standard error.

The protocol lives in `core/src/omrg_ocr_worker_core/protocol.py`. OMRG keeps
a byte-identical copy in `src/omrg/integrations/ocr_worker/protocol.py`. The
same rule applies to `validation.py`. A test fails if the copies differ by one
byte. Do not make one import the other.

OMRG starts an engine with this command, from the engine folder:

```bash
<OCR_WORKERS_DIR>/engines/<engine>/.venv/bin/python -m omrg_ocr_worker_core
```

The core loads the one engine that the environment registers. An environment
with zero engines, or with more than one, reports itself unavailable.

## Routes

OMRG reads two route settings:

| Setting               | Default        | Meaning                                  |
| --------------------- | -------------- | ---------------------------------------- |
| `OCR_WORKERS_DIR`     | empty          | This folder. Empty makes every route unavailable. |
| `OCR_ENGINE_PRIMARY`  | `dots-mocr`    | Engine for every OCR dispatch.           |
| `OCR_ENGINE_FALLBACK` | `paddleocr-vl` | Engine when the primary is unavailable before dispatch. Empty means no fallback. |

A non-empty `OCR_WORKER_COMMAND` (with `OCR_WORKER_ENV_DIR`) overrides the
primary route only. The fallback route still resolves from `OCR_WORKERS_DIR`.

## Provisioning

Run the provisioning script for each engine you want:

```bash
python3 ocr-workers/provision.py paddleocr-vl
python3 ocr-workers/provision.py dots-mocr --accept-model-licence
python3 ocr-workers/provision.py paddleocr-vl --python 3.11
python3 ocr-workers/provision.py dots-mocr --accept-model-licence --dry-run
```

The script:

1. Rejects an unknown engine name.
2. Stops before it installs anything when the engine needs licence acceptance
   and you did not give `--accept-model-licence`. The error names the licence
   file.
3. Rejects any Python outside `>=3.11,<3.14`.
4. Runs `uv sync --locked` in the engine folder. It never changes the OMRG
   main environment.
5. Runs the engine's `omrg-ocr-fetch` script, if the engine has one, to
   download pinned weights and apply patches. `--dry-run` skips this step.

Do not run `uv sync` from the repository root to provision an engine. That
command installs the OMRG main environment.

### Model cache

Each engine keeps its weights in `<engine folder>/.model-cache/`. This folder
is gitignored. To keep weights outside a worktree, set `OMRG_OCR_MODEL_CACHE`.
Engine `<name>` then uses `$OMRG_OCR_MODEL_CACHE/<name>/`.

## Engines

### dots-mocr (primary)

- Model `rednote-hilab/dots.mocr`, pinned revision
  `e539fbb52280393adc081b289ec597430a0f9031`.
- Needs `--accept-model-licence`. Read `engines/dots-mocr/LICENCE-NOTES.md`
  first. It records clauses 3.3(c), 5.2, 8 and 9 of the model licence.
- Uses about 7 to 9 GB of MPS memory in bfloat16 on Apple Silicon. It is slow
  on CPU. On a machine with little memory, set
  `OCR_ENGINE_PRIMARY=paddleocr-vl`.
- Parses offline. The worker refuses to load when a model code file differs
  from the hash recorded at provisioning.

### paddleocr-vl (fallback)

- PaddleOCR-VL 1.6 document pipeline on the CPU PaddlePaddle runtime.
- Apache-2.0. No licence flag.
- `engines/paddleocr-vl/DATA_LOCATIONS.md` names the preserved weight copy.

## Add an engine

A new engine needs one folder and one route setting. OMRG code does not
change. The stub engine in `tests/fixtures/ocr_worker/stub_engine/` has the
same parts.

1. Create `engines/<name>/`. Use a plain folder name: letters, digits, `.`,
   `_` and `-`.
2. Add `engines/<name>/pyproject.toml` with:
   - `requires-python = ">=3.11,<3.14"`;
   - `omrg-ocr-worker-core` in `dependencies`, with
     `[tool.uv.sources] omrg-ocr-worker-core = { path = "../../core" }`;
   - the model runtime packages;
   - one entry point:
     `[project.entry-points."omrg.ocr_engine"] <name> = "<module>:ENGINE"`;
   - if the model licence adds terms: `[tool.omrg-ocr] licence-file = "..."`
     and `requires-acceptance = true`;
   - if the engine downloads weights: `[project.scripts] omrg-ocr-fetch = "..."`.
3. Add the engine module. Its `ENGINE` object has:
   - `name`: the folder name;
   - `backend_id`: the diagnostic name, for example `dots_mocr`;
   - `declared_packages`: every package whose version changes the output;
   - `pipeline` and `model`: `(identity, revision)` pairs;
   - `parse(pdf, pages) -> list[str]`: one Markdown string per page. Return
     `""` for a page the engine cannot read.
   Import model code inside `parse`, never at module level.
4. Add `engines/<name>/.gitignore` with `.venv/`, `.model-cache/` and
   `.ocr-pages-*`.
5. Run `uv lock` in `engines/<name>/` and commit `uv.lock`.
6. If the licence adds terms, add the licence file that step 2 names.
7. Provision the engine: `python3 ocr-workers/provision.py <name>`.
8. Set `OCR_ENGINE_PRIMARY=<name>` or `OCR_ENGINE_FALLBACK=<name>`.
