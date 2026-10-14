# Screen guidance

This file turns the `redesign-web-workspace` spec deltas into layout and styling decisions. The deltas stay the contract. Read the delta for the view you touch, then apply the design rules here. If they disagree, the delta wins. Report the disagreement.

## Shell

Navigation has seven items in this order: Home, Chat, Knowledge Base, Studio, Experiments, Integrations, Settings. Home is the landing view. Each row has a Lucide icon before its label and `aria-current="page"` on the active row.

| Element | Rule |
| --- | --- |
| Top bar | Muted surface, 1px bottom border, elevation shadow. Shows the brand, an engine status pill (collection count, or "offline"), the theme `Select` (System, Light, Dark), and an icon-only button beside it that shows sun or moon for the theme in effect and switches Light and Dark in one click. Its accessible name names the target theme. |
| Inspector | The global toggle and empty panel are gone. Detail regions open inside Chat, Studio, and Experiments on selection. |
| Skip link, main focus | Keep the existing skip link. Focus moves to the view `h1` after navigation. |
| Routes | Typed hash routes from `lib/routes.ts` (design D9): `#/home`, `#/knowledge-base[/<collection>]`, `#/chat[/<collection>]`, `#/studio[/<pipeline-id>]`, `#/experiments`, `#/experiments/runs/<run-id>`, `#/integrations`, `#/settings`. Segments are URI-encoded. An unknown hash opens Home and is rewritten to `#/home`; earlier routes are not redirected. |
| Narrow screens | Below `md`, the navigation becomes one row of the seven area icons with short labels under the top bar (owner decision; no menu button). Targets are at least 44px. No horizontal page scroll. |

Read the presentation spec and `web/src/App.tsx` before you change route names.

## Home

A grid of project cards (`gap-3`, `items-start`). Each card is flat with a 1px border and shows the collection name (subsection title), a profile badge (hue hash), and document and chunk counts as meta text. The whole card opens the project.

Empty state: icon, one sentence naming the cause, one action that starts an ingest into a named collection.

A card opens `#/knowledge-base/<collection>`: source table with orphan status, upload panel, folder ingest panel, profile information, deletion, and search. Orphan status is a badge with text. The route is the active project; `lastCollection` in `omrg-preferences` is only the default for `#/knowledge-base` and `#/chat`.

## Chat

Layout: a centred transcript column at `min(100%, 48rem)`, the composer docked at the bottom of that column, and a right-hand knowledge base panel listing collections with counts and a selected state (`chip` or `--selection`, never the accent).

- Messages are plain rows with role labels. No bubble framework and no chat library.
- The view states that each question answers on its own. Put this notice near the composer in meta text.
- A "New chat" action clears the transcript. It keeps the selected knowledge base.
- Each assistant turn shows the answer, the verification status as text with its badge, citations as chips under the answer, and evidence in a collapsible section. Opening a chip or an evidence row shows the chunk in the shared chunk viewer.
- A failed turn shows one friendly line and a Retry action. The raw message goes to the console only.
- Switching the knowledge base mid-conversation keeps earlier turns. The next turn queries the new collection.
- The composer sends on a clear action. Disable it while a turn is pending, and keep the pending state visible as text.

Reuse `views/shared/ChunkViewer.tsx` (or its moved location). Delete `views/search/` and `views/ask/` only after chat tests cover their behaviour (task 3.5).

## Knowledge Base

Four sections, switched with `chip` buttons and shown one at a time: Sources, Search, Add, Profile (owner decision).

Manages the active project's sources: file upload (managed upload plus an ingest job), folder ingest from approved roots, and the source table.

- Show job status as text with a status badge.
- Refuse an oversized file in the client with a friendly message before any upload. Never send it.
- With no approved root, state that no folder is approved and name the `--root` server flag in a `code` element.
- Pick the active project with the same project switch used elsewhere. Do not add a second selector pattern.

## Studio

Gallery first: cards for engine templates (ingestion, search, answer), the `documents` and `codebase` profile presets, and saved pipelines. Each card has a title, a description, and one action.

The canvas sub-page (`#/studio/<pipeline-id>`):

- The flow surface fills the main area.
- The operation palette is the right-hand column.
- Selecting a node opens its settings in a detail region on the same page.
- Revision, validation, and run behaviour are unchanged.

React Flow nodes and edges read the semantic tokens. Node kind badges use the hue hash. Run state on a node pairs the status colour with text. Respect `prefers-reduced-motion` for edge animation (`runs/useReducedMotion.ts` exists). The canvas needs a keyboard route to add, select, and delete nodes. Do not regress what `CanvasView` tests cover.

## Experiments

Folder groups, each listing its sub-experiments. An empty folder still shows with an empty indication. Provide forms to create a main folder and a sub-experiment with declared factors. A rejected path shows a validation message next to the field.

Keep the notebook panels intact: tool registration, trust notice, one-time credentials, and editor launch with a stop action. The one-time credential is shown once, so keep the copy action and the warning visible. Do not log or screenshot secrets.

A Runs section holds the run list, status filter, refresh, and run detail with evidence. Two sections keep this long view manageable. Use the existing filters.

With no experiment root approved, state it and name the `--experiment-root` server flag.

## Integrations

One card or table row per integration: chroma, hybrid, pdf-pypdfium2, pdf-inspector, community-leiden, azure, llamacpp, openrouter, torch, web, and magika. Each shows name, one-line purpose, an availability badge with text (available or not installed), and the install command in a monospace block with a copy button.

State that availability reflects the running launch, and that installing needs the command run outside the app and the server restarted. The page never installs anything. A failed load shows the friendly line and Retry. Give the copy action visible confirmation and an announcement for assistive technology (a polite live region).

## Settings

Six sections switched with `chip` buttons, one at a time (redesign design D13): Appearance, Connections, MCP, Server log, Runtime, Workspace. Controls that moved to other views are removed with their tests.

- Appearance: the same theme `Select` as the top bar.
- Connections: one card per provider (Ollama, llama.cpp, OpenRouter) with URLs and model names in `code`, role badges (embeddings, answers, metadata, verification), "Key set" or "No key" as text, and a Test button that shows reachable or the reason as a status badge. Read-only: state that values come from `.env` and need a restart. Never render a key.
- MCP: the stdio client configuration (`uv run --directory <config_dir> omrg`) in a `code` block with a copy button, and the HTTP on/off switch, which shows only the state the server returns.
- Server log: a monospace, terminal-style panel on the muted surface (`bg-muted`), one record per line (time, level badge, logger, message), level filter chips, Pause, Copy, and auto-scroll only while scrolled to the bottom. Mark it `role="log"` so screen readers announce new lines politely.
- Runtime and Workspace: capabilities and the workspace path. Keep paths in `code` elements with `overflow-wrap: anywhere`.
