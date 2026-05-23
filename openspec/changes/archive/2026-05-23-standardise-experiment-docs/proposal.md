## Why

The three existing experiments (`experiment-1`, `experiment-2`, `experiment-3`) were written
incrementally and each has a different structure — experiment-1 merges protocol and results
into a single file with no operator or variables table, while experiments 2 and 3 are better
structured but still missing key reproducibility fields. A new `TEMPLATE.md` and `README.md`
have been established in `experiments/`; the existing experiments need to be brought in line
so any contributor can reproduce them without guessing what was tested or how.

## What Changes

- **experiment-1** (`reranker-threshold-calibration-2026-05-12`): Split the single
  `experiments.md` into separate `protocol.md` and `results.md`. Add operator, variables
  table, explicit prerequisites, success criteria, and artefacts sections. Rename directory
  to `reranker-threshold-calibration-2026-05-12`.
- **experiment-2** (`embedding-model-comparison-2026-05-19`): Existing `protocol.md` and
  `results.md` are close to the template. Add operator, variables table, and artefacts
  section. Rename directory to `embedding-model-comparison-2026-05-19`.
- **experiment-3** (`e2e-smoke-test-metadata-2026-05-20`): Existing `protocol.md` and
  `results.md` are the closest to the template. Add variables table and artefacts section.
  Rename directory to `e2e-smoke-test-metadata-2026-05-20`.
- **`experiments/README.md`**: Update the index table to point to the renamed directories.
- No code changes. No test changes. Documentation only.

## Capabilities

### New Capabilities

- `experiment-docs-standard`: Consistent experiment documentation structure across all
  experiments — every experiment has `protocol.md` (hypothesis, variables, prerequisites,
  method, success criteria, artefacts) and `results.md` (findings, conclusion) aligned to
  `TEMPLATE.md`.

### Modified Capabilities

*(none — this change does not alter any spec-level system behaviour)*

## Impact

- `experiments/experiment-1/` → renamed + restructured (docs only)
- `experiments/experiment-2/` → renamed + augmented (docs only)
- `experiments/experiment-3/` → renamed + augmented (docs only)
- `experiments/README.md` → index links updated to new directory names
- No source code, tests, or configuration files are affected
