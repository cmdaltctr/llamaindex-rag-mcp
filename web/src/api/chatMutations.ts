/**
 * Writes for stored chats and folders. Each one refreshes the history list
 * (every key under `["chats"]`), so a rename, a move or a delete shows at once.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import {
  appendChatTurn,
  createChat,
  createChatFolder,
  deleteChat,
  deleteChatFolder,
  deleteChats,
  moveChat,
  renameChatFolder,
  reorderChatFolders,
  type ChatListing,
  type ChatTurnInput,
} from "./chats";
import { queryKeys } from "./queries";

function useRefreshChats() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.chats() });
}

export function useCreateChat() {
  const api = useApi();
  const refresh = useRefreshChats();
  return useMutation({
    mutationFn: (input: { title: string; folder_id?: string | null }) => createChat(api, input),
    onSuccess: refresh,
  });
}

export function useAppendChatTurn() {
  const api = useApi();
  const refresh = useRefreshChats();
  return useMutation({
    mutationFn: (input: { chatId: string; turn: ChatTurnInput }) => appendChatTurn(api, input.chatId, input.turn),
    onSuccess: refresh,
  });
}

export function useMoveChat() {
  const api = useApi();
  const refresh = useRefreshChats();
  return useMutation({
    mutationFn: (input: { chatId: string; folderId: string | null }) => moveChat(api, input.chatId, input.folderId),
    onSuccess: refresh,
  });
}

/** Moves several chats with one request each, then refreshes the listing once. */
export function useMoveChats() {
  const api = useApi();
  const refresh = useRefreshChats();
  return useMutation({
    mutationFn: async (input: { chatIds: string[]; folderId: string | null }) => {
      await Promise.all(input.chatIds.map((chatId) => moveChat(api, chatId, input.folderId)));
    },
    onSettled: refresh,
  });
}

export function useDeleteChat() {
  const api = useApi();
  const refresh = useRefreshChats();
  return useMutation({ mutationFn: (chatId: string) => deleteChat(api, chatId), onSuccess: refresh });
}

export function useDeleteChats() {
  const api = useApi();
  const refresh = useRefreshChats();
  return useMutation({ mutationFn: (chatIds: string[]) => deleteChats(api, chatIds), onSuccess: refresh });
}

export function useCreateChatFolder() {
  const api = useApi();
  const refresh = useRefreshChats();
  return useMutation({ mutationFn: (name: string) => createChatFolder(api, name), onSuccess: refresh });
}

export function useRenameChatFolder() {
  const api = useApi();
  const refresh = useRefreshChats();
  return useMutation({
    mutationFn: (input: { folderId: string; name: string }) => renameChatFolder(api, input.folderId, input.name),
    onSuccess: refresh,
  });
}

export function useDeleteChatFolder() {
  const api = useApi();
  const refresh = useRefreshChats();
  return useMutation({ mutationFn: (folderId: string) => deleteChatFolder(api, folderId), onSuccess: refresh });
}

/**
 * Saves a new folder order. The list shows the new order at once, so a moved
 * folder keeps its place and focus while the request runs; a failed save
 * puts the server's order back on the refresh.
 */
export function useReorderChatFolders() {
  const api = useApi();
  const queryClient = useQueryClient();
  const refresh = useRefreshChats();
  return useMutation({
    mutationFn: (folderIds: string[]) => reorderChatFolders(api, folderIds),
    onMutate: (folderIds) => {
      queryClient.setQueryData<ChatListing>(queryKeys.chats(), (current) => {
        if (current === undefined) return current;
        const byId = new Map(current.folders.map((folder) => [folder.folder_id, folder]));
        return { ...current, folders: folderIds.flatMap((id) => byId.get(id) ?? []) };
      });
    },
    onSettled: refresh,
  });
}
