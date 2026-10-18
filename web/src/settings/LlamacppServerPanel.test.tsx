import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { LlamacppServerStatus } from "../api/llamacppServer";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { serverStatus, settingsServer } from "./test/fixtures";

const NOTE = "omrg starts and stops only this server. It never touches a server you started yourself.";

async function open(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: "llama.cpp" });
  const panel = () => screen.getByRole("group", { name: "Local server" });
  await screen.findByRole("group", { name: "Local server" });
  return { server, user: userEvent.setup(), panel };
}

const RUNNING = serverStatus({ state: "running", pid_running: true, running_with: { context_window: 16384, model_kind: "file" } });

describe("Local server block on the llama.cpp card", () => {
  it("shows the note, the three fields and a Stopped status with Start only", async () => {
    const { panel } = await open();
    expect(panel()).toHaveTextContent(NOTE);
    expect(within(panel()).getByRole("textbox", { name: "Program path" })).toHaveValue("");
    expect(within(panel()).getByRole("textbox", { name: "Model" })).toHaveValue("");
    expect(within(panel()).getByRole("spinbutton", { name: "Context window (tokens)" })).toHaveValue(16384);
    expect(within(panel()).getByRole("status")).toHaveTextContent("Stopped");
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeEnabled();
    expect(within(panel()).queryByRole("button", { name: "Stop" })).toBeNull();
    expect(within(panel()).queryByRole("button", { name: "Restart" })).toBeNull();
  });

  it("saves the program path as text with its own Save button", async () => {
    const put: unknown[] = [];
    const { user, panel } = await open({
      "PUT /v1/llamacpp/server": (body: unknown) => {
        put.push(body);
        return serverStatus({}, { binary: { value: "/opt/llama/llama-server", source: "saved" } });
      },
    });
    const input = within(panel()).getByRole("textbox", { name: "Program path" });
    await user.type(input, "/opt/llama/llama-server");
    await user.click(within(panel()).getByRole("button", { name: "Save program path" }));
    expect(put).toEqual([{ binary: "/opt/llama/llama-server" }]);
    expect(await within(panel()).findByText("Program path source: saved")).toBeInTheDocument();
  });

  it("saves the model and the window as separate changes", async () => {
    const put: unknown[] = [];
    const { user, panel } = await open({
      "PUT /v1/llamacpp/server": (body: unknown) => {
        put.push(body);
        return serverStatus({});
      },
    });
    await user.type(within(panel()).getByRole("textbox", { name: "Model" }), "Qwen/Qwen3-0.6B-GGUF:Q8_0");
    await user.click(within(panel()).getByRole("button", { name: "Save model" }));
    const window = within(panel()).getByRole("spinbutton", { name: "Context window (tokens)" });
    await user.clear(window);
    await user.type(window, "8192");
    await user.click(within(panel()).getByRole("button", { name: "Save context window" }));
    expect(put).toEqual([{ model: "Qwen/Qwen3-0.6B-GGUF:Q8_0" }, { context_window: 8192 }]);
  });

  it("resets a saved value with null", async () => {
    const put: unknown[] = [];
    const { user, panel } = await open({
      "GET /v1/llamacpp/server": () => serverStatus({}, { model: { value: "a/b", source: "saved" } }),
      "PUT /v1/llamacpp/server": (body: unknown) => {
        put.push(body);
        return serverStatus({});
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Reset model" }));
    expect(put).toEqual([{ model: null }]);
  });

  it("shows a locked value as read-only with its source", async () => {
    const { panel } = await open({
      "GET /v1/llamacpp/server": () =>
        serverStatus({}, { model: { value: "/models/q.gguf", source: "config-file", locked: true, lock_reason: "Set in ~/.config/omrg/omrg.jsonc. Edit that file and restart to change it." } }),
    });
    expect(within(panel()).queryByRole("textbox", { name: "Model" })).toBeNull();
    expect(panel()).toHaveTextContent("Set from config file (read-only here)");
    expect(within(panel()).getByText("/models/q.gguf")).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Save model" })).toBeNull();
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
    expect(within(panel()).getByRole("button", { name: "Stop" })).toBeInTheDocument();
  });

  it("shows Running with Stop and Restart, and no pending note", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/server": () => RUNNING });
    expect(within(panel()).getByRole("status")).toHaveTextContent("Running");
    expect(within(panel()).getByRole("button", { name: "Stop" })).toBeInTheDocument();
    expect(within(panel()).getByRole("button", { name: "Restart" })).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Start" })).toBeNull();
    expect(panel()).not.toHaveTextContent("Restart to apply");
  });

  it("says Restart to apply when the saved values differ from the running ones", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/server": () => ({ ...RUNNING, pending_restart: true }) });
    expect(panel()).toHaveTextContent("Restart to apply");
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
    ["not-configured", "Set the program path and the model first."],
    ["binary-invalid", "The program path is not a runnable file named llama-server."],
    ["model-invalid", "The model is not an existing .gguf file or a Hugging Face id."],
    ["not-loopback", "The chat address is not on this machine, so omrg will not start a server for it."],
    ["port-in-use", "Another program already uses the chat port. omrg did not touch it."],
    ["timeout", "The server did not become ready in time and was stopped."],
  ] as const)("shows a friendly sentence for %s", async (reason, sentence) => {
    const { panel } = await open({ "GET /v1/llamacpp/server": () => serverStatus({ state: "failed", reason }) });
    const status = within(panel()).getByRole("status");
    expect(status).toHaveTextContent("Failed");
    expect(status).toHaveTextContent(sentence);
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeEnabled();
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

  it("shows one friendly line when a save is refused", async () => {
    const { user, panel } = await open({
      "PUT /v1/llamacpp/server": () => json({ status: "error", message: "The model must be the absolute path of an existing .gguf file, or a Hugging Face id such as org/name or org/name:tag." }, 400),
    });
    await user.type(within(panel()).getByRole("textbox", { name: "Model" }), "--api-key");
    await user.click(within(panel()).getByRole("button", { name: "Save model" }));
    expect(await within(panel()).findByRole("alert")).toBeInTheDocument();
  });
});
