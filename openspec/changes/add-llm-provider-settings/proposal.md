# Proposal

## Why

Today the Settings page can only show the language model (LLM) providers. It cannot change them. The Connections section reads every value from the server's `.env` file and says that a change needs a restart (`web/src/settings/ConnectionsSection.tsx:27-32`, `src/omrg/transports/api/routes/connections.py:1-8`). Chat has no place to choose its model. It uses the server answer model (`ANSWER__PROVIDER`, `ANSWER__MODEL`, `src/omrg/core/answer/settings.py:51-55`). When no model can be built, Chat shows only "The answer could not be completed." (`web/src/chat/answerStatus.ts:50-54`), and nothing tells the user where to fix it.

The user wants the web app to become the GUI for the whole system. This change lets the user set provider addresses and API keys in Settings, test them, and choose the Chat model by typing its name. Every change applies at once, with no restart. OMMS, a sibling project, has a similar settings page; this change reuses its page shape and its rule that the page never gets a key value, and stores keys in the system keychain in place of the plaintext files OMMS uses.

## What Changes

- The Settings section "Connections" becomes "Providers". It shows one card for each registered LLM provider: Ollama, llama.cpp, OpenRouter, OpenAI-compatible and Anthropic. The cards come from the LLM provider registry. A new provider file and one `register()` line add a card.
- Each card can edit the provider's address (Ollama, llama.cpp chat, OpenAI-compatible) or API key (OpenRouter, OpenAI-compatible, Anthropic). The OpenAI-compatible key is optional. A card states whether the provider is local or cloud. Cloud cards state that text leaves the machine.
- Each value shows its source: `.env`, saved here, or default. A value from the environment or `.env` wins and locks the field, as the upload limit does (ADR-078).
- An API key is write-only. The server stores it in the system keychain (macOS Keychain, Windows Credential Locker, Secret Service or KWallet) through the `keyring` package. The workspace database holds only a "key is set" flag. The app never writes a key to `.env` or to any file. The page shows at most "Key set" and the last four characters. The server log and answer errors remove the key from the moment it is saved.
- With no keychain (for example in a container), the card says so in one line and names the environment variable to set. There is no plaintext fallback.
- The Test action can test typed values before they are saved. A new "List models" action asks the provider for its model names. Both contact a provider only when the user asks.
- A new Settings section "Chat" chooses the provider and the model name for Chat. The model name is free text, with an optional list from the provider. A Test action sends one short prompt.
- The Chat choice is the web server's answer model. MCP clients served by this web server also use it when they cannot supply their own model. Metadata extraction keeps its own model choice.
- Every saved value applies at once inside the running Engine: answers, the verification judge and metadata extraction use it from their next call. Calls in progress finish with the old values. There is no restart banner. Values that cannot apply live are named in design.md D3.
- Two more Chat providers join through the registry, each as one module, one `register()` line and one descriptor. `openai_compatible` ("OpenAI-compatible") covers OpenAI, Together, vLLM, LM Studio and any server that speaks the OpenAI chat API. Its address can be on this machine or remote, and its key is optional. `anthropic` ("Anthropic") needs a key and uses the fixed address `https://api.anthropic.com`. Both serve the answers role only.
- The LlamaIndex OpenAI-like packages (`llama-index-llms-openai-like`, `llama-index-embeddings-openai-like`) move from the `llamacpp` and `openrouter` extras into the base install. Both extras stay as empty extras, so old install commands still work. `llama-index-llms-anthropic` goes into a new opt-in `anthropic` extra (`uv sync --extra anthropic`), because it pulls boto3 and Google SDKs (about 40 MB).
- Secret handling is driven by the descriptors: redaction, the editable set, locking and the Chat readiness check need no change for a new provider. The readiness check honours an optional-key flag.
- Embeddings stay out of scope. Cards show the embedding address and model as read-only. Per-profile embedding models belong to the change `add-profile-embedding-model`.
- Chat shows one line with a link to Settings > Chat when no model is connected.
- Settings sections get their own address, `#/settings/<section>`, so a link can open the Chat section.
- **BREAKING (web API only):** `GET /v1/connections` entries gain fields and change shape (`key_set` becomes part of a field list). The bundled web client changes in the same change. No other client uses the route.
- A new ADR records the decision. ADR-083 is the next free number (ADR-082 is taken by chat history).
- This change lands after `organise-backend-folders`, which moves `routes_*.py` into `transports/api/routes/`.

## Capabilities

### New Capabilities

- `llm-provider-settings`: how the web server stores, resolves, applies, tests and lists LLM provider values and the Chat model. It covers the registry-driven provider list, value precedence, keychain-only key storage, redaction, address validation, live application, the Chat model test and the model list.

### Modified Capabilities

- `workspace-settings`: the section list changes (Providers and Chat added, Connections renamed, each section gets an address). Provider cards become editable. The connection test accepts typed values.
- `workspace-chat`: Chat states when no model is connected and links to Settings > Chat.
- `workspace-presentation`: the route `#/settings/<section>` is added by `studio-profiles-gallery`, which owns the route-list requirement. This change depends on it and adds no delta there.
- `local-web-workspace`: the workspace settings table may now hold provider addresses, the Chat choice and "key is set" flags. It still holds no key. The requirement also gets the `upload_limit_mib` key it was missing.
- `engine-scoped-composition`: a running Engine can take new LLM provider values without a restart.

## Impact

- **Python code:** `src/omrg/core/providers/llm/{registry,ollama,llamacpp,openrouter}.py` (connection descriptors), new `src/omrg/core/providers/llm/{openai_compatible,anthropic}.py`, `src/omrg/compose_connections.py` (registry-driven), a new `src/omrg/compose_providers.py`, `src/omrg/compose.py` (re-exports only), `src/omrg/compose_engine.py`, `src/omrg/engine.py` and a new `src/omrg/engine_providers.py` (live provider values), `src/omrg/config/__init__.py` (records which provider fields came from the environment), `src/omrg/integrations/workspace_sqlite/settings.py`, a new `src/omrg/integrations/keychain.py`, `src/omrg/transports/api/{lifespan,security,log_buffer,connection_probe}.py`, `src/omrg/transports/api/routes/connections.py`, a new `src/omrg/transports/api/routes/chat_settings.py`, `src/omrg/transports/cli/web.py`.
- **API:** `GET /v1/connections` changes shape. New: `PUT /v1/connections/{provider}`, `PUT` and `DELETE /v1/connections/{provider}/key`, `POST /v1/connections/{provider}/models`, `GET` and `PUT /v1/settings/chat`, `POST /v1/settings/chat/test`. `POST /v1/connections/{provider}/test` accepts an optional body. `src/omrg/transports/api/openapi.yaml` changes.
- **Web:** `web/src/settings/` (Providers and Chat sections), `web/src/api/settings.ts`, `web/src/lib/routes.ts`, `web/src/chat/`.
- **Docs:** `docs/guides/configuration.md`, `docs/guides/web-workspace.md`, `.env.example`, a new `docs/adr/083-*.md`.
- **Build:** `pyproject.toml` (`web` extra, base dependencies, new `anthropic` extra) and `uv.lock`; `.github/workflows/ci.yml` (floors matrix and coverage job install `anthropic`).
- **Dependencies:** `keyring` (MIT licence) in the `web` extra (tasks.md 1.5). Two OpenAI-like packages move into the base install. `llama-index-llms-anthropic` joins a new opt-in `anthropic` extra. The user approved the Anthropic extra and the OpenAI-compatible provider on 2026-10-18.
- **Not affected:** the stdio MCP server and the CLI keep reading `.env` only. Experiment contexts keep the `.env` values.
