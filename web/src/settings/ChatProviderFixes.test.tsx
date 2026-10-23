import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Connection } from "../api/settings";
import { startApp } from "../test/startApp";
import { CHAT_READY, CONNECTIONS, OLLAMA, OPENROUTER, settingsServer } from "./test/fixtures";

const ANTHROPIC: Connection = {
  provider: "anthropic",
  display_name: "Anthropic",
  locality: "cloud",
  installed: false,
  install_hint: "uv sync --extra anthropic",
  fields: [{ ...OPENROUTER.fields[0]!, set: false, last4: null, source: "none" }],
  read_only: [],
  roles: [],
};
const OPENROUTER_NO_KEY: Connection = { ...OPENROUTER, fields: [{ ...OPENROUTER.fields[0]!, set: false, last4: null, source: "none" }] };

async function openForm(connections: Connection[]) {
  startApp("#/settings/chat", settingsServer({ "GET /v1/connections": () => ({ ...CONNECTIONS, connections }), "GET /v1/settings/chat": () => CHAT_READY }));
  await screen.findByRole("region", { name: "Chat" });
  await waitFor(() => expect(screen.queryByText("Loading Chat settings.")).toBeNull());
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Edit Chat model" }));
  return user;
}

function form() {
  return screen.getByRole("region", { name: "Answer model" });
}

describe("Provider fix lines", () => {
  it("disables a provider whose extra is not installed and links to its Integrations entry", async () => {
    const user = await openForm([OLLAMA, ANTHROPIC]);
    const fixes = within(form()).getByRole("list", { name: "Providers that cannot answer yet" });
    expect(fixes).toHaveTextContent("Anthropic is not installed.");
    expect(within(fixes).getByRole("link", { name: "Install Anthropic from Integrations" })).toHaveAttribute("href", "#/integrations/anthropic");
    expect(fixes).not.toHaveTextContent(/uv sync|uv tool install/);
    await user.click(within(form()).getByRole("combobox", { name: "Chat provider and model" }));
    expect(await screen.findByRole("option", { name: "Anthropic (not installed)" })).toHaveAttribute("aria-disabled", "true");
  });

  it("builds the link from the extra the server names", async () => {
    await openForm([OLLAMA, { ...ANTHROPIC, install_hint: null, extra: "anthropic" }]);
    const fixes = within(form()).getByRole("list", { name: "Providers that cannot answer yet" });
    expect(within(fixes).getByRole("link", { name: "Install Anthropic from Integrations" })).toHaveAttribute("href", "#/integrations/anthropic");
  });

  it("disables a provider with no key and links to its card under Settings > Providers", async () => {
    const user = await openForm([OLLAMA, OPENROUTER_NO_KEY]);
    const fixes = within(form()).getByRole("list", { name: "Providers that cannot answer yet" });
    expect(fixes).toHaveTextContent("OpenRouter has no key.");
    expect(within(fixes).getByRole("link", { name: /OpenRouter card/ })).toHaveAttribute("href", "#/settings/providers");
    await user.click(within(form()).getByRole("combobox", { name: "Chat provider and model" }));
    expect(await screen.findByRole("option", { name: "OpenRouter (no key)" })).toHaveAttribute("aria-disabled", "true");
  });

  it("shows no fix lines when every provider is ready", async () => {
    await openForm([OLLAMA, OPENROUTER]);
    expect(within(form()).queryByRole("list", { name: "Providers that cannot answer yet" })).toBeNull();
    expect(form()).not.toHaveTextContent(/not installed|has no key/);
  });
});
