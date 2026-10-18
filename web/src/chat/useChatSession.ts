import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "../api/ApiProvider";
import { useAppendChatTurn, useCreateChat } from "../api/chatMutations";
import { ApiError } from "../api/client";
import type { ChatSummary } from "../api/chats";
import type { AnswerResult } from "../api/documents";
import { chatQuery } from "../api/queries";
import { useRoute } from "../lib/RouteProvider";

export interface Turn {
  id: number;
  collection: string;
  question: string;
  /** The stored answer of a reopened chat. A turn without one asks the server. */
  saved: AnswerResult | null;
}

const TITLE_LIMIT = 60;

function titleOf(question: string): string {
  const flat = question.replace(/\s+/g, " ").trim();
  return flat.length <= TITLE_LIMIT ? flat : `${flat.slice(0, TITLE_LIMIT - 1)}…`;
}

/**
 * The transcript of the open chat and its link to the stored chat (ADR-082).
 * The first usable answer creates the chat and puts its id in the route. Each
 * later usable answer is saved as a turn. An error result is never saved. A
 * save that fails does not stop the chat: a 404 means the chat was deleted
 * while the answer was pending and is dropped silently, any other failure
 * shows one line.
 */
export function useChatSession(routeCollection: string | null, routeChatId: string | null) {
  const api = useApi();
  const queryClient = useQueryClient();
  const { navigate } = useRoute();
  const createChat = useCreateChat();
  const appendTurn = useAppendChatTurn();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [session, setSession] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const chatIdRef = useRef<string | null>(null);
  const creating = useRef<Promise<string | null> | null>(null);

  const adopt = useCallback((id: string | null) => {
    chatIdRef.current = id;
    setChatId(id);
  }, []);

  // Opening a chat id that is not the one on screen loads it from the server.
  useEffect(() => {
    if (routeChatId === null || routeChatId === chatIdRef.current) return;
    let cancelled = false;
    queryClient
      .fetchQuery({ ...chatQuery(api, routeChatId), staleTime: 0 })
      .then((chat) => {
        if (cancelled) return;
        adopt(chat.chat_id);
        setNotice(null);
        setSession((n) => n + 1);
        setTurns(chat.turns.map((t, index) => ({ id: index + 1, collection: t.collection, question: t.question, saved: t.answer })));
      })
      .catch(() => {
        if (cancelled) return;
        adopt(null);
        setTurns([]);
        setSession((n) => n + 1);
        setNotice("That chat is no longer stored. You can start a new one.");
        navigate({ area: "chat", collection: routeCollection, chatId: null }, { replace: true });
      });
    return () => {
      cancelled = true;
    };
  }, [routeChatId, routeCollection, api, queryClient, adopt, navigate]);

  /** Opens a stored chat in the collection of its last turn (design D7). */
  const openChat = useCallback(
    async (chat: ChatSummary) => {
      if (chat.chat_id === chatIdRef.current) return;
      try {
        const detail = await queryClient.fetchQuery(chatQuery(api, chat.chat_id));
        const collection = detail.turns.at(-1)?.collection ?? routeCollection;
        navigate({ area: "chat", collection, chatId: chat.chat_id });
      } catch {
        setNotice("That chat is no longer stored. You can start a new one.");
      }
    },
    [api, queryClient, navigate, routeCollection],
  );

  const send = useCallback(
    (collection: string) => (question: string) =>
      setTurns((current) => [...current, { id: (current.at(-1)?.id ?? 0) + 1, collection, question, saved: null }]),
    [],
  );

  const newChat = useCallback(() => {
    adopt(null);
    setTurns([]);
    setNotice(null);
    setSession((n) => n + 1);
    navigate({ area: "chat", collection: routeCollection, chatId: null }, { replace: true });
  }, [adopt, navigate, routeCollection]);

  const ensureChat = useCallback(
    (turn: Turn): Promise<string | null> => {
      if (chatIdRef.current !== null) return Promise.resolve(chatIdRef.current);
      creating.current ??= createChat
        .mutateAsync({ title: titleOf(turn.question) })
        .then((chat) => {
          adopt(chat.chat_id);
          navigate({ area: "chat", collection: turn.collection, chatId: chat.chat_id }, { replace: true });
          return chat.chat_id;
        })
        .catch(() => {
          setNotice("This answer could not be saved to the chat history.");
          return null;
        })
        .finally(() => {
          creating.current = null;
        });
      return creating.current;
    },
    [adopt, createChat, navigate],
  );

  const onResult = useCallback(
    async (turn: Turn, result: AnswerResult) => {
      if (result.status === "error") return;
      const id = await ensureChat(turn);
      if (id === null) return;
      try {
        await appendTurn.mutateAsync({ chatId: id, turn: { collection: turn.collection, question: turn.question, answer: result } });
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 404)) setNotice("This answer could not be saved to the chat history.");
      }
    },
    [appendTurn, ensureChat],
  );

  return { turns, session, notice, chatId, send, newChat, openChat, onResult };
}
