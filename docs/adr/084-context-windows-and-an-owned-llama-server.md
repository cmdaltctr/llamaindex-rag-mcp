# ADR-084: Context Windows and a llama.cpp Server omrg Owns

- **Date:** 2026-10-18
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-083](083-llm-provider-settings-in-the-web-workspace.md) (provider settings, sources and locks), TDR-036 (Ollama failures became an "Empty Response" answer)
- **Change:** `openspec/changes/add-llm-provider-settings/` (design D11 and D12, task groups 17 and 18)

## Context

omrg passed no context window to the Ollama client. LlamaIndex then called `/api/show`, read the model maximum (262,144 tokens for `qwen3:4b`) and sent it as `num_ctx` on every chat call. Ollama reserved about 43 GB, ran out of GPU memory and answered HTTP 200 with an empty reply. Chat showed "Empty Response" and the Mac lagged (TDR-036).

A llama.cpp chat server takes its window from `llama-server -c` at start. The client cannot change it. To set the window from the web workspace, omrg must be able to start and restart that server. Starting a program from a web route is a risk: if the browser can choose what runs, the browser session can run anything on the machine.

Without a decision, Ollama keeps reserving the model maximum, and a llama.cpp window change needs the user to restart the server by hand.

## Decision

1. **A context window setting for Ollama** (D11). `ollama_context_window`, default 16,384 tokens, range 2,048 to 262,144. Sources follow ADR-083: environment and `.env` (lock), `omrg.jsonc` (lock), saved web value, default. It applies live. It is passed as `context_window` to the LlamaIndex Ollama client, so no `/api/show` call happens, and as `options.num_ctx` on `/api/generate` for metadata extraction.
2. **Embedding models are excluded.** An embedding window can change how text is cut, and so the vectors. ADR-083 decision 4 keeps embeddings fixed.
3. **omrg owns at most one `llama-server`** (D12). `omrg web` starts it for Chat, keeps the process handle, and stops, restarts and reports only that process. It never looks up a process by name or port and never signals one it did not start. A server the user started stays safe. If the port is busy at start, the state is `failed` with `port-in-use`.
4. **Four settings, in `omrg.jsonc` and the GUI.** The program path, the model (`.gguf` file or Hugging Face id), the context window (`llamacpp_context_window`, same range and default), the idle sleep (`llamacpp_idle_sleep_seconds`, default 300 seconds, 0 turns it off) and the port, which comes from `llamacpp_chat_url`. The user chose GUI editing of the program path and model on 2026-10-18, against the recommendation to keep them in `omrg.jsonc` only.
5. **Guardrails on what can run.**
   - The program is an absolute path to an executable regular file named exactly `llama-server`, both as given and after links are resolved. It is checked at save and before every launch.
   - The model is an existing `.gguf` file or `org/name[:tag]`, and never starts with `-`.
   - The chat URL is a loopback `http` URL. The child binds `127.0.0.1` only.
   - The argument list is built from fixed flags only (`-m` or `-hf`, `--host`, `--port`, `--sleep-idle-seconds` when the idle sleep is above 0, `-c`). No shell runs and no free-text argument exists.
   - The child gets `PATH`, `HOME`, `LANG` and `TMPDIR`, plus `LLAMA_CACHE`, `HF_HOME` and `HF_TOKEN` only for a Hugging Face model. No provider API key reaches it.
   - Changing the program or model needs the browser session with the `credentials` scope. The window and start, stop and restart need `manage`. A bearer token never works.
6. **A fixed lifecycle.** States `stopped`, `starting`, `running`, `failed`, with fixed reasons `binary-invalid`, `model-invalid`, `not-loopback`, `port-in-use`, `exited`, `timeout` and `not-configured`. Start waits for `GET /health` 200 for up to 180 s. Stop sends SIGTERM to the owned process group, waits 10 s, then SIGKILL. If the child does not lead its own group, omrg signals the child alone, never a shared group. The owned server stops when `omrg web` exits.
7. **Idle sleep is on by default.** The managed server gets `--sleep-idle-seconds 300`, so it frees the model's GPU and RAM after five idle minutes and reloads it on the next request. This matches Ollama's default keep-alive. 0 turns it off.
8. **A save never stops a running server.** The card shows "Restart to apply" when the saved values differ from the values the process started with.
9. **The child's output stays on disk.** It goes to `llamacpp-server.log` in the workspace folder, emptied at each start, capped at 5 MiB, mode 0600. No route returns it and the page never shows it, because it can hold prompts.

## Consequences

### Positive

- Ollama no longer reserves the model maximum. With the default, `qwen3:4b` needs a few GB, not 43 GB.
- The user sets both context windows in the browser, in `omrg.jsonc` or in the environment, with the same precedence and locks as other provider settings.
- The llama.cpp window, program and model change from the page, with one Restart click.
- Each guardrail has a test, and a mutation check showed that breaking any one of them fails a test.

### Negative

- The program path is editable in the GUI. The guardrails limit what can run to a file named `llama-server`, but anyone with the browser session and the `credentials` scope can point the setting at any file with that name.
- If `omrg web` is killed with SIGKILL, the owned server keeps running, because no shutdown hook runs. The user stops it by hand.
- The Windows stop path (terminate, then kill) is not tested.
- The change is larger. It adds a lifecycle module, five routes and a new card panel.

### Neutral

- The first answer after an idle sleep is slower, because the server reloads the model. A `llama-server` build without sleep mode exits on the flag; 0 avoids that.

- A llama.cpp server the user started keeps its own `-c`. omrg does not change it.
- The llama.cpp embedding server is not managed.
- macOS adds `__CF_USER_TEXT_ENCODING` to every new process. It is not a secret and is not set by omrg.
- The stdio MCP server and the CLI never start or stop the server.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Keep reading the maximum from `/api/show`** | It caused TDR-036: 43 GB reserved, out-of-memory errors, empty answers. |
| **Cap the window by free memory** | omrg cannot read GPU memory in a portable way. |
| **Apply the window to embedding models** | It can change how text is cut and so the vectors (ADR-083 decision 4). |
| **Restart any server on the configured port** | It means finding and killing a process by port, which can hit the user's own servers. |
| **Program path and model in `omrg.jsonc` only** | Recommended, but the user chose GUI editing as well. The cost is in Negative. |
| **Free-text extra arguments** | Any flag means any behaviour. The argument list stays fixed. |
| **Show the server's output on the page** | It can hold prompts and file paths. The log file on disk is enough. |
| **Do nothing** | Ollama keeps reserving 43 GB, and a llama.cpp window change needs a manual restart. |

## References

- `openspec/changes/add-llm-provider-settings/design.md` (D11, D12), `specs/llamacpp-server/spec.md`, `specs/llm-provider-settings/spec.md`
- `src/omrg/core/providers/llm/ollama.py`, `src/omrg/core/metadata/ollama.py` (context window use)
- `src/omrg/core/providers/llm/llamacpp_rules.py` (program, model, URL, argument and environment rules)
- `src/omrg/transports/api/llamacpp_server.py` (lifecycle), `src/omrg/transports/api/routes/llamacpp_server.py` (routes)
- `web/src/settings/LlamacppServerPanel.tsx`, `web/src/settings/ProviderNumberField.tsx`
- `docs/tdr/036-ollama-failures-became-an-empty-response-answer-so-carry-seam-errors-past-refine.md`
- [ADR-083](083-llm-provider-settings-in-the-web-workspace.md)
