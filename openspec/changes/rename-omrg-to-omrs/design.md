## Context

The project name is OMRG in about 3,000 code locations, 34 live specs, 31 live documents and every runtime identifier. A recon pass (three read-only agents, ast-grep and graphify) found the following.

- **Imports:** 2,505 `from omrg...` statements in 467 files, 20 `import omrg`, 12 `import omrg.X`. About 940 more dotted paths sit in strings (`patch("omrg.x")`, `import_module`).
- **Settings surface:** 13 `OMRG_*` variables, `omrg.jsonc`, `~/.omrg` (8.9 MB on the owner's machine), `~/.config/omrg` with `secrets/`.
- **Runtime identifiers:** MCP server name, keychain service, launchd labels, log folder, cookie and token prefixes, `x-omrg-*` OpenAPI keys, five browser storage keys.
- **Docs and specs:** 124 requirement blocks in 34 live specs mention the name. 21 requirement headings in 11 specs contain it. No spec folder name contains it. No active change modifies a heading that contains it.
- **Outside the repo:** the MCP client key in `~/.claude.json`, two skills, `DATA/omrg/` (90 GB) and its checksum registry, a gitignored NiftyPM file, the GitHub repository name.

Precedent: ADR-060 renamed `rag_mcp` to `omrg` in v3 with no shim and no alias, and rewrote the live specs in bulk. This change follows that pattern and adds a migration command, because this time the owner has live settings, secrets and a login item under the old names.

## Goals / Non-Goals

**Goals:**

- Every live file, identifier and document uses OMRS.
- Existing stored data (LanceDB collections) opens unchanged.
- An existing install moves to the new names with one command, with a dry run first.
- The old name cannot return unnoticed (guard test).
- Each step leaves the test suite green.

**Non-Goals:**

- No compatibility alias, shim or silent fallback to the old names.
- No rewrite of ADRs, TDRs, archived changes, experiment reports or `CHANGELOG.md`.
- No rename of `DATA/omrg/` (see D7).
- No behaviour change beyond names.
- No change to the OMMS project.

## Decisions

### D1. Full rename, one change

The package, distribution, command, env prefix, folders, MCP name and wire prefixes all move together. A partial rename (display name only) would leave `omrs` branding on an `omrg` command and keep the tool-prefix collision with OMMS that motivated the change.

### D2. Clean cut with a migration command, no dual-read

The old names stop working. A startup check finds the old install and stops, naming the replacement. `omrs migrate` moves the data. This matches ADR-060, the owner's preference for clean renames with documented migration, and the retirement tripwire in `config/legacy.py` (gotcha 11). Dual-read was rejected: a silent fallback hides a half-migrated install, doubles the settings paths to test, and the fallback would need its own retirement date.

The tripwire is the only mechanism that can detect flat `OMRG_*` names, because pydantic-settings discards unknown flat names without an error. The `OMRG_*` entries therefore stay in the tripwire for as long as an upgrade path exists (the rule in the `legacy.py` docstring).

### D2a. The keychain is not a startup sign

The first draft listed an old keychain entry as a startup sign. That fails in two ways. `omrs migrate` copies the entry and leaves the old one in place, so a correct migration would still be refused on every start. And a keychain read can show a macOS permission prompt on every run, because the new `omrs` executable differs from the one that stored the key. The startup check therefore uses only environment and file checks. `omrs migrate` reads the keychain once, after a warning, for the providers that the old workspace records as saved. Confirmed by the owner on 2026-10-22.

### D3. Keep `omrg_dataset_epoch` and `omrg_task`

The key lives inside existing LanceDB tables and feeds the BM25 cache validity token (gotcha 14). A rename would make every existing dataset compare unequal. It is defined once as a constant with a comment, and exempted by name in the guard test.

The same holds for `omrg_task` (`TASK_LAYOUT_KEY` in `core/workspace/records.py`). It is stored in the `layout_json` column of `workspace.db` pipelines and marks a workspace job pipeline. A rename would stop existing job pipelines from being recognised. Found while writing the migrate tests, against a copy of the owner's real `workspace.db`. The same recon found absolute `~/.omrg/workspace/uploads/...` paths in `runs.inputs_json`, so `omrs migrate` rewrites that column (spec step 7).

### D4. ast-grep for code, a scripted pass for the rest

- Python imports: an ast-grep rule on `import_from_statement` and `import_statement` with `regex: '^omrg(\.|$)'` on the module. A dry run found 2,505 statements in 467 files, including multi-line imports. The apply step runs the rule with `--rewrite`, then reviews the diff.
- Dotted-path strings: a second rule on `string_content` with `^omrg(\.|$)`, restricted to the first argument of `patch`, `monkeypatch.setattr`, `import_module` and `mock.patch.object`. A bare `"omrg"` string is the MCP name or the keychain service and needs a human decision, so the rule does not rewrite it.
- Non-Python files (`pyproject.toml`, YAML, JSON, Markdown, `.env.example`, web sources): a Python script over `git ls-files` with an explicit allow list and an explicit skip list. ast-grep has no TOML or Markdown grammar.
- The rule and the script are not committed. The commit holds only the diff.

### D5. Case variants

| Old | New |
| --- | --- |
| `omrg` | `omrs` |
| `OMRG` | `OMRS` |
| `Omrg` | `Omrs` |
| `Opinionated Modular RAG` | `Opinionated Modular RAG System` |

Where the old text is a bare initialism in a sentence, the script substitutes `OMRS`. A reviewer checks the prose hits, because "Opinionated Modular RAG System" is longer and can break line wraps in tables.

### D6. Skip list for the scripted pass

The pass never touches: `docs/adr/`, `docs/tdr/` (or `docs/04_tdr/`), `openspec/changes/archive/`, `experiments/**/report.md` and saved outputs, `CHANGELOG.md`, `uv.lock` (regenerated), `.git`, `graphify-out/`, `__pycache__`, `.venv`. It also skips the `omrg_dataset_epoch` string and the migration module with its tests, which must name the old identity.

### D7. Outside-repo items stay with the owner

- `~/.claude.json` key `omrg`: the MCP tool prefix follows this client key, not the server's own name string. The owner renames the key to `omrs` and updates any prompt, skill or allow-list that names `mcp__omrg__*`.
- Skills `omrg-design` and `s-preserve-omrg`: the owner renames the folders and the frontmatter `name`.
- `DATA/omrg/`: stays. It holds 90 GB, a checksum registry and copy receipts, and `s-preserve-omrg` and gotcha 15 hard-code the path. The registry gets a note that the project is now OMRS and the folder name is historical. Renaming the folder is a later, separate decision.
- NiftyPM `niftypm/omrg.json` is gitignored. The owner renames it and its project title.
- GitHub repository: it is `llamaindex-rag-mcp`, which already differs from `omrg`. The owner decides separately.
- Sibling worktrees (`-v3`, `-v4`, the experiment worktree) each hold their own `src/omrg`. They are not touched.

### D8. Auth prefixes and browser storage

The session cookie and the `omrg_bs_`, `omrg_ss_`, `omrg_bt_` prefixes move to `omrs`. Sessions re-issue at the next login. A stored bearer token with the old prefix fails and the user creates a new one, and the release note says so. The five browser storage keys move with no read-old-then-write-new shim, so unsent canvas drafts reset once. This follows D2. The owner confirmed this: no shim.

### D9. Live specs: in-place token rewrite for most, deltas for the identity contract

Two live requirements define the identity contract and carry real behaviour change: `public-library-api` ("Package identity") and `settings-file` ("The user config folder location"). They get delta files, and the new `project-identity` and `legacy-install-migration` capabilities hold the rest of the contract.

The other 120 or so blocks (about 180 KB of text) change only the name token. Writing MODIFIED deltas for them would copy the full blocks into the change, add a second source of truth, and risk a collision with the active v4 changes at archive time. They are rewritten in place during apply, as the v3 rename did, and `openspec validate --all --strict` checks the result. The 12 other baseline headings that contain the name are renamed in place at the same time. The recon found no active change that modifies one of them, so no archive collision is possible. A task re-checks this just before apply, in case a change is added.

The five active changes (`authority-aware-retrieval`, `mantiq-reasoning-gates`, `experiment-35-full-document-rag-benchmark`, `experiment-42-clef-flash-confirmation`, `tripwire-retirement-and-provider-symmetry`) get the same token pass, so their file paths (`src/omrg/core/...`) match the new tree.

### D10. Order of work

1. Add the guard test and the migration code first, with the old names still in place. Both are testable before the move.
2. Move the package (`git mv`), run the import rewrites, fix the build config. Run the fast suite.
3. Move runtime identifiers and the web workspace.
4. Rewrite docs, specs and active changes.
5. Run the full gates, the migration against a copy of the owner's real folders, and a browser check.
6. Write ADR-092 and the owner hand-off note.

The change merges as one pull request into `v4`. It lands before `authority-aware-retrieval` and `mantiq-reasoning-gates` are applied, so those changes are built on the new tree. If they are applied first, their branches rebase through the same ast-grep rule.

### D11. Release

The commit type is `feat!:`. python-semantic-release makes a major version. `omrs` is free on PyPI (404 on 2026-10-22). `omrg` was never published, so no stub is needed. Re-check `omrs` just before the first release, because a name can be taken in the meantime.

## Risks / Trade-offs

- **Blind replace damage.** A plain `omrg` replace would hit `omrg_dataset_epoch`, `com.omrg.*`, ADR file names and the migration code. Mitigation: skip list (D6), AST-scoped rules (D4), and the guard test with named exemptions.
- **Stale ignore entries.** `unmatched_ignore_imports_alerting = "error"` fails the build when an import-linter ignore string is missed. This is a useful signal. Run `uv run lint-imports` after the move.
- **Tripwire counts.** `tests/test_clean_base_tripwire.py` pins executed and deselected counts. The rename must not change them. Compare before and after.
- **Stale environment.** `.venv`, `__pycache__` and the editable install still point to `omrg`. Run `uv sync --frozen --extra web` in the new worktree (not `--all-extras`, which adds torch and breaks 5 tests).
- **Migration touches real secrets and a login item.** Mitigation: `--dry-run` first, refuse on conflict, run against a copy of the owner's folders in a temp `HOME` before the owner runs it for real, and never print secret values.
- **Client breakage.** MCP clients lose their tools until the client key changes (D7). The release note lists the step first.
- **Keychain copy.** Reading a keychain entry can prompt the user. The migrate command warns before it starts that macOS may ask for permission.
- **Name length.** "System" makes the long form longer. Check README badges, table columns and CLI help wraps.
- **Similar names.** OMRS and OMMS differ by one letter, which is the pair the owner wants. Typos in docs are still likely. The guard test catches `omrg` only. A later check could look for `omrs` and `omms` mix-ups.

## Migration Plan

For users of an existing install:

1. Upgrade the package.
2. Run `omrs migrate --dry-run` and read the plan.
3. Run `omrs migrate`.
4. Set `OMRS_*` for each `OMRG_*` variable the report lists, in the shell profile.
5. Rename the MCP client key to `omrs` and restart the client.
6. Create new bearer tokens if any were in use.

Rollback: the migrate command renames rather than copies folders, so rollback is `mv ~/.omrs ~/.omrg` and `mv ~/.config/omrs ~/.config/omrg` with the previous package version. The keychain copy leaves the old entry in place until the user deletes it. The login item is the only step with no automatic rollback; reinstall the old one with the old version.

For the repository: the branch is `feat/rename-omrg-to-omrs`, forked from `v4`, in a sibling worktree. A revert of the merge commit restores the old tree, because no history is rewritten.

## Decisions confirmed by the owner

1. **Compatibility.** Clean cut with `omrs migrate` (D2). No fallback to the old names, anywhere.
2. **PyPI.** `omrs` and `omrg` both return 404 on PyPI (checked 2026-10-22), so `omrs` is free and `omrg` was never published. No stub is needed.
3. **Outside-repo renames.** The owner renames the MCP client key, the skills and the NiftyPM file to `omrs` (D7).
4. **History.** ADRs, TDRs, archived changes, experiment reports and `CHANGELOG.md` stay unchanged.
5. **Auth and wire names.** Cookie, token prefixes and `x-omrg-*` keys all move to `omrs` (D8). Old bearer tokens stop working.
6. **Browser drafts.** No shim (D8).
7. **OCR workers.** The `omrg_ocr_*` packages are renamed in this change (task 3.1).

## Still open

- **GitHub repository name and `DATA/omrg/`.** Both stay as they are (D7). The owner has not asked to change them. Raise a separate change if that changes.
