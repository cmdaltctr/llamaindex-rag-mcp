import { createEvent, fireEvent, screen, waitFor, within } from "@testing-library/react";
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

const FILED_ONLY: FakeChatSeed = {
  folders: [{ folder_id: "f1", name: "Work", created_at: "t" }],
  chats: [{ chat_id: "c2", folder_id: "f1", title: "Filed chat" }],
};

describe("empty No folder group", () => {
  it("is hidden when no chat is outside a folder", async () => {
    setup(FILED_ONLY);
    await screen.findByText("Filed chat");
    expect(screen.queryByRole("region", { name: "No folder" })).toBeNull();
    expect(screen.getByRole("region", { name: "Folder Work" })).toBeInTheDocument();
  });

  it("shows as a drop target while a filed chat is dragged, and moves the chat out", async () => {
    const { store } = setup(FILED_ONLY);
    const row = (await screen.findByText("Filed chat")).closest("li")!;
    const dataTransfer = { setData: vi.fn(), getData: () => "c2", effectAllowed: "", dropEffect: "" };
    fireEvent.dragStart(row, { dataTransfer });
    const target = await screen.findByRole("region", { name: "No folder" });
    fireEvent.dragOver(target, { dataTransfer });
    fireEvent.drop(target, { dataTransfer });
    await waitFor(() => expect(store.chats.get("c2")?.folder_id).toBeNull());
  });

  it("hides again when the drag ends without a drop", async () => {
    setup(FILED_ONLY);
    const row = (await screen.findByText("Filed chat")).closest("li")!;
    fireEvent.dragStart(row, { dataTransfer: { setData: vi.fn(), getData: () => "c2", effectAllowed: "", dropEffect: "" } });
    await screen.findByRole("region", { name: "No folder" });
    fireEvent.dragEnd(row);
    await waitFor(() => expect(screen.queryByRole("region", { name: "No folder" })).toBeNull());
  });
});

describe("history list", () => {
  it("shows New folder and Select without a History heading", async () => {
    setup();
    await screen.findByRole("button", { name: "New folder" });
    expect(screen.queryByRole("heading", { name: "History" })).toBeNull();
    expect(screen.getByRole("button", { name: "Select" })).toBeInTheDocument();
  });

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

const FOLDERS: FakeChatSeed = {
  folders: [
    { folder_id: "f1", name: "Work", created_at: "t1" },
    { folder_id: "f2", name: "Home", created_at: "t2" },
    { folder_id: "f3", name: "Ideas", created_at: "t3" },
  ],
  chats: [{ chat_id: "c1", folder_id: null, title: "Loose chat" }],
};

type Half = "top" | "bottom";

/** Gives the target a 40px box and puts the pointer in its top or bottom half. */
function overFolder(target: HTMLElement, dataTransfer: object, half: Half, event: "dragOver" | "drop" = "dragOver") {
  target.getBoundingClientRect = () => ({ top: 100, bottom: 140, height: 40, left: 0, right: 200, width: 200, x: 0, y: 100, toJSON: () => ({}) });
  // jsdom has no DragEvent, so the pointer position is set on the plain event.
  const dragEvent = createEvent[event](target, { dataTransfer });
  Object.defineProperty(dragEvent, "clientY", { value: half === "top" ? 105 : 135 });
  fireEvent(target, dragEvent);
}

function startFolderDrag(name: string) {
  const dataTransfer = { setData: vi.fn(), getData: () => "", effectAllowed: "", dropEffect: "" };
  fireEvent.dragStart(screen.getByRole("button", { name: `Reorder folder ${name}` }), { dataTransfer });
  return dataTransfer;
}

function dragFolder(name: string, targetLabel: string, id: string, half: Half) {
  const dataTransfer = { ...startFolderDrag(name), getData: () => id };
  overFolder(group(targetLabel), dataTransfer, half);
  overFolder(group(targetLabel), dataTransfer, half, "drop");
}

const folderOrder = () => screen.getAllByRole("region", { name: /^Folder / }).map((region) => region.getAttribute("aria-label"));

describe("reordering folders", () => {
  it("shows a reorder handle on each folder only in select mode", async () => {
    const { user } = setup(FOLDERS);
    await screen.findByText("Loose chat");
    expect(screen.queryByRole("button", { name: /^Reorder folder/ })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Select" }));
    expect(screen.getAllByRole("button", { name: /^Reorder folder/ }).map((b) => b.getAttribute("aria-label"))).toEqual([
      "Reorder folder Work",
      "Reorder folder Home",
      "Reorder folder Ideas",
    ]);
    expect(within(group("No folder")).queryByRole("button", { name: /^Reorder/ })).toBeNull();
  });

  it("drops a folder above the target when the pointer is in its top half", async () => {
    const { user, store } = setup(FOLDERS);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    dragFolder("Ideas", "Folder Work", "f3", "top");
    await waitFor(() => expect([...store.folders.keys()]).toEqual(["f3", "f1", "f2"]));
    await waitFor(() => expect(folderOrder()).toEqual(["Folder Ideas", "Folder Work", "Folder Home"]));
  });

  it("drops a folder below the target when the pointer is in its bottom half", async () => {
    const { user, store } = setup(FOLDERS);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    dragFolder("Ideas", "Folder Work", "f3", "bottom");
    await waitFor(() => expect([...store.folders.keys()]).toEqual(["f1", "f3", "f2"]));
  });

  it("sends nothing when the drop leaves the order as it was", async () => {
    const { user, server } = setup(FOLDERS);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    dragFolder("Work", "Folder Home", "f1", "top");
    expect(server.find("PUT", "/v1/chat-folders/order")).toHaveLength(0);
  });

  it("draws a line on the side of the target where the folder will land", async () => {
    const { user } = setup(FOLDERS);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    const target = group("Folder Home");
    const dataTransfer = startFolderDrag("Work");
    overFolder(target, dataTransfer, "top");
    expect(target).toHaveAttribute("data-drop-edge", "before");
    overFolder(target, dataTransfer, "bottom");
    expect(target).toHaveAttribute("data-drop-edge", "after");
    fireEvent.dragLeave(target, { dataTransfer });
    expect(target).not.toHaveAttribute("data-drop-edge");
  });

  it("draws no line on the dragged folder itself or for a dragged chat", async () => {
    const { user } = setup(FOLDERS);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    const dataTransfer = startFolderDrag("Work");
    overFolder(group("Folder Work"), dataTransfer, "top");
    expect(group("Folder Work")).not.toHaveAttribute("data-drop-edge");
    fireEvent.dragEnd(screen.getByRole("button", { name: "Reorder folder Work" }), { dataTransfer });
    const chat = { setData: vi.fn(), getData: () => "c1", effectAllowed: "", dropEffect: "" };
    fireEvent.dragStart(screen.getByText("Loose chat").closest("li")!, { dataTransfer: chat });
    overFolder(group("Folder Home"), chat, "top");
    expect(group("Folder Home")).not.toHaveAttribute("data-drop-edge");
  });

  it("moves a folder one place with the arrow keys and keeps focus on its handle", async () => {
    const { user, store } = setup(FOLDERS);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    screen.getByRole("button", { name: "Reorder folder Work" }).focus();
    await user.keyboard("{ArrowDown}");
    await waitFor(() => expect([...store.folders.keys()]).toEqual(["f2", "f1", "f3"]));
    expect(screen.getByRole("button", { name: "Reorder folder Work" })).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    await waitFor(() => expect([...store.folders.keys()]).toEqual(["f1", "f2", "f3"]));
  });

  it("sends nothing when the first folder is moved up", async () => {
    const { user, server } = setup(FOLDERS);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    screen.getByRole("button", { name: "Reorder folder Work" }).focus();
    await user.keyboard("{ArrowUp}");
    expect(server.find("PUT", "/v1/chat-folders/order")).toHaveLength(0);
  });

  it("does not move a chat when a folder is dropped on a folder", async () => {
    const { user, store } = setup(FOLDERS);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    const dataTransfer = startFolderDrag("Home");
    overFolder(group("No folder"), dataTransfer, "top");
    expect(group("No folder")).not.toHaveAttribute("data-drop-edge");
    overFolder(group("No folder"), dataTransfer, "top", "drop");
    expect(store.chats.get("c1")?.folder_id).toBeNull();
    expect([...store.folders.keys()]).toEqual(["f1", "f2", "f3"]);
  });
});

describe("moving selected chats", () => {
  it("moves several selected chats into a folder in one step", async () => {
    const { user, store } = setup(THREE);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    await user.click(screen.getByRole("checkbox", { name: "Select One" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Two" }));
    await user.click(screen.getByRole("button", { name: "Move selected (2)" }));
    await user.click(await screen.findByRole("button", { name: "Work" }));
    await waitFor(() => expect([store.chats.get("c1")?.folder_id, store.chats.get("c2")?.folder_id]).toEqual(["f1", "f1"]));
    await waitFor(() => expect(within(group("Folder Work")).getByText("One")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Select" })).toBeInTheDocument();
  });

  it("takes selected chats out of their folder", async () => {
    const { user, store } = setup(THREE);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Three" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Four" }));
    await user.click(screen.getByRole("button", { name: "Move selected (2)" }));
    await user.click(await screen.findByRole("button", { name: "No folder" }));
    await waitFor(() => expect([store.chats.get("c3")?.folder_id, store.chats.get("c4")?.folder_id]).toEqual([null, null]));
  });

  it("sends no request for a chat already in the chosen folder", async () => {
    const { user, server } = setup(THREE);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    await user.click(screen.getByRole("checkbox", { name: "Select One" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Three" }));
    await user.click(screen.getByRole("button", { name: "Move selected (2)" }));
    await user.click(await screen.findByRole("button", { name: "Work" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Select" })).toBeInTheDocument());
    expect(server.find("PATCH", "/v1/chats/c3")).toHaveLength(0);
    expect(server.find("PATCH", "/v1/chats/c1")).toHaveLength(1);
  });

  it("is off until a chat is selected", async () => {
    const { user } = setup(THREE);
    await user.click(await screen.findByRole("button", { name: "Select" }));
    expect(screen.getByRole("button", { name: "Move selected (0)" })).toBeDisabled();
  });
});

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

  it("deletes one chat from its menu", async () => {
    const { user, store } = setup(THREE);
    await user.click(await screen.findByRole("button", { name: "More actions for Two" }));
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this chat?" });
    expect(within(dialog).getByText(/removes 1 chat\b/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Delete chat" }));
    await waitFor(() => expect(store.chats.has("c2")).toBe(false));
    expect(store.chats.size).toBe(3);
  });

  it("tells the view which chats went, so it can leave the open one", async () => {
    const { user, onRemoved } = setup(THREE);
    await user.click(await screen.findByRole("button", { name: "More actions for One" }));
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
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
