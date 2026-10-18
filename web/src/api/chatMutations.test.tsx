import { useQuery } from "@tanstack/react-query";
import { act, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderHookWithProviders } from "../test/providers";
import { useApi } from "./ApiProvider";
import { useDeleteChats, useMoveChat } from "./chatMutations";
import { chatsQuery } from "./queries";

const LIST = () => ({ status: "ok", folders: [], chats: [] });

function mount<T>(server: ReturnType<typeof documentsServer>, hook: () => T) {
  return renderHookWithProviders(
    () => {
      const api = useApi();
      return { chats: useQuery(chatsQuery(api)), hook: hook() };
    },
    { fetchImpl: server.fetchImpl },
  );
}

const reads = (server: ReturnType<typeof documentsServer>) => server.find("GET", "/v1/chats").length;

describe("chat mutations refresh the history list", () => {
  it("reloads the list after a bulk delete", async () => {
    const server = documentsServer({
      "GET /v1/chats": LIST,
      "POST /v1/chats/delete": () => ({ status: "ok", chats: 2, folders: 0 }),
    });
    const { result } = mount(server, useDeleteChats);
    await waitFor(() => expect(result.current.chats.isSuccess).toBe(true));
    await act(() => result.current.hook.mutateAsync(["a", "b"]));
    await waitFor(() => expect(reads(server)).toBe(2));
  });

  it("reloads the list after a move", async () => {
    const server = documentsServer({
      "GET /v1/chats": LIST,
      "PATCH /v1/chats/c1": () => ({ status: "ok", chat: { chat_id: "c1", folder_id: "f1", title: "Q", created_at: "t", updated_at: "t" } }),
    });
    const { result } = mount(server, useMoveChat);
    await waitFor(() => expect(result.current.chats.isSuccess).toBe(true));
    await act(() => result.current.hook.mutateAsync({ chatId: "c1", folderId: "f1" }));
    await waitFor(() => expect(reads(server)).toBe(2));
  });
});
