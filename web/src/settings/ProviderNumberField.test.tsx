import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Connection, ConnectionList } from "../api/settings";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { CONNECTIONS, intField, LLAMACPP, OLLAMA, OPENROUTER, settingsServer, urlField } from "./test/fixtures";

function list(...connections: Connection[]): ConnectionList {
  return { ...CONNECTIONS, connections };
}

function withWindow(field = intField("context_window", "Context window (tokens)", 16384)): Connection {
  return { ...OLLAMA, fields: [urlField("base_url", "Address", "http://127.0.0.1:11434"), field] };
}

async function open(handlers = {}) {
  startApp("#/settings/providers", settingsServer(handlers));
  await screen.findByRole("heading", { level: 3, name: "Ollama" });
  return { user: userEvent.setup(), card: () => screen.getByRole("region", { name: "Ollama" }) };
}

describe("Integer field (Ollama context window)", () => {
  it("renders a number input with its label, bounds and source", async () => {
    const { card } = await open({ "GET /v1/connections": () => list(withWindow(), LLAMACPP, OPENROUTER) });
    const input = within(card()).getByRole("spinbutton", { name: "Context window (tokens)" });
    expect(input).toHaveValue(16384);
    expect(input).toHaveAttribute("min", "2048");
    expect(input).toHaveAttribute("max", "262144");
    expect(card()).toHaveTextContent("Source: default");
    expect(within(card()).queryByRole("button", { name: "Reset to default" })).toBeNull();
  });

  it("saves a whole number and shows the value and source the server returns", async () => {
    let value = 16384;
    let source: "default" | "saved" = "default";
    const { user, card } = await open({
      "GET /v1/connections": () => list(withWindow(intField("context_window", "Context window (tokens)", value, source)), LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": (body: Record<string, unknown>) => {
        value = (body.fields as Record<string, number>).context_window!;
        source = "saved";
        return { status: "ok" };
      },
    });
    const save = within(card()).getByRole("button", { name: "Save value" });
    expect(save).toBeDisabled();
    const input = within(card()).getByRole("spinbutton", { name: "Context window (tokens)" });
    await user.clear(input);
    await user.type(input, "8192");
    await user.click(save);
    expect(await within(card()).findByText("Source: saved")).toBeInTheDocument();
    expect(within(card()).getByRole("spinbutton", { name: "Context window (tokens)" })).toHaveValue(8192);
  });

  it("sends a number, not text", async () => {
    const put: unknown[] = [];
    const { user, card } = await open({
      "GET /v1/connections": () => list(withWindow(), LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": (body: unknown) => {
        put.push(body);
        return { status: "ok" };
      },
    });
    const input = within(card()).getByRole("spinbutton", { name: "Context window (tokens)" });
    await user.clear(input);
    await user.type(input, "32768");
    await user.click(within(card()).getByRole("button", { name: "Save value" }));
    expect(put).toEqual([{ fields: { context_window: 32768 } }]);
  });

  it("resets a saved value to the default with null", async () => {
    const put: unknown[] = [];
    const { user, card } = await open({
      "GET /v1/connections": () => list(withWindow(intField("context_window", "Context window (tokens)", 8192, "saved")), LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": (body: unknown) => {
        put.push(body);
        return { status: "ok" };
      },
    });
    await user.click(within(card()).getByRole("button", { name: "Reset to default" }));
    expect(put).toEqual([{ fields: { context_window: null } }]);
  });

  it("shows a locked value as read-only with the source and the reason", async () => {
    const locked = intField("context_window", "Context window (tokens)", 8192, "env", "Set from the environment or .env. Remove OLLAMA_CONTEXT_WINDOW there to edit it here.");
    const { card } = await open({ "GET /v1/connections": () => list(withWindow(locked), LLAMACPP, OPENROUTER) });
    expect(within(card()).queryByRole("spinbutton")).toBeNull();
    expect(card()).toHaveTextContent("Set from environment (read-only here)");
    expect(card()).toHaveTextContent("OLLAMA_CONTEXT_WINDOW");
    expect(within(card()).getByText("8192")).toBeInTheDocument();
  });

  it("shows one friendly line when the server refuses the value", async () => {
    const { user, card } = await open({
      "GET /v1/connections": () => list(withWindow(), LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": () => json({ status: "error", message: "The value must be a whole number from 2048 to 262144." }, 400),
    });
    const input = within(card()).getByRole("spinbutton", { name: "Context window (tokens)" });
    await user.clear(input);
    await user.type(input, "5");
    await user.click(within(card()).getByRole("button", { name: "Save value" }));
    const alert = await within(card()).findByRole("alert");
    expect(alert.textContent).not.toMatch(/\bHTTP\b|Traceback/);
  });
});
