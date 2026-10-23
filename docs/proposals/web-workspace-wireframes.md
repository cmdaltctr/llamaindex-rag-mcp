# OMRS web workspace: what to expect

Draft, 14 October 2026. Local only (git-ignored). It shows what `redesign-web-workspace` will build, screen by screen, in ASCII. The specs in `openspec/changes/redesign-web-workspace/` are the contract; the visual rules are in `web/DESIGN.md`.

How to read the drawings:

| Mark | Means |
|---|---|
| `[ Run pipeline ]` | Primary button: orange tint, darker orange text |
| `( Cancel )` | Secondary, outline or ghost button |
| `< documents >` | Chip. Filled grey when selected |
| `{ok}` `{failed}` | Badge: tinted fill, coloured border, word inside |
| `[____________]` | Text field |
| `[ v papers   ]` | Select |
| `|>`  `+`  `x` | Lucide icons (shown as rough symbols) |
| `▌` | Active navigation row (grey selection fill) |
| `...` | More rows of the same kind |

Widths are drawn for a 1280px window unless marked "390px".

---

## 1. The shell (every screen)

```
+-------------------------------------------------------------------------------------+
| OMRS  Local workspace                     ( 3 collections )   [ v System ] [ ☾ ]   |  <- top bar, muted grey,
+--------------------+----------------------------------------------------------------+     thin shadow underneath
| ▌⌂ Home            |                                                                |
|  ◯ Chat            |   Page title                                                   |
|  ▤ Knowledge Base  |   One line saying what this area is for.                       |
|  ⟜ Studio          |                                                                |
|  ⚗ Experiments     |   ... area content ...                                         |
|  ⏚ Integrations    |                                                                |
|  ⚙ Settings        |                                                                |
|                    |                                                                |
|  13rem, muted grey |  canvas (warm off-white), main area                           |
+--------------------+----------------------------------------------------------------+
```

- The pill in the top bar shows the engine state: `( 3 collections )` when the server answers, `( offline )` with a warning badge when it does not.
- Theme: `[ v System ]` picks System, Light or Dark. `[ ☾ ]` is an icon button that shows the theme on screen now (sun in light, moon in dark) and flips between Light and Dark in one click. Its accessible name says what it does, for example "Switch to dark theme".
- No Inspector button any more. Detail panels open inside a view when you select something.
- The address bar always tells you where you are: `#/home`, `#/chat/papers`, `#/studio/p_42`. Reload or share it and you land in the same place. A wrong address opens Home.

At 390px the navigation becomes a top row of icons with labels underneath, each at least 44px tall:

```
+----------------------------------+
| OMRS          ( offline ) [ v ]  |
+----------------------------------+
| ⌂    ◯    ▤    ⟜    ⚗    ⏚    ⚙  |
|Home Chat  KB  Stud Exp  Int  Set |
+----------------------------------+
| Page title                       |
| ...                              |
```

Decided: icon row, no menu button. Every area stays one tap away.

---

## 2. Home `#/home`

Projects are collections. Each card opens that project's Knowledge Base.

```
+--------------------+----------------------------------------------------------------+
| ▌⌂ Home            |  Home                                                          |
|  ◯ Chat            |  Your projects. Each project is one collection.                |
|  ...               |                                                                |
|                    |  +------------------------+  +------------------------+        |
|                    |  | papers                 |  | omrs-code              |        |
|                    |  | {documents}            |  | {codebase}             |        |
|                    |  | 42 documents · 3,118   |  | 311 files · 9,870      |        |
|                    |  | chunks                 |  | chunks                 |        |
|                    |  +------------------------+  +------------------------+        |
|                    |  +------------------------+                                    |
|                    |  | fiqh-notes             |                                    |
|                    |  | {documents}            |                                    |
|                    |  | 7 documents · 512      |                                    |
|                    |  +------------------------+                                    |
+--------------------+----------------------------------------------------------------+
```

- Profile badge colour comes from a hash of the label, so `documents` is always the same colour everywhere.
- Counts refresh by themselves after an upload or deletion finishes anywhere in the app.

Empty (no collections yet):

```
|                    |              ▤                                                 |
|                    |   No projects yet. A project starts with its first upload.     |
|                    |              [ + Upload files ]                                |
```

---

## 3. Knowledge Base `#/knowledge-base/papers`

Everything about one project: its sources, adding more, its profile, and searching it.

```
+--------------------+----------------------------------------------------------------+
|  ⌂ Home            |  papers  {documents}                       [ v papers      ]   |
|  ◯ Chat            |  42 documents · 3,118 chunks                                   |
| ▌▤ Knowledge Base  |                                                                |
|  ...               |  < Sources >  < Search >  < Add >  < Profile >                |
|                    |  --------------------------------------------------------------|
|                    |  Sources                                                       |
|                    |  +------------------------------------------------------------+|
|                    |  | Source                          Chunks  Status         ... ||
|                    |  |------------------------------------------------------------||
|                    |  | ~/papers/attention.pdf             118  {present}      x   ||
|                    |  | ~/papers/rag-survey.pdf            204  {missing here} x   ||
|                    |  | ~/papers/old-notes.md               12  {unknown}      x   ||
|                    |  +------------------------------------------------------------+|
|                    |  "missing here" means this machine cannot see the file now.   |
+--------------------+----------------------------------------------------------------+
```

Decided: the four sections are chips and one section shows at a time, at every width.

**Search** (kept from today's Search view, now inside the project):

```
|  Search                                                                            |
|  [ what is retrieval augmented generation?              ]   [ Search ]            |
|  Filter  [ v file_type ] [ = ] [ pdf      ]  ( + filter )                          |
|  Hybrid [ v Inherit ]   Rerank [ v Inherit ]                                       |
|                                                                                    |
|  1  rag-survey.pdf · p.3          0.812  dense_similarity_v1                       |
|     "Retrieval-augmented generation combines a retriever with..."   ( Open )       |
|  2  attention.pdf · p.11          0.774  dense_similarity_v1                       |
|     "...the model attends to every position..."                     ( Open )       |
```

- The score always shows its kind (`dense_similarity_v1`, `rrf_v1`, `reranker_sigmoid_v1`), so nobody reads it as a probability.
- "Open" shows the chunk in the chunk viewer panel on the right.

**Add** (upload or folder ingest):

```
|  Add sources                                                                       |
|  +-------------------------------+   +-------------------------------+             |
|  | ⇪ Upload files                |   | ▱ Ingest a folder             |             |
|  | Drop files here or [ Browse ] |   | [ v ~/papers                ] |             |
|  | Max 50 MB per file.           |   | [ Start ingest ]              |             |
|  +-------------------------------+   +-------------------------------+             |
|                                                                                    |
|  Jobs                                                                              |
|  ingest  attention-v2.pdf        {running}    started 18:42                        |
|  ingest  ~/papers                {completed}  12 files · 1m 04s                    |
```

- A file over the limit is refused before upload with a friendly line.
- No approved folder: "No folder is approved. Start the server with `--root <path>`."

**Delete** asks first, showing what will go:

```
          +--------------------------------------------------+
          | Delete rag-survey.pdf?                       x   |
          | This removes 204 chunks from papers.             |
          | The file on disk is not touched.                 |
          |                         ( Cancel ) [ Delete ]    |  <- Delete uses the red tint
          +--------------------------------------------------+
```

`#/knowledge-base` without a project opens the last project you used, or a project picker if there is none.

---

## 4. Chat `#/chat/papers`

Ask questions of one knowledge base. Each question is answered on its own (no memory of earlier turns, stated on screen).

```
+--------------------+-------------------------------------------+--------------------+
|  ⌂ Home            |  Chat                       ( + New chat )| Knowledge base     |
| ▌◯ Chat            |                                           |                    |
|  ▤ Knowledge Base  |  You                                      | ▌papers            |
|  ...               |  What does the survey say about           |   42 docs          |
|                    |  chunk size?                              |  omrs-code         |
|                    |                                           |   311 files        |
|                    |  OMRS   {ok}                              |  fiqh-notes        |
|                    |  The survey recommends 512 to 1,024       |   7 docs           |
|                    |  tokens for prose [1] and smaller...      |                    |
|                    |                                           |                    |
|                    |  [1 rag-survey.pdf p.3] [2 attention p.11]|                    |
|                    |  > Evidence (2)                           |                    |
|                    |                                           |                    |
|                    |  +-------------------------------------+  |                    |
|                    |  | Ask papers a question...            |  |                    |
|                    |  |                         [ Send  > ] |  |                    |
|                    |  +-------------------------------------+  |                    |
|                    |  Each question is answered on its own.    |                    |
+--------------------+-------------------------------------------+--------------------+
                      transcript column, max 48rem, centred        right panel
```

- Answer status badge: `{ok}` green, `{no_evidence}` / `{unverified_claims}` / `{generation_unverified}` amber, `{error}` red. The word is always visible.
- Citation chips open the chunk in the chunk viewer.
- "Evidence (2)" expands to the evidence rows.
- Picking another knowledge base mid-chat keeps earlier turns and changes the address to `#/chat/omrs-code`.
- While waiting: the Send button is disabled and the turn says "Answering...".

A failed turn:

```
|  OMRS   {error}                                     |
|  The local server is not reachable.   [ Retry ]   |
```

No parser text, no stack trace; the detail goes to the browser console.

---

## 5. Studio `#/studio` (gallery)

```
+--------------------+----------------------------------------------------------------+
|  ...               |  Studio                                     [ + New pipeline ] |
| ▌⟜ Studio          |  Build and run retrieval pipelines.                            |
|  ...               |                                                                |
|                    |  Start from a template                                         |
|                    |  +------------------+ +------------------+ +------------------+|
|                    |  | Ingestion        | | Search           | | Answer           ||
|                    |  | Read, chunk and  | | Retrieve and     | | Retrieve, then   ||
|                    |  | index files.     | | rank chunks.     | | write an answer. ||
|                    |  | [ Use template ] | | [ Use template ] | | [ Use template ] ||
|                    |  +------------------+ +------------------+ +------------------+|
|                    |                                                                |
|                    |  Profile presets                                               |
|                    |  +----------------------------+ +----------------------------+ |
|                    |  | Documents {documents}      | | Codebase {codebase}        | |
|                    |  | Search with reranking on.  | | Search, reranking off.     | |
|                    |  | [ Use preset ]             | | [ Use preset ]             | |
|                    |  +----------------------------+ +----------------------------+ |
|                    |                                                                |
|                    |  Your pipelines                                                |
|                    |  +----------------------------+                                |
|                    |  | hybrid-test   rev 4        |                                |
|                    |  | last run {succeeded}       |                                |
|                    |  | ( Open )                   |                                |
|                    |  +----------------------------+                                |
+--------------------+----------------------------------------------------------------+
```

Choosing any card creates the pipeline on the server straight away and opens its canvas. There is no "unsaved new pipeline" state.

## 6. Studio canvas `#/studio/p_42`

Node names below are real operation IDs from the engine catalogue.

```
+--------------------+---------------------------------------------+------------------------+
|  ...               | hybrid-test  rev 4  {draft changed}         | Operations             |
| ▌⟜ Studio          | ( Validate ) [ Save revision ] [ Run ]      | [ filter...          ] |
|  ...               |                                             | retrieve               |
|                    |  +----------------+   +----------------+    |  retrieve.prepare_query|
|                    |  | prepare_query  |-->| retrieve.dense |-+  |  retrieve.dense        |
|                    |  | {retrieve}     |   | {retrieve}     | |  |  retrieve.sparse       |
|                    |  +----------------+   +----------------+ |  | combine                |
|                    |          |            +----------------+ v  |  combine.rrf           |
|                    |          +----------->| retrieve.sparse|->+ | select                 |
|                    |                       +----------------+  | |  select.rerank         |
|                    |                         +---------------+ | |  select.threshold      |
|                    |                         | combine.rrf   |<+ | context                |
|                    |                         | {combine}     |   |  context.assemble      |
|                    |                         +---------------+   | verify                 |
|                    |   after a run each node shows {succeeded}   |  verify.claims ...     |
+--------------------+---------------------------------------------+------------------------+
```

Select a node and its settings open in a panel (floating, with the shadow) without leaving the page:

```
|                    | +-----------------------------------+                         |
|                    | | select.rerank                  x  |                         |
|                    | | Enabled   [ v Inherit (on) ]      |                         |
|                    | | Inherited from profile: documents |                         |
|                    | | ( Disable node )                  |                         |
|                    | +-----------------------------------+                         |
```

- Node kinds have hue-hash badges; run state on a node is a status badge with its word.
- Everything works by keyboard too (add, connect, select, delete), and animation stops if you prefer reduced motion.
- Unsaved edits survive a reload (kept per pipeline in the browser) until you save a revision.

---

## 7. Experiments `#/experiments`

Two sections: folders of experiments, and pipeline runs.

```
+--------------------+----------------------------------------------------------------+
|  ...               |  Experiments                                                   |
| ▌⚗ Experiments     |  < Folders >  < Runs >                                         |
|  ...               |  --------------------------------------------------------------|
|                    |  Folders under ~/experiments               [ + New folder ]    |
|                    |                                                                |
|                    |  ▾ reranker-calibration                [ + Sub-experiment ]    |
|                    |      run-1     factors: reranker, top_k      ( Open notebook ) |
|                    |      run-2     factors: reranker             ( Open notebook ) |
|                    |  ▾ hybrid-search                       [ + Sub-experiment ]    |
|                    |      No experiments yet.                                       |
|                    |                                                                |
|                    |  Notebook tool                                                 |
|                    |  marimo 0.9  {available}   ( Re-check )                         |
|                    |  ! Notebooks run Python with your user's file and network      |
|                    |    access. There is no extra sandbox.                          |
+--------------------+----------------------------------------------------------------+
```

- A folder name with `..` or outside the approved root is rejected next to the field.
- No experiment root: "No experiment folder is approved. Start the server with `--experiment-root <path>`."
- A one-time credential shows once, with a Copy button and a warning that it will not show again.

**Runs** section and run detail `#/experiments/runs/r_981`:

```
|  Runs     Status [ v All ]   ( ↻ Refresh )                                         |
|  r_981  hybrid-test rev 4   {succeeded}   18:51   1.8s                             |
|  r_980  hybrid-test rev 3   {failed}      18:40   0.4s                             |
|  r_979  search-template     {cancelled}   18:12   -                                |
|  ...                                                                               |
|                                                                                    |
|  +------------------------------------------------------------------------------+  |
|  | r_981  {succeeded}   hybrid-test rev 4                         ( Replay )    |  |
|  | retrieve.prepare_query {succeeded}  2 ms                                     |  |
|  | retrieve.dense  {succeeded}  140 ms   10 rows                                |  |
|  | retrieve.sparse {succeeded}   35 ms   10 rows                                |  |
|  | combine.rrf {succeeded}  1 ms   rank changes shown, rrf_v1                   |  |
|  | Evidence (10)  >                                                             |  |
|  +------------------------------------------------------------------------------+  |
```

---

## 8. Integrations `#/integrations`

Shows what is installed in this server and the command to add the rest. It never installs anything.

```
+--------------------+----------------------------------------------------------------+
|  ...               |  Integrations                                                  |
| ▌⏚ Integrations    |  Status reflects this launch. Run the command outside the app, |
|                    |  then restart the server.                                      |
|                    |                                                                |
|                    |  pdf-inspector   {available}      Better PDF text extraction   |
|                    |  chroma          {not installed}  Chroma vector store          |
|                    |    | uv sync --extra chroma                       [ Copy ] |   |
|                    |  community-leiden {not installed} Leiden communities        |  |
|                    |    | uv sync --extra community-leiden             [ Copy ] |   |
|                    |  magika          {available}      File type detection          |
|                    |  ...  (hybrid, pdf-pypdfium2, azure, llamacpp, openrouter,     |
|                    |        torch, web)                                             |
+--------------------+----------------------------------------------------------------+
```

After Copy, the button reads "Copied" and screen readers hear it.

---

## 9. Settings `#/settings`

Six sections. Chips switch them, one at a time, like the Knowledge Base.

```
|  Settings                                                                          |
|  [Appearance] [Connections] [MCP] [Server log] [Runtime] [Workspace]               |
```

**Appearance**

```
|  Theme  [ v System ]   (System / Light / Dark, same as the top bar)                |
```

**Connections** (read-only; values come from `.env` and `config/defaults.yaml`)

```
|  Values come from /path/to/project/.env. Change them there and restart omrs web.  |
|                                                                                    |
|  +-- llama.cpp ------------------------------------------------------------------+ |
|  |  Embeddings  http://localhost:8080/v1   model  qwen3-embedding                | |
|  |  Chat        http://localhost:8081/v1   model  (not set)                      | |
|  |  Used for  (embeddings)  (metadata)                                           | |
|  |                                               [ Test ]   ( reachable )        | |
|  +-------------------------------------------------------------------------------+ |
|  +-- Ollama ---------------------------------------------------------------------+ |
|  |  URL  http://localhost:11434            model  qwen3:4b                       | |
|  |  Used for  (answers)                                                          | |
|  |                                               [ Test ]   ( not reachable: refused ) |
|  +-------------------------------------------------------------------------------+ |
|  +-- OpenRouter -----------------------------------------------------------------+ |
|  |  URL  https://openrouter.ai/api/v1      Key set                               | |
|  |  Used for  (claim verification: off)                                          | |
|  |                                               [ Test ]                        | |
|  +-------------------------------------------------------------------------------+ |
```

- Roles follow the real rules: `EMBED_PROVIDER` with `LOCAL_BACKEND`/`CLOUD_BACKEND`, `ANSWER__PROVIDER`, `METADATA_LLM_PROVIDER`, `ANSWER__VERIFY_PROVIDER`. The values above show the shipped defaults; model names are examples.
- Claim verification is off by default (`ANSWER__VERIFY_CLAIMS=false`); the role shows "off" until it is turned on.
- The key is never shown. The page says "Key set" or "No key".
- Test sends one request only when you press it. Reasons: refused, timeout, unauthorised, HTTP error, not configured.
- Editing comes later in its own change (`add-runtime-settings`).

**MCP**

```
|  Use OMRS from an MCP client                                                       |
|                                                                                    |
|  Local (stdio). The client starts OMRS itself, in the folder that holds .env.     |
|  +------------------------------------------------------------------------------+  |
|  | { "mcpServers": { "omrs": { "command": "uv", "args": ["run", "--directory",  |  |
|  |   "/path/to/project", "omrs"] } } }                                           |  |
|  +------------------------------------------------------------------------------+  |
|                                                                       [ Copy ]     |
|                                                                                    |
|  Over HTTP from this server            [  on |o ]                                  |
|  Shares this server's engine. Works while omrs web is running.                     |
|  +------------------------------------------------------------------------------+  |
|  | { "mcpServers": { "omrs": { "type": "http",                                  |  |
|  |     "url": "http://127.0.0.1:8765/mcp",                                      |  |
|  |     "headers": { "Authorization": "Bearer <token>" } } } }                   |  |
|  +------------------------------------------------------------------------------+  |
|                                                                       [ Copy ]     |
|                                                                                    |
|  Token   Created 14 Oct 2026          [ Rotate ]  [ Revoke ]                       |
|          Rotating breaks clients that use the old token.                           |
|                                                                                    |
|  Port    8765 (in use now)    Save a different port  [ 9100   ] [ Save ]           |
|          Applies the next time omrs web starts.                                    |
```

- The switch shows only what the server reports. It is off on a new workspace.
- A new token appears once, with Copy. After you leave the section, only its creation date shows.
- Only paths inside the folders approved with `--root` work over HTTP. Stdio has no such limit.
- If port 8765 is taken, `omrs web` stops and says: start with `--port <n>`, then save it here.
- All of this comes from `add-mcp-http-transport`.

**Server log**

```
|  [All] [Info] [Warning] [Error]                              [ Pause ] [ Copy ]    |
|  +------------------------------------------------------------------------------+  |
|  | 14:02:11  INFO     uvicorn.access   GET /v1/collections 200                  |  |
|  | 14:02:15  INFO     omrs.ingestion   Ingest job j_7 started: 12 files         |  |
|  | 14:02:19  WARNING  omrs.retrieval   Reranker disabled for profile codebase   |  |
|  | 14:02:31  ERROR    omrs.answer      Provider ollama refused the connection   |  |
|  | _                                                                            |  |
|  +------------------------------------------------------------------------------+  |
```

- Monospace, muted surface, newest line at the bottom. It follows new lines while you are at the bottom; scroll up and it stops following.
- Keys are removed before a line is kept. The server keeps the last 1,000 lines in memory only.
- Only this browser session can read it. Notebook credentials cannot.
- The lines above are examples of the shape, not real messages.

**Runtime**

```
|  Vector store  lancedb     PDF reader  pdf_inspector     Sparse backend  bm25        |
```

**Workspace**

```
|  ~/.omrs/workspace                                                                 |
```

---

## 10. States you will see everywhere

| Situation | What appears |
|---|---|
| Loading | The area keeps its layout; content shows "Loading..." in meta text. No spinners that shift the page. |
| Empty | An icon, one sentence, one action. |
| Server down | "The local server is not reachable." plus Retry. |
| Not allowed (session) | "This session cannot do that. Reopen the workspace from `omrs web`." |
| Not found (bad link) | "papers2 does not exist." plus a link back to the picker. |
| File too large | "attention.zip is over the 50 MB limit." |
| Wrong address | Home, with the address bar reset to `#/home`. |

## 11. Light and dark

Same layouts. Light uses a warm off-white page (`#fdfcfa`) and dark warm-grey text; dark uses a near-black warm page (`#120f0e`) and pale warm text. The orange accent brightens in dark (`#da7c47`). Badges stay readable in both (tested at 4.5:1 or better). The theme follows your system unless you pick Light or Dark in Settings or the top bar.

## 12. What is gone

- Separate Search, Ask, Runs and Canvas pages (merged as above).
- The Inspector button and empty side panel.
- Old addresses like `#/library` (they now open Home).
- All the hand-written CSS; every screen uses the shared components.

## Decisions

1. Narrow-screen navigation: icon row (decided 14 October 2026).
2. Knowledge Base sections: chips, one at a time (decided 14 October 2026).
3. Upload limit: 50 MB is the server default (`DEFAULT_MAX_UPLOAD_BYTES`); the page shows the running server's value.
