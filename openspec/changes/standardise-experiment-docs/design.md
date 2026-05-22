## Context

Three experiments exist in `experiments/` with inconsistent structures accumulated over
incremental development. A `TEMPLATE.md` and `README.md` have been established as the
canonical standard. This change backfills the existing experiments to match that standard.
No code is touched — this is purely a documentation restructuring task.

Current state per experiment:

| Experiment | Has protocol.md | Has results.md | Has operator | Has variables table | Has artefacts section | Named with slug-date |
| ---------- | --------------- | -------------- | ------------ | ------------------- | --------------------- | -------------------- |
| experiment-1 | ✗ (merged into experiments.md) | ✗ (merged) | ✗ | ✗ | ✗ | ✗ |
| experiment-2 | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| experiment-3 | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |

## Goals / Non-Goals

**Goals:**
- Every experiment has a `protocol.md` matching the `TEMPLATE.md` structure
- Every experiment has a separate `results.md`
- All three directories are renamed to `<slug>-<YYYY-MM-DD>` convention
- `experiments/README.md` index links updated to new directory names
- Content fidelity preserved — no findings, data, or conclusions are altered

**Non-Goals:**
- Re-running any experiment or changing results
- Modifying `run_experiments.py`, `run_eval.py`, or any JSON data files
- Changing corpus files or ground-truth queries
- Adding new experiments

## Decisions

### Decision 1: Rename directories rather than create new ones

**Choice**: Rename `experiment-1` → `reranker-threshold-calibration-2026-05-12`, etc.

**Rationale**: The new naming convention is the standard going forward. Keeping the old
names alongside new ones would create confusion. Git history preserves the old names via
`git log --follow`. The README index is the only external reference to directory names,
and it will be updated in the same change.

**Alternative considered**: Keep old names and add symlinks. Rejected — symlinks add
complexity and the old names carry no semantic meaning worth preserving.

### Decision 2: Split experiment-1's merged file into protocol.md + results.md

**Choice**: Extract the Methodology and Results sections from `experiments.md` into
`protocol.md` and `results.md` respectively, then remove `experiments.md`.

**Rationale**: Experiment-2 and experiment-3 already use the split structure. Consistency
across all experiments is the goal. The merged file is the outlier.

**Alternative considered**: Rename `experiments.md` to `protocol.md` and keep results
inline. Rejected — results and protocol serve different purposes; keeping them separate
makes it easier to update results without touching the reproduction instructions.

### Decision 3: Preserve all existing content verbatim

**Choice**: Add missing sections (operator, variables, artefacts) without altering any
existing prose, tables, or findings.

**Rationale**: The experiments have already been run and their conclusions are referenced
in `AGENTS.md` and the codebase. Changing the content would invalidate those references.

## Risks / Trade-offs

- **Broken internal links**: `AGENTS.md` references `experiments/experiment-1/` by path.
  After renaming, those references will be stale. → Mitigation: search for all references
  to old directory names across the repo and update them as part of the tasks.
- **Git history**: `git mv` preserves history for the directory rename; plain file deletion
  and recreation does not. → Mitigation: use `git mv` for directory renames.
