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

describe("side cards while the chat scrolls", () => {
  it("keeps both cards in view on a wide screen", async () => {
    setup();
    await grid();
    for (const name of ["Chat history", "Knowledge base panel"]) {
      expect(screen.getByRole("complementary", { name })).toHaveClass("lg:sticky", "lg:top-16", "lg:overflow-y-auto");
    }
  });

  it("pins the knowledge base card under the top bar in the single column", async () => {
    setup();
    // A sticky grid item cannot leave its own row, so the single column is a flex column.
    expect(await grid()).toHaveClass("flex", "flex-col", "lg:grid");
    expect(await grid()).not.toHaveClass("grid");
    expect(screen.getByRole("complementary", { name: "Knowledge base panel" })).toHaveClass("sticky", "top-12");
  });
});

describe("folding the knowledge base card in the single column", () => {
  it("has a fold chevron that shows only below the wide layout", async () => {
    setup();
    await grid();
    const fold = screen.getByRole("button", { name: "Fold knowledge bases" });
    expect(fold).toHaveClass("lg:hidden");
    expect(fold).toHaveAttribute("aria-expanded", "true");
  });

  it("folds the card to its icon row and opens it again", async () => {
    const user = setup();
    await grid();
    const panel = screen.getByRole("complementary", { name: "Knowledge base panel" });
    const views = within(panel).getByTestId("knowledge-panel-views");
    expect(views).not.toHaveClass("max-lg:hidden");
    await user.click(screen.getByRole("button", { name: "Fold knowledge bases" }));
    expect(views).toHaveClass("max-lg:hidden");
    expect(within(panel).getByRole("tablist", { name: "Knowledge base panel views" })).toBeInTheDocument();
    const unfold = screen.getByRole("button", { name: "Unfold knowledge bases" });
    expect(unfold).toHaveAttribute("aria-expanded", "false");
    await user.click(unfold);
    expect(views).not.toHaveClass("max-lg:hidden");
  });

  it("opens a folded card when a tab is chosen", async () => {
    const user = setup();
    await grid();
    await user.click(screen.getByRole("button", { name: "Fold knowledge bases" }));
    await user.click(screen.getByRole("tab", { name: "Citations" }));
    expect(screen.getByTestId("knowledge-panel-views")).not.toHaveClass("max-lg:hidden");
  });
});
