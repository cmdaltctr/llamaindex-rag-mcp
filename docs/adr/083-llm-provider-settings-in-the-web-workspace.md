# ADR-083: LLM Provider Settings in the Web Workspace

- **Date:** 2026-10-18
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-026](026-provider-registry-and-openrouter.md) (provider registry), [ADR-078](078-upload-limit-as-a-workspace-setting-and-run-artefact-route.md) (a launch value wins and locks), [ADR-080](080-profiles-own-pipelines.md) (the web server owns the workspace), [ADR-082](082-chats-live-in-the-workspace-database.md)
- **Change:** `openspec/changes/add-llm-provider-settings/` (design D1 to D9)

## Context

Provider addresses, the OpenRouter key and the Chat model came only from `.env`. The Settings page showed them read-only. A change needed a restart. The user wants to set them in the web workspace, with no restart and no key in a file that an AI agent, `git` or a backup can read.

The user also wants Chat to use more than the three providers the registry held (Ollama, llama.cpp, OpenRouter). OpenAI-compatible servers and Anthropic were missing.

Without a decision, keys would go to `.env` or the database in plaintext. Each new provider would also need edits in about a dozen files, because the secret handling named OpenRouter in many places.

## Decision

1. **Store a typed API key in the OS keychain through `keyring`** (D1). Service `omrg`, user name equal to the provider name. The key never enters `.env`, the database, a log or a response. The user approved adding `keyring` (MIT) to the `web` extra on 2026-10-18. A backend counts as usable only when it is not the fail or null keyring, not from `keyrings.alt`, has priority 1 or higher, and (for a chainer) every member is usable. Every keychain call runs in a worker thread with a time limit.
2. **The environment wins** (D2). A value from the process environment or `.env` locks the field. The route returns 409 and names the variable. Order: environment, saved value, default. The Chat provider and model lock as one unit: if either comes from the environment, both are locked.
3. **Apply saved values live** (D3). `Engine.use_provider_settings()` swaps a provider generation. Each generation freezes its own settings snapshot when it is created, and its factories read that snapshot. A call in flight finishes with the generation it started with. The Engine refuses a swap that changes an embedding field.
4. **Embeddings stay fixed** (D4). The Ollama address is locked while the server default or any catalogue profile uses Ollama embeddings.
5. **Cards come from the registry** (D5). Each LLM provider module has a `CONNECTION` descriptor with its fields, test target, model-list target and read-only rows. A field can be required or optional. A new provider is one module and one `register()` line.
6. **Only the browser session writes** (D7). Key routes need the `credentials` scope.
7. **Two more Chat providers go through the registry.** `openai_compatible` ("OpenAI-compatible") has an editable address (default `https://api.openai.com/v1`) and an optional key. It covers OpenAI, Together, vLLM, LM Studio and any server that speaks the OpenAI chat API. `anthropic` has one required key and the fixed address `https://api.anthropic.com`. Both are for the Chat role only, not embeddings or metadata. The user approved both on 2026-10-18.
8. **The OpenAI-like packages move to the base install. `anthropic` stays an opt-in extra.** `llama-index-llms-openai-like` and `llama-index-embeddings-openai-like` become base dependencies, because `openai_compatible` must work with no local server. The `llamacpp` and `openrouter` extras stay as empty extras, so old install commands work. `llama-index-llms-anthropic` goes in the new `anthropic` extra, because it pulls boto3 and Google SDKs (about 40 MB). The user confirmed this on 2026-10-18.
9. **The descriptors drive secret handling.** One list of secret fields feeds redaction, the editable set, locking and the Chat readiness check. An empty optional key does not block Chat. Redaction is append-only: a replaced key stays redacted until the process ends, in the log filter and in Engine error text.
10. **Redaction runs in one pass.** Every full value and every prefix of six or more characters of every secret goes into one list, longest piece first. Keys of one provider share a prefix (`sk-or-v1-`, `sk-ant-api03-`). Removing one key's short prefix first leaves the tail of a cut-off piece of another key in the text.
11. **An empty key never falls back to the environment.** The OpenAI client reads `OPENAI_API_KEY` when no key is given. The `openai_compatible` provider passes the literal placeholder `no-key` when no key is saved, so a key in the shell is never sent to an address the user typed. A test pins this.

## Consequences

### Positive

- Providers, keys and the Chat model are set in the browser and apply at once.
- A key is encrypted at rest and tied to the user's login. It is not in a file that an agent, `git` or a backup reads by accident.
- Adding a provider needs one module and one register line. The cards, the Chat picker, the test and model-list routes, redaction and live apply follow from the descriptor.
- OpenRouter's test now uses `GET /api/v1/key`, so a wrong key is caught. `/models` answers anyone.
- llama.cpp, OpenRouter and OpenAI-compatible Chat work without an extra install.

### Negative

- Containers and headless servers have no keychain. The card says so, and the environment variable is the only way to set a key there.
- The stdio MCP server and the CLI do not see saved values. They read `.env` by design.
- The base install gains two small LlamaIndex packages. Anthropic needs `uv sync --extra anthropic`, and CI installs that extra in the floors matrix and the coverage job.
- A save is not atomic across the keychain, the database and the running Engine. The route restores the earlier values if the Engine refuses, but a crash between steps can leave the keychain ahead of the database.

### Neutral

- The OpenAI-compatible address may be on this machine or remote. The key goes only to the address saved for that provider.
- Anthropic is tested with `GET /v1/models` and the headers `x-api-key` and `anthropic-version: 2023-06-01`. No request is sent without a key.
- `llamacpp` and `openrouter` do not set `is_chat_model=True` on `OpenAILike`. The new provider does. This change leaves the two older providers alone.
- Values that do not apply live: the embedding address, provider and model; the Ollama address while embeddings use Ollama; any value from the environment or `.env`; values for `omrg` over stdio, the CLI and experiment contexts.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **`.env` written by the app** | Plaintext. Leaks through agents, `git` and backups. The app would rewrite a user-owned file. |
| **Workspace SQLite row** | Plaintext. A schema migration copies it into a `.bak` file. |
| **Plaintext key file, mode 0600** (the OMMS approach) | Same plaintext risk. File permissions do not stop a process of the same user. |
| **Restart banner after each change** | The user rejected it. |
| **Rebuild the whole Engine on each save** | It closes the store and the embedder while requests run. |
| **Pass the Chat model per request** | That path caps rounds, labels the source as the MCP client, and does not reach metadata extraction. |
| **Anthropic in the base install** | Its LlamaIndex wrapper requires `anthropic[bedrock,vertex]`, about 40 MB of AWS and Google SDKs that most users do not need. |
| **One shared prefix pass per key** | Leaves the tail of a cut-off piece of a second key with the same prefix. |
| **Let the OpenAI client use `OPENAI_API_KEY` when no key is saved** | It would send a key from the shell to a typed address. |
| **Do nothing** | Keys and addresses stay in `.env`, every change needs a restart, and Chat is limited to three providers. |

## References

- `openspec/changes/add-llm-provider-settings/` (proposal, design D1 to D9, specs, tasks)
- `src/omrg/integrations/keychain.py` (keychain store and backend rules)
- `src/omrg/core/providers/llm/` (registry, `connection.py`, one module per provider)
- `src/omrg/engine_providers.py` and `src/omrg/compose_providers.py` (live apply and locking)
- `src/omrg/core/vectordb/identity.py` and `src/omrg/transports/api/secret_set.py` (redaction)
- `docs/guides/providers.md`, `docs/guides/configuration.md`, `docs/guides/web-workspace.md`
- [ADR-026](026-provider-registry-and-openrouter.md), [ADR-078](078-upload-limit-as-a-workspace-setting-and-run-artefact-route.md), [ADR-080](080-profiles-own-pipelines.md)
- keyring documentation (backends, priority, `PYTHON_KEYRING_BACKEND`)
