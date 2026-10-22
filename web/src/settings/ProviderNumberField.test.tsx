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

async function type(user: ReturnType<typeof userEvent.setup>, card: () => HTMLElement, text: string) {
  await user.click(within(card()).getByRole("button", { name: "Edit Context window (tokens)" }));
  const input = within(card()).getByRole("spinbutton", { name: "Context window (tokens)" });
  await user.clear(input);
  await user.type(input, text);
  return input;
}

describe("Integer field (Ollama context window)", () => {
  it("shows the value and the default source, with no input until Edit", async () => {
    const { card } = await open({ "GET /v1/connections": () => list(withWindow(), LLAMACPP, OPENROUTER) });
    expect(within(card()).getByText("16384")).toBeInTheDocument();
    expect(within(card()).getAllByText("default")).toHaveLength(2);
    expect(within(card()).queryByRole("spinbutton")).toBeNull();
  });

  it("opens a number input filled with the value, with its bounds", async () => {
    const { user, card } = await open({ "GET /v1/connections": () => list(withWindow(), LLAMACPP, OPENROUTER) });
    await user.click(within(card()).getByRole("button", { name: "Edit Context window (tokens)" }));
    const input = within(card()).getByRole("spinbutton", { name: "Context window (tokens)" });
    expect(input).toHaveValue(16384);
    expect(input).toHaveAttribute("min", "2048");
    expect(input).toHaveAttribute("max", "262144");
    expect(within(card()).queryByRole("button", { name: "Use default" })).toBeNull();
    expect(within(card()).getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("saves a whole number and shows the value and source the server returns", async () => {
    let value = 16384;
    let source: "default" | "config-file" = "default";
    const { user, card } = await open({
      "GET /v1/connections": () => list(withWindow(intField("context_window", "Context window (tokens)", value, source)), LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": (body: Record<string, unknown>) => {
        value = (body.fields as Record<string, number>).context_window!;
        source = "config-file";
        return { status: "ok", revision: "r2" };
      },
    });
    await type(user, card, "32768");
    await user.click(within(card()).getByRole("button", { name: "Save" }));
    expect(await within(card()).findByText("from omrs.jsonc")).toBeInTheDocument();
    expect(within(card()).getByText("32768")).toBeInTheDocument();
    expect(within(card()).queryByRole("spinbutton")).toBeNull();
  });

  it("sends a number, not text, with the revision", async () => {
    const put: unknown[] = [];
    const { user, card } = await open({
      "GET /v1/connections": () => list(withWindow(), LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": (body: unknown) => {
        put.push(body);
        return { status: "ok", revision: "r2" };
      },
    });
    await type(user, card, "32768");
    await user.click(within(card()).getByRole("button", { name: "Save" }));
    expect(put).toEqual([{ fields: { context_window: 32768 }, revision: "r1" }]);
  });

  it("shows the friendly range line and saves nothing when the value is out of range", async () => {
    const put: unknown[] = [];
    const { user, card } = await open({
      "GET /v1/connections": () => list(withWindow(), LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": (body: unknown) => {
        put.push(body);
        return { status: "ok", revision: "r2" };
      },
    });
    await type(user, card, "1000");
    await user.click(within(card()).getByRole("button", { name: "Save" }));
    expect(within(card()).getByText("Enter 2,048 to 262,144.")).toBeInTheDocument();
    expect(put).toEqual([]);
  });

  it("returns a file value to the default with null", async () => {
    const put: unknown[] = [];
    const { user, card } = await open({
      "GET /v1/connections": () => list(withWindow(intField("context_window", "Context window (tokens)", 8192, "config-file")), LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": (body: unknown) => {
        put.push(body);
        return { status: "ok", revision: "r2" };
      },
    });
    await user.click(within(card()).getByRole("button", { name: "Edit Context window (tokens)" }));
    await user.click(within(card()).getByRole("button", { name: "Use default" }));
    expect(put).toEqual([{ fields: { context_window: null }, revision: "r1" }]);
  });

  it.each(["env", "dotenv"] as const)("shows a value set by %s with where it is set and offers no Edit", async (source) => {
    const locked = intField("context_window", "Context window (tokens)", 8192, source, "Remove OLLAMA_CONTEXT_WINDOW from the environment or .env to edit it here.");
    const { card } = await open({ "GET /v1/connections": () => list(withWindow(locked), LLAMACPP, OPENROUTER) });
    expect(within(card()).queryByRole("spinbutton")).toBeNull();
    expect(within(card()).queryByRole("button", { name: "Edit Context window (tokens)" })).toBeNull();
    expect(card()).toHaveTextContent(source === "env" ? "Set in the environment. Change it there." : "Set in .env. Change it there.");
    expect(card()).toHaveTextContent("OLLAMA_CONTEXT_WINDOW");
    expect(within(card()).getByText("8192")).toBeInTheDocument();
  });

  it("shows the rule message when the server refuses the value", async () => {
    const message = "The value must be a whole number from 2048 to 262144.";
    const { user, card } = await open({
      "GET /v1/connections": () => list(withWindow(), LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": () => json({ status: "error", message }, 400),
    });
    await type(user, card, "5000");
    await user.click(within(card()).getByRole("button", { name: "Save" }));
    const alert = await within(card()).findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(alert.textContent).not.toMatch(/\bHTTP\b|Traceback/);
  });
});
