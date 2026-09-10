# Local validation and evidence commands

Run from the repository root in the prepared local worktree. The local agent
owns all execution. These commands have not been run by ChatGPT. New tests and
amendment flags below are implementation deliverables, not existing commands.

Do not run live evaluators, the Experiment 25 builder/accounting tools, or the
Experiment 28 personal-library classifier/study summariser. Do not run
`uv sync`; preserve the operator's existing environment and extras.

## A. Planning validation and historical preservation

Before implementation:

```bash
git status --short
git fetch origin
git branch --show-current
git pull --ff-only origin feat/repair-input-quality-evidence-v2
git rev-parse HEAD
openspec validate repair-input-quality-evidence-v2 --strict
```

Pull only after confirming the correct worktree and preserving any dirty work.

Run the following block before implementation and again after each stage.
It stores its first inventory under Git's private metadata, then refuses any
difference. It reads committed experiment artefacts only, not personal PDFs
or external indexes. The original symlink target text is hashed as text;
external index verification is a separate read-only local task.

```bash
uv run --no-sync python - <<'PY'
import hashlib
import json
import os
import subprocess
from pathlib import Path

base = "afe151e93dd9b79e18618811dc15e35c6a96b16d"
def git(*args):
    return subprocess.check_output(["git", *args])

names = git("ls-tree", "-r", "--name-only", base).decode().splitlines()
def protected(name):
    if name.startswith("experiments/25-token-chunking-ablation-2026-09-08/"):
        return True
    if name.startswith("openspec/changes/improve-rag-input-quality-5/"):
        return True
    if name.startswith(("docs/adr/063-", "docs/adr/064-")):
        return True
    for prefix in (
        "experiments/26-query-instruction-ablation-2026-09-08/",
        "experiments/27-combined-candidate-path-2026-09-09/",
        "experiments/28-pdf-classification-prevalence-2026-09-09/",
    ):
        if name.startswith(prefix):
            tail = name[len(prefix):]
            return tail.startswith("output/") or tail in {
                "plan.json", "protocol.md", "results.md", "discussion.md"
            }
    return name in {
        "experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/ground-truth.json",
        "experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/cells/hybrid__raw.json",
        "experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/eval_results.summary.json",
        "experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/gate_noise.json",
    }

inventory = {}
for name in filter(protected, names):
    original = git("show", f"{base}:{name}")
    path = Path(name)
    current = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
    expected = hashlib.sha256(original).hexdigest()
    actual = hashlib.sha256(current).hexdigest()
    if actual != expected:
        raise SystemExit(f"Historical bytes changed: {name}")
    inventory[name] = {"sha256": expected, "bytes": len(original)}
record = {
    "base_commit": base,
    "base_lock_sha256": hashlib.sha256(git("show", f"{base}:uv.lock")).hexdigest(),
    "files": inventory,
}
destination = Path(git("rev-parse", "--git-path",
    "repair-input-quality-evidence-v2-historical-hashes.json").decode().strip())
if destination.exists():
    assert json.loads(destination.read_text()) == record, "Inventory changed"
else:
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
print(f"Historical SHA-256 checks passed for {len(inventory)} files")
PY
```

Record external Experiment 22/25 index inventories privately using the
existing data-location records. Include filenames, sizes and hashes without
opening a write-capable store. Compare before and after. If a preserved index
is unavailable, report preservation as unverified; do not rebuild it.

## B. Amendment input and output contract to implement

Each repaired summariser accepts:

- `--evidence-manifest PATH`: a local JSON input selection/provenance record.
- `--amendment-dir PATH`: a new non-existing directory outside historical
  output paths, including their resolved symlink targets.

The local agent creates one evidence manifest per experiment after recovery
comparison. The manifest has these required fields:

| Field | Contract |
| --- | --- |
| `schema_version` | Integer 1; unknown versions refuse. |
| `experiment_id` | Exact target experiment directory name. |
| `historical_base_commit` | The pinned base commit in section A. |
| `inputs` | Object keyed by the roles below; every entry has relative `path`, full lowercase `sha256`, `bytes`, and `origin`. |
| `origin` | Each input's object: `kind` is `git` or `recovery`; `identifier` is a commit or opaque recovery ID; `selection_reason` explains its use. |
| `historical_execution` | Object with `status` (`supported`, `incomplete`, `invalid`), `missing_fields` list and `facts` list. |
| `facts` | Each fact names a TDR-014 field, its value and the input role/JSON location supporting it. Unsupported declarations do not become observations. |

Required input roles for Experiment 26:
`plan`, `ground_truth`, `runtime_manifest`, `raw_none`,
`candidate_instruction`, `baseline_production`.
The baseline role is Experiment 22's checkpoint for the drift cross-check.

Required roles for Experiment 27:
`plan`, `ground_truth`, `runtime_manifest`, `baseline_production`,
`instruction_only`, `chunking_only_raw`, `combined_candidate`.
Optional `exp25_summary` and `exp25_accounting` roles support the descriptive
drift and inherited cost sections; missing optional evidence is explicitly
unavailable. Additional provenance input roles must be explicitly referenced
by a historical fact. Refuse unused/unrecognised cell roles.

The provenance status is assessed by the validator, not trusted because a
manifest says `supported`. Validate referenced evidence and required facts.
Hash checks occur before metrics. A selected input can reference the preserved
Git file directly; recovery content uses a separate local input directory.
Do not copy private data into a public manifest. Keep a private detailed
ledger when evidence pointers disclose local information.

Each output directory contains:
- `assessment.json`: evidence status/reasons, null or supported performance
  verdict, cell roles and labelled descriptive recomputations.
- `results.md`: an amended report with historical result, qualifications and
  explicit separation of measurement date from recomputation date.
- `provenance.json`: public input roles, full hashes, byte counts, public
  origin identifiers, repair commit, current lock hash and recomputation time.

Do not copy source runtime manifests verbatim into public output if they
contain private paths. Record only needed public facts. Store details locally.

Missing/malformed input must produce a safe refusal assessment if the new
output directory can be created safely. It must not emit PASS or FAIL.
A performance FAIL on admissible complete evidence is a completed analysis,
not an input error; command exit is zero. INVALID/INCOMPLETE evidence exits
non-zero. Destination refusal must leave existing files unchanged.

Suggested input selection filenames, created locally after inspection:
`amendments/repair-input-quality-evidence-v2/inputs/experiment-26.json` and
`experiment-27.json`. Keep private pointers untracked. Public amendments
may be committed only after privacy and provenance inspection.

## C. Experiment 26

Run tests before the fix to record behavioural failures, then after the fix:

```bash
uv run --no-sync pytest tests/test_exp26_evidence_validity.py -v
uv run --no-sync ruff check experiments/26-query-instruction-ablation-2026-09-08/*.py tests/test_exp26_evidence_validity.py
```

After implementation and input/provenance selection, run offline:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 uv run --no-sync python experiments/26-query-instruction-ablation-2026-09-08/summarise_eval.py --evidence-manifest amendments/repair-input-quality-evidence-v2/inputs/experiment-26.json --amendment-dir amendments/repair-input-quality-evidence-v2/experiment-26
```

Environment flags suppress model downloads; they are not proof of network
isolation. Tests must block network connections and fail if provider/model or
write-capable index APIs are called. Inspect the offline summariser path before
running it. An expected INCOMPLETE assessment is not a passed performance gate.
Use a distinct new amendment directory for another invocation.

## D. Experiment 27

```bash
uv run --no-sync pytest tests/test_exp27_evidence_validity.py -v
uv run --no-sync ruff check experiments/27-combined-candidate-path-2026-09-09/*.py tests/test_exp27_evidence_validity.py
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 uv run --no-sync python experiments/27-combined-candidate-path-2026-09-09/summarise_eval.py --evidence-manifest amendments/repair-input-quality-evidence-v2/inputs/experiment-27.json --amendment-dir amendments/repair-input-quality-evidence-v2/experiment-27
```

The same offline restrictions and expected-refusal interpretation apply.
Do not run `run_eval.py`, even with `--limit` or `--resume`.

## E. Experiment 28: synthetic verification only

```bash
uv run --no-sync pytest tests/test_exp28_identity_privacy.py -v
uv run --no-sync ruff check experiments/28-pdf-classification-prevalence-2026-09-09/*.py tests/test_exp28_identity_privacy.py
git check-ignore -v experiments/28-pdf-classification-prevalence-2026-09-09/output/.local_identity.json experiments/28-pdf-classification-prevalence-2026-09-09/output/.local_manifest.json experiments/28-pdf-classification-prevalence-2026-09-09/output/.local_diagnostics.jsonl
git ls-files 'experiments/28-pdf-classification-prevalence-2026-09-09/output/.local*'
```

The last command must return no tracked private files. Include temporary
variants in regression tests and exclusion checks. Private diagnostics use
`output/.local_diagnostics.jsonl`; test actual owner-only permissions on the
local platform. Tests must inject a synthetic library root and prevent access
to the personal discovery root.

Record the operator stop. Do not execute the classifier CLI or study
summariser. Do not select a routing candidate.

## F. Final validation of the repaired tree

```bash
openspec validate repair-input-quality-evidence-v2 --strict
openspec validate --all --strict
uv run --no-sync ruff check experiments/26-query-instruction-ablation-2026-09-08/*.py experiments/27-combined-candidate-path-2026-09-09/*.py experiments/28-pdf-classification-prevalence-2026-09-09/*.py tests/test_exp26_evidence_validity.py tests/test_exp27_evidence_validity.py tests/test_exp28_identity_privacy.py
uv run --no-sync pytest tests/test_exp26_evidence_validity.py tests/test_exp27_evidence_validity.py tests/test_exp28_identity_privacy.py tests/test_experiment_plan_contract.py tests/test_experiment_preflight.py tests/test_experiment_stats.py tests/test_experiment_manifest.py tests/test_file_size_ceiling.py -v
```

Check every changed text file, including untracked intended additions. The
existing size test alone does not cover experiment Python or Markdown.

```bash
uv run --no-sync python - <<'PY'
import subprocess
from pathlib import Path
base = "afe151e93dd9b79e18618811dc15e35c6a96b16d"
def paths(*args):
    return set(subprocess.check_output(["git", *args]).decode().splitlines())
changed = paths("diff", "--name-only", base)
changed |= paths("ls-files", "--others", "--exclude-standard")
offenders = []
for name in sorted(changed):
    path = Path(name)
    if not path.is_file() or path.is_symlink():
        continue
    try:
        count = len(path.read_text(encoding="utf-8").splitlines())
    except UnicodeDecodeError:
        continue
    if count > 500:
        offenders.append((name, count))
assert not offenders, offenders
print("Changed text files satisfy the 500-line ceiling")
PY
uv run --no-sync pytest -m "not slow" --cov=omrg --cov-branch
git diff --check
git diff --stat afe151e93dd9b79e18618811dc15e35c6a96b16d
git diff --exit-code afe151e93dd9b79e18618811dc15e35c6a96b16d -- src/omrg pyproject.toml uv.lock config .env.example docs/adr/063-model-token-aware-markdown-chunking.md docs/adr/064-input-quality-promotion-decisions.md
git status --short
```

Re-run section A and compare private index inventories. Report the exact
commands, outcomes, skips, coverage, tested platform, recovered inputs,
amendment locations and unresolved provenance. Full-suite success does not
authorise private-document work or routing decisions.
