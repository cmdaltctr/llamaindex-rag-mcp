import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

const OPEN = "lg:grid-cols-[16rem_minmax(0,1fr)_16rem]";
const LEFT_HIDDEN = "lg:grid-cols-[2.25rem_minmax(0,1fr)_16rem]";
const RIGHT_HIDDEN = "lg:grid-cols-[16rem_minmax(0,1fr)_2.25rem]";
const SHOW = /^Show (chat history|knowledge bases)$/;
const BOTH_HIDDEN = "lg:grid-cols-[2.25rem_minmax(0,1fr)_2.25rem]";

function setup() {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  startApp("#/chat/documents", documentsServer());
  return userEvent.setup();
}

async function grid() {
  return screen.findByTestId("chat-grid");
}

describe("hideable cards beside the chat", () => {
  it("shows both cards with a hide chevron and no show button", async () => {
    setup();
    const layout = await grid();
    expect(layout.className).toContain(OPEN);
    expect(screen.getByTestId("chat-column").className).toContain("max-w-[48rem]");
    expect(screen.getByRole("button", { name: "Hide chat history" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Hide knowledge bases" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("button", { name: SHOW })).toBeNull();
  });

  it("hides the knowledge base card, leaves a show button and widens the chat", async () => {
    const user = setup();
    await grid();
    await user.click(screen.getByRole("button", { name: "Hide knowledge bases" }));
    expect((await grid()).className).toContain(RIGHT_HIDDEN);
    expect(screen.getByTestId("chat-column").className).toContain("max-w-[64rem]");
    expect(screen.getByRole("button", { name: "Show knowledge bases" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("complementary", { name: "Knowledge base panel" }).querySelector("[data-collapsed]")).toHaveAttribute("data-collapsed", "true");
  });

  it("hides the history card on its own", async () => {
    const user = setup();
    await grid();
    await user.click(screen.getByRole("button", { name: "Hide chat history" }));
    expect((await grid()).className).toContain(LEFT_HIDDEN);
    expect(screen.getByRole("button", { name: "Show chat history" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide knowledge bases" })).toBeInTheDocument();
  });

  it("widens the chat further when both cards are hidden, and restores it", async () => {
    const user = setup();
    await grid();
    await user.click(screen.getByRole("button", { name: "Hide chat history" }));
    await user.click(screen.getByRole("button", { name: "Hide knowledge bases" }));
    expect((await grid()).className).toContain(BOTH_HIDDEN);
    expect(screen.getByTestId("chat-column").className).toContain("max-w-[80rem]");
    await user.click(screen.getByRole("button", { name: "Show chat history" }));
    await user.click(screen.getByRole("button", { name: "Show knowledge bases" }));
    expect((await grid()).className).toContain(OPEN);
    expect(screen.getByTestId("chat-column").className).toContain("max-w-[48rem]");
    expect(screen.queryByRole("button", { name: SHOW })).toBeNull();
  });

  it("keeps the chosen knowledge base and its chips while the card is hidden", async () => {
    const user = setup();
    await grid();
    await user.click(screen.getByRole("button", { name: "Hide knowledge bases" }));
    expect(window.location.hash).toBe("#/chat/documents");
    const panel = within(screen.getByRole("complementary", { name: "Knowledge base panel" }));
    expect(panel.getByRole("button", { name: /^documents/ })).toHaveAttribute("aria-pressed", "true");
  });
});
