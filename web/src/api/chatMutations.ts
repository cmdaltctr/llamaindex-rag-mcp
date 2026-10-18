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
