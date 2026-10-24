import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Integration } from "../api/integrations";
import type { Connection } from "../api/settings";
import { startApp } from "../test/startApp";
import { CONNECTIONS, OLLAMA, OPENROUTER, settingsServer } from "./test/fixtures";

const ANTHROPIC: Connection = {
  provider: "anthropic",
  display_name: "Anthropic",
  locality: "cloud",
  installed: false,
  install_hint: "uv sync --extra anthropic",
  extra: "anthropic",
  fields: [{ ...OPENROUTER.fields[0]!, set: false, last4: null, source: "none" }],
  read_only: [],
  roles: [],
};

const ANTHROPIC_ENTRY: Integration = {
  id: "anthropic",
  name: "Anthropic provider",
  purpose: "Chat answers from Anthropic models.",
  extra: "anthropic",
  install_command: "uv sync --extra anthropic",
  pip_command: 'pip install "omrs[anthropic]"',
  availability: "not-installed",
  installable: false,
  install_reason: "not-uv-tool",
  packages: ["llama-index-llms-anthropic>=0.11.0"],
  install_caution: null,
};

async function openProviders(connections: Connection[]) {
  startApp(
    "#/settings/providers",
    settingsServer({
      "GET /v1/connections": () => ({ ...CONNECTIONS, connections }),
      "GET /v1/integrations": () => ({ status: "ok", install_type: "checkout", integrations: [ANTHROPIC_ENTRY] }),
    }),
  );
  await screen.findByRole("heading", { level: 3, name: "Ollama" });
}

const card = (name: string) => screen.getByRole("region", { name });

describe("Provider card link to Integrations", () => {
  it("shows Not installed and a link to the anthropic entry, with no install command", async () => {
    await openProviders([OLLAMA, ANTHROPIC]);
    const anthropic = card("Anthropic");
    expect(anthropic).toHaveTextContent("Not installed");
    expect(within(anthropic).getByRole("link", { name: "Install Anthropic from Integrations" })).toHaveAttribute("href", "#/integrations/anthropic");
    expect(anthropic).not.toHaveTextContent(/uv sync|uv tool install|pip install/);
  });

  it("takes the extra from an older server's install hint", async () => {
    await openProviders([OLLAMA, { ...ANTHROPIC, extra: undefined }]);
    expect(within(card("Anthropic")).getByRole("link", { name: "Install Anthropic from Integrations" })).toHaveAttribute("href", "#/integrations/anthropic");
  });

  it("shows no link on an installed provider", async () => {
    await openProviders([OLLAMA, { ...ANTHROPIC, installed: true, install_hint: null }]);
    const anthropic = card("Anthropic");
    expect(within(anthropic).queryByRole("link", { name: /from Integrations/ })).toBeNull();
    expect(anthropic).not.toHaveTextContent("Not installed");
  });

  it("opens the Integrations page with the entry focused", async () => {
    await openProviders([OLLAMA, ANTHROPIC]);
    await userEvent.setup().click(within(card("Anthropic")).getByRole("link", { name: "Install Anthropic from Integrations" }));
    await screen.findByRole("heading", { level: 3, name: "Anthropic provider" });
    await waitFor(() => expect(document.activeElement?.id).toBe("integration-anthropic"));
  });
});
