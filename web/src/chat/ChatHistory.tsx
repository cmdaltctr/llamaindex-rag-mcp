import { useQuery } from "@tanstack/react-query";
import { FolderPlus, Trash2 } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { useApi } from "../api/ApiProvider";
import { useCreateChatFolder, useDeleteChat, useDeleteChatFolder, useDeleteChats, useMoveChat, useMoveChats, useRenameChatFolder, useReorderChatFolders } from "../api/chatMutations";
import type { ChatFolder, ChatSummary } from "../api/chats";
import { chatsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { ChatFolderSection, type DropEdge } from "./ChatFolderSection";
import { ChatRow } from "./ChatRow";
import { DeleteChatsDialog, type DeleteRequest } from "./DeleteChatsDialog";
import { FolderNameField } from "./FolderNameField";
import { FolderReorderHandle } from "./FolderReorderHandle";
import { MoveSelectedMenu } from "./MoveSelectedMenu";

interface ChatHistoryProps {
  activeChatId: string | null;
  onOpen: (chat: ChatSummary) => void;
  /** Called with the ids of the chats a confirmed delete removed, so the view can leave an open chat. */
  onRemoved: (chatIds: string[]) => void;
  /** Shown at the end of the New folder row, for the card's hide chevron. */
  trailing?: ReactNode;
}

const plural = (count: number) => `${count} ${count === 1 ? "chat" : "chats"}`;

/** The stored chats, grouped by folder. Chats move by drag and drop or by the right-click menu. */
export function ChatHistory({ activeChatId, onOpen, onRemoved, trailing }: ChatHistoryProps) {
  const api = useApi();
  const listing = useQuery(chatsQuery(api));
  const createFolder = useCreateChatFolder();
  const renameFolder = useRenameChatFolder();
  const move = useMoveChat();
  const moveMany = useMoveChats();
  const reorder = useReorderChatFolders();
  const deleteChat = useDeleteChat();
  const deleteChats = useDeleteChats();
  const deleteFolder = useDeleteChatFolder();
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [request, setRequest] = useState<DeleteRequest | null>(null);
  const dragged = useRef<string | null>(null);
  const draggedFolder = useRef<string | null>(null);
  const [draggingFolderId, setDraggingFolderId] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [naming, setNaming] = useState(false);

  if (listing.isError) return <ErrorNotice error={listing.error} onRetry={() => void listing.refetch()} />;
  if (listing.data === undefined) return <p role="status" className="text-meta text-muted-foreground">Loading chats.</p>;

  const { folders, chats } = listing.data;
  const moveChat = (chatId: string, folderId: string | null) => move.mutate({ chatId, folderId });
  const onDragStart = (chatId: string, event: React.DragEvent) => {
    dragged.current = chatId;
    setDraggingId(chatId);
    event.dataTransfer?.setData("text/plain", chatId);
  };
  const onDragEnd = () => setDraggingId(null);
  const saveOrder = (ids: string[]) => {
    if (ids.some((id, index) => id !== folders[index]?.folder_id)) reorder.mutate(ids);
  };
  // The arrow keys move a folder one place.
  const stepFolder = (folderId: string, index: number) => {
    const ids = folders.map((folder) => folder.folder_id);
    const from = ids.indexOf(folderId);
    if (from === -1 || index < 0 || index >= ids.length || index === from) return;
    ids.splice(from, 1);
    ids.splice(index, 0, folderId);
    saveOrder(ids);
  };
  // A dropped folder goes above or below the target, where the line showed.
  const dropFolder = (folderId: string, targetId: string, edge: DropEdge) => {
    if (folderId === targetId) return;
    const ids = folders.map((folder) => folder.folder_id).filter((id) => id !== folderId);
    const at = ids.indexOf(targetId);
    if (at === -1) return;
    ids.splice(edge === "after" ? at + 1 : at, 0, folderId);
    saveOrder(ids);
  };
  const endFolderDrag = () => {
    draggedFolder.current = null;
    setDraggingFolderId(null);
  };
  const onFolderDragStart = (folderId: string, event: React.DragEvent) => {
    draggedFolder.current = folderId;
    setDraggingFolderId(folderId);
    event.dataTransfer?.setData("text/plain", folderId);
  };
  const onDrop = (folderId: string | null, event: React.DragEvent, edge: DropEdge | null) => {
    const movedFolder = draggedFolder.current;
    if (movedFolder !== null) {
      endFolderDrag();
      if (folderId !== null && edge !== null) dropFolder(movedFolder, folderId, edge);
      return;
    }
    const chatId = dragged.current ?? event.dataTransfer?.getData("text/plain") ?? "";
    dragged.current = null;
    setDraggingId(null);
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
  // Only chats outside the chosen folder need a request. Select mode ends, as after a bulk delete.
  const moveSelected = (folderId: string | null) => {
    const chatIds = chats.filter((chat) => selected.includes(chat.chat_id) && chat.folder_id !== folderId).map((chat) => chat.chat_id);
    if (chatIds.length > 0) moveMany.mutate({ chatIds, folderId });
    setSelected([]);
    setSelectMode(false);
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
  // An empty No folder group stays hidden, except while a filed chat is dragged: then it is the drop target that takes the chat out.
  const draggedChat = chats.find((chat) => chat.chat_id === draggingId);
  const showNoFolder = chats.some((chat) => chat.folder_id === null) || (draggedChat !== undefined && draggedChat.folder_id !== null);
  const toggle = (chatId: string) => setSelected((current) => (current.includes(chatId) ? current.filter((id) => id !== chatId) : [...current, chatId]));
  const rows = (folderId: string | null) =>
    chats
      .filter((chat) => chat.folder_id === folderId)
      .map((chat) => (
        <ChatRow key={chat.chat_id} chat={chat} folders={folders} active={chat.chat_id === activeChatId} onOpen={onOpen} onMove={moveChat} onDragStart={onDragStart} onDragEnd={onDragEnd} onDelete={askDeleteChat} selectMode={selectMode} selected={selected.includes(chat.chat_id)} onToggle={toggle} />
      ));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
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
        {trailing === undefined ? null : <span className="ms-auto">{trailing}</span>}
      </div>
      {selectMode ? (
        <div className="flex flex-col gap-1">
          <MoveSelectedMenu count={selected.length} folders={folders} onMove={moveSelected} />
          <Button variant="destructive" size="sm" disabled={selected.length === 0} onClick={askDeleteSelected}>
            <Trash2 aria-hidden="true" />
            {`Delete selected (${selected.length})`}
          </Button>
        </div>
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
      {showNoFolder ? (
        <ChatFolderSection folder={null} onDrop={onDrop}>
          {rows(null)}
        </ChatFolderSection>
      ) : null}
      {folders.map((folder, index) => (
        <ChatFolderSection
          key={folder.folder_id}
          folder={folder}
          onDrop={onDrop}
          folderDragOver={draggingFolderId !== null && draggingFolderId !== folder.folder_id}
          onRename={(folderId, name) => renameFolder.mutate({ folderId, name })}
          leading={
            selectMode ? (
              <FolderReorderHandle
                name={folder.name}
                onDragStart={(event) => onFolderDragStart(folder.folder_id, event)}
                onDragEnd={endFolderDrag}
                onStep={(step) => stepFolder(folder.folder_id, index + step)}
              />
            ) : null
          }
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
