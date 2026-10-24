# Design

## Context

- `config/settings_file_write.write_settings()` already writes chosen keys into `omrs.jsonc`, keeps every other byte, checks the revision, replaces the file atomically and never writes a key. Its `ALLOWED_KEYS` is the provider fields, the file-only keys and the document-reading keys (27 of the 119 rows the Configuration section shows).
- `config/settings_file.check_setting(path, value)` already checks a value against the Settings model field (type and bounds) and returns a plain-English rule.
- `transports/settings_view.describe_settings()` builds each row with its value, source, `applies` (`live` or `restart`) and `restart_pending`. The Configuration section renders the rows read-only in tables and already hosts the restart dialog.
- A count on 2026-10-23 of the 92 rows the page cannot write: 11 boolean, 30 number, 22 text or fixed choice, 7 optional number, 2 special (`ingestion.ingest_extensions`, a tuple; `metadata.keyword_rules`, rules text), 20 identity, storage, backend or key rows.
- Document reading already edits keys that are part of the index identity and shows a note. That is the pattern for chunking.

## Goals / Non-Goals

**Goals:**

- Every scalar, non-identity, non-secret setting can be edited on the page and lands in `omrs.jsonc`.
- One rule source: the server says whether a row is editable, why not, and how to edit it. The web does not keep its own key lists.

**Non-Goals:**

- Editing the embedding identity or the storage location. Those need a re-ingest or a move, which is a separate flow.
- Editing lists and rules text (`ingestion.ingest_extensions`, `metadata.keyword_rules`). They keep "Edit this in omrs.jsonc".
- A history of who changed a value. The file stays the single store; a page save and a hand edit look the same.
- A separate "web" source. ADR-087 keeps one store, read by the web server, the CLI and the stdio server alike.

## Decisions

### D1. The writable set is "every scalar setting minus a read-only list"

`settings_file_write` gains `READ_ONLY_KEYS: Mapping[str, str]`, a key or `prefix.` mapped to its reason. `ALLOWED_KEYS` becomes every Settings path that is scalar (bool, int, float, str, `Literal`, or one of them or `None`) and not in `READ_ONLY_KEYS`, `SECRET_FIELDS` or `INTERNAL_FIELDS`. It is computed once from the model, so a new scalar setting is editable with no list change.

- Why: an allow-list of 99 names would drift; the read-only list is short and each entry carries its reason.
- Rejected: hard-coded allow-list per block. It is the drift that left 92 keys read-only today.

Reasons shown on the page:

| Keys | Reason |
|---|---|
| `embed_provider`, `embed_model`, `embedding.*`, embedding backend, address and model keys | The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest. |
| `vector_store`, `lancedb_uri`, `chroma_*`, `collection_name` | Existing collections stay where they are. Change it in omrs.jsonc and restart. |
| `ocr_workers_dir` | The worker folder is set when the OCR workers are installed. |
| key fields | Keys are set on the provider cards as references. |
| `ingestion.ingest_extensions`, `metadata.keyword_rules` | Edit this in omrs.jsonc. |

### D2. Each row describes its own control

`describe_settings` adds to each row: `editable`, `read_only_reason`, `kind` (`bool`, `int`, `float`, `text`, `choice`), `choices` (from `Literal` arguments or the `rules.ACCEPTED` table), `min`/`max` (from the field's `ge`/`le`/`gt`/`lt`), and `nullable`. An `env` or `dotenv` source makes `editable` false with the existing lock reason.

### D3. One save route for many keys

`PUT /v1/settings/configuration` takes `{revision, changes}`. It checks every change with `check_setting` and the D1 rules first, then calls `write_settings` once, so the save is all or none under one revision. It returns the GET body, so the page refreshes from one response. Live keys apply through the existing provider apply path; restart keys raise `restart_pending`, which the section already shows.

### D4. Rows reuse `SettingRow`

The Configuration tables become groups of `SettingRow` mini cards inside each block card. `SettingRow` gains a `kind` prop: `bool` renders a switch, `choice` a select, numbers a number input with `min`/`max` and the existing whole-number check. A read-only row renders the value, the source and the reason.

### D5. Source wording

`connectionWords.sourceText("config-file")` returns "Saved in settings (omrs.jsonc)". All settings rows use it, so Providers, Chat, Document reading, Workspace and Configuration change together.

## Risks / Trade-offs

- [A user sets a value that makes answers fail, for example `answer.timeout` 1] → The rules enforce the model's bounds only. The row shows the default, and Clear restores it.
- [A chunking change makes the next ingest re-read every file] → The row states it, as Document reading does, and the change applies only after a restart.
- [Long section: 99 editable rows] → Rows stay grouped by block in cards; the block cards are collapsed groups only if a later review asks for it.

## Migration Plan

Additive. Existing files read the same. Rollback: revert the change; values the page wrote stay valid hand-written keys.
