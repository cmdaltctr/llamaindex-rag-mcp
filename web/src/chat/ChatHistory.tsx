import { useQuery } from "@tanstack/react-query";
import { FolderPlus, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { useApi } from "../api/ApiProvider";
import { useCreateChatFolder, useDeleteChat, useDeleteChatFolder, useDeleteChats, useMoveChat, useRenameChatFolder } from "../api/chatMutations";
import type { ChatFolder, ChatSummary } from "../api/chats";
import { chatsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { ChatFolderSection } from "./ChatFolderSection";
import { ChatRow } from "./ChatRow";
import { DeleteChatsDialog, type DeleteRequest } from "./DeleteChatsDialog";
import { FolderNameField } from "./FolderNameField";

interface ChatHistoryProps {
  activeChatId: string | null;
  onOpen: (chat: ChatSummary) => void;
  /** Called with the ids of the chats a confirmed delete removed, so the view can leave an open chat. */
  onRemoved: (chatIds: string[]) => void;
}

const plural = (count: number) => `${count} ${count === 1 ? "chat" : "chats"}`;

/** The stored chats, grouped by folder. Chats move by drag and drop or by the Move to menu. */
export function ChatHistory({ activeChatId, onOpen, onRemoved }: ChatHistoryProps) {
  const api = useApi();
  const listing = useQuery(chatsQuery(api));
  const createFolder = useCreateChatFolder();
  const renameFolder = useRenameChatFolder();
  const move = useMoveChat();
  const deleteChat = useDeleteChat();
  const deleteChats = useDeleteChats();
  const deleteFolder = useDeleteChatFolder();
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [request, setRequest] = useState<DeleteRequest | null>(null);
  const dragged = useRef<string | null>(null);
  const [naming, setNaming] = useState(false);

  if (listing.isError) return <ErrorNotice error={listing.error} onRetry={() => void listing.refetch()} />;
  if (listing.data === undefined) return <p role="status" className="text-meta text-muted-foreground">Loading chats.</p>;

  const { folders, chats } = listing.data;
  const moveChat = (chatId: string, folderId: string | null) => move.mutate({ chatId, folderId });
  const onDragStart = (chatId: string, event: React.DragEvent) => {
    dragged.current = chatId;
    event.dataTransfer?.setData("text/plain", chatId);
  };
  const onDropChat = (folderId: string | null, event: React.DragEvent) => {
    const chatId = dragged.current ?? event.dataTransfer?.getData("text/plain") ?? "";
    dragged.current = null;
    const chat = chats.find((c) => c.chat_id === chatId);
    if (chat !== undefined && chat.folder_id !== folderId) moveChat(chatId, folderId);
  };
  const removed = (chatIds: string[]) => async (action: Promise<unknown>) => {
    await action;
    setSelected((current) => current.filter((id) => !chatIds.includes(id)));
    onRemoved(chatIds);
  };
  const askDeleteChat = (chat: ChatSummary) =>
    setRequest({
      heading: "Delete this chat?",
      detail: `This removes ${plural(1)} and its answers for good.`,
      confirmLabel: "Delete chat",
      run: () => removed([chat.chat_id])(deleteChat.mutateAsync(chat.chat_id)),
    });
  const askDeleteSelected = () => {
    const ids = selected;
    setRequest({
      heading: `Delete ${plural(ids.length)}?`,
      detail: `This removes ${plural(ids.length)} and their answers for good.`,
      confirmLabel: `Delete ${plural(ids.length)}`,
      run: async () => {
        await removed(ids)(deleteChats.mutateAsync(ids));
        setSelectMode(false);
      },
    });
  };
  const askDeleteFolder = (folder: ChatFolder) => {
    const inside = chats.filter((chat) => chat.folder_id === folder.folder_id).map((chat) => chat.chat_id);
    setRequest({
      heading: `Delete folder ${folder.name}?`,
      detail: inside.length === 0 ? "This removes the empty folder." : `This removes the folder and ${plural(inside.length)} inside it, with their answers, for good.`,
      confirmLabel: "Delete folder",
      run: () => removed(inside)(deleteFolder.mutateAsync(folder.folder_id)),
    });
  };
  const toggle = (chatId: string) => setSelected((current) => (current.includes(chatId) ? current.filter((id) => id !== chatId) : [...current, chatId]));
  const rows = (folderId: string | null) =>
    chats
      .filter((chat) => chat.folder_id === folderId)
      .map((chat) => (
        <ChatRow key={chat.chat_id} chat={chat} folders={folders} active={chat.chat_id === activeChatId} onOpen={onOpen} onMove={moveChat} onDragStart={onDragStart} onDelete={askDeleteChat} selectMode={selectMode} selected={selected.includes(chat.chat_id)} onToggle={toggle} />
      ));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-subsection-title font-semibold">History</h2>
        <div className="flex gap-1">
          <Button variant="outline" size="xs" onClick={() => setNaming(true)}>
            <FolderPlus aria-hidden="true" />
            New folder
          </Button>
          <Button
            variant="outline"
            size="xs"
            onClick={() => {
              setSelectMode(!selectMode);
              setSelected([]);
            }}
          >
            {selectMode ? "Done" : "Select"}
          </Button>
        </div>
      </div>
      {selectMode ? (
        <Button variant="destructive" size="sm" disabled={selected.length === 0} onClick={askDeleteSelected}>
          <Trash2 aria-hidden="true" />
          {`Delete selected (${selected.length})`}
        </Button>
      ) : null}
      {naming ? (
        <FolderNameField
          initial=""
          onCancel={() => setNaming(false)}
          onSave={(name) => {
            setNaming(false);
            createFolder.mutate(name);
          }}
        />
      ) : null}
      {chats.length === 0 && folders.length === 0 ? <p className="text-meta text-muted-foreground">No chats yet. Ask a question to start one.</p> : null}
      <ChatFolderSection folder={null} onDropChat={onDropChat}>
        {rows(null)}
      </ChatFolderSection>
      {folders.map((folder) => (
        <ChatFolderSection key={folder.folder_id} folder={folder} onDropChat={onDropChat} onRename={(folderId, name) => renameFolder.mutate({ folderId, name })}
          actions={
            <Button variant="ghost" size="icon-xs" aria-label={`Delete folder ${folder.name}`} onClick={() => askDeleteFolder(folder)}>
              <Trash2 aria-hidden="true" />
            </Button>
          }
        >
          {rows(folder.folder_id)}
        </ChatFolderSection>
      ))}
      <DeleteChatsDialog request={request} onClose={() => setRequest(null)} />
    </div>
  );
}
