/**
 * Typed client for the stored-chat routes of the local `/v1` API (ADR-082).
 *
 * Shapes follow `src/omrs/transports/api/routes/chats.py` and the `Chat*`
 * schemas in `openapi.yaml`. The routes need the browser session. A chat that
 * the server no longer knows gives a 404 `ApiError`.
 */
import type { AnswerResult } from "./documents";
import type { ApiClient, CallOptions } from "./client";

export interface ChatFolder {
  folder_id: string;
  name: string;
  created_at: string;
}

export interface ChatSummary {
  chat_id: string;
  folder_id: string | null;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatTurnRecord {
  position: number;
  collection: string;
  question: string;
  answer: AnswerResult;
  created_at: string;
}

export interface ChatDetail extends ChatSummary {
  turns: ChatTurnRecord[];
}

export interface ChatListing {
  folders: ChatFolder[];
  chats: ChatSummary[];
}

export interface ChatTurnInput {
  collection: string;
  question: string;
  answer: AnswerResult;
}

export interface DeleteCounts {
  chats: number;
  folders: number;
}

const chatPath = (chatId: string): string => `/v1/chats/${encodeURIComponent(chatId)}`;
const folderPath = (folderId: string): string => `/v1/chat-folders/${encodeURIComponent(folderId)}`;

function counts(body: DeleteCounts & { status: string }): DeleteCounts {
  return { chats: body.chats, folders: body.folders };
}

export async function listChats(api: ApiClient, options: CallOptions = {}): Promise<ChatListing> {
  const body = await api.request<ChatListing & { status: string }>("GET", "/v1/chats", { signal: options.signal });
  return { folders: body.folders, chats: body.chats };
}

export async function getChat(api: ApiClient, chatId: string, options: CallOptions = {}): Promise<ChatDetail> {
  return (await api.request<{ chat: ChatDetail }>("GET", chatPath(chatId), { signal: options.signal })).chat;
}

export async function createChat(
  api: ApiClient,
  input: { title: string; folder_id?: string | null },
  options: CallOptions = {},
): Promise<ChatSummary> {
  return (await api.request<{ chat: ChatSummary }>("POST", "/v1/chats", { body: input, signal: options.signal })).chat;
}

/** `folderId` null moves the chat out of any folder. */
export async function moveChat(api: ApiClient, chatId: string, folderId: string | null, options: CallOptions = {}): Promise<ChatSummary> {
  const body = { folder_id: folderId };
  return (await api.request<{ chat: ChatSummary }>("PATCH", chatPath(chatId), { body, signal: options.signal })).chat;
}

export async function appendChatTurn(
  api: ApiClient,
  chatId: string,
  input: ChatTurnInput,
  options: CallOptions = {},
): Promise<{ chat_id: string; position: number; created_at: string }> {
  const body = await api.request<{ turn: { chat_id: string; position: number; created_at: string } }>(
    "POST",
    `${chatPath(chatId)}/turns`,
    { body: input, signal: options.signal },
  );
  return body.turn;
}

export async function deleteChat(api: ApiClient, chatId: string, options: CallOptions = {}): Promise<DeleteCounts> {
  return counts(await api.request("DELETE", chatPath(chatId), { signal: options.signal }));
}

export async function deleteChats(api: ApiClient, chatIds: string[], options: CallOptions = {}): Promise<DeleteCounts> {
  return counts(await api.request("POST", "/v1/chats/delete", { body: { chat_ids: chatIds }, signal: options.signal }));
}

export async function createChatFolder(api: ApiClient, name: string, options: CallOptions = {}): Promise<ChatFolder> {
  return (await api.request<{ folder: ChatFolder }>("POST", "/v1/chat-folders", { body: { name }, signal: options.signal })).folder;
}

export async function renameChatFolder(api: ApiClient, folderId: string, name: string, options: CallOptions = {}): Promise<ChatFolder> {
  return (await api.request<{ folder: ChatFolder }>("PATCH", folderPath(folderId), { body: { name }, signal: options.signal })).folder;
}

/** Deletes the folder and every chat inside it. */
export async function deleteChatFolder(api: ApiClient, folderId: string, options: CallOptions = {}): Promise<DeleteCounts> {
  return counts(await api.request("DELETE", folderPath(folderId), { signal: options.signal }));
}
