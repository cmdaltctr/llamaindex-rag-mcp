import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { startApp } from "../test/startApp";
import { settingsServer } from "./test/fixtures";

const CARD = "[data-slot='card']";
const INSET = "[data-slot='card-inset']";

const CONFIGURATION = {
  path: "~/.config/omrs/omrs.jsonc",
  revision: "r1",
  settings: [
    { key: "retrieval.top_k", value: 10, source: "default", applies: "restart", restart_pending: false, editable: true, read_only_reason: null, kind: "int", choices: null, min: 1, max: 100, nullable: false },
  ],
  problems: [],
  handover: { pending: false, folder: null },
};

async function openTab(route: string, title: string) {
  startApp(`#/settings/${route}`, settingsServer({ "GET /v1/settings/configuration": () => CONFIGURATION }));
  const heading = await screen.findByRole("heading", { level: 2, name: title });
  return heading.closest("section") as HTMLElement;
}

describe("every Settings tab uses cards", () => {
  it.each([
    ["appearance", "Appearance"],
    ["chat", "Chat"],
    ["log", "Server log"],
    ["runtime", "Runtime"],
    ["configuration", "Configuration"],
  ])("puts the content of %s in a card", async (route, title) => {
    const section = await openTab(route, title);
    await expect.poll(() => section.querySelectorAll(CARD).length).toBeGreaterThan(0);
  });

  it("shows the Chat model and the claim check judge as two cards, each row in its own mini card", async () => {
    const section = await openTab("chat", "Chat");
    const provider = await within(section).findByText("Chat provider");
    const judgeModel = await within(section).findByText("Judge model");
    const chatCard = provider.closest(CARD);
    const judgeCard = judgeModel.closest(CARD);
    expect(chatCard).not.toBeNull();
    expect(judgeCard).not.toBeNull();
    expect(chatCard).not.toBe(judgeCard);
    expect(provider.closest(INSET)).not.toBeNull();
    expect(within(section).getByText("Chat model").closest(INSET)).not.toBe(provider.closest(INSET));
    expect(judgeModel.closest(INSET)).not.toBeNull();
  });

  it("shows the workspace folder, file access and upload limit as three cards", async () => {
    const section = await openTab("workspace", "Workspace");
    for (const name of ["Workspace folder", "File access", "Upload limit"]) {
      const heading = await within(section).findByRole("heading", { level: 3, name });
      expect(heading.closest(CARD)).not.toBeNull();
    }
  });

  it("puts the theme choice in a mini card", async () => {
    const section = await openTab("appearance", "Appearance");
    expect(within(section).getByRole("combobox").closest(INSET)).not.toBeNull();
  });

  it("shows each Configuration setting in its own mini card inside a block card", async () => {
    const section = await openTab("configuration", "Configuration");
    const key = await within(section).findByText("retrieval.top_k");
    expect(key.closest(INSET)).not.toBeNull();
    expect(key.closest(CARD)).not.toBeNull();
  });
});
