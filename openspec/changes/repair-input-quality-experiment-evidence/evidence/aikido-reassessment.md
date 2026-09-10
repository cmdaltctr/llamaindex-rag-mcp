# Aikido reassessment: Experiments 25 to 28

## Verdict

**BLOCKED**

The deterministic scanner floor is `BLOCKED`. A secret detector matched the public tokenizer revision pin in `estimate_gate.py`. Code tracing shows no credential use, but policy forbids lowering the scanner floor without a recorded, user-approved rationale.

Experiment 28 also retains two known MEDIUM gaps. Tasks 6.1 and 6.2 remain open.

## Scope

- Worktree: `/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3-feat-improve-rag-input-quality-5`
- Branch: `feat/improve-rag-input-quality-5`
- Commit range used to identify new experiment scripts: `2c58b45..afe151e`
- Experiment 25: `build_index.py`, `estimate_gate.py`, `overnight.sh`
- Experiment 26: `run_eval.py`, `summarise_eval.py`
- Experiment 27: `run_eval.py`, `summarise_eval.py`
- Experiment 28: `classify.py`, `summarise_eval.py`
- New scoped tests: `test_exp25_build_authorisation.py`, `test_exp25_estimate_gate_scaffold.py`

The unapproved mixed production patch was excluded. No `src/`, `.env`, index, frozen result, or raw output content was scanned or read. Existing marker presence was checked by the scoped test without reading marker content.

## Scan evidence

### Reproducibility gate

`check-tools.sh` passed:

| Tool | Version |
| --- | --- |
| gitleaks | 8.30.1 |
| semgrep | 1.174.0 |
| osv-scanner | 2.5.1 |
| trivy | 0.74.0 |
| bandit | 1.9.4 |

The vendored Semgrep snapshot is dated 2026-08-26. It contains 559 rules with SHA-256 `a59add95f4e0346fe98d334f363484e3fa343889d0624174f1e99de828eb17b4`.

### Deterministic suite

The 11 scoped files were copied to an isolated temporary directory. `run-scan.sh` scanned only that copy. Bandit was then run directly because the staged root had no root-level Python marker.

Merged result:

- Scanner verdict: `BLOCKED`
- CRITICAL: 1
- LOW: 35
- Deterministic findings: 36
- Semgrep: no findings
- Trivy: no findings
- Bandit: 34 `B101` test-assert notices and one `B311` statistical-random notice

The `B101` findings occur only in pytest tests, where assertions are the test contract. The `B311` call is a seeded statistical bootstrap, not a security or cryptographic operation. These LOW notices require no security change.

OSV exited 128 because the isolated file-only target contained no package source. This audit intentionally excluded broad and live-feed dependency CVE work. `uv pip check` separately confirmed all 183 installed packages are compatible. It is not a CVE-feed result.

### Aikido scan

`aikido_scan_paths` scanned the 11 existing workspace paths. It reported three issues and no tool errors:

1. `AIK_py_LFI`, severity 50, `experiments/26-query-instruction-ablation-2026-09-08/run_eval.py:113`.
2. `AIK_py_LFI`, severity 50, `experiments/27-combined-candidate-path-2026-09-09/run_eval.py:123`.
3. `generic-api-key`, severity 80, `experiments/25-token-chunking-ablation-2026-09-08/estimate_gate.py:38`.

Existing repair evidence names earlier checkpoint and temporary-file `AIK_py_LFI` findings, but preserves no earlier scanner payload or exact file and line pair. The fresh scan reproduced two temporary-write matches. It did not reproduce a checkpoint-read match. Both current checkpoint reads and temporary writes were traced below.

## Findings and dispositions

### CRITICAL: Secret-shaped tokenizer revision remains a scanner-floor blocker

**Source:** `[scanner: gitleaks generic-api-key]`, `[scanner: Aikido generic-api-key]`

**Location:** `experiments/25-token-chunking-ablation-2026-09-08/estimate_gate.py:38`

`TOKENIZER_REVISION` is a 40-character hexadecimal revision pin. It is placed in the tokenizer identity and hashed into future estimate identity records. No code sends it as an API key, password, bearer token, or credential.

The code evidence supports a non-secret revision identifier disposition. This reassessment does not mark the issue accepted or false positive. The deterministic floor stays `BLOCKED` until the user approves a recorded rationale and any narrowly scoped scanner handling.

### LOW: Fixed checkpoint paths prevent arbitrary-input LFI, with a local symlink risk

**Source:** `[scanner: Aikido AIK_py_LFI]` plus `[LLM-judged]` reachability analysis

Experiment 26 source-to-sink:

1. `cell` comes from the fixed `CELLS` mapping: `raw_none` or `candidate_instruction`.
2. `_checkpoint_path` joins that fixed value under `EXP_DIR/output/cells`.
3. `_load_checkpoint` reads only the resulting fixed JSON path.
4. `_save_checkpoint` derives `.json.tmp`, writes JSON, then replaces the fixed checkpoint.
5. CLI input exposes only `--resume` and integer `--limit`. It cannot supply a path or cell name.

Experiment 27 has the same path flow with fixed cells `chunking_only_raw` and `combined_candidate`. Its CLI also exposes no path input.

The summarisers use fixed `CELLS` or fixed `CELL_SOURCES`. Their `checkpoint: Path` function parameter receives only those module-defined paths. A repository fixture can control checkpoint content, but cannot choose another filesystem path through the CLI.

Therefore, no arbitrary CLI-to-file local file inclusion path was found. The scanner description also calls the flagged `write_text` sink a read operation, which does not match the code.

A residual local symlink risk remains. Both the predictable `.json.tmp` file and fixed checkpoint can be replaced with symlinks by an actor who can write inside the checkout. A controlled temporary-directory check confirmed that `Path.write_text` followed the temporary symlink and `Path.read_text` followed the checkpoint symlink. Such access could overwrite or read another file available to the experiment process. Exploitation requires local write access to the experiment directory or a malicious checkout. Keep this as a LOW hardening gap.

Exceptions from these path operations are not serialised into experiment artefacts. An uncaught traceback can expose the fixed checkout path. The checkpoint payload contains query IDs, categories, parent IDs, ranks, and timing. It does not contain document paths or credentials.

### MEDIUM: Experiment 28 serialises unrestricted exception text

**Source:** `[LLM-judged]`

**Location:** `experiments/28-pdf-classification-prevalence-2026-09-09/classify.py:197-199`

`reader.load_data(path)` processes PDFs under the fixed Zotero storage root. Its exception is stored as `str(exc)[:300]` in committed `output/classifications.json`. Parser errors can include a private filename, local path, or extracted content fragment.

The console prints only the document ID and exception class. The committed checkpoint remains the leak path. Task 6.2 correctly remains open. Replace public exception messages with a bounded code, and keep detailed diagnostics in a private local file.

### MEDIUM: Experiment 28 checkpoint identity is not bound to population or policy

**Source:** `[LLM-judged]`

**Location:** `experiments/28-pdf-classification-prevalence-2026-09-09/classify.py:93-118,166-180`

Document IDs depend on the sorted set of current content digests. The checkpoint stores rows and completed IDs without a population digest, immutable ID mapping digest, or gate-policy identity. Adding, removing, or replacing a PDF can shift IDs. Resume can then combine stale rows with a rewritten local mapping.

This is an experiment data-integrity defect. Task 6.1 correctly remains open. Bind a new checkpoint to immutable population, mapping, classifier, and gate identities. Refuse resume when any identity changes.

### LOW: Live rebuild tests do not independently trap every future file read or import

**Source:** `[LLM-judged]`

The current `build_index.py` code was verified to refuse before estimate or approval reads and before OMRG imports. A runtime trap returned exit 1 with zero trapped document reads and zero OMRG imports.

The tests prove zero fake runtime requests. They do not trap a future estimate-file read followed by refusal. Fake OMRG modules are inserted into `sys.modules`, so a future import without a runtime call would also pass. Add explicit `Path.read_text` or `open` traps and an import hook when test hardening is authorised.

### LOW: Historical marker reuse checks existence only

**Source:** `[LLM-judged]`

`build_index.py` returns success when the fixed marker exists and `--force` is absent. It does not validate marker content, historical identity, or preserved-index presence. A stale or planted marker can produce a successful no-op, though it cannot authorise paid work.

Keep marker identity and operational validation unresolved. Paid rebuild safety is unaffected because `--force` still exits 1.

## Experiment 25 authorisation path

The live path is fail-closed:

- `build_index.py` imports only `argparse`, `sys`, and `Path`.
- It parses estimate, approval, and destination arguments without opening them.
- It checks only the fixed marker.
- Marker absence or `--force` produces exit 1.
- Marker presence without `--force` is the only successful exit.
- `overnight.sh` exits 1 before invoking Python or paid work.
- `estimate_gate.py` is labelled `UNVERIFIED SCAFFOLD` and is never imported or called by `build_index.py`.

The scaffold still lacks the production-based estimator and installed-adapter request-text parity proof. Its passing document test proves only internal contract consistency. It cannot authorise spending.

## Test and size evidence

Targeted command:

```text
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider -q \
  tests/test_exp25_build_authorisation.py \
  tests/test_exp25_estimate_gate_scaffold.py
```

Result: `27 passed in 2.78s`.

`overnight.sh` returned exit 1. The dynamic build trap returned exit 1 before any trapped estimate or approval read and before any trapped OMRG import.

Python file lengths:

| File | Lines |
| --- | ---: |
| Experiment 25 `build_index.py` | 90 |
| Experiment 25 `estimate_gate.py` | 438 |
| Experiment 26 `run_eval.py` | 282 |
| Experiment 26 `summarise_eval.py` | 391 |
| Experiment 27 `run_eval.py` | 298 |
| Experiment 27 `summarise_eval.py` | 460 |
| Experiment 28 `classify.py` | 213 |
| Experiment 28 `summarise_eval.py` | 344 |
| `test_exp25_build_authorisation.py` | 251 |
| `test_exp25_estimate_gate_scaffold.py` | 382 |

All scoped Python files remain below the 500-line ceiling.

## Eight-category checklist

| Category | Status |
| --- | --- |
| Secrets and credentials | BLOCKED by the unapproved secret-pattern disposition. No credential use was traced. |
| Input validation | Exp25 path arguments are ignored before reads. Exp26 to 28 expose no arbitrary path CLI input. |
| Authentication and authorisation | N/A. These are local experiment scripts with no authentication boundary. |
| Injection | No SQL, shell construction, `eval`, `exec`, subprocess, XSS, or SSRF sink exists in scope. Fixed-path symlink hardening remains LOW. |
| Data exposure | MEDIUM. Experiment 28 can publish unrestricted parser exception text. |
| Dependency CVEs | Out of scope by instruction. OSV had no package source. Local compatibility check passed. |
| OWASP Top 10 | A03 path reachability traced. A08 data integrity and A09 error exposure remain open. Other web categories are N/A. |
| Cloudflare Workers | N/A. No Worker code is in scope. |

## Required actions

1. Obtain explicit user approval before recording the tokenizer revision as a scanner false positive or adding a narrow allowlist.
2. Complete task 6.1 before reusing Experiment 28 checkpoints on any changed population or policy.
3. Complete task 6.2 before publishing a new Experiment 28 checkpoint or report.
4. Add explicit file-read and OMRG-import traps to the Experiment 25 refusal tests.
5. Harden checkpoint temporary writes against symlinks if the checkout can be shared or untrusted.
6. Validate the exact historical marker identity before treating marker presence as reliable operational success.

## Final verdict

**BLOCKED**

The paid rebuild path fails closed. The scanner-floor exception lacks user approval, and Experiment 28 retains the known privacy and identity defects.
