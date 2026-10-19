import { useIsMutating, useQuery } from "@tanstack/react-query";
import { History, MessageCircle, Plus } from "lucide-react";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import type { ChatSummary } from "../api/chats";
import type { AnswerResult } from "../api/documents";
import { ANSWER_MUTATION_KEY } from "../api/mutations";
import { chatSettingsQuery } from "../api/queries";
import { AlertNotice } from "../components/AlertNotice";
import { ChunkViewer } from "../components/ChunkViewer";
import { CollectionGate } from "../components/CollectionGate";
import { CollectionPicker } from "../components/CollectionPicker";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { ChatHistory } from "./ChatHistory";
import { KnowledgePanel } from "./KnowledgePanel";
import { SidePanel } from "./SidePanel";
import { useRoute } from "../lib/RouteProvider";
import { chatReasonSentence } from "../settings/connectionWords";
import { areaById } from "../lib/views";
import { AssistantTurn } from "./AssistantTurn";
import { Composer } from "./Composer";
import { useChatSession, type Turn } from "./useChatSession";
import { useLatestAnswer } from "./useLatestAnswer";

/** Wide-screen columns by hidden cards. A hidden card keeps a strip for its show button. */
function gridColumns(historyHidden: boolean, knowledgeHidden: boolean): string {
  if (historyHidden) return knowledgeHidden ? "lg:grid-cols-[2.25rem_minmax(0,1fr)_2.25rem]" : "lg:grid-cols-[2.25rem_minmax(0,1fr)_16rem]";
  return knowledgeHidden ? "lg:grid-cols-[16rem_minmax(0,1fr)_2.25rem]" : "lg:grid-cols-[16rem_minmax(0,1fr)_16rem]";
}

/** The chat column grows with the room a hidden card gives back. */
function chatWidth(historyHidden: boolean, knowledgeHidden: boolean): string {
  if (historyHidden && knowledgeHidden) return "max-w-[80rem]";
  return historyHidden || knowledgeHidden ? "max-w-[64rem]" : "max-w-[48rem]";
}

/**
 * `#/chat` and `#/chat/<collection>`: sequential question and answer. The
 * transcript is presentation only and lives in this component, so it survives
 * a change of collection and goes with the view. Turns do not see each other.
 */
export function ChatView() {
  const { route, navigate } = useRoute();
  const routeCollection = route.area === "chat" ? route.collection : null;
  const routeChatId = route.area === "chat" ? route.chatId : null;
  const { turns, session, notice, chatId, send, newChat, openChat, onResult } = useChatSession(routeCollection, routeChatId);
  const { latest, record } = useLatestAnswer(turns, session);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyHidden, setHistoryHidden] = useState(false);
  const [knowledgeHidden, setKnowledgeHidden] = useState(false);
  const [chunk, setChunk] = useState<{ collection: string; chunkId: string } | null>(null);
  const chatStatus = useQuery(chatSettingsQuery(useApi())).data;
  const unavailable = chatStatus !== undefined && !chatStatus.ready;
  const busy = useIsMutating({ mutationKey: ANSWER_MUTATION_KEY }) > 0;

  const openFromHistory = (chat: ChatSummary) => {
    void openChat(chat);
    setHistoryOpen(false);
  };
  const select = (name: string) => navigate({ area: "chat", collection: name, chatId });

  return (
    <section className="flex flex-1 flex-col">
      <PageHeader
        title="Chat"
        summary={areaById("chat").summary}
        actions={
          <Button variant="outline" onClick={newChat}>
            <Plus aria-hidden="true" />
            New chat
          </Button>
        }
      />
      <CollectionGate
        area="chat"
        routeCollection={routeCollection}
        backLabel="Choose a knowledge base"
        picker={(collections) =>
          collections.length === 0 ? (
            <EmptyState
              icon={MessageCircle}
              message="There is no knowledge base to ask yet. Ingest a source first."
              action={
                <Button asChild>
                  <a href="#/knowledge-base">Add a source</a>
                </Button>
              }
            />
          ) : (
            <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_16rem]">
              <EmptyState icon={MessageCircle} message="Choose a knowledge base to start a conversation." />
              <CollectionPicker label="Knowledge bases" collections={collections} selected={null} onSelect={select} stacked showFiles />
            </div>
          )
        }
      >
        {(active, collections) => (
          // The column fills the remaining height so the composer can dock at its bottom.
          <div data-testid="chat-grid" className={`grid flex-1 grid-cols-1 gap-6 lg:grid-rows-[1fr] ${gridColumns(historyHidden, knowledgeHidden)}`}>
            <aside aria-label="Chat history" className={`flex-col self-start lg:order-none lg:flex ${historyOpen ? "order-first flex" : "hidden"}`}>
              <SidePanel side="left" label="chat history" collapsed={historyHidden} onToggle={() => setHistoryHidden(!historyHidden)}>
                {(hide) => (
                  <ChatHistory activeChatId={chatId} onOpen={openFromHistory} onRemoved={(ids) => (chatId !== null && ids.includes(chatId) ? newChat() : undefined)} trailing={hide} />
                )}
              </SidePanel>
            </aside>
            <div data-testid="chat-column" className={`mx-auto flex w-full flex-1 flex-col gap-4 ${chatWidth(historyHidden, knowledgeHidden)}`}>
              <div className="lg:hidden">
                <Button variant="outline" size="sm" aria-expanded={historyOpen} onClick={() => setHistoryOpen(!historyOpen)}>
                  <History aria-hidden="true" />
                  History
                </Button>
              </div>
              <p className="text-meta text-muted-foreground">
                Each question answers from the knowledge base on its own. Earlier turns are not sent with the next question.
              </p>
              {notice !== null ? (
                <p role="status" className="text-meta text-muted-foreground">
                  {notice}
                </p>
              ) : null}
              {turns.length > 0 ? (
                <ol aria-label="Transcript" className="flex flex-col gap-5">
                  {turns.map((turn) => (
                    <TurnRows
                      key={`${session}-${turn.id}`}
                      turn={turn}
                      onResult={(result) => {
                        record(turn, result);
                        void onResult(turn, result);
                      }}
                      onShowChunk={(collection, chunkId) => setChunk({ collection, chunkId })}
                    />
                  ))}
                </ol>
              ) : null}
              {unavailable ? (
                <AlertNotice message={chatReasonSentence(chatStatus.reason)}>
                  <Button asChild variant="outline">
                    <a href="#/settings/chat">Connect a model</a>
                  </Button>
                </AlertNotice>
              ) : null}
              <Composer collection={active.name} busy={busy} unavailable={unavailable} onSend={send(active.name)} />
            </div>
            <aside aria-label="Knowledge base panel" className="order-first flex flex-col gap-2 self-start lg:order-none">
              <SidePanel side="right" label="knowledge bases" collapsed={knowledgeHidden} onToggle={() => setKnowledgeHidden(!knowledgeHidden)}>
                {(hide) => (
                  <KnowledgePanel
                    collections={collections}
                    activeName={active.name}
                    onSelect={select}
                    latest={latest}
                    onShowChunk={(collection, chunkId) => setChunk({ collection, chunkId })}
                    hide={hide}
                  />
                )}
              </SidePanel>
            </aside>
          </div>
        )}
      </CollectionGate>
      {chunk !== null ? <ChunkViewer key={chunk.chunkId} collection={chunk.collection} chunkId={chunk.chunkId} onClose={() => setChunk(null)} /> : null}
    </section>
  );
}

interface TurnRowsProps {
  turn: Turn;
  onResult: (result: AnswerResult) => void;
  onShowChunk: (collection: string, chunkId: string) => void;
}

function TurnRows({ turn, onResult, onShowChunk }: TurnRowsProps) {
  return (
    <>
      <li className="flex flex-col gap-1">
        <p className="text-meta font-medium text-muted-foreground">You</p>
        <p className="whitespace-pre-wrap break-words">{turn.question}</p>
      </li>
      <AssistantTurn collection={turn.collection} question={turn.question} saved={turn.saved} onResult={onResult} onShowChunk={onShowChunk} />
    </>
  );
}
