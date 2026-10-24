# Tasks

Implement after `add-chat-reasoning-and-usage` and `install-integrations-from-the-app`, in the same worktree.

## 1. Writable keys and value checks

- [x] 1.1 Add `READ_ONLY_KEYS` with the D1 reasons and compute `ALLOWED_KEYS` from the Settings model. Verify: a test that `retrieval.top_k`, `answer.enabled` and `metadata.extraction_mode` are allowed, and `embed_model`, `embedding.tokenizer_model`, `lancedb_uri`, `openrouter_api_key`, `ingestion.ingest_extensions` are not; it fails before the change.
- [x] 1.2 Check bounds and choices on write. Verify: tests for `answer.max_rounds` 12 refused with the range rule, `metadata.extraction_mode` `magic` refused with the choices, and `null` removing a key; the file is unchanged after each refusal.
- [x] 1.3 Update the `settings-file` section of `docs/guides/configuration.md`. Verify: the docs drift check passes.

## 2. Row description and save route

- [x] 2.1 Add `editable`, `read_only_reason`, `kind`, `choices`, `min`, `max` and `nullable` to each row. Verify: tests for a bool, a bounded int, a `Literal` choice, an optional float, an identity row and an `env`-locked row.
- [x] 2.2 Add `PUT /v1/settings/configuration` (`manage` session only), all or none under one revision. Verify: route tests for two keys saved, one bad value stopping the save, 409 revision, 409 environment lock and 403 bearer.
- [x] 2.3 Update the OpenAPI 3.1 contract and its contract test.

## 3. Configuration section

- [x] 3.1 Load `omrs-design`. Render each row as a `SettingRow` mini card in its block card, with the control for its kind. Verify: Vitest cases from the `workspace-settings` scenarios fail first, then pass.
- [x] 3.2 Add the switch and choice controls to `SettingRow`. Verify: Vitest cases for bool, choice and range refusal before any request.
- [x] 3.3 Show the index-identity note on chunking rows and Clear on optional rows. Verify: Vitest cases.

## 4. Source wording

- [x] 4.1 Change `sourceText("config-file")` to "Saved in settings (omrs.jsonc)" and update every test and guide that names the old words. Verify: `grep -rn "from omrs.jsonc" web/src docs/guides` returns nothing; all web tests pass.

## 5. Records and checks

- [x] 5.1 Write an ADR amending ADR-087's rule on the keys the page may write (load `s-adr`); add it to the index.
- [x] 5.2 Run `./scripts/local_ci.sh`, `npm run lint`, `npm run typecheck`, `npm test` in `web/`, and `openspec validate edit-settings-from-configuration-page --strict`. Verify: all pass.
  - Done (2026-10-24): local CI passed: 7,893 passed and 152 skipped in the main suite, tripwire 5 passed (re-pinned to 7,900 executed, `_WEB_EXTRA_CASES` 1,408), 152 web test files with 1,887 tests, lint and typecheck clean, 85 specs valid, OpenAPI contract valid. `openspec validate edit-settings-from-configuration-page --strict` passed.
- [x] 5.3 Browser check on a scratch server at 1280 px and 390 px, following the Orca preview steps: edit `retrieval.top_k`, see "Restart to apply", restart, see it in force; confirm `embed_model` has no Edit.
  - Done (2026-10-24): scratch server on port 8791 with a scratch config (no key) in the Orca browser. At 1280 px, `retrieval.top_k` Edit opened with 10; Save 20 wrote `"top_k": 20` into the `retrieval` block, opened the restart dialog, and the row showed 10, "Saved in settings (omrs.jsonc)", "Saved for the next launch: 20" and "Restart to apply". After a restart the row showed 20 with no badge. `embed_model` showed its reason and no Edit. `answer.max_rounds` 12 showed "Enter 1 to 8." and sent no request. Save 30 then Clear on `metadata.ollama_classify_timeout_override` removed the key; the row showed "Not set" and "default". At 390 px the page width was 390 with no element past the edge. The server log held no error and no 500.
