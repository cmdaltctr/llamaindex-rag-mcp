import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { LlamacppServerStatus } from "../api/llamacppServer";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { serverStatus, settingsServer } from "./test/fixtures";

const NOTE = "omrs starts and stops only this server. It never touches a server you started yourself.";

const PROGRAM_RULE = "The program must be the absolute path of an executable file named llama-server, not a script or a program in a hidden folder.";

/** A session that holds the `credentials` scope, which the program path and the model need. */
const WITH_CREDENTIALS = { "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["credentials", "files", "graph", "read", "run"], workspace: "/home/u/.omrs/workspace" }) };

async function open(handlers = {}) {
  const server = settingsServer({ ...WITH_CREDENTIALS, ...handlers });
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: "llama.cpp" });
  const panel = () => screen.getByRole("group", { name: "Local server" });
  await screen.findByRole("group", { name: "Local server" });
  return { server, user: userEvent.setup(), panel };
}

const RUNNING = serverStatus({ state: "running", pid_running: true, running_with: { context_window: 16384, model_kind: "file" } });

describe("Local server block on the llama.cpp card", () => {
  it("shows the note, four setting rows and a Stopped status with Start enabled and Stop disabled", async () => {
    const { panel } = await open();
    expect(panel()).toHaveTextContent(NOTE);
    for (const label of ["Program path", "Model", "Context window (tokens)", "Idle sleep (seconds)"]) {
      expect(within(panel()).getByRole("button", { name: `Edit ${label}` })).toBeInTheDocument();
    }
    expect(within(panel()).queryByRole("textbox")).toBeNull();
    expect(within(panel()).getByText("16384")).toBeInTheDocument();
    expect(within(panel()).getByText("300")).toBeInTheDocument();
    expect(within(panel()).getAllByText("Not set")).toHaveLength(2);
    expect(within(panel()).getAllByText("default")).toHaveLength(4);
    expect(within(panel()).getByRole("status")).toHaveTextContent("Stopped");
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeEnabled();
    expect(within(panel()).getByRole("button", { name: "Stop" })).toBeDisabled();
    expect(within(panel()).getByRole("button", { name: "Restart" })).toBeDisabled();
  });

  it("states that the embedding server is not managed", async () => {
    const { panel } = await open();
    expect(panel()).toHaveTextContent(/embedding server is not managed/i);
  });

  it("shows file values with the omrs.jsonc words and keeps them editable", async () => {
    const { panel } = await open({
      "GET /v1/llamacpp/server": () =>
        serverStatus({}, { binary: { value: "/opt/homebrew/bin/llama-server", source: "config-file" }, model: { value: "a/b", source: "config-file" }, context_window: { value: 8192, source: "config-file" } }),
    });
    expect(within(panel()).getByText("/opt/homebrew/bin/llama-server")).toBeInTheDocument();
    expect(within(panel()).getAllByText("Saved in settings (omrs.jsonc)")).toHaveLength(3);
    expect(within(panel()).getByRole("button", { name: "Edit Model" })).toBeInTheDocument();
  });

  it("opens the program path filled and saves it with the revision, then shows the source the server returns", async () => {
    const put: unknown[] = [];
    let saved = false;
    const { user, panel } = await open({
      "GET /v1/llamacpp/server": () => (saved ? serverStatus({}, { binary: { value: "/opt/llama/llama-server", source: "config-file" } }) : serverStatus({})),
      "PUT /v1/llamacpp/server": (body: unknown) => {
        put.push(body);
        saved = true;
        return { ...serverStatus({}, { binary: { value: "/opt/llama/llama-server", source: "config-file" } }), revision: "r2" };
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Edit Program path" }));
    const input = within(panel()).getByRole("textbox", { name: "Program path" });
    expect(input).toHaveValue("");
    await user.type(input, "/opt/llama/llama-server");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(put).toEqual([{ binary: "/opt/llama/llama-server", revision: "r1" }]);
    expect(await within(panel()).findByText("/opt/llama/llama-server")).toBeInTheDocument();
    expect(within(panel()).getByText("Saved in settings (omrs.jsonc)")).toBeInTheDocument();
    expect(within(panel()).queryByRole("textbox")).toBeNull();
  });

  it("opens an edit filled with the value in force", async () => {
    const { user, panel } = await open({
      "GET /v1/llamacpp/server": () => serverStatus({}, { binary: { value: "/opt/homebrew/bin/llama-server", source: "config-file" } }),
    });
    await user.click(within(panel()).getByRole("button", { name: "Edit Program path" }));
    expect(within(panel()).getByRole("textbox", { name: "Program path" })).toHaveValue("/opt/homebrew/bin/llama-server");
  });

  it("saves the model and the window as separate changes", async () => {
    const put: unknown[] = [];
    const { user, panel } = await open({
      "PUT /v1/llamacpp/server": (body: unknown) => {
        put.push(body);
        return serverStatus({});
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Edit Model" }));
    await user.type(within(panel()).getByRole("textbox", { name: "Model" }), "Qwen/Qwen3-0.6B-GGUF:Q8_0");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    await user.click(within(panel()).getByRole("button", { name: "Edit Context window (tokens)" }));
    const window = within(panel()).getByRole("spinbutton", { name: "Context window (tokens)" });
    await user.clear(window);
    await user.type(window, "8192");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(put).toEqual([
      { model: "Qwen/Qwen3-0.6B-GGUF:Q8_0", revision: "r1" },
      { context_window: 8192, revision: "r1" },
    ]);
  });

  it("saves the idle sleep in seconds and says what sleep does", async () => {
    const put: unknown[] = [];
    const { user, panel } = await open({
      "PUT /v1/llamacpp/server": (body: unknown) => {
        put.push(body);
        return serverStatus({});
      },
    });
    expect(panel()).toHaveTextContent(/frees the model after this many idle seconds/i);
    expect(panel()).toHaveTextContent(/0 turns sleep off/i);
    await user.click(within(panel()).getByRole("button", { name: "Edit Idle sleep (seconds)" }));
    const sleep = within(panel()).getByRole("spinbutton", { name: "Idle sleep (seconds)" });
    expect(sleep).toHaveValue(300);
    await user.clear(sleep);
    await user.type(sleep, "0");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(put).toEqual([{ idle_sleep: 0, revision: "r1" }]);
  });

  it("returns a file value to the default with null", async () => {
    const put: unknown[] = [];
    const { user, panel } = await open({
      "GET /v1/llamacpp/server": () => serverStatus({}, { model: { value: "a/b", source: "config-file" } }),
      "PUT /v1/llamacpp/server": (body: unknown) => {
        put.push(body);
        return serverStatus({});
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Edit Model" }));
    await user.click(within(panel()).getByRole("button", { name: "Use default" }));
    expect(put).toEqual([{ model: null, revision: "r1" }]);
  });

  it.each([
    ["env", "Set in the environment. Change it there."],
    ["dotenv", "Set in .env. Change it there."],
  ] as const)("shows a value set by %s as read-only and says where", async (source, words) => {
    const { panel } = await open({
      "GET /v1/llamacpp/server": () => serverStatus({}, { model: { value: "/models/q.gguf", source, locked: true, lock_reason: "Remove LLAMACPP_SERVER_MODEL from the environment or .env to edit it here." } }),
    });
    expect(panel()).toHaveTextContent(words);
    expect(panel()).toHaveTextContent("LLAMACPP_SERVER_MODEL");
    expect(within(panel()).getByText("/models/q.gguf")).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Edit Model" })).toBeNull();
  });

  it("makes the program path and the model read-only when the session lacks the credentials scope", async () => {
    const { panel } = await open({ "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["files", "graph", "read", "run"], workspace: null }) });
    await waitFor(() => expect(within(panel()).queryByRole("button", { name: "Edit Program path" })).toBeNull());
    expect(within(panel()).queryByRole("button", { name: "Edit Model" })).toBeNull();
    expect(within(panel()).getAllByText(/credentials session is needed/i)).toHaveLength(2);
    expect(within(panel()).getByRole("button", { name: "Edit Context window (tokens)" })).toBeInTheDocument();
    expect(within(panel()).getByRole("button", { name: "Edit Idle sleep (seconds)" })).toBeInTheDocument();
  });

  it("shows the program rule message in place of a generic line when a save is refused", async () => {
    const { user, panel } = await open({ "PUT /v1/llamacpp/server": () => json({ status: "error", message: PROGRAM_RULE }, 400) });
    await user.click(within(panel()).getByRole("button", { name: "Edit Program path" }));
    await user.type(within(panel()).getByRole("textbox", { name: "Program path" }), "~/.llama-app/llama");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    const alert = await within(panel()).findByRole("alert");
    expect(alert).toHaveTextContent(PROGRAM_RULE);
    expect(alert).not.toHaveTextContent("The local server could not complete that request.");
  });

  it("shows the range message of the server for a context window out of range", async () => {
    const message = "The context window must be a whole number from 2048 to 262144.";
    const { user, panel } = await open({ "PUT /v1/llamacpp/server": () => json({ status: "error", message }, 400) });
    await user.click(within(panel()).getByRole("button", { name: "Edit Context window (tokens)" }));
    const window = within(panel()).getByRole("spinbutton", { name: "Context window (tokens)" });
    await user.clear(window);
    await user.type(window, "1000");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(await within(panel()).findByRole("alert")).toHaveTextContent(message);
  });

  it("shows the conflict with a Reload action when omrs.jsonc changed on disk", async () => {
    const message = "omrs.jsonc changed on disk. Reload to see the new values.";
    const { user, panel, server } = await open({ "PUT /v1/llamacpp/server": () => json({ status: "error", message }, 409) });
    await user.click(within(panel()).getByRole("button", { name: "Edit Program path" }));
    await user.type(within(panel()).getByRole("textbox", { name: "Program path" }), "/x/llama-server");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(await within(panel()).findByRole("alert")).toHaveTextContent(message);
    const reads = server.find("GET", "/v1/llamacpp/server").length;
    await user.click(within(panel()).getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(server.find("GET", "/v1/llamacpp/server").length).toBe(reads + 1));
  });

  it("starts the server and shows Starting", async () => {
    let started = false;
    const { user, panel, server } = await open({
      "GET /v1/llamacpp/server": () => (started ? serverStatus({ state: "starting", pid_running: true }) : serverStatus({})),
      "POST /v1/llamacpp/server/start": () => {
        started = true;
        return serverStatus({ state: "starting", pid_running: true });
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Start" }));
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Starting"));
    expect(server.find("POST", "/v1/llamacpp/server/start")).toHaveLength(1);
    expect(within(panel()).getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeDisabled();
  });

  it("shows Running with Start disabled, Stop and Restart enabled, and no pending note", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/server": () => RUNNING });
    expect(within(panel()).getByRole("status")).toHaveTextContent("Running");
    expect(within(panel()).getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(within(panel()).getByRole("button", { name: "Restart" })).toBeEnabled();
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeDisabled();
    expect(panel()).not.toHaveTextContent("Restart to apply");
  });

  it("keeps the server running and says Restart to apply when the saved values differ from the running ones", async () => {
    let saved = false;
    const { user, panel } = await open({
      "GET /v1/llamacpp/server": () => ({ ...RUNNING, pending_restart: saved, ...(saved ? { saved: serverStatus({}, { model: { value: "a/b", source: "config-file" } }).saved } : {}) }),
      "PUT /v1/llamacpp/server": () => {
        saved = true;
        return { ...RUNNING, pending_restart: true, saved: serverStatus({}, { model: { value: "a/b", source: "config-file" } }).saved };
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Edit Model" }));
    await user.type(within(panel()).getByRole("textbox", { name: "Model" }), "a/b");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(await within(panel()).findByText("Restart to apply")).toBeInTheDocument();
    expect(within(panel()).getByRole("status")).toHaveTextContent("Running");
  });

  it("stops and restarts through POST", async () => {
    const { user, panel, server } = await open({
      "GET /v1/llamacpp/server": () => RUNNING,
      "POST /v1/llamacpp/server/stop": () => serverStatus({}),
      "POST /v1/llamacpp/server/restart": () => RUNNING,
    });
    await user.click(within(panel()).getByRole("button", { name: "Restart" }));
    await waitFor(() => expect(server.find("POST", "/v1/llamacpp/server/restart")).toHaveLength(1));
    await user.click(within(panel()).getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(server.find("POST", "/v1/llamacpp/server/stop")).toHaveLength(1));
  });

  it.each([
    ["not-configured", "Set the program path first."],
    ["binary-invalid", "The program path is not a runnable file named llama-server."],
    ["model-invalid", "The model is not an existing .gguf file or a Hugging Face id."],
    ["not-loopback", "The chat address is not on this machine, so omrs will not start a server for it."],
    ["port-in-use", "Another program already uses the chat port. omrs did not touch it."],
    ["timeout", "The server did not become ready in time and was stopped."],
  ] as const)("shows a friendly sentence for %s", async (reason, sentence) => {
    const { panel } = await open({ "GET /v1/llamacpp/server": () => serverStatus({ state: "failed", reason }) });
    const status = within(panel()).getByRole("status");
    expect(status).toHaveTextContent("Failed");
    expect(status).toHaveTextContent(sentence);
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeEnabled();
  });

  it("names the model when only the model is missing", async () => {
    const { panel } = await open({
      "GET /v1/llamacpp/server": () => serverStatus({ state: "failed", reason: "not-configured" }, { binary: { value: "/opt/llama/llama-server", source: "config-file" } }),
    });
    expect(within(panel()).getByRole("status")).toHaveTextContent("Set the model first.");
  });

  it("shows Set the program path first after Start when nothing is set", async () => {
    let started = false;
    const { user, panel } = await open({
      "GET /v1/llamacpp/server": () => serverStatus(started ? { state: "failed", reason: "not-configured" } : {}),
      "POST /v1/llamacpp/server/start": () => {
        started = true;
        return serverStatus({ state: "failed", reason: "not-configured" });
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Start" }));
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Failed: Set the program path first."));
  });

  it("shows the exit code for exited", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/server": () => serverStatus({ state: "failed", reason: "exited", exit_code: 3 }) });
    expect(within(panel()).getByRole("status")).toHaveTextContent("The server stopped by itself with exit code 3. See llamacpp-server.log in the workspace folder.");
  });

  it("never puts raw log or process text in the page", async () => {
    const hostile = { ...serverStatus({ state: "failed", reason: "exited", exit_code: 1 }), log: "SECRET-CHILD-TEXT", output: "SECRET-CHILD-TEXT" } as LlamacppServerStatus;
    await open({ "GET /v1/llamacpp/server": () => hostile });
    expect(document.body.textContent).not.toContain("SECRET-CHILD-TEXT");
  });
});
