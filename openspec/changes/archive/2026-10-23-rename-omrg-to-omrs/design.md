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
- The owner's install moves to the new names once, by hand, after the merge.
- The old name cannot return unnoticed (guard test).
- Each step leaves the test suite green.

**Non-Goals:**

- No compatibility alias, shim or silent fallback to the old names.
- No rewrite of ADRs, TDRs, archived changes, run experiment records or `CHANGELOG.md`.
- No migration command or startup check: the owner is the only user (D2).
- No behaviour change beyond names.
- No change to the OMMS project.

## Decisions

### D1. Full rename, one change

The package, distribution, command, env prefix, folders, MCP name and wire prefixes all move together. A partial rename (display name only) would leave `omrs` branding on an `omrg` command and keep the tool-prefix collision with OMMS that motivated the change.

### D2. Clean cut, no migration code

The old names stop working. There is no alias, no dual-read, no startup check and no migration command. The owner is the only user, so migration code would be dead weight the day after it runs. The owner's install moves once, by hand, with the steps in the Migration Plan. This matches ADR-060.

The first draft had a startup check and an `omrs migrate` command. They were built, tested against a copy of the owner's data, then removed on the owner's call (2026-10-22): more code to keep than the one-off move is worth.

### D3. Stored keys move to `omrs`

The LanceDB key `omrg_dataset_epoch` becomes `omrs_dataset_epoch` and the workspace layout key `omrg_task` becomes `omrs_task`.

- A LanceDB table written before the rename has no epoch under the new key. The store already handles that case (an unmarked table from an older release): `get_data_version` returns `None`, BM25 falls back to the process-local counter, and the next write gives the table an epoch. No re-ingest is needed.
- `workspace.db` pipelines carry `omrg_task` in `layout_json`, and `runs.inputs_json` holds absolute `~/.omrg/...` paths. The manual move rewrites both with two SQL updates (Migration Plan step 3).

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

The pass never touches: `docs/adr/`, `docs/tdr/` (or `docs/04_tdr/`), `openspec/changes/archive/`, `CHANGELOG.md`, `uv.lock` (regenerated), `.git`, `graphify-out/`, `__pycache__`, `.venv`, and run experiment records. A run experiment is one with a `report.md`; every numbered `experiments/` folder qualifies, and so does the `experiment-42-clef-flash-confirmation` change. Their scripts keep the names they ran with. The exception is the 43 experiment scripts that the test suite or shared tooling (`experiments/_lib`, `experiments/example`) imports: those must import `omrs` to run. The only unrun experiment is `experiment-35-full-document-rag-benchmark`, which is renamed.

### D7. Outside-repo items

- `~/.claude.json` key `omrg`: the MCP tool prefix follows this client key, not the server's own name string. Replaced with an `omrs` entry on 2026-10-22 (task 8.1).
- Skills `omrg-design` and `s-preserve-omrg`: renamed to `omrs-design` and `s-preserve-omrs` on 2026-10-22 (task 8.3).
- `DATA/omrg/` became `DATA/omrs/` on 2026-10-22 (a same-disk rename of 90 GB). Six gitignored symlinks in four worktrees were repointed. `DATA_LOCATIONS.md`, the global agent instructions and the preserve skill name the new path. Copy receipts, recovery files and run experiment records inside the folder keep the old path as history.
- NiftyPM `niftypm/omrg.json` is gitignored. The owner renames it and its project title.
- GitHub repository: it is `llamaindex-rag-mcp`, which already differs from `omrg`. The owner decides separately.
- Sibling worktrees (`-v3`, `-v4`, the experiment worktree) each hold their own `src/omrg`. They are not touched.

### D8. Auth prefixes and browser storage

The session cookie and the `omrg_bs_`, `omrg_ss_`, `omrg_bt_` prefixes move to `omrs`. Sessions re-issue at the next login. A stored bearer token with the old prefix fails and the user creates a new one, and the release note says so. The five browser storage keys move with no read-old-then-write-new shim, so unsent canvas drafts reset once. This follows D2. The owner confirmed this: no shim.

### D9. Live specs: in-place token rewrite for most, deltas for the identity contract

Two live requirements define the identity contract and carry real behaviour change: `public-library-api` ("Package identity") and `settings-file` ("The user config folder location"). They get delta files, and the new `project-identity` capability holds the rest of the contract.

The other 120 or so blocks (about 180 KB of text) change only the name token. Writing MODIFIED deltas for them would copy the full blocks into the change, add a second source of truth, and risk a collision with the active v4 changes at archive time. They are rewritten in place during apply, as the v3 rename did, and `openspec validate --all --strict` checks the result. The 12 other baseline headings that contain the name are renamed in place at the same time. The recon found no active change that modifies one of them, so no archive collision is possible. A task re-checks this just before apply, in case a change is added.

Four active changes (`authority-aware-retrieval`, `mantiq-reasoning-gates`, `experiment-35-full-document-rag-benchmark`, `tripwire-retirement-and-provider-symmetry`) get the same token pass, so their file paths (`src/omrg/core/...`) match the new tree. `experiment-42-clef-flash-confirmation` is a run experiment and keeps its text (D6).

### D10. Order of work

1. Add the guard test first, with the old names still in place, and confirm it fails.
2. Move the package (`git mv`), run the import rewrites, fix the build config. Run the fast suite.
3. Move runtime identifiers and the web workspace.
4. Rewrite docs, specs and active changes.
5. Run the full gates and a browser check.
6. Write ADR-092 and the owner hand-off note.

The change merges as one pull request into `v4`. It lands before `authority-aware-retrieval` and `mantiq-reasoning-gates` are applied, so those changes are built on the new tree. If they are applied first, their branches rebase through the same ast-grep rule.

### D11. Release

The commit type is `feat!:`. python-semantic-release makes a major version. `omrs` is free on PyPI (404 on 2026-10-22). `omrg` was never published, so no stub is needed. Re-check `omrs` just before the first release, because a name can be taken in the meantime.

## Risks / Trade-offs

- **Blind replace damage.** A plain `omrg` replace would hit ADR file names, run experiment records and the pinned path that Experiment 29 reads from an old commit. Mitigation: skip list (D6), AST-scoped rules (D4), and the guard test with named exemptions.
- **Stale ignore entries.** `unmatched_ignore_imports_alerting = "error"` fails the build when an import-linter ignore string is missed. This is a useful signal. Run `uv run lint-imports` after the move.
- **Tripwire counts.** `tests/test_clean_base_tripwire.py` pins executed and deselected counts. The rename must not change them. Compare before and after.
- **Stale environment.** `.venv`, `__pycache__` and the editable install still point to `omrg`. Run `uv sync --frozen --extra web` in the new worktree (not `--all-extras`, which adds torch and breaks 5 tests).
- **Manual move touches real secrets and a login item.** Mitigation: the backup from task 1.6, each step checked before the next, no secret value printed.
- **BM25 cache after the move.** Old tables have no epoch under the new key until their next write, so the BM25 cache uses the process-local counter until then (D3).
- **Client breakage.** MCP clients lose their tools until the client key changes (D7). The release note lists the step first.
- **Keychain copy.** Reading a keychain entry can prompt the user. Expect one macOS prompt during the manual move.
- **Name length.** "System" makes the long form longer. Check README badges, table columns and CLI help wraps.
- **Similar names.** OMRS and OMMS differ by one letter, which is the pair the owner wants. Typos in docs are still likely. The guard test catches `omrg` only. A later check could look for `omrs` and `omms` mix-ups.

## Migration Plan

The owner's machine, once, after the merge. Stop the app first (`omrg web stop`), then:

1. Install the new package (`uv tool install` from the merged checkout) and remove the old `omrg` tool.
2. Move the folders: `mv ~/.omrg ~/.omrs`, `mv ~/.config/omrg ~/.config/omrs`, `mv ~/.config/omrs/omrg.jsonc ~/.config/omrs/omrs.jsonc`. Rewrite `/omrg/secrets/` to `/omrs/secrets/` in `omrs.jsonc`.
3. Update `workspace.db`: replace `"omrg_task"` with `"omrs_task"` in `pipelines.layout_json`, and `/.omrg/` with `/.omrs/` in `runs.inputs_json`.
4. Copy the keychain entries from service `omrg` to `omrs` (one macOS prompt).
5. Replace the login item: unload `com.omrg.web`, delete its plist, run `omrs web install`.
6. Rename `OMRG_*` variables in the shell profile, if any. Rename the MCP client key to `omrs` and restart the clients. Create new bearer tokens if any were in use.

Rollback: reverse the two folder moves with the previous package version installed. The backup from task 1.6 holds the original folders.

For the repository: the branch is `feat/rename-omrg-to-omrs`, forked from `v4`, in a sibling worktree. A revert of the merge commit restores the old tree, because no history is rewritten.

## Decisions confirmed by the owner

1. **Compatibility.** Clean cut with no migration code (D2). No fallback to the old names, anywhere.
2. **PyPI.** `omrs` and `omrg` both return 404 on PyPI (checked 2026-10-22), so `omrs` is free and `omrg` was never published. No stub is needed.
3. **Outside-repo renames.** The owner renames the MCP client key, the skills and the NiftyPM file to `omrs` (D7).
4. **History.** ADRs, TDRs, archived changes, run experiment records and `CHANGELOG.md` stay unchanged. Only unrun experiments are renamed (D6).
5. **Auth and wire names.** Cookie, token prefixes and `x-omrg-*` keys all move to `omrs` (D8). Old bearer tokens stop working.
6. **Browser drafts.** No shim (D8).
7. **OCR workers.** The `omrg_ocr_*` packages are renamed in this change (task 3.1).
8. **Stored keys.** `omrg_dataset_epoch` and `omrg_task` move to `omrs` (D3).
9. **DATA folder.** `DATA/omrg/` becomes `DATA/omrs/` (D7).
