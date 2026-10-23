import type { ChatFolder, ChatSummary, ChatTurnRecord } from "../api/chats";
import { json, type Call, type Handler } from "./fakeDocumentsServer";

interface StoredChat extends ChatSummary {
  turns: ChatTurnRecord[];
}

export interface FakeChatSeed {
  folders?: ChatFolder[];
  chats?: (Omit<ChatSummary, "created_at" | "updated_at"> & { turns?: ChatTurnRecord[] })[];
}

/**
 * An in-memory chat store behind the chat routes. Spread `handlers` into a
 * `documentsServer`; read `chats` and `folders` to see what the server holds.
 */
export function fakeChats(seed: FakeChatSeed = {}) {
  let next = 0;
  const folders = new Map<string, ChatFolder>((seed.folders ?? []).map((f) => [f.folder_id, { ...f }]));
  const chats = new Map<string, StoredChat>();
  (seed.chats ?? []).forEach((c, index) => {
    const stamp = `2026-10-18T10:00:${String(index).padStart(2, "0")}`;
    chats.set(c.chat_id, { ...c, turns: c.turns ?? [], created_at: stamp, updated_at: stamp });
  });

  const idOf = (call: Call, after: string) => decodeURIComponent(call.path.split("?")[0]!.split(`${after}/`)[1]!.split("/")[0]!);
  const summary = ({ turns, ...rest }: StoredChat): ChatSummary => {
    void turns;
    return rest;
  };
  const missing = () => json({ status: "error", message: "That chat or folder does not exist." }, 404);
  const countsFor = (c: number, f: number) => ({ status: "ok", chats: c, folders: f });

  const handlers: Record<string, Handler> = {
    "GET /v1/chats": () => ({
      status: "ok",
      folders: [...folders.values()],
      chats: [...chats.values()].map(summary).sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    }),
    "POST /v1/chats": (body) => {
      next += 1;
      const stamp = `2026-10-18T11:00:${String(next).padStart(2, "0")}`;
      const chat: StoredChat = {
        chat_id: `chat-${next}`,
        folder_id: (body.folder_id as string | null | undefined) ?? null,
        title: String(body.title),
        created_at: stamp,
        updated_at: stamp,
        turns: [],
      };
      chats.set(chat.chat_id, chat);
      return json({ status: "ok", chat: summary(chat) }, 201);
    },
    "POST /v1/chats/delete": (body) => {
      const ids = body.chat_ids as string[];
      if (ids.some((id) => !chats.has(id))) return missing();
      ids.forEach((id) => chats.delete(id));
      return countsFor(ids.length, 0);
    },
    "GET /v1/chats/:id": (_body, call) => {
      const chat = chats.get(idOf(call, "chats"));
      return chat === undefined ? missing() : { status: "ok", chat };
    },
    "PATCH /v1/chats/:id": (body, call) => {
      const chat = chats.get(idOf(call, "chats"));
      if (chat === undefined) return missing();
      chat.folder_id = body.folder_id as string | null;
      return { status: "ok", chat: summary(chat) };
    },
    "DELETE /v1/chats/:id": (_body, call) => {
      const id = idOf(call, "chats");
      return chats.delete(id) ? countsFor(1, 0) : missing();
    },
    "POST /v1/chats/:id/turns": (body, call) => {
      const chat = chats.get(idOf(call, "chats"));
      if (chat === undefined) return missing();
      const position = chat.turns.length + 1;
      chat.turns.push({
        position,
        collection: String(body.collection),
        question: String(body.question),
        answer: body.answer as ChatTurnRecord["answer"],
        created_at: "2026-10-18T12:00:00",
      });
      return json({ status: "ok", turn: { chat_id: chat.chat_id, position, created_at: "2026-10-18T12:00:00" } }, 201);
    },
    "POST /v1/chat-folders": (body) => {
      next += 1;
      const folder = { folder_id: `folder-${next}`, name: String(body.name), created_at: "2026-10-18T11:00:00" };
      folders.set(folder.folder_id, folder);
      return json({ status: "ok", folder }, 201);
    },
    "PATCH /v1/chat-folders/:id": (body, call) => {
      const folder = folders.get(idOf(call, "chat-folders"));
      if (folder === undefined) return missing();
      folder.name = String(body.name);
      return { status: "ok", folder };
    },
    "PUT /v1/chat-folders/order": (body) => {
      const ids = body.folder_ids as string[];
      if (ids.length !== folders.size || ids.some((id) => !folders.has(id))) return json({ status: "error", message: "The new order must name every folder exactly once." }, 400);
      const ordered = ids.map((id) => folders.get(id)!);
      folders.clear();
      ordered.forEach((folder) => folders.set(folder.folder_id, folder));
      return { status: "ok", folders: ordered };
    },
    "DELETE /v1/chat-folders/:id": (_body, call) => {
      const id = idOf(call, "chat-folders");
      if (!folders.delete(id)) return missing();
      const inside = [...chats.values()].filter((c) => c.folder_id === id);
      inside.forEach((c) => chats.delete(c.chat_id));
      return countsFor(inside.length, 1);
    },
  };

  return { handlers, chats, folders };
}
