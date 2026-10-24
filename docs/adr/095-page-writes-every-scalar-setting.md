# ADR-095: The Settings Page Writes Every Scalar Setting Except Identity, Storage and Keys

- **Date:** 2026-10-24
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-087](087-settings-live-in-omrg-jsonc.md) (decision 5 and the document-reading addendum are amended), [ADR-086](086-web-power-menu.md) (the restart dialog), [ADR-037](037-architecture-v2-conformance.md) (settings are frozen at launch)
- **Change:** `openspec/changes/edit-settings-from-configuration-page/` (design D1 to D5)

## Context

ADR-087 made `omrs.jsonc` the single store of settings. Decision 5 lets the
page write only the keys it edits. In October 2026 that was 29 keys: the
provider fields, the three file-only keys and the nine document-reading keys.
The Configuration section listed all 121 settings, but read-only. To change
`retrieval.top_k` or `answer.timeout`, a user had to open the file in an
editor.

The document-reading addendum of ADR-087 rejected a generic write route,
because each setting has its own restart and identity effects. Two facts
changed that view:

- The restart effect is already handled for every setting. A restart-only
  key that differs from its launch value shows "Restart to apply", and the
  section offers the restart dialog.
- The identity effect is confined to a short list: the embedding model and
  its backend, and the storage location. A change there breaks existing
  collections. Chunking also feeds the index identity, but a change only
  makes the next ingest read existing files again, as document reading does.

## Decision

1. **The writable set is every scalar setting minus a read-only list.**
   `ALLOWED_KEYS` in `config/settings_file_write.py` is computed from the
   `Settings` model. It holds every path whose value is a boolean, a number,
   a text or one of them with `None`, plus the file-only keys. It excludes
   `READ_ONLY_KEYS`, the secret fields and the internal fields. A new scalar
   setting is therefore editable with no list change.
2. **Each read-only key carries its reason.** The list and the reasons:

   | Keys | Reason |
   |---|---|
   | `embed_provider`, `embed_model`, `local_backend`, `cloud_backend`, `llamacpp_embed_url`, `llamacpp_embed_model`, `openrouter_embed_model`, `embedding.*` | The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest. |
   | `vector_store`, `lancedb_uri`, `chroma_persist_dir`, `chroma_mode`, `collection_name` | Existing collections stay where they are. Change it in omrs.jsonc and restart. |
   | `ocr_workers_dir` | The worker folder is set when the OCR workers are installed. |
   | key fields | Keys are set on the provider cards as references. |
   | `ingestion.ingest_extensions`, `metadata.keyword_rules` | Edit this in omrs.jsonc. |

3. **Key references stay with the provider cards.** The writer still accepts
   a reference (`keychain://`, `env://`, `file://`) for the provider key
   fields, because the cards save keys that way (ADR-087 decision 6). The
   Configuration route refuses every key field.
4. **The server describes each row.** `GET /v1/settings/configuration` adds
   `editable`, `read_only_reason`, `kind`, `choices`, `min`, `max` and
   `nullable` to each row. The page keeps no key lists of its own. A key set
   in the environment or `.env` is read-only and names its variable, as
   ADR-087 decision 3 requires.
5. **One save route, all or none.** `PUT /v1/settings/configuration` takes a
   `revision` and a `changes` object. It checks every change against the
   setting's rule (type, bounds, accepted choices) first, then writes once.
   A stale revision gets 409. A bearer credential gets 403. `null` removes a
   key, so the default applies. Live keys apply at once through the provider
   state; restart-only keys wait for a restart (ADR-037 keeps settings
   frozen).
6. **One source word for the file.** A page save and a hand edit land in the
   same file, so every settings row shows "Saved in settings (omrs.jsonc)".
   A separate "web" source was rejected (see below).

## Consequences

### Positive

- A user can change 96 of the 121 settings without an editor (count on 2026-10-24).
- The read-only list is short, and each entry explains itself on the page.
- A new scalar setting is editable with no list edit and no web change.

### Negative

- The rules enforce only the model's bounds. A legal but poor value, such as
  `answer.timeout` 1, is accepted. The row shows the source, and Clear
  restores the default.
- The Configuration section is long. The rows stay grouped by block.

### Neutral

- The dedicated document-reading route stays. It adds checks the generic
  route does not run, such as "the PDF reader is installed".
- Startup reading does not change. Values the page wrote are ordinary
  hand-written keys, so a rollback leaves the file valid.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **A hard-coded allow-list per block** | It is the drift that left 92 settings read-only. Every new setting would need a list edit. |
| **Edit the embedding identity and storage on the page** | Those changes break existing collections. They need a re-ingest or a move, which is a separate flow. |
| **A "web" source next to `config-file`** | ADR-087 keeps one store, read by the web server, the CLI and the stdio server. A page save and a hand edit are the same file change. |
| **A history comment in the file for each page save** | Deferred. The file stays plain, and no request asked for an audit trail. |
| **Keep the Configuration section read-only** | Users must edit JSONC by hand for most settings, while a safe writer already exists. |

## References

- `src/omrs/config/settings_file_write.py` (`READ_ONLY_KEYS`, `ALLOWED_KEYS`)
- `src/omrs/transports/settings_view.py` (row description)
- `src/omrs/transports/api/routes/configuration.py` (`GET` and `PUT`)
- `web/src/settings/ConfigurationSection.tsx`, `web/src/settings/SettingRow.tsx`
- `docs/guides/configuration.md`, `docs/guides/web-workspace.md`
