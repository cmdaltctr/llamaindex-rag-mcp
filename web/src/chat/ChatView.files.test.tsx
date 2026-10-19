import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

function setup(hash = "#/chat/documents", handlers = {}) {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const { server } = startApp(hash, documentsServer(handlers));
  return { server, user: userEvent.setup() };
}

async function panel() {
  return within(await screen.findByRole("complementary", { name: "Knowledge base panel" }));
}

describe("file list under a knowledge base chip", () => {
  it("shows no file list until the chevron is pressed", async () => {
    const { server } = setup();
    const kb = await panel();
    const toggle = await kb.findByRole("button", { name: "Show files in documents" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(kb.queryByRole("list", { name: "Files in documents" })).toBeNull();
    expect(server.find("GET", "/v1/collections/documents/documents")).toHaveLength(0);
  });

  it("lists file names, not chunks, when the chevron is pressed", async () => {
    const { user } = setup();
    const kb = await panel();
    await user.click(await kb.findByRole("button", { name: "Show files in documents" }));
    const list = await kb.findByRole("list", { name: "Files in documents" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual(["present.md", "gone.md", "unknown.md"]);
    expect(items[0]).toHaveAttribute("title", "/srv/docs/present.md");
    expect(list.textContent).not.toMatch(/chunk/i);
    expect(kb.getByRole("button", { name: "Hide files in documents" })).toHaveAttribute("aria-expanded", "true");
  });

  it("points down when the list is closed and up when it is open, so it differs from the card's hide chevron", async () => {
    const { user } = setup();
    const kb = await panel();
    const toggle = await kb.findByRole("button", { name: "Show files in documents" });
    expect(toggle.querySelector("svg")).toHaveClass("lucide-chevron-down");
    await user.click(toggle);
    const open = await kb.findByRole("button", { name: "Hide files in documents" });
    expect(open.querySelector("svg")).toHaveClass("lucide-chevron-up");
  });

  it("closes the list when the chevron is pressed again", async () => {
    const { user } = setup();
    const kb = await panel();
    await user.click(await kb.findByRole("button", { name: "Show files in documents" }));
    await kb.findByRole("list", { name: "Files in documents" });
    await user.click(kb.getByRole("button", { name: "Hide files in documents" }));
    expect(kb.queryByRole("list", { name: "Files in documents" })).toBeNull();
  });

  it("keeps the chip itself for switching collection", async () => {
    const { user } = setup();
    const kb = await panel();
    await user.click(await kb.findByRole("button", { name: "Show files in documents" }));
    await user.click(kb.getByRole("button", { name: /^notes/ }));
    expect(window.location.hash).toBe("#/chat/notes");
    expect(kb.queryByRole("list", { name: "Files in documents" })).not.toBeNull();
  });

  it("says so when the collection has no files", async () => {
    const { user } = setup("#/chat/notes");
    const kb = await panel();
    await user.click(await kb.findByRole("button", { name: "Show files in notes" }));
    expect(await kb.findByText("No files in this knowledge base.")).toBeInTheDocument();
  });

  it("shows a friendly line and a retry when the list fails", async () => {
    const { user } = setup("#/chat/documents", {
      "GET /v1/collections/documents/documents": () => json({ status: "error", message: "store offline" }, 500),
    });
    const kb = await panel();
    await user.click(await kb.findByRole("button", { name: "Show files in documents" }));
    expect(await kb.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("offers the chevron on the picker shown before a knowledge base is chosen", async () => {
    setup("#/chat");
    expect(await screen.findByRole("button", { name: "Show files in documents" })).toBeInTheDocument();
  });
});
