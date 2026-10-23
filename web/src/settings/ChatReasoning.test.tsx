import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ChatSettings, Connection } from "../api/settings";
import { json, type Call } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { CHAT_READY, CONNECTIONS, JUDGE_SAVED, OLLAMA, OPENROUTER, settingsServer, urlField } from "./test/fixtures";

const GLM = "z-ai/glm-5.3-flash";
const GLM_LEVELS = { status: "ok", known: true, levels: ["max", "high", "low"], default: "max", mandatory: true };
const OPENAI_COMPATIBLE: Connection = {
  provider: "openai_compatible",
  display_name: "OpenAI-compatible",
  locality: "local",
  installed: true,
  install_hint: null,
  fields: [urlField("base_url", "Address", "http://127.0.0.1:1234/v1")],
  read_only: [],
  roles: [],
};
const OPENROUTER_CHAT: ChatSettings = { ...CHAT_READY, provider: "openrouter", model: GLM, reasoning: "", reasoning_locked: false, reasoning_lock_reason: null, reasoning_ignored: false };

/** Answers the levels route from the provider and model in the query string. */
function levels(call: Call) {
  const query = new URLSearchParams(call.path.split("?")[1] ?? "");
  return query.get("provider") === "openrouter" && query.get("model") === GLM ? GLM_LEVELS : { status: "ok", known: false };
}

async function openChat(handlers = {}) {
  const server = settingsServer({
    "GET /v1/connections": () => ({ ...CONNECTIONS, connections: [OLLAMA, OPENROUTER, OPENAI_COMPATIBLE] }),
    "GET /v1/settings/chat": () => OPENROUTER_CHAT,
    "GET /v1/settings/chat/reasoning-levels": (_body: unknown, call: Call) => levels(call),
    ...handlers,
  });
  startApp("#/settings/chat", server);
  await screen.findByRole("region", { name: "Chat" });
  await waitFor(() => expect(screen.queryByText("Loading Chat settings.")).toBeNull());
  return { server, user: userEvent.setup() };
}

function model() {
  return screen.getByRole("region", { name: "Answer model" });
}

describe("Chat reasoning level", () => {
  it("lists the catalogue levels with the provider default first and no none for an OpenRouter model", async () => {
    const { user, server } = await openChat();
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    const control = await within(model()).findByRole("combobox", { name: "Reasoning" });
    expect(control).toHaveTextContent("Provider default (max)");
    await user.click(control);
    const options = (await screen.findAllByRole("option")).map((option) => option.textContent);
    expect(options).toEqual(["Provider default (max)", "max", "high", "low"]);
    expect(options).not.toContain("none");
    expect(server.find("GET", "/v1/settings/chat/reasoning-levels")[0]?.path).toContain(`model=${encodeURIComponent(GLM)}`);
  });

  it("shows a text box for a provider without a catalogue", async () => {
    const { user } = await openChat();
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    await within(model()).findByRole("combobox", { name: "Reasoning" });
    await user.click(within(model()).getByRole("combobox", { name: "Chat provider and model" }));
    await user.click(await screen.findByRole("option", { name: "OpenAI-compatible" }));
    expect(await within(model()).findByRole("textbox", { name: "Reasoning" })).toBeInTheDocument();
    expect(within(model()).queryByRole("combobox", { name: "Reasoning" })).toBeNull();
  });

  it("saves the level with the provider and model in one write and shows it read-only", async () => {
    let state = OPENROUTER_CHAT;
    const { user, server } = await openChat({
      "GET /v1/settings/chat": () => state,
      "PUT /v1/settings/chat": (body: Record<string, unknown>) => {
        state = { ...state, reasoning: body.reasoning as string };
        return { status: "ok", revision: "r2" };
      },
    });
    expect(model()).toHaveTextContent("Reasoning: Provider default");
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    await user.click(await within(model()).findByRole("combobox", { name: "Reasoning" }));
    await user.click(await screen.findByRole("option", { name: "low" }));
    await user.click(within(model()).getByRole("button", { name: "Save" }));
    expect(await within(model()).findByText(/Reasoning:/)).toHaveTextContent("Reasoning: low");
    const puts = server.find("PUT", "/v1/settings/chat");
    expect(puts).toHaveLength(1);
    expect(puts[0]?.body).toEqual({ provider: "openrouter", model: GLM, reasoning: "low", revision: "r1" });
  });

  it("sends an empty level for Provider default and a typed level from the text box", async () => {
    const { user, server } = await openChat({
      "GET /v1/settings/chat": () => ({ ...OPENROUTER_CHAT, provider: "openai_compatible", model: "local", reasoning: "medium" }),
      "PUT /v1/settings/chat": () => ({ status: "ok", revision: "r2" }),
    });
    expect(model()).toHaveTextContent("Reasoning: medium");
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    const box = await within(model()).findByRole("textbox", { name: "Reasoning" });
    expect(box).toHaveValue("medium");
    await user.clear(box);
    await user.type(box, "high");
    await user.click(within(model()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(1));
    expect(server.find("PUT", "/v1/settings/chat")[0]?.body).toMatchObject({ reasoning: "high" });
  });

  it("says under the control when the provider ignores the level", async () => {
    const { user } = await openChat({ "GET /v1/settings/chat": () => ({ ...OPENROUTER_CHAT, reasoning_ignored: true }) });
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    await within(model()).findByRole("combobox", { name: "Reasoning" });
    expect(model()).toHaveTextContent(/this provider ignores the reasoning level/i);
  });

  it("takes the ignored note from the levels route for the provider in the form", async () => {
    const { user } = await openChat({ "GET /v1/settings/chat/reasoning-levels": () => ({ status: "ok", known: false, ignored: true }) });
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    await within(model()).findByRole("textbox", { name: "Reasoning" });
    await waitFor(() => expect(model()).toHaveTextContent(/this provider ignores the reasoning level/i));
  });

  it("shows a level locked by the environment read-only with the variable named and sends no level", async () => {
    const lock = "Set by ANSWER__REASONING in .env. Remove it to edit here.";
    const { user, server } = await openChat({
      "GET /v1/settings/chat": () => ({ ...OPENROUTER_CHAT, reasoning: "low", reasoning_locked: true, reasoning_lock_reason: lock }),
      "PUT /v1/settings/chat": () => ({ status: "ok", revision: "r2" }),
    });
    expect(model()).toHaveTextContent("ANSWER__REASONING");
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    const control = within(model()).getByRole("textbox", { name: "Reasoning" });
    expect(control).toHaveAttribute("readonly");
    expect(control).toHaveValue("low");
    expect(within(model()).queryByRole("combobox", { name: "Reasoning" })).toBeNull();
    expect(model()).toHaveTextContent(lock);
    await user.click(within(model()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(1));
    expect(server.find("PUT", "/v1/settings/chat")[0]?.body).not.toHaveProperty("reasoning");
  });

  it("shows the 409 that names ANSWER__REASONING when a save is refused", async () => {
    const message = "ANSWER__REASONING is set in .env, so the level cannot be saved here.";
    const { user } = await openChat({ "PUT /v1/settings/chat": () => json({ status: "error", message }, 409) });
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    await user.click(within(model()).getByRole("button", { name: "Save" }));
    expect(await within(model()).findByRole("alert")).toHaveTextContent("ANSWER__REASONING");
  });
});

describe("Judge reasoning level", () => {
  function judge() {
    return screen.getByRole("region", { name: "Claim check judge" });
  }

  it("has its own control, saves its level on the judge route and shows it read-only", async () => {
    const { user, server } = await openChat({
      "GET /v1/settings/judge": () => ({ ...JUDGE_SAVED, model: GLM, reasoning: "high" }),
      "PUT /v1/settings/judge": () => ({ status: "ok", revision: "r2" }),
    });
    await waitFor(() => expect(judge()).toHaveTextContent("Reasoning: high"));
    await user.click(within(judge()).getByRole("button", { name: "Edit claim check judge" }));
    const control = await within(judge()).findByRole("combobox", { name: "Reasoning" });
    expect(control).toHaveTextContent("high");
    await user.click(control);
    await user.click(await screen.findByRole("option", { name: "Provider default (max)" }));
    await user.click(within(judge()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/judge")).toHaveLength(1));
    expect(server.find("PUT", "/v1/settings/judge")[0]?.body).toEqual({ provider: "openrouter", model: GLM, reasoning: "", revision: "r1" });
    expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(0);
  });
});
