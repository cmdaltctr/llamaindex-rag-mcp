import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ChatSummary } from "../api/chats";
import { fakeChats, type FakeChatSeed } from "../test/fakeChats";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { ChatHistory } from "./ChatHistory";

const SEED: FakeChatSeed = {
  folders: [
    { folder_id: "f1", name: "Work", created_at: "t" },
    { folder_id: "f2", name: "Ideas", created_at: "t" },
  ],
  chats: [
    { chat_id: "c1", folder_id: null, title: "Loose chat" },
    { chat_id: "c2", folder_id: "f1", title: "Filed chat" },
  ],
};

function setup(seed: FakeChatSeed = SEED) {
  const store = fakeChats(seed);
  const server = documentsServer(store.handlers);
  renderWithProviders(<ChatHistory activeChatId="c1" onOpen={vi.fn<(chat: ChatSummary) => void>()} onRemoved={vi.fn()} />, {
    fetchImpl: server.fetchImpl,
  });
  return { store, user: userEvent.setup() };
}

async function rightClick(title: string) {
  const row = (await screen.findByText(title)).closest("li")!;
  fireEvent.contextMenu(row);
}

describe("right-click menu on a chat", () => {
  it("replaces the Move to dropdown on every row", async () => {
    setup();
    await screen.findByText("Loose chat");
    expect(screen.queryByRole("combobox", { name: /^Move/ })).toBeNull();
  });

  it("has no bin button on a row, so a stray click cannot delete a chat", async () => {
    setup();
    await screen.findByText("Loose chat");
    expect(screen.queryByRole("button", { name: "Delete Loose chat" })).toBeNull();
  });

  it("offers Move to a folder and Delete on right-click", async () => {
    setup();
    await rightClick("Loose chat");
    expect(await screen.findByRole("menuitem", { name: "Move to a folder" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
  });

  it("lists the folders that exist in a side menu and moves the chat", async () => {
    const { user, store } = setup();
    await rightClick("Loose chat");
    await user.click(await screen.findByRole("menuitem", { name: "Move to a folder" }));
    expect(await screen.findByRole("menuitemradio", { name: "No folder" })).toBeChecked();
    expect(screen.getByRole("menuitemradio", { name: "Ideas" })).not.toBeChecked();
    // jsdom has no layout, so Radix closes the side menu on a pointer move; a click on the item stands in for the pick.
    fireEvent.click(screen.getByRole("menuitemradio", { name: "Work" }));
    await waitFor(() => expect(store.chats.get("c1")?.folder_id).toBe("f1"));
  });

  it("marks the current folder and can move a filed chat back to No folder", async () => {
    const { user, store } = setup();
    await rightClick("Filed chat");
    await user.click(await screen.findByRole("menuitem", { name: "Move to a folder" }));
    expect(await screen.findByRole("menuitemradio", { name: "Work" })).toBeChecked();
    fireEvent.click(screen.getByRole("menuitemradio", { name: "No folder" }));
    await waitFor(() => expect(store.chats.get("c2")?.folder_id).toBeNull());
  });

  it("shows No folder alone when no folder has been made", async () => {
    const { user } = setup({ folders: [], chats: [{ chat_id: "c1", folder_id: null, title: "Loose chat" }] });
    await rightClick("Loose chat");
    await user.click(await screen.findByRole("menuitem", { name: "Move to a folder" }));
    const options = await screen.findAllByRole("menuitemradio");
    expect(options.map((option) => option.textContent)).toEqual(["No folder"]);
  });

  it("asks before it deletes from the menu", async () => {
    const { user, store } = setup();
    await rightClick("Loose chat");
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this chat?" });
    expect(store.chats.has("c1")).toBe(true);
    await user.click(within(dialog).getByRole("button", { name: "Delete chat" }));
    await waitFor(() => expect(store.chats.has("c1")).toBe(false));
  });

  it("opens the same menu from the more button, for keyboard and touch", async () => {
    const { user } = setup();
    await user.click(await screen.findByRole("button", { name: "More actions for Loose chat" }));
    expect(await screen.findByRole("menuitem", { name: "Move to a folder" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
  });
});
