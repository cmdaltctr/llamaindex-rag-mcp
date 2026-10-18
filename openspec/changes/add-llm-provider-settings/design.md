# Design

## Context

See proposal.md (Why). This section lists only the facts that shape the approach. "Exists today" means code on `integration/core-web` at `739c7a1`. Paths use the current names; `organise-backend-folders` moves `routes_*.py` to `routes/*.py` before this change lands.

**Exists today**

- Settings resolve once. `compose.py` is the only production caller of `get_settings()` (repository rule). The source order is init, environment, `.env`, profile YAML, `defaults.yaml` (`src/omrg/config/__init__.py:415-420`). `config` already records whether `vector_store` came from an explicit source (`src/omrg/config/__init__.py:154,409`).
- The provider summary and test targets are pure functions over `Settings` (`src/omrg/compose_connections.py`). The provider list is a fixed tuple (`:28`), and the URL and model rows branch on provider names (`:89-111`). The test sends one model-list request with a 5-second limit, no redirects, and never reads a body (`src/omrg/transports/api/connection_probe.py:45-64`). OpenRouter is tested with `GET /models` (`compose_connections.py:162-164`).
- The LLM registry maps names to `module:build` strings and keeps registration order in its dict (`src/omrg/core/providers/llm/registry.py:14-26,74-76`). `available()` sorts names (`:68-70`). `llamacpp` and `openrouter` needed an optional extra for the OpenAI-like packages (`:32-35`); this change moves those packages into the base install. Provider modules import LlamaIndex only inside `build()` (for example `llm/ollama.py:36`), so importing a module is cheap.
- `build_engine` derives the server-default `EffectiveSettings` with `settings_to_effective(settings)` and gives the Engine factories that close over the startup `Settings`: answer model, judge and profile resolver (`src/omrg/compose_engine.py:122-157`).
- The Engine builds its answer model lazily and keeps it (`src/omrg/engine.py:112-116,459-463`). Each operation resolves per-collection settings through the profile resolver (`engine.py:471-482`). The judge factory runs at the start of every answer (`src/omrg/engine_answer.py:95-98`); graph runs cache judges per answer block (`src/omrg/compose_pipelines.py:392-406`). `engine.py` has 498 lines.
- Metadata extraction reads provider values from the resolved `EffectiveSettings` of each ingest (`src/omrg/core/metadata/ollama.py:249`, `llamacpp.py:85`, `openrouter.py:170`). The embedder is built once at start (`compose_engine.py:122`). Ollama embeddings and the Ollama LLM share `ollama_base_url` (`src/omrg/core/providers/common.py:25`).
- Workspace settings: a key/value table with a fixed key set (`src/omrg/integrations/workspace_sqlite/settings.py:15-19`). A schema migration copies the whole database to a `.bak` file (`schema.py:175-185`).
- The upload limit is the model for a run-time setting (ADR-078): a launch value wins and locks; the route writes the database first, then changes the running value (`src/omrg/transports/api/routes/mcp.py:154-172`).
- Log redaction gets the provider keys once at launch (`src/omrg/transports/cli/web.py:103,131,147`). `RedactingFilter` copies them into a tuple (`src/omrg/transports/api/security.py:438`). Validation errors never echo a value (`src/omrg/transports/api/errors.py:68-74`).
- Chat calls `answerCollection`. With no model, core returns status `error` with `NO_PROVIDER_MESSAGE` (`src/omrg/core/answer/results.py:18-23`, `pipeline.py:270-271`). The web client then shows "The answer could not be completed." (`web/src/chat/answerStatus.ts:50-54`).
- Settings sections are view state; the route stays `#/settings` (`web/src/settings/SettingsView.tsx:22-24`, `web/src/lib/routes.ts:37-38`).

**OMMS (sibling project), read for reuse**

- A pasted key goes to a plaintext file, `~/.config/omms/secrets/<name>.key`, mode 0600 in a 0700 directory, written atomically (`omms/src/services/memory-key-source.ts:23,97-137`, `global-config-writer.ts:194-201`). The config holds only an `env://` or `file://` reference.
- The page gets `{set, source, reference}` for a key and no characters of it (`omms/src/services/settings-snapshot.ts:141-161`).
- The embedding card tests typed, unsaved values (`omms/web/src/lib/components/settings/EmbeddingSection.tsx:178-197`). Model names are free text (`ExternalApiSection.tsx:176-185`). Changes apply live (`omms/src/services/web-server.ts:1191-1193`).
- OMMS has no provider registry: its provider list is repeated in four places.

## Goals / Non-Goals

**Goals:**

- One place in the GUI to set LLM provider addresses and keys, test them, and choose the Chat model.
- A saved value applies at once, with no restart and no restart banner.
- No key ever reaches the browser beyond its last four characters, a file, the database or a log.
- Nothing changes the vectors of an existing collection.
- A provider added to the registry gets a card with no web or route change.

**Non-Goals:**

- Embedding provider, model or address editing. `add-profile-embedding-model` owns per-profile embedding models.
- Metadata extraction mode and model choice, and the judge model. They keep their `.env` settings; only the connection values they use change.
- Giving the stdio MCP server, the CLI or experiment contexts the saved web values. They read the user config folder (D10), not the database or the keychain.
- Writing to the user config folder from the page, and several named OpenAI-compatible endpoints.
- Providers beyond OpenAI-compatible and Anthropic. Others come later as one file and one registry line each.

## Decisions

### D1. Secret storage: the OS keychain through `keyring`

A typed API key goes to the system keychain through the `keyring` package: macOS Keychain, Windows Credential Locker (Credential Manager), or Secret Service on a Linux desktop (GNOME Keyring, or KWallet through Secret Service). The key is encrypted at rest and tied to the user's login. It is not in a plain file that an AI coding agent, `git` or a backup reads by accident.

- **Backend check.** At launch the server calls `keyring.core.init_backend(limit=keyring.core.recommended)`, which loads only backends with priority 1 or higher (Context7, `jaraco/keyring`). `PYTHON_KEYRING_BACKEND` can still force a backend, so the server then checks `keyring.get_keyring()`. It treats the keychain as unavailable when the backend is the fail or null keyring, a chainer with no backends, any backend from the `keyrings.alt` package (its plaintext and file backends), or any backend with priority below 1. There is no silent fallback to a plaintext backend.
- **Names.** One service name, `omrg`, with the user name equal to the provider name (for example service `omrg`, user `openrouter`). All workspaces of one login share one key per provider, which matches how a user thinks of "my OpenRouter key".
- **What the database holds.** `provider.<name>.key_saved_at` records that this workspace saved a key, and when. The key itself never enters the database.
- **Reads.** At launch the server reads the `omrg` entry for each secret field, in a worker thread with a time limit, and keeps the key in memory in a value object whose `repr` hides it. The keychain entry is the truth for "key set". When the flag is set and the entry is gone (for example another workspace removed the shared key), the field state is `keychain-missing`. When the read fails, the state is `keychain-unreadable`. In both cases the provider has no key.
- **No keychain.** A save returns 409. Nothing is written anywhere. The card says in one line that no system keychain was found and names the variable to set, for example `OPENROUTER_API_KEY`. There is no silent plaintext fallback.
- **Environment wins.** `OPENROUTER_API_KEY` in the environment or `.env` still works, wins, and locks the field ("Set from environment (read-only here)"). Containers and headless servers keep working this way.
- **Never written by the app:** `.env`, the database, a file.
- **Display.** "Key set", the source, the save time, and the last four characters when the key has 16 or more characters. The last four come from the key in memory and are never stored.

| Option | Verdict |
|---|---|
| **OS keychain through `keyring`, with the environment variable as override (chosen, confirmed by the user)** | Encrypted at rest, per user, outside every file an agent or backup reads. Cost: a new dependency (approval recorded in task 1.5) and no keychain in most containers, where the environment variable is the answer. |
| `.env` written by the app | Plaintext. Easy to leak through agents that read the project, through `git`, and through backups. The app would also rewrite a user-owned file. |
| Workspace SQLite row | Plaintext, the same risk in a different file. Every schema migration also copies it into a `.bak` file (`schema.py:175-185`). |
| Plaintext key file, mode 0600 (the OMMS approach) | Same plaintext risk as `.env`, only with tighter permissions. |

OMMS stores pasted keys as plaintext 0600 files. This change still recommends the keychain because the risk the user named is accidental reading by agents, `git` and backups, and file permissions do not stop a process that runs as the same user. This change reuses from OMMS the shape the page gets (set, source, never the value), the write-only key form, testing typed values before save, and free-text model names.

**Platforms.**

| Platform | Backend `keyring` picks | Extra package to add | Result |
|---|---|---|---|
| macOS | Keychain (`keyring.backends.macOS`) | none | Keys saved in the login keychain |
| Windows | Windows Credential Locker, also called Credential Manager (`keyring.backends.Windows.WinVaultKeyring`, priority 5) | none: the backend uses `win32ctypes`, which `keyring` installs on Windows through a platform marker | Keys saved in Credential Manager |
| Linux desktop | Secret Service (`keyring.backends.SecretService`, priority 5): GNOME Keyring, or KWallet through its Secret Service interface | none: `keyring` installs `SecretStorage` and `jeepney` on Linux | Keys saved while the desktop keyring runs |
| Containers, WSL without a keyring, headless servers | none usable (fail keyring, or Secret Service with no daemon on D-Bus) | none | Unavailable: the card shows the one-line message and the environment variable works |

The Windows and Linux rows follow the `keyring` docs (Context7, `jaraco/keyring`): WinVault "implements storage in the Windows Credential Locker through `win32cred` (preferring the `win32ctypes.pywin32` distribution)", and the Secret Service backend raises when "the Secret Service daemon is neither running nor activatable through D-Bus". Task 1.6 confirms the platform markers in `uv.lock`. The separate KWallet D-Bus backend needs `dbus-python`; this change does not add it.

**Dependency.** `keyring` is MIT-licensed. Only `omrg web` reads keys, so the plan puts `keyring` in the `web` extra beside FastAPI and Uvicorn (`pyproject.toml:135-138`). The floor follows `tests/test_dependency_floors.py`: at most one minor below the locked version. Task 1.5 asks the user to approve the dependency and its place before any install.

### D2. Precedence: a fixed order, with locks

The order follows ADR-078, extended by D10. For each field, the first source that holds a value wins. From highest to lowest:

| Rank | Source | `source` value | Locks the field |
|---|---|---|---|
| 1 | Process environment | `env` | yes |
| 2 | `.env` | `env` | yes |
| 3 | `omrg.jsonc` in the user config folder (D10) | `config-file` | yes |
| 4 | Saved web value (database address, keychain key) | `saved` or `keychain` | no |
| 5 | Key file `secrets/<provider>.key` (secret fields only, D10) | `key-file` | no |
| 6 | Default | `default` | no |

A field with no value in any source reports `none` (secret fields) or its default (address fields).

A value from rank 1 to 3 wins and locks the field. The route returns 409 and names the variable or the file to change. A restart can then never undo a Settings change in silence. A key file does not lock: a key saved in the keychain overrides it, and removing the saved key falls back to the file.

`config` records which editable fields came from an explicit source, in the same way it records `vector_store` (`config/__init__.py:409`). The editable fields are `OLLAMA_BASE_URL`, `LLAMACPP_CHAT_URL`, `OPENROUTER_API_KEY`, `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY`, `ANTHROPIC_API_KEY`, `ANSWER__PROVIDER` and `ANSWER__MODEL`. Profile YAML and `defaults.yaml` count as `default`. The Chat choice locks as one unit when either answer variable is explicit, or when `omrg.jsonc` holds an `answer` block.

`.env.example` sets `LLAMACPP_CHAT_URL` without a comment mark (line 89). Users who copied it would see the field locked. This change comments that line out; the default value is the same.

Alternative: the saved value wins over `.env`. Rejected, because a user who edits `.env` would see no effect and not know why. The same reasoning puts `omrg.jsonc` above the saved value.

### D3. Live application inside the running Engine

Every saved value applies at once in the `omrg web` process. There is no restart banner.

A new pure module, `src/omrg/compose_providers.py`, holds `ProviderValues` (saved addresses, keys in memory, Chat choice) and `apply_provider_values(settings, values, explicit) -> Settings`, which returns a copy with each unlocked saved value in place. `compose.py` re-exports it (`compose.py` has 428 lines).

`compose.build_engine()` gains one keyword, `provider_source: Callable[[], ProviderValues] | None`. With `None` nothing changes, so the CLI, stdio and library paths stay as they are. With a source, `build_engine`:

1. resolves `Settings` and runs the environment safeguards as today (the `settings` argument stays unset, so the safeguards still run);
2. applies the values once and builds the Engine, the embedder and the store from that copy;
3. gives the Engine answer, judge and profile resolver factories that call `provider_source()` and apply the values when they build.

The Engine gains one public method, `use_provider_settings(effective)`. The web runtime calls it after a save with `compose.provider_effective_settings(source)`. The Engine:

1. refuses the new settings when an embedding field differs: embedding provider, embedding model, llama.cpp embedding address, the OpenRouter embedding model, and the Ollama address while embeddings use Ollama;
2. swaps in a new provider "generation": the new server-default settings, an empty answer-model slot, an empty judge cache and an unbuilt profile resolver. Each is built on first use through the factories.

A call that already started holds the old generation and finishes with it:

| Call | What it holds from its start |
|---|---|
| Answer (Chat, MCP over HTTP) | The model from `select_completion` and the judge from `build_verifier` (`engine_answer.py:65-73,95-98`) |
| Ingest, with metadata extraction | The `EffectiveSettings` resolved once at the entry point |
| Graph run | The generation object captured when its host is built (`engine.py:439-457` builds the host) |

New calls use the new generation. The generation is replaced, never changed in place, so no lock is needed beyond one reference swap.

Values that do not apply live, and why:

| Value | Why not |
|---|---|
| Embedding address, provider and model | The embedder is built once and every collection is stamped with its identity. Not editable here; see `add-profile-embedding-model`. |
| Ollama address while embeddings use Ollama | The running embedder keeps the address it was built with; a live change would split the two roles. Locked (D4). |
| A value from the environment, `.env` or the config file | Read once when the process starts. The field is locked and says so. |
| Saved web values for `omrg` over stdio, the CLI and experiment contexts | Separate processes or contexts that read the environment, `.env` and the user config folder (D10) by design. Experiment contexts stay reproducible. |

Alternatives: (a) restart for each change with a banner. Rejected by the user. (b) Rebuild the whole Engine. Rejected: it closes the store and the embedder while requests run. (c) Pass the Chat model per request as a client completion (`engine_answer.py:65-71`). Rejected: that path caps rounds, labels the source as an MCP client, and does not reach metadata extraction.

`engine.py` sits at 498 lines. The generation holder, the embedding-field guard and the answer-model slot go into a new `src/omrg/engine_providers.py`. `Engine` delegates to it, and `_get_answer_llm` and its fields move there. The file stays under 500 lines.

### D4. Embeddings stay safe

The editable fields are the Ollama address, the llama.cpp chat address, the OpenRouter key, the OpenAI-compatible address and key, and the Anthropic key. The llama.cpp embedding address and every embedding model stay read-only on the cards.

The Ollama address is shared by Ollama embeddings and the Ollama LLM. When the embeddings role resolves to Ollama, the address is locked with the reason "embeddings use it", and the Engine guard (D3) refuses it as well. A key change never changes embedding identity, because the stamp is provider and model. When `add-profile-embedding-model` lands, the lock must also cover profiles that choose Ollama embeddings. That change, or whichever lands second, adds the check.

### D5. Cards come from the registry

Each LLM provider module gains a `CONNECTION` descriptor: pure data plus small pure functions.

- `display_name`, `locality` (`local` or `cloud`), `requires_module` (for example `llama_index.llms.openai_like`) and `extra`.
- `fields`: each with `id`, label, kind (`url` or `secret`), the `Settings` field name and the environment variable name.
- `read_only(settings)`: labelled values to show, such as the embedding address and models.
- `test_targets(settings)`: the URLs and headers of the test. Ollama `GET /api/tags`, llama.cpp `GET <url>/models` on each address, OpenRouter `GET /api/v1/key`.
- `models_target(settings)` and `parse_models(payload)`: Ollama `models[].name`, llama.cpp and OpenRouter `data[].id` (Context7: Ollama API docs, OpenRouter API reference).

The registry gains `describe_all()`, which imports each registered module and returns the descriptors in registration order. `compose_connections` loops over it and has no branch on a provider name. "Installed" is `importlib.util.find_spec(requires_module) is not None`.

- `fields` also carry an `optional` flag (default false). A required secret field that is empty makes Chat not ready with the reason `not-configured`; an optional one does not. The set of editable fields, the redaction set, the lock and the readiness check read the descriptors, so a new provider needs no change outside its module and one register line.

Two providers join in this change, both for the answers role only:

| Provider | Display | Fields | Test and model list | Package |
|---|---|---|---|---|
| `openai_compatible` | OpenAI-compatible | `base_url` (url, `OPENAI_COMPATIBLE_BASE_URL`, default `https://api.openai.com/v1`), `api_key` (secret, `OPENAI_COMPATIBLE_API_KEY`, optional) | `GET {base_url}/models`, with `Authorization: Bearer` only when a key is set; `data[].id` | `OpenAILike`, now in the base install |
| `anthropic` | Anthropic | `api_key` (secret, `ANTHROPIC_API_KEY`, required), fixed address `https://api.anthropic.com` | `GET /v1/models` with `x-api-key` and `anthropic-version: 2023-06-01`; no request without a key; `data[].id` | `llama-index-llms-anthropic` in the opt-in `anthropic` extra; install hint `uv sync --extra anthropic` |

The OpenAI-compatible address can be loopback (LM Studio) or remote (OpenAI, Together, vLLM on another host). Locality is `cloud`, because the default address is a cloud host; the card adds the "leaves this machine" line for any non-loopback address (D7). The key goes only to the address saved or typed for this provider.

The OpenAI-like packages move into the base dependencies. The `llamacpp` and `openrouter` extras stay as empty extras so `uv sync --extra llamacpp` still works.

OpenRouter moves its test from `/models` to `/key`. The OpenRouter documentation says anonymous requests to `/models` get the public catalogue, so a wrong key may still pass today's test. `GET /api/v1/key` returns 401 without a valid key.

### D6. Routes

| Route | Scope | Body | Result |
|---|---|---|---|
| `GET /v1/connections` (changed) | `read` | none | `config_dir`, `user_config_dir` (D10, `~` for home), `keychain` (`available` or `unavailable`), one entry per registered provider (D5): `fields[]` of `{id, label, kind, value (url only), source (`env`, `config-file`, `saved`, `keychain`, `key-file`, `default` or `none`), locked, lock_reason, set, last4, saved_at, state}`, `read_only[]`, `roles`, `installed`, `install_hint` |
| `PUT /v1/connections/{provider}` | `manage`, session | `{fields: {<id>: url or null}}` | Saves or clears addresses. 400 bad address, 404 unknown provider or field, 409 locked |
| `PUT /v1/connections/{provider}/key` | `credentials`, session | `{api_key}` (8 to 512 printable characters, no spaces) | Saves to the keychain. 409 from `env` or with no keychain |
| `DELETE /v1/connections/{provider}/key` | `credentials`, session | none | Removes from the keychain and clears the flag |
| `POST /v1/connections/{provider}/test` (changed) | `manage`, session | optional `{fields: {<id>: value}}` | `{reachable, reason}`. Typed values are tested, not saved |
| `POST /v1/connections/{provider}/models` | `manage`, session | optional `{fields: {<id>: value}}` | `{reachable, reason, models[], truncated}` |
| `GET /v1/settings/chat` | `read` | none | `{provider, model, source, locked, lock_reason, enabled, ready, reason}` |
| `PUT /v1/settings/chat` | `manage`, session | `{provider, model}` or `null` | Saves or clears. 400, 409 as in the spec |
| `POST /v1/settings/chat/test` | `manage`, session | optional `{provider, model}` | `{ok, reason, elapsed_ms}` |

Routes go in `src/omrg/transports/api/routes/connections.py` and a new `routes/chat_settings.py`. Each validates, calls one store or compose function, and returns. A save writes in this order: keychain (keys only), database, runtime values, `engine.use_provider_settings(...)`. If the Engine refuses, the route restores the previous runtime values and database row and returns 409.

The Chat test builds the model through the registry with the candidate provider and model, calls `acomplete("Reply with the word OK.")` inside `asyncio.timeout(30)`, and maps the exception by its type and its `status_code` attribute, never by provider name: connection errors to `refused`, time-outs to `timeout`, 401 and 403 to `unauthorised`, other statuses to `http-<status>`, `ModuleNotFoundError` to `not-installed`, anything else to `failed`. It returns no text.

The model list reads at most 8 MiB of the body and returns at most 1,000 names. It is the only route that reads a provider body, and it returns only names that pass the length and character check.

### D7. Security

- Every write, test and list route needs the browser session (`require_session`, `src/omrg/transports/api/engine_access.py:72-97`). Keys need the `credentials` scope, as the MCP token routes do (`routes/mcp.py:34`). A bearer credential never passes.
- The existing middleware checks `Host`, rejects foreign `Origin` and cross-site fetch metadata on `/v1`, and refuses credentials in the query string (`src/omrg/transports/api/middleware.py:1-7`). No change is needed.
- Address check before any save or request (spec "Provider addresses are validated"). Local network hosts are allowed because a user may run Ollama on another machine. Redirects stay off.
- Key prefixes such as `sk-or-` (OpenRouter) and `sk-ant-` (Anthropic) are not special. Redaction matches the saved key text, and the key check (8 to 512 printable characters, no spaces) is the same for every provider.
- Redaction: a new append-only `SecretSet` in `security.py`, filled from every secret field of every registered descriptor. `RedactingFilter` and `LogBuffer` read it at filter time in place of the launch tuple. The key route adds a key to the set before it calls the keychain. The answer route runs the result's `error` text through the set. Replaced keys stay in the set until shutdown. A test proves a saved key never reaches a log record (task 6.1).
- Validators never put a value in an error message. The key body model uses a check whose message names only the rule.
- Keychain calls block and may show a system prompt on macOS. They run in a worker thread with a time limit, never on the event loop.

### D8. Web

The design follows `web/DESIGN.md` and the `omrg-design` skill: primitives only (`Card`, `Badge`, `Button`, `Input`, `Label`, Radix `Select`, `AlertNotice`, `ErrorNotice`), semantic tokens, status shown with text as well as colour, one friendly line per failure.

- **Sections and routes.** `SECTIONS` in `SettingsView.tsx` becomes Appearance, Providers, Chat, MCP, Server log, Runtime, Workspace. `studio-profiles-gallery` adds `{ area: "settings"; section: SectionId | null }` to `routes.ts` and makes each chip write `#/settings/<section>`; this change adds the Providers and Chat ids.
- **Providers.** `ConnectionsSection.tsx` becomes `ProvidersSection.tsx`. The card is split so no file passes about 200 lines: `ProviderCard.tsx` (header, badges, read-only rows, notices), `ProviderAddressField.tsx` (`Input` with `Label`, source line, Save, Reset), `ProviderKeyField.tsx` (`Input type="password"`, `autoComplete="off"`, `spellCheck={false}`, Save key, Remove key; the input empties after save; the no-keychain line replaces the input), and `ProviderTest.tsx` (Test, which sends typed values when a field is dirty). The grid stays `grid-cols-1 md:grid-cols-2 xl:grid-cols-3`. Display names come from the server, so `PROVIDER_NAMES` goes.
- **Chat section.** `ChatSection.tsx` and `ChatModelForm.tsx`: a Radix `Select` for the provider (items that are not ready are disabled and show their reason), an `Input` for the model name with hint text, List models (fills a second `Select`; picking an item fills the input), Test, Save, Clear. The notes of the requirement "The Chat section says where the choice applies" sit under the form.
- **Chat view.** `ChatView.tsx` reads the Chat status. When not ready it shows one `AlertNotice` line with a link to `#/settings/chat`, and the composer's Send is disabled. `failureLine` adds the same link for a `generation` failure.

### D9. ADR

ADR-083, "LLM provider settings in the web workspace". ADR-082 is taken by `add-chat-history-and-canvas-view-controls`, so this change uses ADR-083.

### D10. User config folder (read-only)

The user wants operator-set values in files, as in OMMS (`~/.config/omms/omms.jsonc` and `secrets/<name>.key`). The web page cannot write them. Decision made on 2026-10-18.

**Location.** `$OMRG_CONFIG_DIR`, else `$XDG_CONFIG_HOME/omrg`, else `~/.config/omrg`. The folder holds `omrg.jsonc` and `secrets/<provider>.key`. The app never writes, creates or changes the permissions of anything there. A missing folder or file is normal and gives no value and no warning.

**`omrg.jsonc`.** JSON with comments and trailing commas. Optional non-secret keys: `ollama_base_url`, `llamacpp_chat_url`, `openai_compatible_base_url`, and `answer: {provider, model}`. Secret fields hold only a reference: `env://NAME` (read the named environment variable) or `file://<absolute path>` (the path MUST resolve inside `secrets/`). A literal key in the file is ignored, with one warning that names the field and never the value. A broken file gives no values and one warning.

**Key files.** One key per provider; the file name is the registry provider name (`secrets/openrouter.key`). At most 4 KiB; surrounding whitespace is stripped. A symlink that leaves the folder, or a file that is not a regular file, is refused. A file looser than 0600, or a folder looser than 0700, is still read, and logs one warning with the path and the mode (never the content). The permission check is skipped on Windows.

**Where it lives in the code.** The sources are read by the `config/` package (a new module), so the CLI and the stdio MCP server read the same folder. Saved web values stay web-only. Both files are read at launch. A change needs a restart, as for `.env`.

**Redaction.** Keys that come from the folder (a key file, or an `env://` or `file://` reference) join the redaction set exactly like environment keys.

**API.** `GET /v1/connections`: the field `source` gains `config-file` and `key-file`. The response gains a top-level `user_config_dir`, with `~` for the home folder. The lock text for a config-file field reads "Set in ~/.config/omrg/omrg.jsonc. Edit that file and restart to change it." The card text for a locked field reads "Set from config file (read-only here)". For a key file it reads "Set from key file (read-only here). Saving a key in the keychain overrides it."

**Tests.** Tests set `OMRG_CONFIG_DIR` to a temporary folder, so they never read the real one.

**Honest limits.** The files are plaintext on disk. Permissions do not stop another process of the same user, and an AI coding agent runs as that user. The folder gives no security gain over `.env`. It suits headless machines and containers that mount a folder. On a desktop the keychain stays the advice.

| Option | Verdict |
|---|---|
| **Read-only folder with `omrg.jsonc` and `secrets/` (chosen, confirmed by the user)** | Mirrors OMMS. Operator edits the files, the app reads them. No write path to secure. Cost: plaintext, and a restart for each change. |
| Write key files from the page | Rejected. It reverses the rule "no keychain means no saved key" and makes the app a writer of plaintext secrets. |
| Allow a literal key in `omrg.jsonc` | Rejected. One config file would mix settings and secrets, and would be shared or committed by accident. References keep the file safe to share. |
| Put the values in `.env` | Rejected. It is the status quo. `.env` sits in the project folder and cannot be shared by several projects or mounted into a container as one folder. |
| Several named OpenAI-compatible endpoints | Out of scope. A possible later change. |

### Rejected alternatives for the new providers

| Option | Verdict |
|---|---|
| Put `llama-index-llms-anthropic` in the base install | Rejected. It pulls boto3 and Google SDKs (about 40 MB) that most users never need. It stays in the opt-in `anthropic` extra. |
| Keep the OpenAI-like packages in the `llamacpp` and `openrouter` extras | Rejected. `openai_compatible` needs them with no local server or OpenRouter, so they move to the base install. Both extras stay empty so old commands work. |
| A separate branch in the routes or web for each new provider | Rejected. The descriptors drive the card, the test, the readiness check and the secret rules. |

## Risks / Trade-offs

- [Keys are shared by every workspace of one login] → A delete from one workspace removes the key for all. The card names the shared entry ("Stored in the system keychain as omrg / openrouter"), and `keychain-missing` explains a key removed elsewhere.
- [macOS shows a Keychain prompt when a new Python binary reads the key, for example after `uv` rebuilds the virtual environment] → The read runs in a worker thread with a time limit. A refused prompt gives `keychain-unreadable` on the card, not a failed start.
- [Most containers have no keychain] → The environment variable works and the card says so in one line.
- [Saved values do not reach `omrg` over stdio] → The Providers and Chat sections and the docs say so. The user can still put the value in `.env`.
- [A swap during a long graph run] → The run keeps the generation it captured at start; a test covers it (task 5.1).
- [A user saves an address on another machine; text then leaves this machine, maybe over plain HTTP] → The card states it when the host is not a loopback address.
- [The model list from OpenRouter is large] → 8 MiB read limit, 1,000 names, sorted; free text still works.
- [`add-profile-embedding-model` adds per-profile Ollama embeddings] → D4: the Ollama lock and the Engine guard must cover profiles.
- [The route `#/settings/<section>` is needed by this change] → Resolved: `studio-profiles-gallery` carries the route and its scenario in its `workspace-presentation` delta, so only one change modifies that requirement. This change lands after it. Task 1.2 checks this.

- [Key files are plaintext, and an AI coding agent can read them] → docs and ADR-083 say so. The keychain stays the advice on a desktop. The folder is for headless machines and containers.
- [A user edits `omrg.jsonc` and sees no change] → both files are read at launch. The lock text says "restart to change it".
- [A bad file mode exposes a key to other users] → one warning with the path and mode, never the content.
- [Experiment contexts that call `get_settings()` also read the folder] → they read the same sources as the CLI. Experiment write-ups SHOULD record when a value came from the folder.

## Migration Plan

1. Land after `organise-backend-folders`. Use the new route paths.
2. No schema migration: new keys use the existing `workspace_settings` table.
3. Existing `.env` setups keep working and show as locked.
4. Rollback: revert the change. Saved rows stay and nothing reads them. Keys stay in the keychain under the service `omrg` until the user deletes them; the ADR and `docs/guides/web-workspace.md` say how.

## Open Questions

- Resolved on 2026-10-18 (task 14.5, real service): `GET /api/v1/models` returns 200 for a wrong key and for no key. `GET /api/v1/key` returns 401 for both, and 200 for a good key. D5 stays: the connection test uses `/key`, because `/models` cannot tell a wrong key from a good one.
