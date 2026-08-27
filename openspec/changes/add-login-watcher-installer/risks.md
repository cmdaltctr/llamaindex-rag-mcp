# Security Assessment: `add-login-watcher-installer`

> **Ratification (build owner, post-audit)**: the floor-lowering is
> APPROVED. All 76 gitleaks CRITICALs are 64-hex sha256 model checksums
> and 40-hex git SHAs inside untracked experiment JSON — entropy false
> positives, zero findings in committed history. Audit F2 and F4 were
> fixed with regression tests (relative `--command-path` rejection,
> dash-prefixed collection rejection) plus F7's two test pins; F3
> (launchctl via PATH) and F5 (NaN debounce) are accepted residual
> risks — both fail loudly at login time, not silently.

## Summary

- **Date**: 2026-08-26
- **Auditor**: a-security (read-only audit; no source files modified)
- **Scope**: uncommitted working-tree changes on `feat/add-login-watcher-installer`
  - New: `src/rag_mcp/transports/cli/_launchagent.py`, `src/rag_mcp/transports/cli/install_login_watcher.py`, `tests/test_install_login_watcher.py`, `tests/unit/test_launchagent.py`
  - Modified: `src/rag_mcp/transports/cli/__init__.py` (import registration only), `src/rag_mcp/transports/cli/watch.py` (help wording only), `src/rag_mcp/core/vectordb/registry.py` (additive `cross_process_writes_safe` flag), `tests/test_clean_base_tripwire.py` (count bump, reviewed — no assertion weakened)
- **Commit range audited**: `fc12d58` (HEAD, clean) + uncommitted working-tree diff (the 8 files above). `src/rag_mcp/transports/mcp.py` confirmed untouched.
- **Scanner verdict (deterministic floor)**: `BLOCKED` (76 CRITICAL / 4 HIGH / 6 MEDIUM / 2936 LOW / 98 INFO) — see deconfirmation analysis below.
- **Final verdict**: **NEEDS FIXES** (change-scoped code: clean above LOW; the fix-required items are pre-existing, out-of-diff dependency CVEs plus LOW hardening)
- **Verdict raised above floor?**: No. Verdict is below the scanner floor of BLOCKED. The lowering rationale is recorded below and requires your ratification.

## Deterministic Scan Results

- **Tools**: gitleaks 8.30.1, semgrep 1.174.0, osv-scanner 2.5.1, trivy 0.74.0, bandit 1.9.4 (all present per `check-tools.sh`; bandit stage re-run scoped to `src/ + tests/` after the full-repo pass hit the 10-minute timeout crawling `.venv`)
- **Counts by layer**: deterministic 3112 / live-feed 8 (of 3120 total; the long tail is bandit B101 `assert` noise across `tests/`, out of scope)

### Floor deconfirmation analysis (why the floor is BLOCKED and the final verdict is lower)

1. **All 76 gitleaks CRITICALs are verified false positives.** Every hit is the `generic-api-key` rule matching 64-character hex strings inside `experiments/5b-persistent-mps-reranker-worker-2026-08-20/output*/preflight/*.json`. Inspection of the flagged values shows they are the JSON fields `/evidence/model_file_sha256/*` (64-hex model-file checksums) and `/evidence/model_revision` (40-hex git SHA) — integrity evidence, not credentials. These files are untracked experiment output (not committed); the gitleaks **history** scan of all commits returned **0 findings**. No secret exists in code or history.
2. **The 4 chromadb CVEs are real feed entries against pre-existing repo state.** `uv.lock` (chromadb 1.5.9) is untouched by this diff — the CVEs pre-date and are unaffected by this change. Neither osv-scanner nor trivy publishes a fixed version (`Fixed Version:` empty), and the advisory IDs (CVE-2026-45829/-45830/-45831/-45833, GHSA-f4j7-r4q5-qw2c, GHSA-36p7-vc44-83pf, GHSA-2wm9-hf6c-p5cr, GHSA-xph7-9rjv-w5fr) return no public advisory page (search returned zero results), so advisory detail is **UNCERTAIN**. Per the skill's failure-mode table, an unpatchable dependency CVE is documented with mitigation and flagged NEEDS FIXES, not BLOCKED.
3. Lowering below the floor requires user approval — see "Residual risks → action-required". If you do not ratify, treat the verdict as BLOCKED on the repo-wide floor alone; nothing in the changed code itself blocks.

## Findings

| ID | Severity | Location | Description | Evidence | Recommended fix | Source |
|----|----------|----------|-------------|----------|-----------------|--------|
| F1 | HIGH (feed-reported CRITICAL 9.3/9.4, 8.8) | `uv.lock` (pre-existing, not in diff) | chromadb 1.5.9 flagged for CVE-2026-45829 (CRITICAL 9.3), CVE-2026-45833 (CRITICAL 9.4), CVE-2026-45830 (HIGH 8.8), CVE-2026-45831 (HIGH 8.8). No fixed version published; advisory detail unverifiable publicly. Reachability from this repo: the only default construction site is `chromadb.PersistentClient(path=...)` (`src/rag_mcp/core/vectordb/chroma.py:113,465`) — embedded, in-process, no network listener. `CloudClient` (`chroma.py:403`) is an explicit opt-in (ADR-024) and would be the exposed surface if used. The watcher daemon adds no new chromadb usage (no chromadb import under `src/rag_mcp/daemon/`); it reuses the vectordb layer. | osv.sarif + trivy.sarif rule details; grep of `src/rag_mcp/core/vectordb/` | Track upstream; upgrade chromadb the day a fixed version lands; keep `CloudClient` opt-in-only. Re-run `osv-scanner` in CI (already wired). | [scanner: osv-scanner CVE-2026-45829…45833, trivy] + [LLM-judged] reachability |
| F2 | LOW | `src/rag_mcp/transports/cli/_launchagent.py:144-145` | `--command-path` override used verbatim (spec D4 says "use that path exactly") with no absolute/existence check. A relative override is persisted into the plist; launchd execs with cwd `/`, so the watcher would silently never start. Robustness/availability footgun, not injection — threat model is self-inflicted (invoking user → same user's agent). | `resolve_command_path`: `if override: return str(Path(override).expanduser())` | Warn (or error) when the override is not absolute or does not exist at install time. One guard clause, keeps spec wording. | [LLM-judged] |
| F3 | LOW | `src/rag_mcp/transports/cli/_launchagent.py:262-275` | `run_launchctl` invokes `"launchctl"` resolved via `PATH` (bandit B607). An attacker controlling the invoking user's PATH can substitute a fake `launchctl`. Same-uid self-inflicted only — an attacker with PATH control already has user-level exec. | `return ["launchctl", "bootstrap", ...]` + bandit SARIF B607 | Pin `/bin/launchctl` (stable on macOS) or keep the noqa with the rationale. Cosmetic hardening. | [scanner: bandit B607] |
| F4 | LOW | `src/rag_mcp/transports/cli/_launchagent.py:194` | `plan.collection` is an unvalidated argv element after `--collection`. A collection name beginning with `-` (e.g. `--collection --verbose`) is misparsed by the spawned `watch` CLI at login → watcher fails to start. No shell, no cross-boundary flow — self-inflicted availability only. | `build_program_arguments` argv list; no collection validation in `install_login_watcher.py` | Reject collection names starting with `-` at install time (the `watch` CLI contract already implies plain names). | [LLM-judged] |
| F5 | INFO | `src/rag_mcp/transports/cli/install_login_watcher.py:213` | `debounce < MIN_DEBOUNCE_SECONDS` is `False` for `NaN`, so `--debounce nan` bypasses the minimum check and persists the literal `nan` into the plist argv. Downstream watcher clamps/validates again; availability nit only. | `if debounce < MIN_DEBOUNCE_SECONDS:` with typer-parsed float | Add `math.isnan(debounce)` to the guard. | [LLM-judged] |
| F6 | INFO | `src/rag_mcp/transports/cli/_launchagent.py:250-256` | Overwrite TOCTOU: `target.exists()` check at :250 races with `os.replace` at :256 — a plist created in the window is replaced even without `overwrite=True`. Exploitation requires a process already writing to the user's own `~/Library/LaunchAgents` (per-user dir under a 0700 home on modern macOS); such a process already has user-level login persistence, so no privilege boundary is crossed. | exists-check → mkstemp → os.replace sequence | None required. (If desired, `os.link`/`O_EXCL` dance could close it, at complexity cost with no boundary gained.) | [LLM-judged] |
| F7 | LOW | `tests/unit/test_launchagent.py:83-86`, `tests/test_install_login_watcher.py:341-368` | Test-honesty: existing assertions are honest (see PASS list), but two behaviours are unpinned: (a) `slugify_label_part`'s leading/trailing-dash strip — a custom label `-x` would pass the current `isalnum() or "-"` assertion; (b) design.md D8 claims "`--force` does not bypass profile-resolution failure", but no test passes `--force` to the fail-closed resolver-error path (only the ingest-execution-error path is force-tested). | assertion code cited | Add one slugify test (`slugify_label_part("-x") == "x"`) and one resolver-error-with-`--force` test asserting exit ≠ 0 and no plist. | [LLM-judged] |

No CRITICAL or HIGH findings exist in the changed code itself.

## Checklist PASS evidence

1. **launchd/plist injection — PASS.** Plist is built exclusively via `plistlib.dumps` over a fixed 7-key dict (`_launchagent.py:218-230`); `ProgramArguments` is always the argv list from `build_program_arguments` (`:183-204`); no string-concatenated plist XML anywhere in either file (grep: zero hits).
2. **launchctl argv injection — PASS.** All three builders return list argv (`:263-275`); `uid` is `os.getuid()` (int) from `install_login_watcher.py:309`; custom labels pass through `slugify_label_part` (`:52-61`) which lowercases, strips every non-`[a-z0-9]` run, and `.strip("-")`s both ends — a label can never begin with `-`, contain spaces, or smuggle a second argv element; the plist path is absolute (starts `/`). `find_existing_plist`'s glob pattern uses the same slugified value, so it is glob-metacharacter-safe (`:207-217`).
3. **Path traversal / symlink — PASS with threat-model note.** `validate_watch_path` (`:85-115`) requires existence, `resolve()`s symlinks, and rejects non-directories; the resolved absolute path is what gets persisted (D4). `--command-path` can point anywhere — but the installer runs as the invoking user and the LaunchAgent runs as that same user in the per-user GUI domain: no privilege boundary is crossed anywhere, so a hostile value is strictly self-inflicted (an attacker with installer access already has equivalent user exec). Residual: F2 (relative override footgun).
4. **Atomic write race — PASS.** `write_plist` (`:247-260`) uses `tempfile.mkstemp` in the target directory (0600) + `os.replace`; the rename preserves the temp inode's 0600 mode on the final plist, and launchd reads the plist as the same user, so 0600 is correct and additionally hides paths from other local users. The plist contains only label, argv (paths/collection/debounce), log paths, two booleans — no `EnvironmentVariables`, no credentials. The overwrite TOCTOU (F6) is same-uid only; `/tmp`-style multi-user races do not apply to a per-user directory.
5. **Secrets/PII — PASS.** No env vars, tokens, or credentials written to the plist (key set is fixed at `_launchagent.py:222-229`); CLI output (stderr, per gotcha #5) prints the same user-supplied values only; gitleaks working-tree CRITICALs deconfirmed as sha256 checksums/git SHAs (see floor analysis); committed history 0 findings.
6. **subprocess usage — PASS.** Single subprocess site in the new code: `_launchagent.py:289` — `subprocess.run(list(cmd), capture_output=True, text=True, check=False)`, shell=False (default), `# noqa: S603` justified (fixed argv). `check=False` is correct: callers handle returncode — bootstrap at `install_login_watcher.py:312-315`, kickstart at `:319-322`; the bootout at `:310` is deliberately fire-and-forget with an in-code comment. No `shell=` anywhere in the diff (grep).
7. **Error-message disclosure — PASS.** `_print_launchctl_failure` (`install_login_watcher.py:57-64`) echoes only the operation name, exit code, and launchctl's own stdout/stderr for the user's own operation; `InstallerError` messages echo the user-supplied path text; no stack traces reach output (`"Traceback" not in result.output` asserted by tests).
8. **Test honesty — PASS.** Overwrite protection: `tests/unit/test_launchagent.py:243-256` asserts `ExistingPlistError` **and** old bytes preserved — removing the `:250` guard flips it red. CLI overwrite gate: `test_existing_plist_protected_without_force` asserts non-zero exit **and** untouched bytes. Fail-closed: `test_profile_resolution_failure_is_fail_closed` asserts exit ≠ 0, `mock_ingest.assert_not_called()`, `mock_launchctl.assert_not_called()`, and empty LaunchAgents. No-write-on-failure: `test_ingest_error_stops_install_without_force` and `test_dry_run_prints_plan_and_writes_nothing` (dir absent + launchctl uncalled). Bootstrap argv shape is pinned as a list (`c.args[0][:2] == ["launchctl", "bootstrap"]`), which a shell-string rewrite would break. Gap noted as F7.
9. **MCP transport regression — PASS.** `git status`/`git diff --stat` on `src/rag_mcp/transports/mcp.py`: empty — untouched. The only transport change is the import-registration line in `transports/cli/__init__.py:218-229` and help wording in `watch.py`.
10. **ruff bandit S-rules — PASS.** `uv run ruff check --output-format=concise src/rag_mcp/transports/cli/_launchagent.py src/rag_mcp/transports/cli/install_login_watcher.py` → `All checks passed!` (exit 0). No S-rule findings.

## OWASP Top 10 coverage (change scope)

| ID | Category | Status |
|----|----------|--------|
| A01 | Broken Access Control | N/A — single-user CLI, no auth surface; per-user agent runs as invoking user |
| A02 | Cryptographic Failures | N/A — no cryptography in diff |
| A03 | Injection | ✓ — plist via `plistlib`, argv lists only, no shell (items 1, 2, 6) |
| A04 | Insecure Design | ✓ — fail-closed ingest (D8), overwrite gates, atomic writes, dry-run |
| A05 | Security Misconfiguration | ✓ — 0600 plist, KeepAlive off by default, macOS gate |
| A06 | Vulnerable Components | ✗ — chromadb CVEs (F1, pre-existing, unpatchable today) |
| A07 | Identification & Auth Failures | N/A — no auth in scope |
| A08 | Software & Data Integrity | ✓ — atomic mkstemp+rename; sha256-based deterministic labels |
| A09 | Logging & Monitoring | ✓ — logs to `~/Library/Logs/rag-mcp/`, no PII/secrets (item 5) |
| A10 | SSRF | N/A — no URL handling in diff |

Cloudflare Workers: N/A — macOS CLI project.

## Verdict justification

The changed code is sound against every injection, path, race, and disclosure vector the checklist probes: plist rendering is `plistlib`-only, every `launchctl` invocation is a fixed argv list built from sanitised labels and an int uid, writes are atomic at 0600 with honest overwrite-protection tests, and the fail-closed behaviour the design mandates is genuinely pinned by tests that flip if the guards are removed. Nothing above LOW was found in the diff itself. The verdict is NEEDS FIXES for two reasons: Category 6 is mandatory and surfaces four chromadb CVEs (two CRITICAL by feed severity) in the exact subsystem this change exercises — pre-existing, unpatchable today, and unreachable on the default embedded `PersistentClient` path, but action-required regardless (F1); and the floor-lowering from BLOCKED needs your explicit ratification because the floor's BLOCKED rests on 76 gitleaks hits I have deconfirmed as sha256/git-SHA false positives (evidence in the floor analysis). If you ratify the deconfirmation and accept F1's tracking plan, the change-scoped verdict is APPROVED with the LOW hardening items (F2–F4, F7) as follow-ups.

## Residual risks

**Accepted** (self-inflicted threat model; no privilege boundary crossed):
- `--command-path` and watch path point at arbitrary locations — per-user agent, invoking user = agent user (design D1/D4).
- `launchctl` resolved via `PATH` at install time (F3) — attacker controlling PATH already equals the user.
- Overwrite TOCTOU in `write_plist` (F6) — same-uid prerequisite.
- Plist persists absolute filesystem paths — user-owned 0600 file; disclosed nowhere else.
- Best-effort bootout before bootstrap (returncode ignored) — intentional, documented in code.

**Action-required**:
1. F1 — chromadb CVEs: monitor for a fixed version; upgrade immediately when published; keep `CloudClient` opt-in-only. (Pre-existing; not blockable by this PR.)
2. Ratify (or reject) the floor-lowering rationale so the verdict can be recorded as final. — **Ratified above (build owner).**
3. ~~F7 — add the two missing test pins~~ — **Done** (slugify leading-dash pin; `--force` vs profile-resolution failure pin).
4. ~~Optional hardening: F2 (absolute/existing `--command-path` guard), F4 (reject `-`-prefixed collection names)~~ — **Done, with regression tests.** F5 (NaN debounce) and F3 (pin `/bin/launchctl`) remain accepted residuals.

**Post-audit remediation (CodeRabbit round, 2026-08-27)** — three functional fixes applied on top of the audited tree, each with regression tests: existing-watcher detection now verifies the persisted watch path instead of trusting the slug glob (no more `docs`/`docs-backup` false positives); a different label on the same folder now refuses with exact removal instructions and only removes the old watcher on explicit confirmation or `--force` (bootout + plist delete — consent-gated, never silent); `~user` watch paths are rejected instead of mis-expanded. No new subprocess sites, no new writes outside the plist/log paths, plist rendering unchanged.
