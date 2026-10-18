# ADR-083: LLM Provider Settings in the Web Workspace

- **Date:** 2026-10-18
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-078](078-upload-limit-as-a-workspace-setting-and-run-artefact-route.md) (launch value wins and locks), [ADR-080](080-profiles-own-pipelines.md) (the web server owns the workspace), [ADR-082](082-chats-live-in-the-workspace-database.md), [ADR-026](026-provider-registry-and-openrouter.md) (provider registry)
- **Change:** `openspec/changes/add-llm-provider-settings/` (design D1 to D7)

## Context

Provider addresses, the OpenRouter key and the Chat model came only from `.env`. The Settings page showed them read-only. A change needed a restart. The user wants to set them in the GUI, with no restart and no key in a file that an AI agent, `git` or a backup can read.

## Decision

1. **Store a typed API key in the OS keychain through `keyring`** (D1). Service `omrg`, user name equal to the provider name. The key never enters `.env`, the database or a log. The user approved adding `keyring` (MIT) to the `web` extra on 2026-10-18.
2. **The environment wins** (D2). A value from the process environment or `.env` locks the field. The route returns 409 and names the variable. Order: environment, saved value, default.
3. **Apply saved values live** (D3). `Engine.use_provider_settings()` swaps a provider generation. A running call finishes with the generation it started with.
4. **Embeddings stay fixed** (D4). Only the Ollama address, the llama.cpp chat address and the OpenRouter key are editable. The Ollama address is locked while embeddings use Ollama.
5. **Cards come from the registry** (D5). Each LLM provider module has a `CONNECTION` descriptor. A new provider needs no web or route change.
6. **Only the browser session writes** (D7). Key routes need the `credentials` scope.
7. **Two more Chat providers go through the registry** (D5). `openai_compatible` ("OpenAI-compatible") has an editable address and an optional key. It covers OpenAI, Together, vLLM, LM Studio and any server that speaks the OpenAI chat API. `anthropic` has one required key and the fixed address `https://api.anthropic.com`. Each is one module, one `register()` line and one descriptor. The user approved both on 2026-10-18.
8. **The OpenAI-like packages move to the base install. `anthropic` stays an opt-in extra.** `llama-index-llms-openai-like` and `llama-index-embeddings-openai-like` become base dependencies, because `openai_compatible` needs them with no local server. The `llamacpp` and `openrouter` extras stay as empty extras, so old install commands work. `llama-index-llms-anthropic` goes in the new `anthropic` extra (`uv sync --extra anthropic`). It pulls boto3 and Google SDKs, about 40 MB, which most users do not need.
9. **The descriptors drive secret handling.** Redaction, the editable set, locking and the Chat readiness check read the descriptors. A field can be optional (the OpenAI-compatible key), and an empty optional field does not block Chat. A new provider needs no change outside its module and one register line.

## Rejected storage options

| Option | Reason |
|---|---|
| `.env` written by the app | Plaintext. Leaks through agents, `git` and backups. The app would rewrite a user-owned file. |
| Workspace SQLite row | Plaintext. A schema migration copies it into a `.bak` file. |
| Plaintext key file, mode 0600 | Same plaintext risk. File permissions do not stop a process of the same user. |

## Values that do not apply live

- Embedding address, provider and model. The embedder is built once.
- The Ollama address while embeddings use Ollama.
- A value from the environment or `.env`. It is read once at start.
- Values for `omrg` over stdio, the CLI and experiment contexts. They read `.env` by design.

## Consequences

- Containers and headless servers have no keychain. The card says so and the environment variable works.
- The stdio MCP server and the CLI do not see saved values.
- OpenRouter is tested with `GET /api/v1/key`, because `/models` accepts a wrong key.
- The OpenAI-compatible address may be on this machine or remote. The key goes only to the address saved for that provider.
- Anthropic is tested with `GET /v1/models` and the headers `x-api-key` and `anthropic-version: 2023-06-01`. No request is sent without a key.
- The base install gains two small LlamaIndex packages. CI adds the `anthropic` extra to the floors matrix and to the coverage job.
