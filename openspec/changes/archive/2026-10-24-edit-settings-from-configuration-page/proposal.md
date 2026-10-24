# Proposal

## Why

The Configuration section lists all 119 settings but is read-only. To change, for example, `retrieval.top_k` or `answer.timeout`, a user must open `omrs.jsonc` in an editor. Many users find a JSONC file harder than a form. The safe file writer (ADR-087) already exists, but it accepts only the 27 keys that the Providers, Chat and Document reading cards edit.

## What Changes

- The Configuration section becomes editable. Each setting is a mini card with its value, its source and Edit. Edit opens a control that matches the type: an on/off switch, a number field with its range, a choice list, or a text field. Save writes `omrs.jsonc` through the existing writer, with the revision check.
- The page may write 72 more keys: the retrieval, reranker, hybrid, chunking, ingestion, metadata and answer settings, and the remaining OCR and server options. Each value is checked against the Settings model before the write.
- 20 keys stay read-only, with the reason on the row: the embedding identity (`embed_provider`, `embed_model`, `embedding.*`, the embedding backend, address and model keys), the storage location (`vector_store`, `lancedb_uri`, `chroma_*`, `collection_name`), `ocr_workers_dir` and the key fields. Changing these would break existing collections or would put a key in the file.
- An optional number can be cleared. Clear removes the key from the file, so the default applies again.
- A chunking key shows the same index-identity note as Document reading: the next ingest after a restart can read existing files again.
- A save of a restart-only key shows "Restart to apply" and offers the existing restart dialog. A live key applies at once.
- A key set in the environment or `.env` stays read-only and names the variable.
- The source "from omrs.jsonc" becomes "Saved in settings (omrs.jsonc)" on every settings row, because a page save and a hand edit both land in the same file.
- `ingestion.ingest_extensions` (a list) and `metadata.keyword_rules` (a rules text) stay read-only in this change, with "Edit this in omrs.jsonc".

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `settings-file`: the keys the page may write grow from the card keys to every non-identity, non-secret, scalar setting; each write is checked against the setting's rule.
- `workspace-settings`: the Configuration section becomes editable, and the source wording changes to "Saved in settings (omrs.jsonc)".

## Impact

- `src/omrs/config/settings_file_write.py`: `ALLOWED_KEYS` grows; a new `READ_ONLY_KEYS` list with a reason for each group.
- `src/omrs/transports/settings_view.py` and `transports/api/routes/configuration.py`: each row gains `editable`, `read_only_reason`, `kind`, `choices`, `min`, `max` and `nullable`. New `PUT /v1/settings/configuration` (browser session, `manage` scope) that takes `revision` and `changes`.
- Web: `web/src/settings/ConfigurationSection.tsx` (rows become `SettingRow` mini cards), `connectionWords.ts` (source wording), a new typed input for booleans and choices.
- OpenAPI 3.1 contract, `docs/guides/web-workspace.md`, `docs/guides/configuration.md`.
- Records: a new ADR that amends ADR-087 rule on which keys the page may write.
- No new dependency. No change to how settings are read at startup.
