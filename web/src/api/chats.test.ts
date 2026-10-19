import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "./client";
import type { AnswerResult } from "./documents";
import {
  appendChatTurn,
  createChat,
  createChatFolder,
  deleteChat,
  deleteChatFolder,
  deleteChats,
  getChat,
  listChats,
  moveChat,
  renameChatFolder,
} from "./chats";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function setup(body: unknown, status = 200) {
  const fetchImpl = vi.fn(async (input: string, init?: RequestInit) => {
    void input;
    void init;
    return json(body, status);
  });
  return { fetchImpl, api: createApiClient(fetchImpl) };
}

const CHAT = { chat_id: "c1", folder_id: null, title: "Q", created_at: "t", updated_at: "t" };
const FOLDER = { folder_id: "f1", name: "Work", created_at: "t" };

describe("chat API client", () => {
  it("lists folders and chats", async () => {
    const { api, fetchImpl } = setup({ status: "ok", folders: [FOLDER], chats: [CHAT] });
    expect(await listChats(api)).toEqual({ folders: [FOLDER], chats: [CHAT] });
    expect(fetchImpl.mock.calls[0]![0]).toBe("/v1/chats");
  });

  it("creates a chat with an optional folder", async () => {
    const { api, fetchImpl } = setup({ status: "ok", chat: CHAT }, 201);
    expect(await createChat(api, { title: "Q", folder_id: "f1" })).toEqual(CHAT);
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/chats");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ title: "Q", folder_id: "f1" });
  });

  it("reads one chat, encoding the id", async () => {
    const { api, fetchImpl } = setup({ status: "ok", chat: { ...CHAT, turns: [] } });
    expect((await getChat(api, "a/b")).turns).toEqual([]);
    expect(fetchImpl.mock.calls[0]![0]).toBe("/v1/chats/a%2Fb");
  });

  it("moves a chat out of its folder with null", async () => {
    const { api, fetchImpl } = setup({ status: "ok", chat: CHAT });
    await moveChat(api, "c1", null);
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/chats/c1");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ folder_id: null });
  });

  it("saves a turn", async () => {
    const { api, fetchImpl } = setup({ status: "ok", turn: { chat_id: "c1", position: 1, created_at: "t" } }, 201);
    const turn = await appendChatTurn(api, "c1", { collection: "docs", question: "q", answer: { status: "ok" } as AnswerResult });
    expect(turn.position).toBe(1);
    expect(fetchImpl.mock.calls[0]![0]).toBe("/v1/chats/c1/turns");
  });

  it("deletes one chat, many chats and a folder, and returns the counts", async () => {
    const counts = { status: "ok", chats: 2, folders: 0 };
    const one = setup({ ...counts, chats: 1 });
    expect(await deleteChat(one.api, "c1")).toEqual({ chats: 1, folders: 0 });
    expect(one.fetchImpl.mock.calls[0]![1]?.method).toBe("DELETE");
    const many = setup(counts);
    expect(await deleteChats(many.api, ["c1", "c2"])).toEqual({ chats: 2, folders: 0 });
    expect(many.fetchImpl.mock.calls[0]![0]).toBe("/v1/chats/delete");
    expect(JSON.parse(String(many.fetchImpl.mock.calls[0]![1]?.body))).toEqual({ chat_ids: ["c1", "c2"] });
    const folder = setup({ status: "ok", chats: 3, folders: 1 });
    expect(await deleteChatFolder(folder.api, "f1")).toEqual({ chats: 3, folders: 1 });
    expect(folder.fetchImpl.mock.calls[0]![0]).toBe("/v1/chat-folders/f1");
  });

  it("creates and renames folders", async () => {
    const created = setup({ status: "ok", folder: FOLDER }, 201);
    expect(await createChatFolder(created.api, "Work")).toEqual(FOLDER);
    const renamed = setup({ status: "ok", folder: { ...FOLDER, name: "Home" } });
    expect((await renameChatFolder(renamed.api, "f1", "Home")).name).toBe("Home");
    expect(renamed.fetchImpl.mock.calls[0]![1]?.method).toBe("PATCH");
  });
});
