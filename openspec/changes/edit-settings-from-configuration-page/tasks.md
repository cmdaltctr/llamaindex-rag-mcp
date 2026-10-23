# Tasks

Implement after `add-chat-reasoning-and-usage` and `install-integrations-from-the-app`, in the same worktree.

## 1. Writable keys and value checks

- [ ] 1.1 Add `READ_ONLY_KEYS` with the D1 reasons and compute `ALLOWED_KEYS` from the Settings model. Verify: a test that `retrieval.top_k`, `answer.enabled` and `metadata.extraction_mode` are allowed, and `embed_model`, `embedding.tokenizer_model`, `lancedb_uri`, `openrouter_api_key`, `ingestion.ingest_extensions` are not; it fails before the change.
- [ ] 1.2 Check bounds and choices on write. Verify: tests for `answer.max_rounds` 12 refused with the range rule, `metadata.extraction_mode` `magic` refused with the choices, and `null` removing a key; the file is unchanged after each refusal.
- [ ] 1.3 Update the `settings-file` section of `docs/guides/configuration.md`. Verify: the docs drift check passes.

## 2. Row description and save route

- [ ] 2.1 Add `editable`, `read_only_reason`, `kind`, `choices`, `min`, `max` and `nullable` to each row. Verify: tests for a bool, a bounded int, a `Literal` choice, an optional float, an identity row and an `env`-locked row.
- [ ] 2.2 Add `PUT /v1/settings/configuration` (`manage` session only), all or none under one revision. Verify: route tests for two keys saved, one bad value stopping the save, 409 revision, 409 environment lock and 403 bearer.
- [ ] 2.3 Update the OpenAPI 3.1 contract and its contract test.

## 3. Configuration section

- [ ] 3.1 Load `omrs-design`. Render each row as a `SettingRow` mini card in its block card, with the control for its kind. Verify: Vitest cases from the `workspace-settings` scenarios fail first, then pass.
- [ ] 3.2 Add the switch and choice controls to `SettingRow`. Verify: Vitest cases for bool, choice and range refusal before any request.
- [ ] 3.3 Show the index-identity note on chunking rows and Clear on optional rows. Verify: Vitest cases.

## 4. Source wording

- [ ] 4.1 Change `sourceText("config-file")` to "Saved in settings (omrs.jsonc)" and update every test and guide that names the old words. Verify: `grep -rn "from omrs.jsonc" web/src docs/guides` returns nothing; all web tests pass.

## 5. Records and checks

- [ ] 5.1 Write an ADR amending ADR-087's rule on the keys the page may write (load `s-adr`); add it to the index.
- [ ] 5.2 Run `./scripts/local_ci.sh`, `npm run lint`, `npm run typecheck`, `npm test` in `web/`, and `openspec validate edit-settings-from-configuration-page --strict`. Verify: all pass.
- [ ] 5.3 Browser check on a scratch server at 1280 px and 390 px, following the Orca preview steps: edit `retrieval.top_k`, see "Restart to apply", restart, see it in force; confirm `embed_model` has no Edit.
