import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ChatSummary } from "../api/chats";
import { fakeChats, type FakeChatSeed } from "../test/fakeChats";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { ChatHistory } from "./ChatHistory";

const SEED: FakeChatSeed = {
  folders: [{ folder_id: "f1", name: "Work", created_at: "t" }],
  chats: [
    { chat_id: "c1", folder_id: null, title: "Loose chat" },
    { chat_id: "c2", folder_id: "f1", title: "Filed chat" },
  ],
};

function setup(seed: FakeChatSeed = SEED) {
  const store = fakeChats(seed);
  const server = documentsServer(store.handlers);
  const onOpen = vi.fn<(chat: ChatSummary) => void>();
  const onRemoved = vi.fn<(chatIds: string[]) => void>();
  renderWithProviders(<ChatHistory activeChatId="c1" onOpen={onOpen} onRemoved={onRemoved} />, { fetchImpl: server.fetchImpl });
  return { store, server, onOpen, onRemoved, user: userEvent.setup() };
}

const group = (name: string) => screen.getByRole("region", { name });

/** A drag and drop with the data transfer a browser would give. */
function drag(chat: HTMLElement, target: HTMLElement, id: string) {
  const dataTransfer = { setData: vi.fn(), getData: () => id, effectAllowed: "", dropEffect: "" };
  fireEvent.dragStart(chat, { dataTransfer });
  fireEvent.dragOver(target, { dataTransfer });
  fireEvent.drop(target, { dataTransfer });
}

describe("history list", () => {
  it("groups chats under their folder and the No folder row", async () => {
    setup();
    expect(await within(await screen.findByRole("region", { name: "No folder" })).findByText("Loose chat")).toBeInTheDocument();
    expect(within(group("Folder Work")).getByText("Filed chat")).toBeInTheDocument();
    expect(within(group("No folder")).queryByText("Filed chat")).not.toBeInTheDocument();
  });

  it("opens a chat when its title is pressed", async () => {
    const { user, onOpen } = setup();
    await user.click(await screen.findByRole("button", { name: "Loose chat" }));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ chat_id: "c1" }));
  });

  it("says so when there are no chats", async () => {
    setup({});
    expect(await screen.findByText(/no chats yet/i)).toBeInTheDocument();
  });
});

describe("folders", () => {
  it("creates a folder from a name typed in the list", async () => {
    const { user, store } = setup();
    await user.click(await screen.findByRole("button", { name: "New folder" }));
    await user.type(screen.getByRole("textbox", { name: "Folder name" }), "Ideas{Enter}");
    await waitFor(() => expect([...store.folders.values()].map((f) => f.name)).toContain("Ideas"));
    expect(await screen.findByRole("region", { name: "Folder Ideas" })).toBeInTheDocument();
  });

  it("renames a folder", async () => {
    const { user, store } = setup();
    await user.click(await screen.findByRole("button", { name: "Rename folder Work" }));
    const field = screen.getByRole("textbox", { name: "Folder name" });
    await user.clear(field);
    await user.type(field, "Home{Enter}");
    await waitFor(() => expect(store.folders.get("f1")?.name).toBe("Home"));
    expect(await screen.findByRole("region", { name: "Folder Home" })).toBeInTheDocument();
  });

  it("keeps the old name when Escape is pressed while renaming", async () => {
    const { user, store } = setup();
    await user.click(await screen.findByRole("button", { name: "Rename folder Work" }));
    await user.type(screen.getByRole("textbox", { name: "Folder name" }), "X{Escape}");
    expect(store.folders.get("f1")?.name).toBe("Work");
    expect(screen.queryByRole("textbox", { name: "Folder name" })).not.toBeInTheDocument();
  });
});

describe("moving chats", () => {
  it("moves a chat into a folder when it is dropped on the folder", async () => {
    const { store } = setup();
    const row = (await screen.findByText("Loose chat")).closest("li")!;
    drag(row, group("Folder Work"), "c1");
    await waitFor(() => expect(store.chats.get("c1")?.folder_id).toBe("f1"));
    await waitFor(() => expect(within(group("Folder Work")).getByText("Loose chat")).toBeInTheDocument());
  });

  it("takes a chat out of its folder when it is dropped on the No folder row", async () => {
    const { store } = setup();
    const row = (await screen.findByText("Filed chat")).closest("li")!;
    drag(row, group("No folder"), "c2");
    await waitFor(() => expect(store.chats.get("c2")?.folder_id).toBeNull());
    await waitFor(() => expect(within(group("No folder")).getByText("Filed chat")).toBeInTheDocument());
  });

  it("moves a chat with the Move to menu, without a pointer drag", async () => {
    const { user, store } = setup();
    await user.click(await screen.findByRole("combobox", { name: "Move Loose chat to" }));
    await user.click(await screen.findByRole("option", { name: "Work" }));
    await waitFor(() => expect(store.chats.get("c1")?.folder_id).toBe("f1"));
  });

  it("offers No folder in the menu of a filed chat", async () => {
    const { user, store } = setup();
    await user.click(await screen.findByRole("combobox", { name: "Move Filed chat to" }));
    await user.click(await screen.findByRole("option", { name: "No folder" }));
    await waitFor(() => expect(store.chats.get("c2")?.folder_id).toBeNull());
  });
});


const THREE: FakeChatSeed = {
  folders: [{ folder_id: "f1", name: "Work", created_at: "t" }],
  chats: [
    { chat_id: "c1", folder_id: null, title: "One" },
    { chat_id: "c2", folder_id: null, title: "Two" },
    { chat_id: "c3", folder_id: "f1", title: "Three" },
    { chat_id: "c4", folder_id: "f1", title: "Four" },
  ],
};

describe("deleting chats", () => {
  it("deletes several selected chats after a count confirmation", async () => {
    const { user, store, onRemoved } = setup(THREE);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    await user.click(screen.getByRole("checkbox", { name: "Select One" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Three" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Four" }));
    await user.click(screen.getByRole("button", { name: "Delete selected (3)" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete 3 chats?" });
    expect(within(dialog).getByText(/removes 3 chats/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Delete 3 chats" }));
    await waitFor(() => expect([...store.chats.keys()]).toEqual(["c2"]));
    expect(onRemoved).toHaveBeenCalledWith(["c1", "c3", "c4"]);
    await waitFor(() => expect(screen.queryByText("Three")).not.toBeInTheDocument());
  });

  it("deletes nothing when the confirmation is cancelled", async () => {
    const { user, store, server } = setup(THREE);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Two" }));
    await user.click(screen.getByRole("button", { name: "Delete selected (1)" }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(store.chats.size).toBe(4);
    expect(server.find("POST", "/v1/chats/delete")).toHaveLength(0);
  });

  it("deletes one chat from its own button", async () => {
    const { user, store } = setup(THREE);
    await user.click(await screen.findByRole("button", { name: "Delete Two" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this chat?" });
    expect(within(dialog).getByText(/removes 1 chat\b/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Delete chat" }));
    await waitFor(() => expect(store.chats.has("c2")).toBe(false));
    expect(store.chats.size).toBe(3);
  });

  it("tells the view which chats went, so it can leave the open one", async () => {
    const { user, onRemoved } = setup(THREE);
    await user.click(await screen.findByRole("button", { name: "Delete One" }));
    await user.click(await screen.findByRole("button", { name: "Delete chat" }));
    await waitFor(() => expect(onRemoved).toHaveBeenCalledWith(["c1"]));
  });

  it("deletes a folder with the number of chats inside it in the prompt", async () => {
    const { user, store, onRemoved } = setup(THREE);
    await user.click(await screen.findByRole("button", { name: "Delete folder Work" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete folder Work?" });
    expect(within(dialog).getByText(/folder and 2 chats inside it/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Delete folder" }));
    await waitFor(() => expect(store.folders.size).toBe(0));
    expect([...store.chats.keys()]).toEqual(["c1", "c2"]);
    expect([...onRemoved.mock.calls[0]![0]].sort()).toEqual(["c3", "c4"]);
  });
});
